"""
OpenAI API 数据模型定义
"""

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict


# 配置允许额外字段，以支持 API 的新特性
class BaseModelWithExtras(BaseModel):
    model_config = ConfigDict(extra="allow")


class OpenAIMessage(BaseModelWithExtras):
    """OpenAI消息模型"""

    role: str
    content: Optional[Union[str, List[Dict[str, Any]]]] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None


class OpenAIFunction(BaseModelWithExtras):
    """OpenAI函数定义"""

    name: str
    description: Optional[str] = None
    parameters: Dict[str, Any]


class OpenAITool(BaseModelWithExtras):
    """OpenAI工具定义"""

    type: str = "function"
    function: OpenAIFunction


class OpenAIRequest(BaseModelWithExtras):
    """OpenAI请求模型"""

    model: str
    messages: List[OpenAIMessage]
    max_tokens: Optional[int] = None
    temperature: Optional[float] = 1.0
    top_p: Optional[float] = None
    stream: Optional[bool] = False
    stop: Optional[Union[str, List[str]]] = None
    tools: Optional[List[OpenAITool]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None
    n: Optional[int] = None
    seed: Optional[int] = None
    response_format: Optional[Dict[str, Any]] = None
    logit_bias: Optional[Dict[str, float]] = None
    logprobs: Optional[bool] = None
    top_logprobs: Optional[int] = None
    user: Optional[str] = None


class ResponsesInputMessage(BaseModelWithExtras):
    """Responses API 输入消息"""

    type: str = "message"
    role: str
    content: List[Dict[str, Any]]


class ResponsesReasoningConfig(BaseModelWithExtras):
    """Responses API 推理配置"""

    effort: str = "high"  # low, medium, high
    summary: str = "auto"  # auto, off


class ResponsesRequest(BaseModelWithExtras):
    """OpenAI Responses API 请求模型（用于 Claude Code 等客户端）"""

    model: str
    instructions: Optional[str] = None
    input: List[ResponsesInputMessage]
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = "auto"
    parallel_tool_calls: Optional[bool] = False
    reasoning: Optional[ResponsesReasoningConfig] = None
    store: Optional[bool] = False
    stream: Optional[bool] = True
    include: Optional[List[str]] = None
    prompt_cache_key: Optional[str] = None
    # 其他参数
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    stop: Optional[Union[str, List[str]]] = None


class OpenAIUsage(BaseModelWithExtras):
    """OpenAI使用统计"""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class OpenAIChoice(BaseModelWithExtras):
    """OpenAI选择结果"""

    index: int
    message: OpenAIMessage
    finish_reason: Optional[str] = None
    logprobs: Optional[Dict[str, Any]] = None


class OpenAIResponse(BaseModelWithExtras):
    """OpenAI响应模型"""

    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[OpenAIChoice]
    usage: Optional[OpenAIUsage] = None
    system_fingerprint: Optional[str] = None


class OpenAIStreamDelta(BaseModelWithExtras):
    """OpenAI流式响应增量"""

    role: Optional[str] = None
    content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None


class OpenAIStreamChoice(BaseModelWithExtras):
    """OpenAI流式响应选择"""

    index: int
    delta: OpenAIStreamDelta
    finish_reason: Optional[str] = None
    logprobs: Optional[Dict[str, Any]] = None


class OpenAIStreamResponse(BaseModelWithExtras):
    """OpenAI流式响应模型"""

    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: List[OpenAIStreamChoice]
    system_fingerprint: Optional[str] = None
