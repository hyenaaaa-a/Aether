"""
Gemini CLI Adapter - 基于通用 CLI Adapter 基类的实现

继承 CliAdapterBase，处理 Gemini CLI 格式的请求。
"""

from typing import Any, Dict, Optional, Type

from fastapi import Request

from src.api.handlers.base.cli_adapter_base import CliAdapterBase, register_cli_adapter
from src.api.handlers.base.cli_handler_base import CliMessageHandlerBase


@register_cli_adapter
class GeminiCliAdapter(CliAdapterBase):
    """
    Gemini CLI API 适配器

    处理 Gemini CLI 格式的请求（透传模式，最小验证）。
    """

    FORMAT_ID = "GEMINI_CLI"
    name = "gemini.cli"

    @property
    def HANDLER_CLASS(self) -> Type[CliMessageHandlerBase]:
        """延迟导入 Handler 类避免循环依赖"""
        from src.api.handlers.gemini_cli.handler import GeminiCliMessageHandler

        return GeminiCliMessageHandler

    def __init__(self, allowed_api_formats: Optional[list[str]] = None):
        super().__init__(allowed_api_formats or ["GEMINI_CLI"])

    def extract_api_key(self, request: Request) -> Optional[str]:
        """
        从请求中提取客户端 API 密钥。

        兼容：
        - Header: x-goog-api-key
        - Query: ?key=
        - Header: Authorization: Bearer <key>
        """
        header_key = request.headers.get("x-goog-api-key")
        if header_key:
            return header_key

        query_key = request.query_params.get("key")
        if query_key:
            return query_key

        authorization = request.headers.get("authorization")
        if authorization and authorization.lower().startswith("bearer "):
            return authorization[7:].strip() or None

        return request.headers.get("x-api-key")

    def _merge_path_params(
        self, original_request_body: Dict[str, Any], path_params: Dict[str, Any]  # noqa: ARG002
    ) -> Dict[str, Any]:
        """
        合并 URL 路径参数到请求体 - Gemini CLI 特化版本

        Gemini API 特点:
        - model 不合并到请求体（Gemini 原生请求体不含 model，通过 URL 路径传递）
        - stream 不合并到请求体（Gemini API 通过 URL 端点区分流式/非流式）

        基类已经从 path_params 获取 model 和 stream 用于日志和路由判断。

        Args:
            original_request_body: 原始请求体字典
            path_params: URL 路径参数字典（包含 model、stream 等）

        Returns:
            原始请求体（不合并任何 path_params）
        """
        # Gemini: 不合并任何 path_params 到请求体
        return original_request_body.copy()

    def _extract_message_count(self, payload: Dict[str, Any]) -> int:
        """Gemini CLI 使用 contents 字段"""
        contents = payload.get("contents", [])
        return len(contents) if isinstance(contents, list) else 0

    def _build_audit_metadata(
        self,
        payload: Dict[str, Any],
        path_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Gemini CLI 特定的审计元数据"""
        # 从 path_params 获取 model（Gemini 请求体不含 model）
        model = path_params.get("model", "unknown") if path_params else "unknown"
        contents = payload.get("contents", [])
        generation_config = payload.get("generation_config", {}) or {}

        role_counts: Dict[str, int] = {}
        for content in contents:
            role = content.get("role", "unknown") if isinstance(content, dict) else "unknown"
            role_counts[role] = role_counts.get(role, 0) + 1

        return {
            "action": "gemini_cli_request",
            "model": model,
            "stream": bool(payload.get("stream", False)),
            "max_output_tokens": generation_config.get("max_output_tokens"),
            "contents_count": len(contents),
            "content_roles": role_counts,
            "temperature": generation_config.get("temperature"),
            "top_p": generation_config.get("top_p"),
            "top_k": generation_config.get("top_k"),
            "tools_count": len(payload.get("tools") or []),
            "system_instruction_present": bool(payload.get("system_instruction")),
            "safety_settings_count": len(payload.get("safety_settings") or []),
        }


def build_gemini_cli_adapter(x_app_header: str = "") -> GeminiCliAdapter:
    """
    构建 Gemini CLI 适配器

    Args:
        x_app_header: X-App 请求头值（预留扩展）

    Returns:
        GeminiCliAdapter 实例
    """
    return GeminiCliAdapter()


__all__ = ["GeminiCliAdapter", "build_gemini_cli_adapter"]
