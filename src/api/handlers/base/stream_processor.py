"""
流式处理器 - 从 ChatHandlerBase 提取的流式响应处理逻辑

职责：
1. SSE 事件解析和处理
2. 响应流生成
3. 预读和嵌套错误检测
4. 客户端断开检测
"""

import asyncio
import codecs
import json
import time
from typing import Any, AsyncGenerator, Callable, Optional

import httpx

from src.api.handlers.base.parsers import get_parser_for_format
from src.api.handlers.base.response_parser import ResponseParser
from src.api.handlers.base.stream_context import StreamContext
from src.core.exceptions import EmbeddedErrorException
from src.core.logger import logger
from src.models.database import Provider, ProviderEndpoint
from src.utils.sse_parser import SSEEventParser


class StreamProcessor:
    """
    流式响应处理器

    负责处理 SSE 流的解析、错误检测和响应生成。
    """

    def __init__(
        self,
        request_id: str,
        default_parser: ResponseParser,
        on_streaming_start: Optional[Callable[[], None]] = None,
        *,
        collect_text: bool = False,
    ) -> None:
        self.request_id = request_id
        self.default_parser = default_parser
        self.on_streaming_start = on_streaming_start
        self.collect_text = collect_text

    def get_parser_for_provider(self, ctx: StreamContext) -> ResponseParser:
        """根据 Provider 的 api_format 选择对应的解析器"""
        if ctx.provider_api_format:
            try:
                return get_parser_for_format(ctx.provider_api_format)
            except KeyError:
                pass
        return self.default_parser

    def handle_sse_event(
        self,
        ctx: StreamContext,
        event_name: Optional[str],
        data_str: str,
    ) -> None:
        """处理单个 SSE 事件：解析 usage、收集文本、识别完成事件"""
        if not data_str:
            return

        if data_str == "[DONE]":
            ctx.has_completion = True
            return

        try:
            data = json.loads(data_str)
        except json.JSONDecodeError:
            return

        ctx.data_count += 1

        if not isinstance(data, dict):
            return

        ctx.parsed_chunks.append(data)

        parser = self.get_parser_for_provider(ctx)

        usage = parser.extract_usage_from_response(data)
        if usage:
            ctx.update_usage(
                input_tokens=usage.get("input_tokens"),
                output_tokens=usage.get("output_tokens"),
                cached_tokens=usage.get("cache_read_tokens"),
                cache_creation_tokens=usage.get("cache_creation_tokens"),
            )

        if self.collect_text:
            text = parser.extract_text_content(data)
            if text:
                ctx.append_text(text)

        event_type = event_name or data.get("type", "")
        if event_type in ("response.completed", "message_stop"):
            ctx.has_completion = True

    async def prefetch_and_check_error(
        self,
        byte_iterator: Any,
        provider: Provider,
        endpoint: ProviderEndpoint,
        ctx: StreamContext,
        max_prefetch_lines: int = 5,
    ) -> list:
        """
        预读流的前几行，检测嵌套错误

        某些 Provider（如 Gemini）可能返回 HTTP 200，但在响应体中包含错误信息；
        需要在流开始输出之前检测，以便触发重试逻辑。
        """
        prefetched_chunks: list = []
        parser = self.get_parser_for_provider(ctx)
        buffer = b""
        line_count = 0
        should_stop = False
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

        try:
            async for chunk in byte_iterator:
                prefetched_chunks.append(chunk)
                buffer += chunk

                while b"\n" in buffer:
                    line_bytes, buffer = buffer.split(b"\n", 1)
                    try:
                        line = decoder.decode(line_bytes + b"\n", False).rstrip("\r\n")
                    except Exception as e:
                        logger.warning(
                            f"[{self.request_id}] 预读时 UTF-8 解码失败: {e}, bytes={line_bytes[:50]!r}"
                        )
                        continue

                    line_count += 1

                    # 跳过空行和注释行
                    if not line or line.startswith(":"):
                        if line_count >= max_prefetch_lines:
                            should_stop = True
                            break
                        continue

                    data_str = line[6:] if line.startswith("data: ") else line
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

                    if isinstance(data, dict) and parser.is_error_response(data):
                        parsed = parser.parse_response(data, 200)
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

    async def create_response_stream(
        self,
        ctx: StreamContext,
        byte_iterator: Any,
        response_ctx: Any,
        http_client: httpx.AsyncClient,
        prefetched_chunks: Optional[list] = None,
        *,
        start_time: Optional[float] = None,
    ) -> AsyncGenerator[bytes, None]:
        """
        创建响应流生成器

        从字节流中解析 SSE 数据并转发，支持预读数据。
        """
        try:
            sse_parser = SSEEventParser()
            streaming_started = False
            buffer = b""
            decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

            if prefetched_chunks:
                if not streaming_started and self.on_streaming_start:
                    self.on_streaming_start()
                    streaming_started = True

                for chunk in prefetched_chunks:
                    if start_time is not None:
                        ctx.record_first_byte_time(start_time)
                        start_time = None

                    yield chunk

                    buffer += chunk
                    while b"\n" in buffer:
                        line_bytes, buffer = buffer.split(b"\n", 1)
                        try:
                            line = decoder.decode(line_bytes + b"\n", False)
                            self._process_line(ctx, sse_parser, line)
                        except Exception as e:
                            logger.warning(
                                f"[{self.request_id}] UTF-8 解码失败: {e}, bytes={line_bytes[:50]!r}"
                            )
                            continue

            async for chunk in byte_iterator:
                if not streaming_started and self.on_streaming_start:
                    self.on_streaming_start()
                    streaming_started = True

                if start_time is not None:
                    ctx.record_first_byte_time(start_time)
                    start_time = None

                yield chunk

                buffer += chunk
                while b"\n" in buffer:
                    line_bytes, buffer = buffer.split(b"\n", 1)
                    try:
                        line = decoder.decode(line_bytes + b"\n", False)
                        self._process_line(ctx, sse_parser, line)
                    except Exception as e:
                        logger.warning(
                            f"[{self.request_id}] UTF-8 解码失败: {e}, bytes={line_bytes[:50]!r}"
                        )
                        continue

            if buffer:
                try:
                    line = decoder.decode(buffer, True)
                    self._process_line(ctx, sse_parser, line)
                except Exception as e:
                    logger.warning(
                        f"[{self.request_id}] 处理剩余缓冲区失败: {e}, bytes={buffer[:50]!r}"
                    )

            for event in sse_parser.flush():
                self.handle_sse_event(ctx, event.get("event"), event.get("data") or "")

        except GeneratorExit:
            raise
        finally:
            await self._cleanup(response_ctx, http_client)

    def _process_line(
        self,
        ctx: StreamContext,
        sse_parser: SSEEventParser,
        line: str,
    ) -> None:
        """
        处理单行数据

        SSEEventParser 以“去掉换行符”的单行文本作为输入；这里统一剔除 CR/LF，
        避免把空行误判成 "\\n" 并导致事件边界解析错误。
        """
        normalized_line = line.rstrip("\r\n")
        events = sse_parser.feed_line(normalized_line)

        if normalized_line == "":
            for event in events:
                self.handle_sse_event(ctx, event.get("event"), event.get("data") or "")
        else:
            ctx.chunk_count += 1
            for event in events:
                self.handle_sse_event(ctx, event.get("event"), event.get("data") or "")

    async def create_monitored_stream(
        self,
        ctx: StreamContext,
        stream_generator: AsyncGenerator[bytes, None],
        is_disconnected: Callable[[], Any],
    ) -> AsyncGenerator[bytes, None]:
        """
        创建带监控的流生成器：检测客户端断开连接并更新状态码
        """
        try:
            # 断连检查节流：避免每个 chunk 都 await 带来的调度开销
            next_disconnect_check_at = 0.0
            disconnect_check_interval_s = 0.25

            async for chunk in stream_generator:
                now = time.monotonic()
                if now >= next_disconnect_check_at:
                    next_disconnect_check_at = now + disconnect_check_interval_s
                    if await is_disconnected():
                        logger.warning(f"ID:{self.request_id} | Client disconnected")
                        ctx.status_code = 499
                        ctx.error_message = "client_disconnected"
                        break
                yield chunk
        except asyncio.CancelledError:
            ctx.status_code = 499
            ctx.error_message = "client_disconnected"
            raise
        except Exception as e:
            ctx.status_code = 500
            ctx.error_message = str(e)
            raise

    async def _cleanup(
        self,
        response_ctx: Any,
        http_client: httpx.AsyncClient,
    ) -> None:
        """清理资源"""
        try:
            await response_ctx.__aexit__(None, None, None)
        except Exception:
            pass
        try:
            await http_client.aclose()
        except Exception:
            pass
