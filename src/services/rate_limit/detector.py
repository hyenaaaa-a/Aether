"""
速率限制检测器 - 解析429响应头，区分并发限制和RPM限制
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from src.core.logger import logger


class RateLimitType:
    """速率限制类型"""

    CONCURRENT = "concurrent"  # 并发限制
    RPM = "rpm"  # 每分钟请求数限制
    DAILY = "daily"  # 每日限制
    MONTHLY = "monthly"  # 每月限制
    UNKNOWN = "unknown"  # 未知类型


class RateLimitInfo:
    """速率限制信息"""

    def __init__(
        self,
        limit_type: str,
        retry_after: Optional[int] = None,
        limit_value: Optional[int] = None,
        remaining: Optional[int] = None,
        reset_at: Optional[datetime] = None,
        current_usage: Optional[int] = None,
        raw_headers: Optional[Dict[str, str]] = None,
    ):
        self.limit_type = limit_type
        self.retry_after = retry_after  # 需要等待的秒数
        self.limit_value = limit_value  # 限制值
        self.remaining = remaining  # 剩余配额
        self.reset_at = reset_at  # 重置时间
        self.current_usage = current_usage  # 当前使用量
        self.raw_headers = raw_headers or {}

    def __repr__(self) -> str:
        return (
            f"RateLimitInfo(type={self.limit_type}, "
            f"retry_after={self.retry_after}, "
            f"limit={self.limit_value}, "
            f"remaining={self.remaining})"
        )


class RateLimitDetector:
    """
    速率限制检测器

    支持的提供商：
    - Anthropic Claude API
    - OpenAI API
    - 通用 HTTP 标准头
    """

    @staticmethod
    def detect_from_headers(
        headers: Dict[str, str],
        provider_name: str = "unknown",
        current_concurrent: Optional[int] = None,
    ) -> RateLimitInfo:
        """
        从响应头中检测速率限制类型

        Args:
            headers: 429响应的HTTP头
            provider_name: 提供商名称（用于选择解析策略）
            current_concurrent: 当前并发数（用于判断是否为并发限制）

        Returns:
            RateLimitInfo对象
        """
        # 标准化header key (转小写)
        headers_lower = {k.lower(): v for k, v in headers.items()}

        # 根据提供商选择解析策略
        if "anthropic" in provider_name.lower() or "claude" in provider_name.lower():
            return RateLimitDetector._parse_anthropic_headers(headers_lower, current_concurrent)
        elif "openai" in provider_name.lower():
            return RateLimitDetector._parse_openai_headers(headers_lower, current_concurrent)
        else:
            return RateLimitDetector._parse_generic_headers(headers_lower, current_concurrent)

    @staticmethod
    def _parse_anthropic_headers(
        headers: Dict[str, str],
        current_concurrent: Optional[int] = None,
    ) -> RateLimitInfo:
        """
        解析 Anthropic Claude API 的速率限制头

        常见头部：
        - anthropic-ratelimit-requests-limit: 50
        - anthropic-ratelimit-requests-remaining: 0
        - anthropic-ratelimit-requests-reset: 2024-01-01T00:00:00Z
        - anthropic-ratelimit-tokens-limit: 100000
        - anthropic-ratelimit-tokens-remaining: 50000
        - retry-after: 60
        """
        retry_after = RateLimitDetector._parse_retry_after(headers)

        # 获取请求限制信息
        requests_limit = RateLimitDetector._parse_int(
            headers.get("anthropic-ratelimit-requests-limit")
        )
        requests_remaining = RateLimitDetector._parse_int(
            headers.get("anthropic-ratelimit-requests-remaining")
        )
        requests_reset = RateLimitDetector._parse_datetime(
            headers.get("anthropic-ratelimit-requests-reset")
        )

        # 判断限制类型
        # 1. 明确的 RPM 限制：请求数剩余为 0
        if requests_remaining is not None and requests_remaining == 0:
            return RateLimitInfo(
                limit_type=RateLimitType.RPM,
                retry_after=retry_after,
                limit_value=requests_limit,
                remaining=requests_remaining,
                reset_at=requests_reset,
                raw_headers=headers,
            )

        # 2. 可能的并发限制判断（多条件综合）
        # 条件：当前并发数存在，且 remaining > 0（说明不是 RPM 耗尽）
        # 同时 retry_after 较短（并发限制通常 retry_after 较短，如 1-10 秒）
        is_likely_concurrent = (
            current_concurrent is not None
            and current_concurrent >= 2  # 至少有 2 个并发
            and (requests_remaining is None or requests_remaining > 0)  # RPM 未耗尽
            and (retry_after is None or retry_after <= 30)  # 短暂等待
        )

        if is_likely_concurrent:
            logger.info(
                f"检测到可能的并发限制: current_concurrent={current_concurrent}, "
                f"remaining={requests_remaining}, retry_after={retry_after}"
            )
            return RateLimitInfo(
                limit_type=RateLimitType.CONCURRENT,
                retry_after=retry_after,
                current_usage=current_concurrent,
                raw_headers=headers,
            )

        # 3. 未知类型
        return RateLimitInfo(
            limit_type=RateLimitType.UNKNOWN,
            retry_after=retry_after,
            raw_headers=headers,
        )

    @staticmethod
    def _parse_openai_headers(
        headers: Dict[str, str],
        current_concurrent: Optional[int] = None,
    ) -> RateLimitInfo:
        """
        解析 OpenAI API 的速率限制头

        常见头部：
        - x-ratelimit-limit-requests: 3500
        - x-ratelimit-remaining-requests: 0
        - x-ratelimit-reset-requests: 2024-01-01T00:00:00Z
        - x-ratelimit-limit-tokens: 90000
        - x-ratelimit-remaining-tokens: 50000
        - retry-after: 60
        """
        retry_after = RateLimitDetector._parse_retry_after(headers)

        # 获取请求限制信息
        requests_limit = RateLimitDetector._parse_int(headers.get("x-ratelimit-limit-requests"))
        requests_remaining = RateLimitDetector._parse_int(
            headers.get("x-ratelimit-remaining-requests")
        )
        requests_reset = RateLimitDetector._parse_datetime(
            headers.get("x-ratelimit-reset-requests")
        )

        # 判断限制类型
        # 1. 明确的 RPM 限制
        if requests_remaining is not None and requests_remaining == 0:
            return RateLimitInfo(
                limit_type=RateLimitType.RPM,
                retry_after=retry_after,
                limit_value=requests_limit,
                remaining=requests_remaining,
                reset_at=requests_reset,
                raw_headers=headers,
            )

        # 2. 可能的并发限制（多条件综合判断）
        is_likely_concurrent = (
            current_concurrent is not None
            and current_concurrent >= 2
            and (requests_remaining is None or requests_remaining > 0)
            and (retry_after is None or retry_after <= 30)
        )

        if is_likely_concurrent:
            return RateLimitInfo(
                limit_type=RateLimitType.CONCURRENT,
                retry_after=retry_after,
                current_usage=current_concurrent,
                raw_headers=headers,
            )

        # 3. 未知类型
        return RateLimitInfo(
            limit_type=RateLimitType.UNKNOWN,
            retry_after=retry_after,
            raw_headers=headers,
        )

    @staticmethod
    def _parse_generic_headers(
        headers: Dict[str, str],
        current_concurrent: Optional[int] = None,
    ) -> RateLimitInfo:
        """
        解析通用的速率限制头

        标准头部：
        - retry-after: 60
        - x-ratelimit-limit: 100
        - x-ratelimit-remaining: 0
        - x-ratelimit-reset: 1609459200
        """
        retry_after = RateLimitDetector._parse_retry_after(headers)

        limit_value = RateLimitDetector._parse_int(headers.get("x-ratelimit-limit"))
        remaining = RateLimitDetector._parse_int(headers.get("x-ratelimit-remaining"))

        # 1. 明确的 RPM 限制
        if remaining is not None and remaining == 0:
            return RateLimitInfo(
                limit_type=RateLimitType.RPM,
                retry_after=retry_after,
                limit_value=limit_value,
                remaining=remaining,
                raw_headers=headers,
            )

        # 2. 可能的并发限制
        is_likely_concurrent = (
            current_concurrent is not None
            and current_concurrent >= 2
            and (remaining is None or remaining > 0)
            and (retry_after is None or retry_after <= 30)
        )

        if is_likely_concurrent:
            return RateLimitInfo(
                limit_type=RateLimitType.CONCURRENT,
                retry_after=retry_after,
                current_usage=current_concurrent,
                raw_headers=headers,
            )

        # 3. 未知类型
        return RateLimitInfo(
            limit_type=RateLimitType.UNKNOWN,
            retry_after=retry_after,
            raw_headers=headers,
        )

    @staticmethod
    def _parse_retry_after(headers: Dict[str, str]) -> Optional[int]:
        """解析 Retry-After 头"""
        retry_after_str = headers.get("retry-after")
        if not retry_after_str:
            return None

        try:
            # 尝试解析为整数（秒数）
            return int(retry_after_str)
        except ValueError:
            # 尝试解析为HTTP日期格式
            try:
                retry_date = datetime.strptime(retry_after_str, "%a, %d %b %Y %H:%M:%S %Z")
                delta = retry_date - datetime.now(timezone.utc)
                return max(int(delta.total_seconds()), 0)
            except Exception:
                return None

    @staticmethod
    def _parse_int(value: Optional[str]) -> Optional[int]:
        """安全解析整数"""
        if not value:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
        """安全解析ISO 8601日期时间"""
        if not value:
            return None
        try:
            # 尝试解析 ISO 8601 格式
            if value.endswith("Z"):
                value = value[:-1] + "+00:00"
            return datetime.fromisoformat(value)
        except (ValueError, TypeError):
            return None


# 便捷函数
def detect_rate_limit_type(
    headers: Dict[str, str],
    provider_name: str = "unknown",
    current_concurrent: Optional[int] = None,
) -> RateLimitInfo:
    """
    检测速率限制类型（便捷函数）

    Args:
        headers: 429响应头
        provider_name: 提供商名称
        current_concurrent: 当前并发数

    Returns:
        RateLimitInfo对象
    """
    return RateLimitDetector.detect_from_headers(headers, provider_name, current_concurrent)
