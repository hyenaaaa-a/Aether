"""响应标准化服务，用于 STANDARD 模式下的响应格式验证和补全"""

from typing import Any, Dict, Optional

from src.core.logger import logger
from src.models.claude import ClaudeResponse
from src.models.openai import OpenAIResponse



class ResponseNormalizer:
    """响应标准化器 - 用于标准模式下验证和补全响应字段"""

    @staticmethod
    def normalize_openai_response(
        response_data: Dict[str, Any],
        request_id: Optional[str] = None,
        *,
        strict: bool = False,
    ) -> Dict[str, Any]:
        """
        æ ‡å‡†åŒ?OpenAI Chat Completions API å“åº”

        Args:
            response_data: åŽŸå§‹å“åº”æ•°æ®
            request_id: è¯·æ±‚IDï¼ˆç”¨äºŽæ—¥å¿—ï¼‰
            strict: ä¸º True æ—¶ï¼ŒéªŒè¯å¤±è´¥å°†æŠ›å‡ºå¼‚å¸¸

        Returns:
            æ ‡å‡†åŒ–åŽçš„å“åº”æ•°æ®ï¼ˆå¤±è´¥æ—¶è¿”å›žåŽŸå§‹æ•°æ®ï¼‰
        """
        if "error" in response_data:
            logger.debug(
                f"[ResponseNormalizer] æ£€æµ‹åˆ°é”™è¯¯å“åº”ï¼Œè·³è¿‡æ ‡å‡†åŒ– | ID:{request_id}"
            )
            return response_data

        try:
            validated = OpenAIResponse.model_validate(response_data)
            normalized = validated.model_dump(mode="json", exclude_none=False)

            logger.debug(f"[ResponseNormalizer] å“åº”æ ‡å‡†åŒ–æˆåŠ?| ID:{request_id}")
            return normalized

        except Exception:
            logger.debug(
                f"[ResponseNormalizer] å“åº”éªŒè¯å¤±è´¥ï¼Œé€ä¼ åŽŸå§‹æ•°æ® | ID:{request_id}"
            )
            if strict:
                raise
            return response_data

    @staticmethod
    def normalize_claude_response(
        response_data: Dict[str, Any], request_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        标准化 Claude API 响应

        Args:
            response_data: 原始响应数据
            request_id: 请求ID（用于日志）

        Returns:
            标准化后的响应数据（失败时返回原始数据）
        """
        if "error" in response_data:
            logger.debug(f"[ResponseNormalizer] 检测到错误响应，跳过标准化 | ID:{request_id}")
            return response_data

        try:
            validated = ClaudeResponse.model_validate(response_data)
            normalized = validated.model_dump(mode="json", exclude_none=False)

            logger.debug(f"[ResponseNormalizer] 响应标准化成功 | ID:{request_id}")
            return normalized

        except Exception as e:
            logger.debug(f"[ResponseNormalizer] 响应验证失败，透传原始数据 | ID:{request_id}")
            return response_data

    @staticmethod
    def should_normalize(response_data: Dict[str, Any]) -> bool:
        """
        判断是否需要进行标准化

        Args:
            response_data: 响应数据

        Returns:
            是否需要标准化
        """
        # 错误响应不需要标准化
        if "error" in response_data:
            return False

        # 已经包含新字段的响应不需要再次标准化
        if "context_management" in response_data and "container" in response_data:
            return False

        return True
