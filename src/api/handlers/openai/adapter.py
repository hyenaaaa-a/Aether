"""
OpenAI Chat Adapter - 基于 ChatAdapterBase 的 OpenAI Chat API 适配器

处理 /v1/chat/completions 端点的 OpenAI Chat 格式请求。
"""

from typing import Any, Dict, Optional, Type

from fastapi import Request
from fastapi.responses import JSONResponse

from src.api.handlers.base.chat_adapter_base import ChatAdapterBase, register_adapter
from src.api.handlers.base.chat_handler_base import ChatHandlerBase
from src.core.logger import logger
from src.models.openai import OpenAIRequest


@register_adapter
class OpenAIChatAdapter(ChatAdapterBase):
    """
    OpenAI Chat Completions API 适配器

    处理 OpenAI Chat 格式的请求（/v1/chat/completions 端点）。
    """

    FORMAT_ID = "OPENAI"
    name = "openai.chat"

    @property
    def HANDLER_CLASS(self) -> Type[ChatHandlerBase]:
        """延迟导入 Handler 类避免循环依赖"""
        from src.api.handlers.openai.handler import OpenAIChatHandler

        return OpenAIChatHandler

    def __init__(self, allowed_api_formats: Optional[list[str]] = None):
        super().__init__(allowed_api_formats or ["OPENAI"])

    def extract_api_key(self, request: Request) -> Optional[str]:
        """从请求中提取 API 密钥 (Authorization: Bearer)"""
        authorization = request.headers.get("authorization")
        if authorization and authorization.startswith("Bearer "):
            return authorization.replace("Bearer ", "")
        return None

    def _validate_request_body(self, original_request_body: dict, path_params: dict = None):
        """验证请求体"""
        if not isinstance(original_request_body, dict):
            return self._error_response(
                400, "Request body must be a JSON object", "invalid_request_error"
            )

        required_fields = ["model", "messages"]
        missing = [f for f in required_fields if f not in original_request_body]
        if missing:
            return self._error_response(
                400,
                f"Missing required fields: {', '.join(missing)}",
                "invalid_request_error",
            )

        try:
            return OpenAIRequest.model_validate(original_request_body, strict=False)
        except ValueError as e:
            return self._error_response(400, str(e), "invalid_request_error")
        except Exception as e:
            logger.warning(f"Pydantic验证警告(将继续处理): {str(e)}")
            return OpenAIRequest.model_construct(
                model=original_request_body.get("model"),
                messages=original_request_body.get("messages", []),
                stream=original_request_body.get("stream", False),
                max_tokens=original_request_body.get("max_tokens"),
            )

    def _build_audit_metadata(self, payload: Dict[str, Any], request_obj) -> Dict[str, Any]:
        """构建 OpenAI Chat 特定的审计元数据"""
        role_counts = {}
        for message in request_obj.messages:
            role_counts[message.role] = role_counts.get(message.role, 0) + 1

        return {
            "action": "openai_chat_completion",
            "model": request_obj.model,
            "stream": bool(request_obj.stream),
            "max_tokens": request_obj.max_tokens,
            "temperature": request_obj.temperature,
            "top_p": request_obj.top_p,
            "messages_count": len(request_obj.messages),
            "message_roles": role_counts,
            "tools_count": len(request_obj.tools or []),
            "response_format": bool(request_obj.response_format),
            "user_identifier": request_obj.user,
        }

    def _error_response(self, status_code: int, message: str, error_type: str) -> JSONResponse:
        """生成 OpenAI 格式的错误响应"""
        return JSONResponse(
            status_code=status_code,
            content={
                "error": {
                    "type": error_type,
                    "message": message,
                    "code": status_code,
                }
            },
        )


__all__ = ["OpenAIChatAdapter"]
