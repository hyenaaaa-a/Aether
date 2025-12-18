"""
CLI Handler Base - 薄封装层

此文件用于在尽量不改动本地体系的前提下，对齐上游 F10 的改动点：
- 使用 `aiter_raw()` + 增量解码，避免 `aiter_lines()` 的性能/边界问题
- 在首次输出前记录 TTFB（写入 `ctx.response_metadata["first_byte_time_ms"]`）
- 预读检测嵌套错误（HTTP 200 但 body 中包含错误）仍保持原逻辑
- 修复默认 usage 更新策略：避免被早期的 0 token 锁死
"""

from __future__ import annotations

import codecs
import json
import time
from typing import Any, AsyncGenerator, Dict, Optional

import httpx

from src.api.handlers.base.cli_handler_base_impl import (
    CliMessageHandlerBase as _CliMessageHandlerBaseImpl,
    StreamContext,
)
from src.api.handlers.base.parsers import get_parser_for_format
from src.core.exceptions import EmbeddedErrorException, ProviderNotAvailableException
from src.core.logger import logger
from src.models.database import Provider, ProviderAPIKey, ProviderEndpoint
from src.services.provider.transport import build_provider_url
from src.utils.sse_parser import SSEEventParser


class CliMessageHandlerBase(_CliMessageHandlerBaseImpl):
    async def _execute_stream_request(
        self,
        ctx: StreamContext,
        provider: Provider,
        endpoint: ProviderEndpoint,
        key: ProviderAPIKey,
        original_request_body: Dict[str, Any],
        original_headers: Dict[str, str],
        query_params: Optional[Dict[str, str]] = None,
    ) -> AsyncGenerator[bytes, None]:
        ctx.parsed_chunks = []
        ctx.chunk_count = 0
        ctx.data_count = 0
        ctx.has_completion = False
        ctx.collected_text = ""
        ctx.input_tokens = 0
        ctx.output_tokens = 0
        ctx.cached_tokens = 0
        ctx.cache_creation_tokens = 0
        ctx.final_usage = None
        ctx.final_response = None
        ctx.response_id = None
        ctx.response_metadata = {}

        ctx.provider_name = str(provider.name)
        ctx.provider_id = str(provider.id)
        ctx.endpoint_id = str(endpoint.id)
        ctx.key_id = str(key.id)

        ctx.provider_api_format = str(endpoint.api_format) if endpoint.api_format else ""
        ctx.client_api_format = ctx.api_format

        mapped_model = await self._get_mapped_model(
            source_model=ctx.model,
            provider_id=str(provider.id),
        )

        if mapped_model:
            ctx.mapped_model = mapped_model
            request_body = self.apply_mapped_model(original_request_body, mapped_model)
        else:
            request_body = original_request_body

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
            client_path=self._client_path,
        )

        timeout_config = httpx.Timeout(
            connect=10.0,
            read=float(endpoint.timeout),
            write=60.0,
            pool=10.0,
        )

        logger.debug(
            f"  └─ [{self.request_id}] 发送流式请求 "
            f"Provider={provider.name}, Endpoint={endpoint.id[:8]}..., "
            f"Key=***{key.api_key[-4:]}, "
            f"原始模型={ctx.model}, 映射={mapped_model or '无映射'}, URL模型={url_model}"
        )

        http_client = httpx.AsyncClient(timeout=timeout_config, follow_redirects=True)
        try:
            response_ctx = http_client.stream("POST", url, json=provider_payload, headers=provider_headers)
            stream_response = await response_ctx.__aenter__()

            ctx.status_code = stream_response.status_code
            ctx.response_headers = dict(stream_response.headers)

            logger.debug(f"  └─ 收到响应: status={stream_response.status_code}")

            stream_response.raise_for_status()

            byte_iterator = stream_response.aiter_raw()

            prefetched_chunks = await self._prefetch_and_check_embedded_error(
                byte_iterator, provider, endpoint, ctx
            )

        except httpx.HTTPStatusError as e:
            error_text = await self._extract_error_text(e)
            logger.error(f"Provider 返回错误状态 {e.response.status_code}\n  Response: {error_text}")
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

        return self._create_response_stream_with_prefetch(
            ctx,
            byte_iterator,
            response_ctx,
            http_client,
            prefetched_chunks,
        )

    async def _prefetch_and_check_embedded_error(
        self,
        byte_iterator: Any,
        provider: Provider,
        endpoint: ProviderEndpoint,
        ctx: StreamContext,
    ) -> list:
        prefetched_chunks: list = []
        max_prefetch_lines = 5

        provider_format = ctx.provider_api_format
        if provider_format:
            try:
                provider_parser = get_parser_for_format(provider_format)
            except KeyError:
                provider_parser = self.parser
        else:
            provider_parser = self.parser

        buffer = b""
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        line_count = 0
        should_stop = False

        try:
            async for chunk in byte_iterator:
                prefetched_chunks.append(chunk)
                buffer += chunk

                while b"\n" in buffer:
                    line_bytes, buffer = buffer.split(b"\n", 1)
                    line = decoder.decode(line_bytes + b"\n", False).rstrip("\n")
                    normalized_line = line.rstrip("\r")
                    line_count += 1

                    lower_line = normalized_line.lower()
                    if lower_line.startswith("<!doctype") or lower_line.startswith("<html"):
                        logger.error(
                            f"  [{self.request_id}] 检测到 HTML 响应，可能是 base_url 配置错误: "
                            f"Provider={provider.name}, Endpoint={endpoint.id[:8]}..., "
                            f"base_url={endpoint.base_url}"
                        )
                        raise ProviderNotAvailableException(
                            f"提供商'{provider.name}' 返回了 HTML 页面而非 API 响应，请检查 endpoint 的 base_url 配置是否正确"
                        )

                    if not normalized_line or normalized_line.startswith(":"):
                        if line_count >= max_prefetch_lines:
                            should_stop = True
                            break
                        continue

                    data_str = normalized_line
                    if normalized_line.startswith("data: "):
                        data_str = normalized_line[6:]

                    if data_str == "[DONE]":
                        should_stop = True
                        break

                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        if line_count >= max_prefetch_lines:
                            should_stop = True
                            break
                        continue

                    if isinstance(data, dict) and provider_parser.is_error_response(data):
                        parsed = provider_parser.parse_response(data, 200)
                        logger.warning(
                            f"  [{self.request_id}] 检测到嵌套错误: "
                            f"Provider={provider.name}, "
                            f"error_type={parsed.error_type}, "
                            f"message={parsed.error_message}"
                        )
                        raise EmbeddedErrorException(
                            provider_name=str(provider.name),
                            error_code=(
                                int(parsed.error_type)
                                if parsed.error_type and parsed.error_type.isdigit()
                                else None
                            ),
                            error_message=parsed.error_message,
                            error_status=parsed.error_type,
                        )

                    should_stop = True
                    break

                if should_stop or line_count >= max_prefetch_lines:
                    break

        except EmbeddedErrorException:
            raise
        except Exception as e:
            logger.debug(f"  [{self.request_id}] 预读流时发生异常: {e}")

        return prefetched_chunks

    async def _create_response_stream_with_prefetch(
        self,
        ctx: StreamContext,
        byte_iterator: Any,
        response_ctx: Any,
        http_client: httpx.AsyncClient,
        prefetched_chunks: list,
    ) -> AsyncGenerator[bytes, None]:
        try:
            sse_parser = SSEEventParser()
            last_data_time = time.time()
            decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
            buffer = b""
            needs_conversion = self._needs_format_conversion(ctx)

            streaming_status_updated = False
            first_byte_recorded = False

            def _record_first_byte_time() -> None:
                nonlocal first_byte_recorded
                if first_byte_recorded:
                    return
                first_byte_recorded = True
                if "first_byte_time_ms" not in ctx.response_metadata:
                    ctx.response_metadata["first_byte_time_ms"] = int((time.time() - ctx.start_time) * 1000)

            def _maybe_update_streaming_status() -> None:
                nonlocal streaming_status_updated
                if streaming_status_updated:
                    return
                self._update_usage_to_streaming(ctx.request_id)
                streaming_status_updated = True

            def _handle_line(line: str) -> Optional[bytes]:
                normalized_line = line.rstrip("\r")
                events = sse_parser.feed_line(normalized_line)

                if normalized_line == "":
                    for event in events:
                        self._handle_sse_event(ctx, event.get("event"), event.get("data") or "")
                    return b"\n"

                ctx.chunk_count += 1

                if ctx.chunk_count > self.EMPTY_CHUNK_THRESHOLD and ctx.data_count == 0:
                    elapsed = time.time() - last_data_time
                    if elapsed > self.DATA_TIMEOUT:
                        logger.warning(f"提供商'{ctx.provider_name}' 流超时且无数据")
                        error_event = {
                            "type": "error",
                            "error": {
                                "type": "empty_stream_timeout",
                                "message": f"提供商'{ctx.provider_name}' 流超时且未返回有效数据",
                            },
                        }
                        return f"event: error\ndata: {json.dumps(error_event)}\n\n".encode("utf-8")

                if needs_conversion:
                    converted_line = self._convert_sse_line(ctx, line, events)
                    if converted_line:
                        out = (converted_line + "\n").encode("utf-8")
                    else:
                        out = None
                else:
                    out = (line + "\n").encode("utf-8")

                for event in events:
                    self._handle_sse_event(ctx, event.get("event"), event.get("data") or "")

                return out

            # 先处理预读的 chunks（不直接输出 raw bytes，而是按行输出以支持转换）
            for chunk in prefetched_chunks:
                buffer += chunk
                while b"\n" in buffer:
                    line_bytes, buffer = buffer.split(b"\n", 1)
                    line = decoder.decode(line_bytes + b"\n", False).rstrip("\n")

                    out = _handle_line(line)
                    if out is None:
                        continue
                    _maybe_update_streaming_status()
                    _record_first_byte_time()
                    yield out

                    if ctx.data_count > 0:
                        last_data_time = time.time()

                    if out.startswith(b"event: error"):
                        return

            async for chunk in byte_iterator:
                buffer += chunk

                while b"\n" in buffer:
                    line_bytes, buffer = buffer.split(b"\n", 1)
                    line = decoder.decode(line_bytes + b"\n", False).rstrip("\n")

                    out = _handle_line(line)
                    if out is None:
                        continue
                    _maybe_update_streaming_status()
                    _record_first_byte_time()
                    yield out

                    if ctx.data_count > 0:
                        last_data_time = time.time()

                    if out.startswith(b"event: error"):
                        return

            if buffer:
                try:
                    line = decoder.decode(buffer, True)
                    out = _handle_line(line)
                    if out is not None:
                        _maybe_update_streaming_status()
                        _record_first_byte_time()
                        yield out
                except Exception as e:
                    logger.warning(
                        f"[{self.request_id}] 处理剩余缓冲区失败: {e}, bytes={buffer[:50]!r}"
                    )

            flushed_events = sse_parser.flush()
            for event in flushed_events:
                self._handle_sse_event(ctx, event.get("event"), event.get("data") or "")

            if ctx.data_count == 0:
                logger.error(
                    f"提供商'{ctx.provider_name}' 返回空流式响应(收到 {ctx.chunk_count} 个非数据行, "
                    f"可能是 endpoint base_url 配置错误)"
                )
                error_event = {
                    "type": "error",
                    "error": {
                        "type": "empty_response",
                        "message": (
                            f"提供商'{ctx.provider_name}' 返回了空的流式响应(收到 {ctx.chunk_count} 行非 SSE 数据)，"
                            f"请检查 endpoint 的 base_url 配置是否指向了正确的 API 地址"
                        ),
                    },
                }
                yield f"event: error\ndata: {json.dumps(error_event)}\n\n".encode("utf-8")
            else:
                logger.debug("流式数据转发完成")

        except GeneratorExit:
            raise
        except httpx.StreamClosed:
            if ctx.data_count == 0:
                logger.warning(f"提供商'{ctx.provider_name}' 流连接关闭且无数据")
                error_event = {
                    "type": "error",
                    "error": {
                        "type": "stream_closed",
                        "message": f"提供商'{ctx.provider_name}' 连接关闭且未返回数据",
                    },
                }
                yield f"event: error\ndata: {json.dumps(error_event)}\n\n".encode("utf-8")
        except httpx.RemoteProtocolError:
            if ctx.data_count > 0:
                error_event = {
                    "type": "error",
                    "error": {
                        "type": "connection_error",
                        "message": "上游连接意外关闭，部分响应已成功传输",
                    },
                }
                yield f"event: error\ndata: {json.dumps(error_event)}\n\n".encode("utf-8")
            else:
                raise
        finally:
            try:
                await response_ctx.__aexit__(None, None, None)
            except Exception:
                pass
            try:
                await http_client.aclose()
            except Exception:
                pass

    async def _create_response_stream(
        self,
        ctx: StreamContext,
        stream_response: httpx.Response,
        response_ctx: Any,
        http_client: httpx.AsyncClient,
    ) -> AsyncGenerator[bytes, None]:
        async for chunk in self._create_response_stream_with_prefetch(
            ctx,
            stream_response.aiter_raw(),
            response_ctx,
            http_client,
            [],
        ):
            yield chunk

    def _process_event_data(
        self,
        ctx: StreamContext,
        event_type: str,
        data: Dict[str, Any],
    ) -> None:
        if not ctx.response_id:
            response_obj = data.get("response")
            if isinstance(response_obj, dict) and response_obj.get("id"):
                ctx.response_id = response_obj["id"]
            elif "id" in data:
                ctx.response_id = data["id"]

        usage = self.parser.extract_usage_from_response(data)
        if usage:
            ctx.final_usage = usage

            input_tokens = usage.get("input_tokens")
            output_tokens = usage.get("output_tokens")
            cache_read_tokens = usage.get("cache_read_tokens")
            cache_creation_tokens = usage.get("cache_creation_tokens")

            if isinstance(input_tokens, int) and (input_tokens > 0 or ctx.input_tokens == 0):
                ctx.input_tokens = input_tokens
            if isinstance(output_tokens, int) and (output_tokens > 0 or ctx.output_tokens == 0):
                ctx.output_tokens = output_tokens
            if isinstance(cache_read_tokens, int) and (cache_read_tokens > 0 or ctx.cached_tokens == 0):
                ctx.cached_tokens = cache_read_tokens
            if isinstance(cache_creation_tokens, int) and (
                cache_creation_tokens > 0 or ctx.cache_creation_tokens == 0
            ):
                ctx.cache_creation_tokens = cache_creation_tokens

        text = self.parser.extract_text_content(data)
        if text:
            ctx.collected_text += text

        if event_type in ("response.completed", "message_stop"):
            ctx.has_completion = True
            response_obj = data.get("response")
            if isinstance(response_obj, dict):
                ctx.final_response = response_obj

    async def _record_stream_stats(
        self,
        ctx: StreamContext,
        original_headers: Dict[str, str],
        original_request_body: Dict[str, Any],
    ) -> None:
        # 上游 F10: 统计写入前需要 delay，但 response_time_ms 不应包含该 delay。
        original_start_time = ctx.start_time
        ctx.start_time = original_start_time + 0.1
        try:
            await super()._record_stream_stats(ctx, original_headers, original_request_body)
        finally:
            ctx.start_time = original_start_time


__all__ = ["CliMessageHandlerBase", "StreamContext"]
