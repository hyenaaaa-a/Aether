"""
Google Gemini API 请求/响应模型

支持 Gemini 3 Pro 及之前版本的 API 格式
参考文档: https://ai.google.dev/gemini-api/docs/gemini-3
"""

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class BaseModelWithExtras(BaseModel):
    """允许额外字段的基础模型"""

    model_config = ConfigDict(extra="allow")


# ---------------------------------------------------------------------------
# 内容块定义
# ---------------------------------------------------------------------------


class GeminiTextPart(BaseModelWithExtras):
    """文本内容块"""

    text: str
    thought_signature: Optional[str] = Field(
        default=None,
        alias="thoughtSignature",
        description="Gemini 3 思维签名，用于维护多轮对话中的推理上下文",
    )


class GeminiInlineData(BaseModelWithExtras):
    """内联数据（图片等）"""

    mime_type: str = Field(alias="mimeType")
    data: str  # base64 encoded


class GeminiMediaResolution(BaseModelWithExtras):
    """
    媒体分辨率配置 (Gemini 3 新增)

    控制图片/视频的处理分辨率:
    - media_resolution_low: 图片 280 tokens, 视频 70 tokens/帧
    - media_resolution_medium: 图片 560 tokens, 视频 70 tokens/帧
    - media_resolution_high: 图片 1120 tokens, 视频 280 tokens/帧
    """

    level: Literal["media_resolution_low", "media_resolution_medium", "media_resolution_high"]


class GeminiFileData(BaseModelWithExtras):
    """文件引用"""

    mime_type: Optional[str] = Field(default=None, alias="mimeType")
    file_uri: str = Field(alias="fileUri")


class GeminiFunctionCall(BaseModelWithExtras):
    """函数调用"""

    name: str
    args: Dict[str, Any]


class GeminiFunctionResponse(BaseModelWithExtras):
    """函数响应"""

    name: str
    response: Dict[str, Any]


class GeminiPart(BaseModelWithExtras):
    """
    Gemini 内容部分 - 支持多种类型

    可以是以下类型之一:
    - text: 文本内容
    - inline_data: 内联数据（图片等）
    - file_data: 文件引用
    - function_call: 函数调用
    - function_response: 函数响应

    Gemini 3 新增:
    - thought_signature: 思维签名，用于维护推理上下文
    - media_resolution: 媒体分辨率配置
    """

    text: Optional[str] = None
    inline_data: Optional[GeminiInlineData] = Field(default=None, alias="inlineData")
    file_data: Optional[GeminiFileData] = Field(default=None, alias="fileData")
    function_call: Optional[GeminiFunctionCall] = Field(default=None, alias="functionCall")
    function_response: Optional[GeminiFunctionResponse] = Field(
        default=None, alias="functionResponse"
    )
    # Gemini 3 新增
    thought_signature: Optional[str] = Field(
        default=None,
        alias="thoughtSignature",
        description="思维签名，用于函数调用和图片生成的上下文保持",
    )
    media_resolution: Optional[GeminiMediaResolution] = Field(
        default=None, alias="mediaResolution", description="媒体分辨率配置"
    )


class GeminiContent(BaseModelWithExtras):
    """
    Gemini 消息内容

    对应 Gemini API 的 Content 对象
    """

    role: Optional[Literal["user", "model"]] = None
    parts: List[Union[GeminiPart, Dict[str, Any]]]


# ---------------------------------------------------------------------------
# 配置定义
# ---------------------------------------------------------------------------


class GeminiImageConfig(BaseModelWithExtras):
    """
    图片生成配置 (Gemini 3 Pro Image)

    用于 gemini-3-pro-image-preview 模型
    """

    aspect_ratio: Optional[str] = Field(
        default=None, alias="aspectRatio", description="图片宽高比，如 '16:9', '1:1', '4:3'"
    )
    image_size: Optional[Literal["2K", "4K"]] = Field(
        default=None, alias="imageSize", description="图片尺寸: 2K 或 4K"
    )


class GeminiGenerationConfig(BaseModelWithExtras):
    """
    生成配置

    Gemini 3 新增:
    - thinking_level: 思考深度 (low/medium/high)
    - response_json_schema: 结构化输出的 JSON Schema
    - image_config: 图片生成配置
    """

    temperature: Optional[float] = Field(
        default=None, description="采样温度，Gemini 3 建议保持默认值 1.0"
    )
    top_p: Optional[float] = Field(default=None, alias="topP")
    top_k: Optional[int] = Field(default=None, alias="topK")
    max_output_tokens: Optional[int] = Field(default=None, alias="maxOutputTokens")
    stop_sequences: Optional[List[str]] = Field(default=None, alias="stopSequences")
    candidate_count: Optional[int] = Field(default=None, alias="candidateCount")
    response_mime_type: Optional[str] = Field(default=None, alias="responseMimeType")
    response_schema: Optional[Dict[str, Any]] = Field(default=None, alias="responseSchema")
    # Gemini 3 新增
    response_json_schema: Optional[Dict[str, Any]] = Field(
        default=None, alias="responseJsonSchema", description="结构化输出的 JSON Schema"
    )
    thinking_level: Optional[Literal["low", "medium", "high"]] = Field(
        default=None,
        alias="thinkingLevel",
        description="Gemini 3 思考深度: low(快速), medium(平衡), high(深度推理，默认)",
    )
    image_config: Optional[GeminiImageConfig] = Field(
        default=None, alias="imageConfig", description="图片生成配置"
    )


class GeminiSafetySettings(BaseModelWithExtras):
    """安全设置"""

    category: str
    threshold: str


class GeminiFunctionDeclaration(BaseModelWithExtras):
    """函数声明"""

    name: str
    description: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None


class GeminiGoogleSearchTool(BaseModelWithExtras):
    """Google Search 工具 (Gemini 3)"""

    pass  # 空对象表示启用


class GeminiUrlContextTool(BaseModelWithExtras):
    """URL Context 工具 (Gemini 3)"""

    pass  # 空对象表示启用


class GeminiCodeExecutionTool(BaseModelWithExtras):
    """代码执行工具"""

    pass  # 空对象表示启用


class GeminiTool(BaseModelWithExtras):
    """
    工具定义

    支持的工具类型:
    - function_declarations: 自定义函数
    - code_execution: 代码执行
    - google_search: Google 搜索 (Gemini 3)
    - url_context: URL 上下文 (Gemini 3)
    """

    function_declarations: Optional[List[GeminiFunctionDeclaration]] = Field(
        default=None, alias="functionDeclarations"
    )
    code_execution: Optional[Dict[str, Any]] = Field(default=None, alias="codeExecution")
    # Gemini 3 内置工具
    google_search: Optional[Dict[str, Any]] = Field(
        default=None, alias="googleSearch", description="启用 Google 搜索工具"
    )
    url_context: Optional[Dict[str, Any]] = Field(
        default=None, alias="urlContext", description="启用 URL 上下文工具"
    )


class GeminiToolConfig(BaseModelWithExtras):
    """工具配置"""

    function_calling_config: Optional[Dict[str, Any]] = Field(
        default=None, alias="functionCallingConfig"
    )


class GeminiSystemInstruction(BaseModelWithExtras):
    """系统指令"""

    parts: List[Union[GeminiPart, Dict[str, Any]]]


# ---------------------------------------------------------------------------
# 请求模型
# ---------------------------------------------------------------------------


class GeminiGenerateContentRequest(BaseModelWithExtras):
    """
    Gemini generateContent 请求模型

    对应 POST /v1beta/models/{model}:generateContent 端点
    """

    contents: List[GeminiContent]
    system_instruction: Optional[GeminiSystemInstruction] = Field(
        default=None, alias="systemInstruction"
    )
    tools: Optional[List[GeminiTool]] = None
    tool_config: Optional[GeminiToolConfig] = Field(default=None, alias="toolConfig")
    safety_settings: Optional[List[GeminiSafetySettings]] = Field(
        default=None, alias="safetySettings"
    )
    generation_config: Optional[GeminiGenerationConfig] = Field(
        default=None, alias="generationConfig"
    )


class GeminiStreamGenerateContentRequest(BaseModelWithExtras):
    """
    Gemini streamGenerateContent 请求模型

    对应 POST /v1beta/models/{model}:streamGenerateContent 端点
    与 generateContent 相同，但返回流式响应
    """

    contents: List[GeminiContent]
    system_instruction: Optional[GeminiSystemInstruction] = Field(
        default=None, alias="systemInstruction"
    )
    tools: Optional[List[GeminiTool]] = None
    tool_config: Optional[GeminiToolConfig] = Field(default=None, alias="toolConfig")
    safety_settings: Optional[List[GeminiSafetySettings]] = Field(
        default=None, alias="safetySettings"
    )
    generation_config: Optional[GeminiGenerationConfig] = Field(
        default=None, alias="generationConfig"
    )


# ---------------------------------------------------------------------------
# 统一请求模型（用于内部处理）
# ---------------------------------------------------------------------------


class GeminiRequest(BaseModelWithExtras):
    """
    Gemini 统一请求模型

    内部使用，统一处理 generateContent 和 streamGenerateContent

    注意: Gemini API 通过 URL 端点区分流式/非流式请求:
    - generateContent - 非流式
    - streamGenerateContent - 流式
    请求体中不应包含 stream 字段
    """

    model: Optional[str] = Field(default=None, description="模型名称，从 URL 路径提取（内部使用）")
    contents: List[GeminiContent]
    system_instruction: Optional[GeminiSystemInstruction] = Field(
        default=None, alias="systemInstruction"
    )
    tools: Optional[List[GeminiTool]] = None
    tool_config: Optional[GeminiToolConfig] = Field(default=None, alias="toolConfig")
    safety_settings: Optional[List[GeminiSafetySettings]] = Field(
        default=None, alias="safetySettings"
    )
    generation_config: Optional[GeminiGenerationConfig] = Field(
        default=None, alias="generationConfig"
    )


# ---------------------------------------------------------------------------
# 响应模型
# ---------------------------------------------------------------------------


class GeminiUsageMetadata(BaseModelWithExtras):
    """Token 使用量"""

    prompt_token_count: int = Field(default=0, alias="promptTokenCount")
    candidates_token_count: int = Field(default=0, alias="candidatesTokenCount")
    total_token_count: int = Field(default=0, alias="totalTokenCount")
    cached_content_token_count: Optional[int] = Field(default=None, alias="cachedContentTokenCount")


class GeminiSafetyRating(BaseModelWithExtras):
    """安全评级"""

    category: str
    probability: str
    blocked: Optional[bool] = None


class GeminiCitationSource(BaseModelWithExtras):
    """引用来源"""

    start_index: Optional[int] = Field(default=None, alias="startIndex")
    end_index: Optional[int] = Field(default=None, alias="endIndex")
    uri: Optional[str] = None
    license: Optional[str] = None


class GeminiCitationMetadata(BaseModelWithExtras):
    """引用元数据"""

    citation_sources: Optional[List[GeminiCitationSource]] = Field(
        default=None, alias="citationSources"
    )


class GeminiGroundingMetadata(BaseModelWithExtras):
    """
    Grounding 元数据 (Gemini 3)

    当使用 Google Search 工具时返回
    """

    search_entry_point: Optional[Dict[str, Any]] = Field(default=None, alias="searchEntryPoint")
    grounding_chunks: Optional[List[Dict[str, Any]]] = Field(default=None, alias="groundingChunks")
    grounding_supports: Optional[List[Dict[str, Any]]] = Field(
        default=None, alias="groundingSupports"
    )
    web_search_queries: Optional[List[str]] = Field(default=None, alias="webSearchQueries")


class GeminiCandidate(BaseModelWithExtras):
    """候选响应"""

    content: Optional[GeminiContent] = None
    finish_reason: Optional[str] = Field(default=None, alias="finishReason")
    safety_ratings: Optional[List[GeminiSafetyRating]] = Field(default=None, alias="safetyRatings")
    citation_metadata: Optional[GeminiCitationMetadata] = Field(
        default=None, alias="citationMetadata"
    )
    grounding_metadata: Optional[GeminiGroundingMetadata] = Field(
        default=None, alias="groundingMetadata"
    )
    token_count: Optional[int] = Field(default=None, alias="tokenCount")
    index: Optional[int] = None


class GeminiPromptFeedback(BaseModelWithExtras):
    """提示反馈"""

    block_reason: Optional[str] = Field(default=None, alias="blockReason")
    safety_ratings: Optional[List[GeminiSafetyRating]] = Field(default=None, alias="safetyRatings")


class GeminiGenerateContentResponse(BaseModelWithExtras):
    """
    Gemini generateContent 响应模型

    对应 generateContent 端点的响应体
    """

    candidates: Optional[List[GeminiCandidate]] = None
    prompt_feedback: Optional[GeminiPromptFeedback] = Field(default=None, alias="promptFeedback")
    usage_metadata: Optional[GeminiUsageMetadata] = Field(default=None, alias="usageMetadata")
    model_version: Optional[str] = Field(default=None, alias="modelVersion")


# ---------------------------------------------------------------------------
# 流式响应模型
# ---------------------------------------------------------------------------


class GeminiStreamChunk(BaseModelWithExtras):
    """
    Gemini 流式响应块

    流式响应中的单个数据块，结构与完整响应相同
    """

    candidates: Optional[List[GeminiCandidate]] = None
    prompt_feedback: Optional[GeminiPromptFeedback] = Field(default=None, alias="promptFeedback")
    usage_metadata: Optional[GeminiUsageMetadata] = Field(default=None, alias="usageMetadata")
    model_version: Optional[str] = Field(default=None, alias="modelVersion")


# ---------------------------------------------------------------------------
# 错误响应
# ---------------------------------------------------------------------------


class GeminiErrorDetail(BaseModelWithExtras):
    """错误详情"""

    type: Optional[str] = Field(default=None, alias="@type")
    reason: Optional[str] = None
    domain: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class GeminiError(BaseModelWithExtras):
    """错误信息"""

    code: int
    message: str
    status: str
    details: Optional[List[GeminiErrorDetail]] = None


class GeminiErrorResponse(BaseModelWithExtras):
    """错误响应"""

    error: GeminiError


# ---------------------------------------------------------------------------
# Thought Signature 常量
# ---------------------------------------------------------------------------

# 用于从其他模型迁移对话时绕过签名验证
DUMMY_THOUGHT_SIGNATURE = "context_engineering_is_the_way_to_go"
