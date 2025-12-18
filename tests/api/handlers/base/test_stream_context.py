import pytest

from src.api.handlers.base.stream_context import StreamContext


def test_append_text_accumulates_without_copying() -> None:
    ctx = StreamContext(model="m", api_format="f")
    assert ctx.collected_text == ""

    ctx.append_text("a")
    ctx.append_text("b")
    ctx.append_text("")

    assert ctx.collected_text == "ab"


def test_reset_for_retry_clears_stream_state_but_keeps_identity() -> None:
    ctx = StreamContext(model="m", api_format="f", request_id="req_1")
    ctx.provider_name = "p"
    ctx.parsed_chunks = [{"k": "v"}]
    ctx.chunk_count = 3
    ctx.data_count = 2
    ctx.has_completion = True
    ctx.append_text("hello")
    ctx.input_tokens = 1
    ctx.output_tokens = 2
    ctx.cached_tokens = 3
    ctx.cache_creation_tokens = 4
    ctx.first_byte_time_ms = 123
    ctx.status_code = 500
    ctx.error_message = "boom"
    ctx.response_metadata = {"x": 1}

    ctx.reset_for_retry()

    assert ctx.model == "m"
    assert ctx.api_format == "f"
    assert ctx.request_id == "req_1"

    assert ctx.parsed_chunks == []
    assert ctx.chunk_count == 0
    assert ctx.data_count == 0
    assert ctx.has_completion is False
    assert ctx.collected_text == ""

    assert ctx.input_tokens == 0
    assert ctx.output_tokens == 0
    assert ctx.cached_tokens == 0
    assert ctx.cache_creation_tokens == 0

    assert ctx.first_byte_time_ms is None
    assert ctx.status_code == 200
    assert ctx.error_message is None
    assert ctx.response_metadata == {}


def test_record_first_byte_time_only_records_once(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = StreamContext(model="m", api_format="f")

    monkeypatch.setattr("src.api.handlers.base.stream_context.time.time", lambda: 200.0)
    ctx.record_first_byte_time(100.0)
    assert ctx.first_byte_time_ms == 100_000

    monkeypatch.setattr("src.api.handlers.base.stream_context.time.time", lambda: 250.0)
    ctx.record_first_byte_time(0.0)
    assert ctx.first_byte_time_ms == 100_000


def test_get_log_summary_includes_ttfb_when_present() -> None:
    ctx = StreamContext(model="m", api_format="f")
    ctx.provider_name = "p"
    ctx.input_tokens = 1
    ctx.output_tokens = 2
    ctx.first_byte_time_ms = 123

    summary = ctx.get_log_summary("req_12345678", response_time_ms=456)
    assert "TTFB: 123ms" in summary
    assert "Total: 456ms" in summary

