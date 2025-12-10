"""
格式转换器注册表

自动管理不同 API 格式之间的转换器，支持：
- 请求转换：客户端格式 → Provider 格式
- 响应转换：Provider 格式 → 客户端格式

使用方法：
1. 实现 Converter 类（需要有 convert_request 和/或 convert_response 方法）
2. 调用 registry.register() 注册转换器
3. 在 Handler 中调用 registry.convert_request/convert_response

示例：
    from src.api.handlers.base.format_converter_registry import converter_registry

    # 注册转换器
    converter_registry.register("CLAUDE", "GEMINI", ClaudeToGeminiConverter())
    converter_registry.register("GEMINI", "CLAUDE", GeminiToClaudeConverter())

    # 使用转换器
    gemini_request = converter_registry.convert_request(claude_request, "CLAUDE", "GEMINI")
    claude_response = converter_registry.convert_response(gemini_response, "GEMINI", "CLAUDE")
"""

from typing import Any, Dict, Optional, Protocol, Tuple

from src.core.logger import logger



class RequestConverter(Protocol):
    """请求转换器协议"""

    def convert_request(self, request: Dict[str, Any]) -> Dict[str, Any]: ...


class ResponseConverter(Protocol):
    """响应转换器协议"""

    def convert_response(self, response: Dict[str, Any]) -> Dict[str, Any]: ...


class StreamChunkConverter(Protocol):
    """流式响应块转换器协议"""

    def convert_stream_chunk(self, chunk: Dict[str, Any]) -> Dict[str, Any]: ...


class FormatConverterRegistry:
    """
    格式转换器注册表

    管理不同 API 格式之间的双向转换器
    """

    def __init__(self):
        # key: (source_format, target_format), value: converter instance
        self._converters: Dict[Tuple[str, str], Any] = {}

    def register(
        self,
        source_format: str,
        target_format: str,
        converter: Any,
    ) -> None:
        """
        注册格式转换器

        Args:
            source_format: 源格式（如 "CLAUDE", "OPENAI", "GEMINI"）
            target_format: 目标格式
            converter: 转换器实例（需要有 convert_request/convert_response 方法）
        """
        key = (source_format.upper(), target_format.upper())
        self._converters[key] = converter
        logger.info(f"[ConverterRegistry] 注册转换器: {source_format} -> {target_format}")

    def get_converter(
        self,
        source_format: str,
        target_format: str,
    ) -> Optional[Any]:
        """
        获取转换器

        Args:
            source_format: 源格式
            target_format: 目标格式

        Returns:
            转换器实例，如果不存在返回 None
        """
        key = (source_format.upper(), target_format.upper())
        return self._converters.get(key)

    def has_converter(
        self,
        source_format: str,
        target_format: str,
    ) -> bool:
        """检查是否存在转换器"""
        key = (source_format.upper(), target_format.upper())
        return key in self._converters

    def convert_request(
        self,
        request: Dict[str, Any],
        source_format: str,
        target_format: str,
    ) -> Dict[str, Any]:
        """
        转换请求

        Args:
            request: 原始请求字典
            source_format: 源格式（客户端格式）
            target_format: 目标格式（Provider 格式）

        Returns:
            转换后的请求字典，如果无需转换或没有转换器则返回原始请求
        """
        # 同格式无需转换
        if source_format.upper() == target_format.upper():
            return request

        converter = self.get_converter(source_format, target_format)
        if converter is None:
            logger.warning(f"[ConverterRegistry] 未找到请求转换器: {source_format} -> {target_format}，返回原始请求")
            return request

        if not hasattr(converter, "convert_request"):
            logger.warning(f"[ConverterRegistry] 转换器缺少 convert_request 方法: {source_format} -> {target_format}")
            return request

        try:
            converted = converter.convert_request(request)
            logger.debug(f"[ConverterRegistry] 请求转换成功: {source_format} -> {target_format}")
            return converted
        except Exception as e:
            logger.error(f"[ConverterRegistry] 请求转换失败: {source_format} -> {target_format}: {e}")
            return request

    def convert_response(
        self,
        response: Dict[str, Any],
        source_format: str,
        target_format: str,
    ) -> Dict[str, Any]:
        """
        转换响应

        Args:
            response: 原始响应字典
            source_format: 源格式（Provider 格式）
            target_format: 目标格式（客户端格式）

        Returns:
            转换后的响应字典，如果无需转换或没有转换器则返回原始响应
        """
        # 同格式无需转换
        if source_format.upper() == target_format.upper():
            return response

        converter = self.get_converter(source_format, target_format)
        if converter is None:
            logger.warning(f"[ConverterRegistry] 未找到响应转换器: {source_format} -> {target_format}，返回原始响应")
            return response

        if not hasattr(converter, "convert_response"):
            logger.warning(f"[ConverterRegistry] 转换器缺少 convert_response 方法: {source_format} -> {target_format}")
            return response

        try:
            converted = converter.convert_response(response)
            logger.debug(f"[ConverterRegistry] 响应转换成功: {source_format} -> {target_format}")
            return converted
        except Exception as e:
            logger.error(f"[ConverterRegistry] 响应转换失败: {source_format} -> {target_format}: {e}")
            return response

    def convert_stream_chunk(
        self,
        chunk: Dict[str, Any],
        source_format: str,
        target_format: str,
    ) -> Dict[str, Any]:
        """
        转换流式响应块

        Args:
            chunk: 原始流式响应块
            source_format: 源格式（Provider 格式）
            target_format: 目标格式（客户端格式）

        Returns:
            转换后的流式响应块
        """
        # 同格式无需转换
        if source_format.upper() == target_format.upper():
            return chunk

        converter = self.get_converter(source_format, target_format)
        if converter is None:
            return chunk

        # 优先使用专门的流式转换方法
        if hasattr(converter, "convert_stream_chunk"):
            try:
                return converter.convert_stream_chunk(chunk)
            except Exception as e:
                logger.error(f"[ConverterRegistry] 流式块转换失败: {source_format} -> {target_format}: {e}")
                return chunk

        # 降级到普通响应转换
        if hasattr(converter, "convert_response"):
            try:
                return converter.convert_response(chunk)
            except Exception:
                return chunk

        return chunk

    def list_converters(self) -> list[Tuple[str, str]]:
        """列出所有已注册的转换器"""
        return list(self._converters.keys())


# 全局单例
converter_registry = FormatConverterRegistry()


def register_all_converters():
    """
    注册所有内置的格式转换器

    在应用启动时调用此函数
    """
    # Claude <-> OpenAI
    try:
        from src.api.handlers.claude.converter import OpenAIToClaudeConverter
        from src.api.handlers.openai.converter import ClaudeToOpenAIConverter

        converter_registry.register("OPENAI", "CLAUDE", OpenAIToClaudeConverter())
        converter_registry.register("CLAUDE", "OPENAI", ClaudeToOpenAIConverter())
    except ImportError as e:
        logger.warning(f"[ConverterRegistry] 无法加载 Claude/OpenAI 转换器: {e}")

    # Claude <-> Gemini
    try:
        from src.api.handlers.gemini.converter import (
            ClaudeToGeminiConverter,
            GeminiToClaudeConverter,
        )

        converter_registry.register("CLAUDE", "GEMINI", ClaudeToGeminiConverter())
        converter_registry.register("GEMINI", "CLAUDE", GeminiToClaudeConverter())
    except ImportError as e:
        logger.warning(f"[ConverterRegistry] 无法加载 Claude/Gemini 转换器: {e}")

    # OpenAI <-> Gemini
    try:
        from src.api.handlers.gemini.converter import (
            GeminiToOpenAIConverter,
            OpenAIToGeminiConverter,
        )

        converter_registry.register("OPENAI", "GEMINI", OpenAIToGeminiConverter())
        converter_registry.register("GEMINI", "OPENAI", GeminiToOpenAIConverter())
    except ImportError as e:
        logger.warning(f"[ConverterRegistry] 无法加载 OpenAI/Gemini 转换器: {e}")

    logger.info(f"[ConverterRegistry] 已注册 {len(converter_registry.list_converters())} 个格式转换器")


__all__ = [
    "FormatConverterRegistry",
    "converter_registry",
    "register_all_converters",
]
