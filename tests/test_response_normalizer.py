import pytest

from src.services.provider.response_normalizer import ResponseNormalizer


def test_normalize_openai_response_valid_shape() -> None:
    normalizer = ResponseNormalizer()
    response = {
        "id": "chatcmpl_1",
        "object": "chat.completion",
        "created": 123,
        "model": "gpt-4o",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "hi"},
                "finish_reason": "stop",
            }
        ],
        "usage": None,
    }

    normalized = normalizer.normalize_openai_response(response, request_id="req_1", strict=False)
    assert normalized["id"] == "chatcmpl_1"
    assert normalized["choices"][0]["message"]["content"] == "hi"


def test_normalize_openai_response_non_strict_passthrough_on_invalid() -> None:
    normalizer = ResponseNormalizer()
    bad = {"unexpected": "shape"}

    assert normalizer.normalize_openai_response(bad, strict=False) == bad
    with pytest.raises(Exception):
        normalizer.normalize_openai_response(bad, strict=True)

