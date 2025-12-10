"""
OpenAI CLI Adapter - 基于通用 CLI Adapter 基类的简化实现

继承 CliAdapterBase，只需配置 FORMAT_ID 和 HANDLER_CLASS。
"""

from typing import Optional, Type

from fastapi import Request

from src.api.handlers.base.cli_adapter_base import CliAdapterBase, register_cli_adapter
from src.api.handlers.base.cli_handler_base import CliMessageHandlerBase


@register_cli_adapter
class OpenAICliAdapter(CliAdapterBase):
    """
    OpenAI CLI API 适配器

    处理 /v1/responses 端点的请求。
    """

    FORMAT_ID = "OPENAI_CLI"
    name = "openai.cli"

    @property
    def HANDLER_CLASS(self) -> Type[CliMessageHandlerBase]:
        """延迟导入 Handler 类避免循环依赖"""
        from src.api.handlers.openai_cli.handler import OpenAICliMessageHandler

        return OpenAICliMessageHandler

    def __init__(self, allowed_api_formats: Optional[list[str]] = None):
        super().__init__(allowed_api_formats or ["OPENAI_CLI"])

    def extract_api_key(self, request: Request) -> Optional[str]:
        """从请求中提取 API 密钥 (Authorization: Bearer)"""
        authorization = request.headers.get("authorization")
        if authorization and authorization.startswith("Bearer "):
            return authorization.replace("Bearer ", "")
        return None


__all__ = ["OpenAICliAdapter"]
