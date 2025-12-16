"""
统一的 Provider 请求构建工具。

负责:
- 根据 endpoint/key 构建标准请求头
- 根据 API 格式或端点配置生成请求 URL
"""

from typing import Any, Dict, Optional
from urllib.parse import urlencode

from src.core.api_format_metadata import get_auth_config, get_default_path, resolve_api_format
from src.core.crypto import crypto_service
from src.core.enums import APIFormat
from src.core.logger import logger



def build_provider_headers(
    endpoint,
    key,
    original_headers: Optional[Dict[str, str]] = None,
    *,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """
    根据 endpoint/key 构建请求头，并透传客户端自定义头。
    """
    headers: Dict[str, str] = {}

    decrypted_key = crypto_service.decrypt(key.api_key)

    # 根据 API 格式自动选择认证头
    api_format = getattr(endpoint, "api_format", None)
    resolved_format = resolve_api_format(api_format)
    auth_header, auth_type = (
        get_auth_config(resolved_format) if resolved_format else ("Authorization", "bearer")
    )

    if auth_type == "bearer":
        headers[auth_header] = f"Bearer {decrypted_key}"
    else:
        headers[auth_header] = decrypted_key

    if endpoint.headers:
        headers.update(endpoint.headers)

    excluded_headers = {
        "host",
        "authorization",
        "x-api-key",
        "x-goog-api-key",
        "content-length",
        "transfer-encoding",
    }

    if original_headers:
        for name, value in original_headers.items():
            if name.lower() not in excluded_headers:
                headers[name] = value

    if extra_headers:
        headers.update(extra_headers)

    if "Content-Type" not in headers and "content-type" not in headers:
        headers["Content-Type"] = "application/json"

    return headers


def build_provider_url(
    endpoint,
    *,
    query_params: Optional[Dict[str, Any]] = None,
    path_params: Optional[Dict[str, Any]] = None,
    is_stream: bool = False,
    is_responses_request: bool = False,
    client_path: Optional[str] = None,
) -> str:
    """
    根据 endpoint 配置生成请求 URL

    优先级：
    1. endpoint.custom_path - 自定义路径（支持模板变量如 {model}）
    2. client_path - 客户端原始请求路径（自适应路由）
    3. is_responses_request - 向后兼容的 /v1/responses 特殊处理
    4. API 格式默认路径 - 根据 api_format 自动选择

    Args:
        endpoint: 端点配置
        query_params: 查询参数
        path_params: 路径模板参数 (如 {model})
        is_stream: 是否为流式请求，用于 Gemini API 选择正确的操作方法
        is_responses_request: 是否为 /v1/responses 请求（向后兼容）
        client_path: 客户端原始请求路径（用于自适应路由，优先于 is_responses_request）
    """
    base = endpoint.base_url.rstrip("/")

    # 准备路径参数，添加 Gemini API 所需的 action 参数
    effective_path_params = dict(path_params) if path_params else {}

    # 为 Gemini API 格式自动添加 action 参数
    resolved_format = resolve_api_format(endpoint.api_format)
    if resolved_format in (APIFormat.GEMINI, APIFormat.GEMINI_CLI):
        if "action" not in effective_path_params:
            effective_path_params["action"] = (
                "streamGenerateContent" if is_stream else "generateContent"
            )

    # 优先使用 custom_path 字段
    if endpoint.custom_path:
        path = endpoint.custom_path
        if effective_path_params:
            try:
                path = path.format(**effective_path_params)
            except KeyError:
                # 如果模板变量不匹配，保持原路径
                pass
    else:
        # 自适应路由：当 custom_path 为空时，尝试使用客户端原始请求路径
        # 优先级：client_path > is_responses_request > 默认路径
        if client_path:
            # 使用客户端原始请求路径（自适应路由）
            path = client_path
        elif is_responses_request and resolved_format == APIFormat.OPENAI:
            # 向后兼容：/v1/responses 特殊处理
            path = "/v1/responses"
        else:
            # 使用 API 格式的默认路径
            path = _resolve_default_path(endpoint.api_format)
        if effective_path_params:
            try:
                path = path.format(**effective_path_params)
            except KeyError:
                # 如果模板变量不匹配，保持原路径
                pass

    if not path.startswith("/"):
        path = f"/{path}"

    url = f"{base}{path}"

    # 添加查询参数（过滤敏感参数）
    if query_params:
        # 过滤敏感的认证查询参数，防止客户端凭证被转发到上游
        sensitive_params = {"key", "api_key", "apikey", "token", "access_token"}
        filtered_params = {
            k: v for k, v in query_params.items() 
            if k.lower() not in sensitive_params
        }
        if filtered_params:
            query_string = urlencode(filtered_params, doseq=True)
            if query_string:
                url = f"{url}?{query_string}"

    return url


def _resolve_default_path(api_format) -> str:
    """
    根据 API 格式返回默认路径
    """
    resolved = resolve_api_format(api_format)
    if resolved:
        return get_default_path(resolved)

    logger.warning(f"Unknown api_format '{api_format}' for endpoint, fallback to '/'")
    return "/"
