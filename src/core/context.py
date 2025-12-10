"""
统一的请求上下文

RequestContext 贯穿整个请求生命周期，包含所有请求相关信息。
这确保了数据在各层之间传递时不会丢失。

使用方式：
1. Pipeline 层创建 RequestContext
2. 各层通过 context 访问和更新信息
3. Adapter 层使用 context 记录 Usage
"""

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class RequestContext:
    """
    请求上下文 - 贯穿整个请求生命周期

    设计原则：
    1. 在请求开始时创建，包含所有已知信息
    2. 在请求执行过程中逐步填充 Provider 信息
    3. 在请求结束时用于记录 Usage
    """

    # ==================== 请求标识 ====================
    request_id: str

    # ==================== 认证信息 ====================
    user: Any  # User model
    api_key: Any  # ApiKey model
    db: Any  # Database session

    # ==================== 请求信息 ====================
    api_format: str  # CLAUDE, OPENAI, GEMINI, etc.
    model: str  # 用户请求的模型名
    is_stream: bool = False

    # ==================== 原始请求 ====================
    original_headers: Dict[str, str] = field(default_factory=dict)
    original_body: Dict[str, Any] = field(default_factory=dict)

    # ==================== 客户端信息 ====================
    client_ip: str = "unknown"
    user_agent: str = ""

    # ==================== 计时 ====================
    start_time: float = field(default_factory=time.time)

    # ==================== Provider 信息（请求执行后填充）====================
    provider_name: Optional[str] = None
    provider_id: Optional[str] = None
    endpoint_id: Optional[str] = None
    provider_api_key_id: Optional[str] = None

    # ==================== 模型映射信息 ====================
    resolved_model: Optional[str] = None  # 映射后的模型名
    original_model: Optional[str] = None  # 原始模型名（用于价格计算）

    # ==================== 请求/响应头 ====================
    provider_request_headers: Dict[str, str] = field(default_factory=dict)
    provider_response_headers: Dict[str, str] = field(default_factory=dict)

    # ==================== 追踪信息 ====================
    attempt_id: Optional[str] = None

    # ==================== 能力需求 ====================
    capability_requirements: Dict[str, bool] = field(default_factory=dict)
    # 运行时计算的能力需求，来源于:
    # 1. 用户 model_capability_settings
    # 2. 用户 ApiKey.force_capabilities
    # 3. 请求头 X-Require-Capability
    # 4. 失败重试时动态添加

    @classmethod
    def create(
        cls,
        *,
        db: Any,
        user: Any,
        api_key: Any,
        api_format: str,
        model: str,
        is_stream: bool = False,
        original_headers: Optional[Dict[str, str]] = None,
        original_body: Optional[Dict[str, Any]] = None,
        client_ip: str = "unknown",
        user_agent: str = "",
        request_id: Optional[str] = None,
    ) -> "RequestContext":
        """创建请求上下文"""
        return cls(
            request_id=request_id or str(uuid.uuid4()),
            db=db,
            user=user,
            api_key=api_key,
            api_format=api_format,
            model=model,
            is_stream=is_stream,
            original_headers=original_headers or {},
            original_body=original_body or {},
            client_ip=client_ip,
            user_agent=user_agent,
            original_model=model,  # 初始时原始模型等于请求模型
        )

    def update_provider_info(
        self,
        *,
        provider_name: str,
        provider_id: str,
        endpoint_id: str,
        provider_api_key_id: str,
        resolved_model: Optional[str] = None,
    ) -> None:
        """更新 Provider 信息（请求执行后调用）"""
        self.provider_name = provider_name
        self.provider_id = provider_id
        self.endpoint_id = endpoint_id
        self.provider_api_key_id = provider_api_key_id
        if resolved_model:
            self.resolved_model = resolved_model

    def update_headers(
        self,
        *,
        request_headers: Optional[Dict[str, str]] = None,
        response_headers: Optional[Dict[str, str]] = None,
    ) -> None:
        """更新请求/响应头"""
        if request_headers:
            self.provider_request_headers = request_headers
        if response_headers:
            self.provider_response_headers = response_headers

    @property
    def elapsed_ms(self) -> int:
        """计算已经过的时间（毫秒）"""
        return int((time.time() - self.start_time) * 1000)

    @property
    def effective_model(self) -> str:
        """获取有效的模型名（映射后优先）"""
        return self.resolved_model or self.model

    @property
    def billing_model(self) -> str:
        """获取计费模型名（原始模型优先）"""
        return self.original_model or self.model

    def to_metadata_dict(self) -> Dict[str, Any]:
        """转换为元数据字典（用于 Usage 记录）"""
        return {
            "api_format": self.api_format,
            "provider": self.provider_name or "unknown",
            "model": self.effective_model,
            "original_model": self.billing_model,
            "provider_id": self.provider_id,
            "provider_endpoint_id": self.endpoint_id,
            "provider_api_key_id": self.provider_api_key_id,
            "provider_request_headers": self.provider_request_headers,
            "provider_response_headers": self.provider_response_headers,
            "attempt_id": self.attempt_id,
        }
