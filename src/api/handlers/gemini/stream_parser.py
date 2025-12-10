"""
Gemini SSE/JSON 流解析器

Gemini API 的流式响应格式与 Claude/OpenAI 不同:
- 使用 JSON 数组格式 (不是 SSE)
- 每个块是一个完整的 JSON 对象
- 响应以 [ 开始，以 ] 结束，块之间用 , 分隔

参考: https://ai.google.dev/api/generate-content#method:-models.streamgeneratecontent
"""

import json
from typing import Any, Dict, List, Optional


class GeminiStreamParser:
    """
    Gemini 流解析器

    解析 Gemini streamGenerateContent API 的响应流。

    Gemini 流式响应特点:
    - 返回 JSON 数组格式: [{chunk1}, {chunk2}, ...]
    - 每个 chunk 包含 candidates、usageMetadata 等字段
    - finish_reason 可能值: STOP, MAX_TOKENS, SAFETY, RECITATION, OTHER
    """

    # 停止原因
    FINISH_REASON_STOP = "STOP"
    FINISH_REASON_MAX_TOKENS = "MAX_TOKENS"
    FINISH_REASON_SAFETY = "SAFETY"
    FINISH_REASON_RECITATION = "RECITATION"
    FINISH_REASON_OTHER = "OTHER"

    def __init__(self):
        self._buffer = ""
        self._in_array = False
        self._brace_depth = 0

    def reset(self):
        """重置解析器状态"""
        self._buffer = ""
        self._in_array = False
        self._brace_depth = 0

    def parse_chunk(self, chunk: bytes | str) -> List[Dict[str, Any]]:
        """
        解析流式数据块

        Args:
            chunk: 原始数据（bytes 或 str）

        Returns:
            解析后的事件列表
        """
        if isinstance(chunk, bytes):
            text = chunk.decode("utf-8")
        else:
            text = chunk

        events: List[Dict[str, Any]] = []

        for char in text:
            if char == "[" and not self._in_array:
                self._in_array = True
                continue

            if char == "]" and self._in_array and self._brace_depth == 0:
                # 数组结束
                self._in_array = False
                if self._buffer.strip():
                    try:
                        obj = json.loads(self._buffer.strip().rstrip(","))
                        events.append(obj)
                    except json.JSONDecodeError:
                        pass
                self._buffer = ""
                continue

            if self._in_array:
                if char == "{":
                    self._brace_depth += 1
                elif char == "}":
                    self._brace_depth -= 1

                self._buffer += char

                # 当 brace_depth 回到 0 时，说明一个完整的 JSON 对象结束
                if self._brace_depth == 0 and self._buffer.strip():
                    try:
                        obj = json.loads(self._buffer.strip().rstrip(","))
                        events.append(obj)
                        self._buffer = ""
                    except json.JSONDecodeError:
                        # 可能还不完整，继续累积
                        pass

        return events

    def parse_line(self, line: str) -> Optional[Dict[str, Any]]:
        """
        解析单行 JSON 数据

        Args:
            line: JSON 数据行

        Returns:
            解析后的事件字典，如果无法解析返回 None
        """
        if not line or line.strip() in ["[", "]", ","]:
            return None

        try:
            return json.loads(line.strip().rstrip(","))
        except json.JSONDecodeError:
            return None

    def is_done_event(self, event: Dict[str, Any]) -> bool:
        """
        判断是否为结束事件

        Args:
            event: 事件字典

        Returns:
            True 如果是结束事件
        """
        candidates = event.get("candidates", [])
        if candidates:
            for candidate in candidates:
                finish_reason = candidate.get("finishReason")
                if finish_reason in (
                    self.FINISH_REASON_STOP,
                    self.FINISH_REASON_MAX_TOKENS,
                    self.FINISH_REASON_SAFETY,
                    self.FINISH_REASON_RECITATION,
                    self.FINISH_REASON_OTHER,
                ):
                    return True
        return False

    def is_error_event(self, event: Dict[str, Any]) -> bool:
        """
        判断是否为错误事件

        检测多种 Gemini 错误格式:
        1. 顶层 error: {"error": {...}}
        2. chunks 内嵌套 error: {"chunks": [{"error": {...}}]}
        3. candidates 内的错误状态

        Args:
            event: 事件字典

        Returns:
            True 如果是错误事件
        """
        # 顶层 error
        if "error" in event:
            return True

        # chunks 内嵌套 error (某些 Gemini 响应格式)
        chunks = event.get("chunks", [])
        if chunks and isinstance(chunks, list):
            for chunk in chunks:
                if isinstance(chunk, dict) and "error" in chunk:
                    return True

        return False

    def extract_error_info(self, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        从事件中提取错误信息

        Args:
            event: 事件字典

        Returns:
            错误信息字典 {"code": int, "message": str, "status": str}，无错误返回 None
        """
        # 顶层 error
        if "error" in event:
            error = event["error"]
            if isinstance(error, dict):
                return {
                    "code": error.get("code"),
                    "message": error.get("message", str(error)),
                    "status": error.get("status"),
                }
            return {"code": None, "message": str(error), "status": None}

        # chunks 内嵌套 error
        chunks = event.get("chunks", [])
        if chunks and isinstance(chunks, list):
            for chunk in chunks:
                if isinstance(chunk, dict) and "error" in chunk:
                    error = chunk["error"]
                    if isinstance(error, dict):
                        return {
                            "code": error.get("code"),
                            "message": error.get("message", str(error)),
                            "status": error.get("status"),
                        }
                    return {"code": None, "message": str(error), "status": None}

        return None

    def get_finish_reason(self, event: Dict[str, Any]) -> Optional[str]:
        """
        获取结束原因

        Args:
            event: 事件字典

        Returns:
            结束原因字符串
        """
        candidates = event.get("candidates", [])
        if candidates:
            return candidates[0].get("finishReason")
        return None

    def extract_text_delta(self, event: Dict[str, Any]) -> Optional[str]:
        """
        从响应中提取文本内容

        Args:
            event: 事件字典

        Returns:
            文本内容，如果没有文本返回 None
        """
        candidates = event.get("candidates", [])
        if not candidates:
            return None

        content = candidates[0].get("content", {})
        parts = content.get("parts", [])

        text_parts = []
        for part in parts:
            if "text" in part:
                text_parts.append(part["text"])

        return "".join(text_parts) if text_parts else None

    def extract_usage(self, event: Dict[str, Any]) -> Optional[Dict[str, int]]:
        """
        从事件中提取 token 使用量

        这是 Gemini token 提取的单一实现源，其他地方都应该调用此方法。

        Args:
            event: 事件字典（包含 usageMetadata）

        Returns:
            使用量字典，如果没有完整的使用量信息返回 None

        注意:
            - 只有当 totalTokenCount 存在时才提取（确保是完整的 usage 数据）
            - 输出 token = thoughtsTokenCount + candidatesTokenCount
        """
        usage_metadata = event.get("usageMetadata", {})
        if not usage_metadata or "totalTokenCount" not in usage_metadata:
            return None

        # 输出 token = thoughtsTokenCount + candidatesTokenCount
        thoughts_tokens = usage_metadata.get("thoughtsTokenCount", 0)
        candidates_tokens = usage_metadata.get("candidatesTokenCount", 0)
        output_tokens = thoughts_tokens + candidates_tokens

        return {
            "input_tokens": usage_metadata.get("promptTokenCount", 0),
            "output_tokens": output_tokens,
            "total_tokens": usage_metadata.get("totalTokenCount", 0),
            "cached_tokens": usage_metadata.get("cachedContentTokenCount", 0),
        }

    def extract_model_version(self, event: Dict[str, Any]) -> Optional[str]:
        """
        从响应中提取模型版本

        Args:
            event: 事件字典

        Returns:
            模型版本，如果没有返回 None
        """
        return event.get("modelVersion")

    def extract_safety_ratings(self, event: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """
        从响应中提取安全评级

        Args:
            event: 事件字典

        Returns:
            安全评级列表，如果没有返回 None
        """
        candidates = event.get("candidates", [])
        if not candidates:
            return None

        return candidates[0].get("safetyRatings")


__all__ = ["GeminiStreamParser"]
