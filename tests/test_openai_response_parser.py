from src.api.handlers.base.parsers import OpenAIResponseParser


def test_extract_usage_from_response_allows_null_usage() -> None:
    parser = OpenAIResponseParser()
    assert parser.extract_usage_from_response({"usage": None}) == {}


def test_extract_usage_from_response_chat_completions_shape() -> None:
    parser = OpenAIResponseParser()
    usage = parser.extract_usage_from_response(
        {"usage": {"prompt_tokens": 12, "completion_tokens": 34, "total_tokens": 46}}
    )
    assert usage["input_tokens"] == 12
    assert usage["output_tokens"] == 34


def test_extract_usage_from_response_responses_api_shape() -> None:
    parser = OpenAIResponseParser()
    usage = parser.extract_usage_from_response({"usage": {"input_tokens": 7, "output_tokens": 8}})
    assert usage["input_tokens"] == 7
    assert usage["output_tokens"] == 8


def test_extract_usage_from_response_event_wrapped_response() -> None:
    parser = OpenAIResponseParser()
    usage = parser.extract_usage_from_response(
        {"type": "response.completed", "response": {"usage": {"input_tokens": 1, "output_tokens": 2}}}
    )
    assert usage["input_tokens"] == 1
    assert usage["output_tokens"] == 2


def test_extract_text_content_supports_streaming_delta() -> None:
    parser = OpenAIResponseParser()
    assert parser.extract_text_content({"choices": [{"delta": {"content": "hi"}}]}) == "hi"


def test_parse_response_allows_null_usage() -> None:
    parser = OpenAIResponseParser()
    parsed = parser.parse_response(
        {"id": "resp_1", "choices": [{"message": {"content": "hello"}}], "usage": None},
        status_code=200,
    )
    assert parsed.text_content == "hello"
    assert parsed.input_tokens == 0
    assert parsed.output_tokens == 0
