"""
流式处理上下文 - 类型安全的数据类替代 dict

提供流式请求处理过程中的状态跟踪，包括：
- Provider/Endpoint/Key 信息
- Token 统计
- 响应状态
- 请求/响应数据
"""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class StreamContext:
    """
    流式处理上下文

    用于在流式请求处理过程中跟踪状态，替代原有的 ctx dict。
    所有字段都有类型注解，提供更好的 IDE 支持和运行时类型安全。
    """

    # 请求基本信息
    model: str
    api_format: str

    # 请求标识信息（CLI/遥测等场景可能需要）
    request_id: str = ""
    user_id: int = 0
    api_key_id: int = 0

    # Provider 信息（在请求执行时填充）
    provider_name: Optional[str] = None
    provider_id: Optional[str] = None
    endpoint_id: Optional[str] = None
    key_id: Optional[str] = None
    attempt_id: Optional[str] = None
    attempt_synced: bool = False
    provider_api_format: Optional[str] = None  # Provider 的响应格式

    # 模型映射
    mapped_model: Optional[str] = None

    # Token 统计
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    cache_creation_tokens: int = 0

    # 响应内容（按需收集）
    _collected_text_parts: List[str] = field(default_factory=list, repr=False)
    response_id: Optional[str] = None
    final_usage: Optional[Dict[str, Any]] = None
    final_response: Optional[Dict[str, Any]] = None

    # 时间指标
    first_byte_time_ms: Optional[int] = None  # TTFB - Time To First Byte
    start_time: float = field(default_factory=time.time)

    # 响应状态
    status_code: int = 200
    error_message: Optional[str] = None
    has_completion: bool = False

    # 请求/响应数据
    response_headers: Dict[str, str] = field(default_factory=dict)
    provider_request_headers: Dict[str, str] = field(default_factory=dict)
    provider_request_body: Optional[Dict[str, Any]] = None

    # 格式转换信息（CLI handler 可能需要）
    client_api_format: str = ""

    # Provider 响应元数据（例如 Gemini modelVersion 等）
    response_metadata: Dict[str, Any] = field(default_factory=dict)

    # 流式处理统计
    data_count: int = 0
    chunk_count: int = 0
    parsed_chunks: List[Dict[str, Any]] = field(default_factory=list)

    def reset_for_retry(self) -> None:
        """
        重试时重置状态

        在故障转移重试时调用，清理之前的数据避免累积。
        保留 model 和 api_format，重置其他所有状态。
        """
        self.parsed_chunks = []
        self.chunk_count = 0
        self.data_count = 0
        self.has_completion = False
        self._collected_text_parts = []
        self.input_tokens = 0
        self.output_tokens = 0
        self.cached_tokens = 0
        self.cache_creation_tokens = 0
        self.error_message = None
        self.status_code = 200
        self.first_byte_time_ms = None
        self.response_headers = {}
        self.provider_request_headers = {}
        self.provider_request_body = None
        self.response_id = None
        self.final_usage = None
        self.final_response = None
        self.response_metadata = {}

    def update_provider_info(
        self,
        provider_name: str,
        provider_id: str,
        endpoint_id: str,
        key_id: str,
        provider_api_format: Optional[str] = None,
    ) -> None:
        """更新 Provider 信息"""
        self.provider_name = provider_name
        self.provider_id = provider_id
        self.endpoint_id = endpoint_id
        self.key_id = key_id
        self.provider_api_format = provider_api_format

    @property
    def collected_text(self) -> str:
        """已收集的文本内容（按需拼接，避免流式过程中频繁字符串拷贝）"""
        return "".join(self._collected_text_parts)

    def append_text(self, text: str) -> None:
        """追加文本内容（仅在需要收集文本时调用）"""
        if text:
            self._collected_text_parts.append(text)

    def update_usage(
        self,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        cached_tokens: Optional[int] = None,
        cache_creation_tokens: Optional[int] = None,
    ) -> None:
        """
        更新 Token 使用统计（防御性更新）

        流式响应里部分事件可能返回 0 或缺失 usage 字段，后续事件才给出完整统计；
        这里避免用 0 覆盖已经得到的非 0 正确值。
        """
        if input_tokens is not None and (input_tokens > 0 or self.input_tokens == 0):
            self.input_tokens = input_tokens
        if output_tokens is not None and (output_tokens > 0 or self.output_tokens == 0):
            self.output_tokens = output_tokens
        if cached_tokens is not None and (cached_tokens > 0 or self.cached_tokens == 0):
            self.cached_tokens = cached_tokens
        if cache_creation_tokens is not None and (
            cache_creation_tokens > 0 or self.cache_creation_tokens == 0
        ):
            self.cache_creation_tokens = cache_creation_tokens

    def mark_failed(self, status_code: int, error_message: str) -> None:
        """标记请求失败"""
        self.status_code = status_code
        self.error_message = error_message

    def record_first_byte_time(self, start_time: float) -> None:
        """记录首字节时间 (TTFB)，只记录一次"""
        if self.first_byte_time_ms is None:
            self.first_byte_time_ms = int((time.time() - start_time) * 1000)

    def is_success(self) -> bool:
        """检查请求是否成功"""
        return self.status_code < 400

    def build_response_body(self, response_time_ms: int) -> Dict[str, Any]:
        """
        构建响应体元数据

        用于记录到 Usage 表的 response_body 字段。
        """
        return {
            "chunks": self.parsed_chunks,
            "metadata": {
                "stream": True,
                "total_chunks": len(self.parsed_chunks),
                "data_count": self.data_count,
                "has_completion": self.has_completion,
                "response_time_ms": response_time_ms,
                "first_byte_time_ms": self.first_byte_time_ms,
            },
        }

    def get_log_summary(self, request_id: str, response_time_ms: int) -> str:
        """
        获取日志摘要

        用于请求完成/失败时的日志输出，包含首字节时间与总耗时。
        """
        status = "OK" if self.is_success() else "FAIL"

        line1 = f"[{status}] {request_id[:8]} | {self.model} | {self.provider_name or 'unknown'}"
        if self.first_byte_time_ms is not None:
            line1 += f" | TTFB: {self.first_byte_time_ms}ms"

        line2 = f"      Total: {response_time_ms}ms | in:{self.input_tokens} out:{self.output_tokens}"
        return f"{line1}\n{line2}"
