from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


# 配置允许额外字段，以支持API的新特性
class BaseModelWithExtras(BaseModel):
    model_config = ConfigDict(extra="allow")


class ClaudeContentBlockText(BaseModelWithExtras):
    type: Literal["text"]
    text: str


class ClaudeContentBlockImage(BaseModelWithExtras):
    type: Literal["image"]
    source: Dict[str, Any]


class ClaudeContentBlockToolUse(BaseModelWithExtras):
    type: Literal["tool_use"]
    id: str
    name: str
    input: Dict[str, Any]


class ClaudeContentBlockToolResult(BaseModelWithExtras):
    type: Literal["tool_result"]
    tool_use_id: str
    content: Union[str, List[Dict[str, Any]], Dict[str, Any]]


class ClaudeContentBlockThinking(BaseModelWithExtras):
    type: Literal["thinking"]
    thinking: str


class ClaudeSystemContent(BaseModelWithExtras):
    type: Literal["text"]
    text: str


class ClaudeMessage(BaseModelWithExtras):
    role: Literal["user", "assistant"]
    # 宽松的内容类型定义 - 接受字符串或任意字典列表
    # 作为转发代理,不应该严格限制内容块类型,以支持API的新特性
    content: Union[str, List[Dict[str, Any]]]


class ClaudeTool(BaseModelWithExtras):
    name: str
    description: Optional[str] = None
    input_schema: Dict[str, Any]


class ClaudeThinkingConfig(BaseModelWithExtras):
    enabled: bool = True


class ClaudeMessagesRequest(BaseModelWithExtras):
    model: str
    max_tokens: int
    messages: List[ClaudeMessage]
    # 宽松的system类型 - 接受字符串、字典列表或任意字典
    system: Optional[Union[str, List[Dict[str, Any]], Dict[str, Any]]] = None
    stop_sequences: Optional[List[str]] = None
    stream: Optional[bool] = False
    temperature: Optional[float] = 1.0
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None
    tools: Optional[List[Dict[str, Any]]] = None  # 改为更宽松的类型
    tool_choice: Optional[Dict[str, Any]] = None
    thinking: Optional[Dict[str, Any]] = None  # 改为更宽松的类型


class ClaudeTokenCountRequest(BaseModelWithExtras):
    model: str
    messages: List[ClaudeMessage]
    # 宽松的类型定义以支持API新特性
    system: Optional[Union[str, List[Dict[str, Any]], Dict[str, Any]]] = None
    tools: Optional[List[Dict[str, Any]]] = None
    thinking: Optional[Dict[str, Any]] = None
    tool_choice: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# 响应模型
# ---------------------------------------------------------------------------


class ClaudeResponseUsage(BaseModelWithExtras):
    """Claude 响应 token 使用量"""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: Optional[int] = None
    cache_read_input_tokens: Optional[int] = None


class ClaudeResponse(BaseModelWithExtras):
    """
    Claude Messages API 响应模型

    对应 POST /v1/messages 端点的响应体。
    """

    id: str
    model: str
    type: Literal["message"] = "message"
    role: Literal["assistant"] = "assistant"
    content: List[Dict[str, Any]]
    stop_reason: Optional[str] = None
    stop_sequence: Optional[str] = None
    usage: Optional[ClaudeResponseUsage] = None
    context_management: Optional[Dict[str, Any]] = None
    container: Optional[Dict[str, Any]] = None
