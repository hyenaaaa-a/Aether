"""
Chat Handler Base - Chat API 格式的通用基类

此文件作为薄封装层，覆盖流式链路以对齐上游 F10 的改动：
- 使用 `aiter_raw()` + 增量解码（避免 `aiter_lines()` 的性能/边界问题）
- 记录 TTFB（在 `StreamContext.build_response_body()` 的 metadata 中）
- 修复 BackgroundTasks 里 response_time_ms 计算过早的问题（传入 start_time，由后台计算）

其余逻辑（同步请求、请求构建、映射等）保持原实现不变。
"""

from __future__ import annotations

from typing import Any, AsyncGenerator, Dict, Optional

import httpx
from fastapi import BackgroundTasks, Request
from fastapi.responses import StreamingResponse

from src.api.handlers.base.chat_handler_base_impl import ChatHandlerBase as _ChatHandlerBaseImpl
from src.api.handlers.base.stream_context import StreamContext
from src.api.handlers.base.stream_processor import StreamProcessor
from src.api.handlers.base.stream_telemetry import StreamTelemetryRecorder
from src.config.settings import config
from src.core.exceptions import EmbeddedErrorException
from src.core.logger import logger
from src.models.database import Provider, ProviderAPIKey, ProviderEndpoint
from src.services.provider.transport import build_provider_url


class ChatHandlerBase(_ChatHandlerBaseImpl):
    async def process_stream(
        self,
        request: Any,
        http_request: Request,
        original_headers: Dict[str, Any],
        original_request_body: Dict[str, Any],
        query_params: Optional[Dict[str, str]] = None,
    ) -> StreamingResponse:
        logger.debug(f"开始流式响应处理({self.FORMAT_ID})")

        converted_request = await self._convert_request(request)
        model = getattr(converted_request, "model", original_request_body.get("model", "unknown"))
        api_format = self.allowed_api_formats[0]

        ctx = StreamContext(model=model, api_format=api_format)

        stream_processor = StreamProcessor(
            request_id=self.request_id,
            default_parser=self.parser,
            on_streaming_start=self._update_usage_to_streaming,
        )

        async def stream_request_func(
            provider: Provider,
            endpoint: ProviderEndpoint,
            key: ProviderAPIKey,
        ) -> AsyncGenerator[bytes, None]:
            return await self._execute_stream_request(
                ctx,
                stream_processor,
                provider,
                endpoint,
                key,
                original_request_body,
                original_headers,
                query_params,
            )

        try:
            capability_requirements = self._resolve_capability_requirements(
                model_name=model,
                request_headers=original_headers,
            )

            (
                stream_generator,
                provider_name,
                attempt_id,
                provider_id,
                endpoint_id,
                key_id,
            ) = await self.orchestrator.execute_with_fallback(
                api_format=api_format,
                model_name=model,
                user_api_key=self.api_key,
                request_func=stream_request_func,
                request_id=self.request_id,
                is_stream=True,
                capability_requirements=capability_requirements or None,
            )

            ctx.attempt_id = attempt_id
            ctx.provider_name = provider_name
            ctx.provider_id = provider_id
            ctx.endpoint_id = endpoint_id
            ctx.key_id = key_id

            telemetry_recorder = StreamTelemetryRecorder(
                request_id=self.request_id,
                user_id=str(self.user.id),
                api_key_id=str(self.api_key.id),
                client_ip=self.client_ip,
                format_id=self.FORMAT_ID,
            )

            background_tasks = BackgroundTasks()
            background_tasks.add_task(
                telemetry_recorder.record_stream_stats,
                ctx,
                original_headers,
                original_request_body,
                self.start_time,
            )

            monitored_stream = stream_processor.create_monitored_stream(
                ctx,
                stream_generator,
                http_request.is_disconnected,
            )

            return StreamingResponse(
                monitored_stream,
                media_type="text/event-stream",
                background=background_tasks,
            )

        except Exception as e:
            logger.exception(f"流式请求失败: {e}")
            await self._record_stream_failure(ctx, e, original_headers, original_request_body)
            raise

    async def _execute_stream_request(
        self,
        ctx: StreamContext,
        stream_processor: StreamProcessor,
        provider: Provider,
        endpoint: ProviderEndpoint,
        key: ProviderAPIKey,
        original_request_body: Dict[str, Any],
        original_headers: Dict[str, str],
        query_params: Optional[Dict[str, str]] = None,
    ) -> AsyncGenerator[bytes, None]:
        ctx.reset_for_retry()

        ctx.update_provider_info(
            provider_name=str(provider.name),
            provider_id=str(provider.id),
            endpoint_id=str(endpoint.id),
            key_id=str(key.id),
            provider_api_format=str(endpoint.api_format) if endpoint.api_format else None,
        )

        mapped_model = await self._get_mapped_model(
            source_model=ctx.model,
            provider_id=str(provider.id),
        )

        if mapped_model:
            ctx.mapped_model = mapped_model
            request_body = self.apply_mapped_model(original_request_body, mapped_model)
        else:
            request_body = dict(original_request_body)

        request_body = self.prepare_provider_request_body(request_body)

        provider_payload, provider_headers = self._request_builder.build(
            request_body,
            original_headers,
            endpoint,
            key,
            is_stream=True,
        )

        ctx.provider_request_headers = provider_headers
        ctx.provider_request_body = provider_payload

        url_model = self.get_model_for_url(request_body, mapped_model) or ctx.model
        url = build_provider_url(
            endpoint,
            query_params=query_params,
            path_params={"model": url_model},
            is_stream=True,
        )

        logger.debug(
            f"  [{self.request_id}] 发送流式请求 Provider={provider.name}, 模型={ctx.model} -> {mapped_model or '无映射'}"
        )

        timeout_config = httpx.Timeout(
            connect=config.http_connect_timeout,
            read=float(endpoint.timeout),
            write=config.http_write_timeout,
            pool=config.http_pool_timeout,
        )

        http_client = httpx.AsyncClient(timeout=timeout_config, follow_redirects=True)
        try:
            response_ctx = http_client.stream("POST", url, json=provider_payload, headers=provider_headers)
            stream_response = await response_ctx.__aenter__()

            ctx.status_code = stream_response.status_code
            ctx.response_headers = dict(stream_response.headers)

            stream_response.raise_for_status()

            # 使用字节流迭代器（避免 aiter_lines 的性能/边界问题）
            byte_iterator = stream_response.aiter_raw()

            prefetched_chunks = await stream_processor.prefetch_and_check_error(
                byte_iterator,
                provider,
                endpoint,
                ctx,
                max_prefetch_lines=config.stream_prefetch_lines,
            )

        except httpx.HTTPStatusError as e:
            error_text = await self._extract_error_text(e)
            logger.error(f"Provider 返回错误: {e.response.status_code}\n  Response: {error_text}")
            await http_client.aclose()
            raise

        except EmbeddedErrorException:
            try:
                await response_ctx.__aexit__(None, None, None)
            except Exception:
                pass
            await http_client.aclose()
            raise

        except Exception:
            await http_client.aclose()
            raise

        return stream_processor.create_response_stream(
            ctx,
            byte_iterator,
            response_ctx,
            http_client,
            prefetched_chunks,
            start_time=self.start_time,
        )

