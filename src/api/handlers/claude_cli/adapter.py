"""
Claude CLI Adapter - 基于通用 CLI Adapter 基类的简化实现

继承 CliAdapterBase，只需配置 FORMAT_ID 和 HANDLER_CLASS。
"""

from typing import Any, Dict, Optional, Type

from fastapi import Request

from src.api.handlers.base.cli_adapter_base import CliAdapterBase, register_cli_adapter
from src.api.handlers.base.cli_handler_base import CliMessageHandlerBase
from src.api.handlers.claude.adapter import ClaudeCapabilityDetector


@register_cli_adapter
class ClaudeCliAdapter(CliAdapterBase):
    """
    Claude CLI API 适配器

    处理 Claude CLI 格式的请求（/v1/messages 端点，使用 Bearer 认证）。
    """

    FORMAT_ID = "CLAUDE_CLI"
    name = "claude.cli"

    @property
    def HANDLER_CLASS(self) -> Type[CliMessageHandlerBase]:
        """延迟导入 Handler 类避免循环依赖"""
        from src.api.handlers.claude_cli.handler import ClaudeCliMessageHandler

        return ClaudeCliMessageHandler

    def __init__(self, allowed_api_formats: Optional[list[str]] = None):
        super().__init__(allowed_api_formats or ["CLAUDE_CLI"])

    def extract_api_key(self, request: Request) -> Optional[str]:
        """从请求中提取 API 密钥 (Authorization: Bearer)"""
        authorization = request.headers.get("authorization")
        if authorization and authorization.startswith("Bearer "):
            return authorization.replace("Bearer ", "")
        return None

    def detect_capability_requirements(
        self,
        headers: Dict[str, str],
        request_body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, bool]:
        """检测 Claude CLI 请求中隐含的能力需求"""
        return ClaudeCapabilityDetector.detect_from_headers(headers)

    # =========================================================================
    # Claude CLI 特定的计费逻辑
    # =========================================================================

    def compute_total_input_context(
        self,
        input_tokens: int,
        cache_read_input_tokens: int,
        cache_creation_input_tokens: int = 0,
    ) -> int:
        """
        计算 Claude CLI 的总输入上下文（用于阶梯计费判定）

        Claude 的总输入 = input_tokens + cache_creation_input_tokens + cache_read_input_tokens
        """
        return input_tokens + cache_creation_input_tokens + cache_read_input_tokens

    def _extract_message_count(self, payload: Dict[str, Any]) -> int:
        """Claude CLI 使用 messages 字段"""
        messages = payload.get("messages", [])
        return len(messages) if isinstance(messages, list) else 0

    def _build_audit_metadata(
        self,
        payload: Dict[str, Any],
        path_params: Optional[Dict[str, Any]] = None,  # noqa: ARG002
    ) -> Dict[str, Any]:
        """Claude CLI 特定的审计元数据"""
        model = payload.get("model", "unknown")
        stream = payload.get("stream", False)
        messages = payload.get("messages", [])

        role_counts = {}
        for msg in messages:
            role = msg.get("role", "unknown")
            role_counts[role] = role_counts.get(role, 0) + 1

        return {
            "action": "claude_cli_request",
            "model": model,
            "stream": bool(stream),
            "max_tokens": payload.get("max_tokens"),
            "messages_count": len(messages),
            "message_roles": role_counts,
            "temperature": payload.get("temperature"),
            "top_p": payload.get("top_p"),
            "tool_count": len(payload.get("tools") or []),
            "system_present": bool(payload.get("system")),
        }


__all__ = ["ClaudeCliAdapter"]
