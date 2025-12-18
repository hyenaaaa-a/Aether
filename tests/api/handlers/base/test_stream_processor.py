from src.api.handlers.base.parsers import OpenAIResponseParser
from src.api.handlers.base.stream_context import StreamContext
from src.api.handlers.base.stream_processor import StreamProcessor
from src.utils.sse_parser import SSEEventParser


def test_process_line_parses_sse_and_updates_context() -> None:
    ctx = StreamContext(model="gpt-4o", api_format="OPENAI")
    processor = StreamProcessor(request_id="req_1", default_parser=OpenAIResponseParser(), collect_text=True)
    sse_parser = SSEEventParser()

    processor._process_line(ctx, sse_parser, 'data: {"choices": [{"delta": {"content": "hi"}}]}\r\n')
    assert ctx.chunk_count == 1
    assert ctx.data_count == 0

    processor._process_line(ctx, sse_parser, "")
    assert ctx.data_count == 1
    assert ctx.collected_text == "hi"

    processor._process_line(ctx, sse_parser, 'data: {"usage": {"input_tokens": 7, "output_tokens": 8}}\n')
    processor._process_line(ctx, sse_parser, "")

    assert ctx.input_tokens == 7
    assert ctx.output_tokens == 8

