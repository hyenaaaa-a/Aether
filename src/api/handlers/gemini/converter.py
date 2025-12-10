"""
Gemini 格式转换器

提供 Gemini 与其他 API 格式（Claude、OpenAI）之间的转换
"""

from typing import Any, Dict, List, Optional


class ClaudeToGeminiConverter:
    """
    Claude -> Gemini 请求转换器

    将 Claude Messages API 格式转换为 Gemini generateContent 格式
    """

    def convert_request(self, claude_request: Dict[str, Any]) -> Dict[str, Any]:
        """
        将 Claude 请求转换为 Gemini 请求

        Args:
            claude_request: Claude 格式的请求字典

        Returns:
            Gemini 格式的请求字典
        """
        gemini_request: Dict[str, Any] = {
            "contents": self._convert_messages(claude_request.get("messages", [])),
        }

        # 转换 system prompt
        system = claude_request.get("system")
        if system:
            gemini_request["system_instruction"] = self._convert_system(system)

        # 转换生成配置
        generation_config = self._build_generation_config(claude_request)
        if generation_config:
            gemini_request["generation_config"] = generation_config

        # 转换工具
        tools = claude_request.get("tools")
        if tools:
            gemini_request["tools"] = self._convert_tools(tools)

        return gemini_request

    def _convert_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """转换消息列表"""
        contents = []
        for msg in messages:
            role = msg.get("role", "user")
            # Gemini 使用 "model" 而不是 "assistant"
            gemini_role = "model" if role == "assistant" else "user"

            content = msg.get("content", "")
            parts = self._convert_content_to_parts(content)

            contents.append(
                {
                    "role": gemini_role,
                    "parts": parts,
                }
            )
        return contents

    def _convert_content_to_parts(self, content: Any) -> List[Dict[str, Any]]:
        """将 Claude 内容转换为 Gemini parts"""
        if isinstance(content, str):
            return [{"text": content}]

        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, str):
                    parts.append({"text": block})
                elif isinstance(block, dict):
                    block_type = block.get("type")
                    if block_type == "text":
                        parts.append({"text": block.get("text", "")})
                    elif block_type == "image":
                        # 转换图片
                        source = block.get("source", {})
                        if source.get("type") == "base64":
                            parts.append(
                                {
                                    "inline_data": {
                                        "mime_type": source.get("media_type", "image/png"),
                                        "data": source.get("data", ""),
                                    }
                                }
                            )
                    elif block_type == "tool_use":
                        # 转换工具调用
                        parts.append(
                            {
                                "function_call": {
                                    "name": block.get("name", ""),
                                    "args": block.get("input", {}),
                                }
                            }
                        )
                    elif block_type == "tool_result":
                        # 转换工具结果
                        parts.append(
                            {
                                "function_response": {
                                    "name": block.get("tool_use_id", ""),
                                    "response": {"result": block.get("content", "")},
                                }
                            }
                        )
            return parts

        return [{"text": str(content)}]

    def _convert_system(self, system: Any) -> Dict[str, Any]:
        """转换 system prompt"""
        if isinstance(system, str):
            return {"parts": [{"text": system}]}

        if isinstance(system, list):
            parts = []
            for item in system:
                if isinstance(item, str):
                    parts.append({"text": item})
                elif isinstance(item, dict) and item.get("type") == "text":
                    parts.append({"text": item.get("text", "")})
            return {"parts": parts}

        return {"parts": [{"text": str(system)}]}

    def _build_generation_config(self, claude_request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """构建生成配置"""
        config: Dict[str, Any] = {}

        if "max_tokens" in claude_request:
            config["max_output_tokens"] = claude_request["max_tokens"]
        if "temperature" in claude_request:
            config["temperature"] = claude_request["temperature"]
        if "top_p" in claude_request:
            config["top_p"] = claude_request["top_p"]
        if "top_k" in claude_request:
            config["top_k"] = claude_request["top_k"]
        if "stop_sequences" in claude_request:
            config["stop_sequences"] = claude_request["stop_sequences"]

        return config if config else None

    def _convert_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """转换工具定义"""
        function_declarations = []
        for tool in tools:
            func_decl = {
                "name": tool.get("name", ""),
            }
            if "description" in tool:
                func_decl["description"] = tool["description"]
            if "input_schema" in tool:
                func_decl["parameters"] = tool["input_schema"]
            function_declarations.append(func_decl)

        return [{"function_declarations": function_declarations}]


class GeminiToClaudeConverter:
    """
    Gemini -> Claude 响应转换器

    将 Gemini generateContent 响应转换为 Claude Messages API 格式
    """

    def convert_response(self, gemini_response: Dict[str, Any]) -> Dict[str, Any]:
        """
        将 Gemini 响应转换为 Claude 响应

        Args:
            gemini_response: Gemini 格式的响应字典

        Returns:
            Claude 格式的响应字典
        """
        candidates = gemini_response.get("candidates", [])
        if not candidates:
            return self._create_empty_response()

        candidate = candidates[0]
        content = candidate.get("content", {})
        parts = content.get("parts", [])

        # 转换内容块
        claude_content = self._convert_parts_to_content(parts)

        # 转换使用量
        usage = self._convert_usage(gemini_response.get("usageMetadata", {}))

        # 转换停止原因
        stop_reason = self._convert_finish_reason(candidate.get("finishReason"))

        return {
            "id": f"msg_{gemini_response.get('modelVersion', 'gemini')}",
            "type": "message",
            "role": "assistant",
            "content": claude_content,
            "model": gemini_response.get("modelVersion", "gemini"),
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": usage,
        }

    def _convert_parts_to_content(self, parts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """将 Gemini parts 转换为 Claude content blocks"""
        content = []
        for part in parts:
            if "text" in part:
                content.append(
                    {
                        "type": "text",
                        "text": part["text"],
                    }
                )
            elif "functionCall" in part:
                func_call = part["functionCall"]
                content.append(
                    {
                        "type": "tool_use",
                        "id": f"toolu_{func_call.get('name', '')}",
                        "name": func_call.get("name", ""),
                        "input": func_call.get("args", {}),
                    }
                )
        return content

    def _convert_usage(self, usage_metadata: Dict[str, Any]) -> Dict[str, int]:
        """转换使用量信息"""
        return {
            "input_tokens": usage_metadata.get("promptTokenCount", 0),
            "output_tokens": usage_metadata.get("candidatesTokenCount", 0),
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": usage_metadata.get("cachedContentTokenCount", 0),
        }

    def _convert_finish_reason(self, finish_reason: Optional[str]) -> Optional[str]:
        """转换停止原因"""
        mapping = {
            "STOP": "end_turn",
            "MAX_TOKENS": "max_tokens",
            "SAFETY": "content_filtered",
            "RECITATION": "content_filtered",
            "OTHER": "stop_sequence",
        }
        return mapping.get(finish_reason, "end_turn")

    def _create_empty_response(self) -> Dict[str, Any]:
        """创建空响应"""
        return {
            "id": "msg_empty",
            "type": "message",
            "role": "assistant",
            "content": [],
            "model": "gemini",
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {
                "input_tokens": 0,
                "output_tokens": 0,
            },
        }


class OpenAIToGeminiConverter:
    """
    OpenAI -> Gemini 请求转换器

    将 OpenAI Chat Completions API 格式转换为 Gemini generateContent 格式
    """

    def convert_request(self, openai_request: Dict[str, Any]) -> Dict[str, Any]:
        """
        将 OpenAI 请求转换为 Gemini 请求

        Args:
            openai_request: OpenAI 格式的请求字典

        Returns:
            Gemini 格式的请求字典
        """
        messages = openai_request.get("messages", [])

        # 分离 system 消息和其他消息
        system_messages = []
        other_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                system_messages.append(msg)
            else:
                other_messages.append(msg)

        gemini_request: Dict[str, Any] = {
            "contents": self._convert_messages(other_messages),
        }

        # 转换 system messages
        if system_messages:
            system_text = "\n".join(msg.get("content", "") for msg in system_messages)
            gemini_request["system_instruction"] = {"parts": [{"text": system_text}]}

        # 转换生成配置
        generation_config = self._build_generation_config(openai_request)
        if generation_config:
            gemini_request["generation_config"] = generation_config

        # 转换工具
        tools = openai_request.get("tools")
        if tools:
            gemini_request["tools"] = self._convert_tools(tools)

        return gemini_request

    def _convert_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """转换消息列表"""
        contents = []
        for msg in messages:
            role = msg.get("role", "user")
            gemini_role = "model" if role == "assistant" else "user"

            content = msg.get("content", "")
            parts = self._convert_content_to_parts(content)

            # 处理工具调用
            tool_calls = msg.get("tool_calls", [])
            for tc in tool_calls:
                if tc.get("type") == "function":
                    func = tc.get("function", {})
                    import json

                    try:
                        args = json.loads(func.get("arguments", "{}"))
                    except json.JSONDecodeError:
                        args = {}
                    parts.append(
                        {
                            "function_call": {
                                "name": func.get("name", ""),
                                "args": args,
                            }
                        }
                    )

            if parts:
                contents.append(
                    {
                        "role": gemini_role,
                        "parts": parts,
                    }
                )
        return contents

    def _convert_content_to_parts(self, content: Any) -> List[Dict[str, Any]]:
        """将 OpenAI 内容转换为 Gemini parts"""
        if content is None:
            return []

        if isinstance(content, str):
            return [{"text": content}]

        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append({"text": item})
                elif isinstance(item, dict):
                    item_type = item.get("type")
                    if item_type == "text":
                        parts.append({"text": item.get("text", "")})
                    elif item_type == "image_url":
                        # OpenAI 图片 URL 格式
                        image_url = item.get("image_url", {})
                        url = image_url.get("url", "")
                        if url.startswith("data:"):
                            # base64 数据 URL
                            # 格式: data:image/png;base64,xxxxx
                            try:
                                header, data = url.split(",", 1)
                                mime_type = header.split(":")[1].split(";")[0]
                                parts.append(
                                    {
                                        "inline_data": {
                                            "mime_type": mime_type,
                                            "data": data,
                                        }
                                    }
                                )
                            except (ValueError, IndexError):
                                pass
            return parts

        return [{"text": str(content)}]

    def _build_generation_config(self, openai_request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """构建生成配置"""
        config: Dict[str, Any] = {}

        if "max_tokens" in openai_request:
            config["max_output_tokens"] = openai_request["max_tokens"]
        if "temperature" in openai_request:
            config["temperature"] = openai_request["temperature"]
        if "top_p" in openai_request:
            config["top_p"] = openai_request["top_p"]
        if "stop" in openai_request:
            stop = openai_request["stop"]
            if isinstance(stop, str):
                config["stop_sequences"] = [stop]
            elif isinstance(stop, list):
                config["stop_sequences"] = stop
        if "n" in openai_request:
            config["candidate_count"] = openai_request["n"]

        return config if config else None

    def _convert_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """转换工具定义"""
        function_declarations = []
        for tool in tools:
            if tool.get("type") == "function":
                func = tool.get("function", {})
                func_decl = {
                    "name": func.get("name", ""),
                }
                if "description" in func:
                    func_decl["description"] = func["description"]
                if "parameters" in func:
                    func_decl["parameters"] = func["parameters"]
                function_declarations.append(func_decl)

        return [{"function_declarations": function_declarations}]


class GeminiToOpenAIConverter:
    """
    Gemini -> OpenAI 响应转换器

    将 Gemini generateContent 响应转换为 OpenAI Chat Completions API 格式
    """

    def convert_response(self, gemini_response: Dict[str, Any]) -> Dict[str, Any]:
        """
        将 Gemini 响应转换为 OpenAI 响应

        Args:
            gemini_response: Gemini 格式的响应字典

        Returns:
            OpenAI 格式的响应字典
        """
        import time

        candidates = gemini_response.get("candidates", [])
        choices = []

        for i, candidate in enumerate(candidates):
            content = candidate.get("content", {})
            parts = content.get("parts", [])

            # 提取文本内容
            text_parts = []
            tool_calls = []

            for part in parts:
                if "text" in part:
                    text_parts.append(part["text"])
                elif "functionCall" in part:
                    func_call = part["functionCall"]
                    import json

                    tool_calls.append(
                        {
                            "id": f"call_{func_call.get('name', '')}_{i}",
                            "type": "function",
                            "function": {
                                "name": func_call.get("name", ""),
                                "arguments": json.dumps(func_call.get("args", {})),
                            },
                        }
                    )

            message: Dict[str, Any] = {
                "role": "assistant",
                "content": "".join(text_parts) if text_parts else None,
            }

            if tool_calls:
                message["tool_calls"] = tool_calls

            finish_reason = self._convert_finish_reason(candidate.get("finishReason"))

            choices.append(
                {
                    "index": i,
                    "message": message,
                    "finish_reason": finish_reason,
                }
            )

        # 转换使用量
        usage = self._convert_usage(gemini_response.get("usageMetadata", {}))

        return {
            "id": f"chatcmpl-{gemini_response.get('modelVersion', 'gemini')}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": gemini_response.get("modelVersion", "gemini"),
            "choices": choices,
            "usage": usage,
        }

    def _convert_usage(self, usage_metadata: Dict[str, Any]) -> Dict[str, int]:
        """转换使用量信息"""
        prompt_tokens = usage_metadata.get("promptTokenCount", 0)
        completion_tokens = usage_metadata.get("candidatesTokenCount", 0)
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }

    def _convert_finish_reason(self, finish_reason: Optional[str]) -> Optional[str]:
        """转换停止原因"""
        mapping = {
            "STOP": "stop",
            "MAX_TOKENS": "length",
            "SAFETY": "content_filter",
            "RECITATION": "content_filter",
            "OTHER": "stop",
        }
        return mapping.get(finish_reason, "stop")


__all__ = [
    "ClaudeToGeminiConverter",
    "GeminiToClaudeConverter",
    "OpenAIToGeminiConverter",
    "GeminiToOpenAIConverter",
]
