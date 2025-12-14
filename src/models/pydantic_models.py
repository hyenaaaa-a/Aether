"""
Pydantic 数据模型（阶段一统一模型管理）
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator

from .api import ModelCreate


# ========== 阶梯计费相关模型 ==========


class CacheTTLPricing(BaseModel):
    """缓存时长定价配置"""

    ttl_minutes: int = Field(..., ge=1, description="缓存时长（分钟）")
    cache_creation_price_per_1m: float = Field(..., ge=0, description="该时长的缓存创建价格/M tokens")


class PricingTier(BaseModel):
    """单个价格阶梯配置"""

    up_to: Optional[int] = Field(
        None,
        ge=1,
        description="阶梯上限（tokens），null 表示无上限（最后一个阶梯）"
    )
    input_price_per_1m: float = Field(..., ge=0, description="输入价格/M tokens")
    output_price_per_1m: float = Field(..., ge=0, description="输出价格/M tokens")
    cache_creation_price_per_1m: Optional[float] = Field(
        None, ge=0, description="缓存创建价格/M tokens"
    )
    cache_read_price_per_1m: Optional[float] = Field(
        None, ge=0, description="缓存读取价格/M tokens"
    )
    cache_ttl_pricing: Optional[List[CacheTTLPricing]] = Field(
        None, description="按缓存时长分价格（可选）"
    )


class TieredPricingConfig(BaseModel):
    """阶梯计费配置"""

    tiers: List[PricingTier] = Field(
        ...,
        min_length=1,
        description="价格阶梯列表，按 up_to 升序排列"
    )

    @model_validator(mode="after")
    def validate_tiers(self) -> "TieredPricingConfig":
        """验证阶梯配置的合法性"""
        tiers = self.tiers
        if not tiers:
            raise ValueError("至少需要一个价格阶梯")

        # 检查阶梯顺序和唯一性
        prev_up_to = 0
        has_unlimited = False

        for i, tier in enumerate(tiers):
            if has_unlimited:
                raise ValueError("无上限阶梯（up_to=null）必须是最后一个")

            if tier.up_to is None:
                has_unlimited = True
            else:
                if tier.up_to <= prev_up_to:
                    raise ValueError(
                        f"阶梯 {i+1} 的 up_to ({tier.up_to}) 必须大于前一个阶梯 ({prev_up_to})"
                    )
                prev_up_to = tier.up_to

            # 验证缓存时长定价顺序
            if tier.cache_ttl_pricing:
                prev_ttl = 0
                for ttl_pricing in tier.cache_ttl_pricing:
                    if ttl_pricing.ttl_minutes <= prev_ttl:
                        raise ValueError(
                            f"cache_ttl_pricing 必须按 ttl_minutes 升序排列"
                        )
                    prev_ttl = ttl_pricing.ttl_minutes

        # 最后一个阶梯必须是无上限的
        if not has_unlimited:
            raise ValueError("最后一个阶梯必须设置 up_to=null（无上限）")

        return self


# ========== 其他模型 ==========


class ModelCapabilities(BaseModel):
    """模型能力聚合"""

    supports_vision: bool = False
    supports_function_calling: bool = False
    supports_streaming: bool = False


class ModelPriceRange(BaseModel):
    """统一模型价格区间"""

    min_input: Optional[float] = None
    max_input: Optional[float] = None
    min_output: Optional[float] = None
    max_output: Optional[float] = None


class ModelCatalogProviderDetail(BaseModel):
    """统一模型目录中的关联提供商信息"""

    provider_id: str
    provider_name: str
    provider_display_name: Optional[str]
    model_id: Optional[str]
    target_model: str
    input_price_per_1m: Optional[float]
    output_price_per_1m: Optional[float]
    cache_creation_price_per_1m: Optional[float]
    cache_read_price_per_1m: Optional[float]
    cache_1h_creation_price_per_1m: Optional[float] = None  # 1h 缓存创建价格
    price_per_request: Optional[float] = None  # 按次计费价格
    effective_tiered_pricing: Optional[Dict[str, Any]] = None  # 有效阶梯计费配置（含继承）
    tier_count: int = 1  # 阶梯数量
    supports_vision: Optional[bool] = None
    supports_function_calling: Optional[bool] = None
    supports_streaming: Optional[bool] = None
    is_active: bool
    mapping_id: Optional[str]


class OrphanedModel(BaseModel):
    """孤立的统一模型（Mapping 存在但 GlobalModel 缺失）"""

    alias: str  # 别名
    global_model_name: Optional[str]  # 关联的 GlobalModel 名称（如果有）
    mapping_count: int


class ModelCatalogItem(BaseModel):
    """统一模型目录条目（方案 A：基于 GlobalModel）"""

    global_model_name: str  # GlobalModel.name
    display_name: str  # GlobalModel.display_name
    description: Optional[str]  # GlobalModel.description
    aliases: List[str]  # 所有指向该 GlobalModel 的别名列表
    providers: List[ModelCatalogProviderDetail]  # 支持该模型的 Provider 列表
    price_range: ModelPriceRange  # 价格区间（从所有 Provider 的 Model 中聚合）
    total_providers: int
    capabilities: ModelCapabilities  # 能力聚合（从所有 Provider 的 Model 中聚合）


class ModelCatalogResponse(BaseModel):
    """统一模型目录响应"""

    models: List[ModelCatalogItem]
    total: int
    orphaned_models: List[OrphanedModel]


class ProviderModelPriceInfo(BaseModel):
    """Provider 维度的模型价格信息"""

    input_price_per_1m: Optional[float]
    output_price_per_1m: Optional[float]
    cache_creation_price_per_1m: Optional[float]
    cache_read_price_per_1m: Optional[float]
    price_per_request: Optional[float] = None  # 按次计费价格


class ProviderAvailableSourceModel(BaseModel):
    """Provider 支持的统一模型条目（方案 A）"""

    global_model_name: str  # GlobalModel.name
    display_name: str  # GlobalModel.display_name
    provider_model_name: str  # Model.provider_model_name (Provider 侧的模型名)
    has_alias: bool  # 是否有别名指向该 GlobalModel
    aliases: List[str]  # 别名列表
    model_id: Optional[str]  # Model.id
    price: ProviderModelPriceInfo
    capabilities: ModelCapabilities
    is_active: bool


class ProviderAvailableSourceModelsResponse(BaseModel):
    """Provider 可用统一模型响应"""

    models: List[ProviderAvailableSourceModel]
    total: int


class BatchAssignProviderConfig(BaseModel):
    """批量添加映射的 Provider 配置"""

    provider_id: str
    create_model: bool = Field(False, description="是否需要创建新的 Model")
    model_data: Optional[ModelCreate] = Field(
        None, description="create_model=true 时需要提供的模型配置", alias="model_config"
    )
    model_id: Optional[str] = Field(None, description="create_model=false 时需要提供的现有模型 ID")


class BatchAssignModelMappingRequest(BaseModel):
    """批量添加模型映射请求（方案 A：暂不支持，需要重构）"""

    global_model_id: str  # 要分配的 GlobalModel ID
    providers: List[BatchAssignProviderConfig]


class BatchAssignProviderResult(BaseModel):
    """批量映射结果条目"""

    provider_id: str
    mapping_id: Optional[str]
    created_model: bool
    model_id: Optional[str]
    updated: bool = False


class BatchAssignError(BaseModel):
    """批量映射错误信息"""

    provider_id: str
    error: str


class BatchAssignModelMappingResponse(BaseModel):
    """批量映射响应"""

    success: bool
    created_mappings: List[BatchAssignProviderResult]
    errors: List[BatchAssignError]


# ========== 阶段二：GlobalModel 相关模型 ==========


class GlobalModelCreate(BaseModel):
    """创建 GlobalModel 请求"""

    name: str = Field(..., min_length=1, max_length=100, description="统一模型名（唯一）")
    display_name: str = Field(..., min_length=1, max_length=100, description="显示名称")
    description: Optional[str] = Field(None, description="模型描述")
    official_url: Optional[str] = Field(None, max_length=500, description="官方文档链接")
    icon_url: Optional[str] = Field(None, max_length=500, description="图标 URL")
    # 按次计费配置（可选，与阶梯计费叠加）
    default_price_per_request: Optional[float] = Field(None, ge=0, description="每次请求固定费用")
    # 统一阶梯计费配置（必填）
    # 固定价格也用单阶梯表示: {"tiers": [{"up_to": null, "input_price_per_1m": X, ...}]}
    default_tiered_pricing: TieredPricingConfig = Field(
        ..., description="阶梯计费配置（固定价格用单阶梯表示）"
    )
    # 默认能力配置
    default_supports_vision: Optional[bool] = Field(False, description="默认是否支持视觉")
    default_supports_function_calling: Optional[bool] = Field(
        False, description="默认是否支持函数调用"
    )
    default_supports_streaming: Optional[bool] = Field(True, description="默认是否支持流式输出")
    default_supports_extended_thinking: Optional[bool] = Field(
        False, description="默认是否支持扩展思考"
    )
    default_supports_image_generation: Optional[bool] = Field(
        False, description="默认是否支持图像生成"
    )
    # Key 能力配置 - 模型支持的能力列表（如 ["cache_1h", "context_1m"]）
    supported_capabilities: Optional[List[str]] = Field(
        None, description="支持的 Key 能力列表"
    )
    is_active: Optional[bool] = Field(True, description="是否激活")


class GlobalModelUpdate(BaseModel):
    """更新 GlobalModel 请求"""

    display_name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    official_url: Optional[str] = Field(None, max_length=500)
    icon_url: Optional[str] = Field(None, max_length=500)
    is_active: Optional[bool] = None
    # 按次计费配置
    default_price_per_request: Optional[float] = Field(None, ge=0, description="每次请求固定费用")
    # 阶梯计费配置
    default_tiered_pricing: Optional[TieredPricingConfig] = Field(
        None, description="阶梯计费配置"
    )
    # 默认能力配置
    default_supports_vision: Optional[bool] = None
    default_supports_function_calling: Optional[bool] = None
    default_supports_streaming: Optional[bool] = None
    default_supports_extended_thinking: Optional[bool] = None
    default_supports_image_generation: Optional[bool] = None
    # Key 能力配置 - 模型支持的能力列表（如 ["cache_1h", "context_1m"]）
    supported_capabilities: Optional[List[str]] = Field(
        None, description="支持的 Key 能力列表"
    )


class GlobalModelResponse(BaseModel):
    """GlobalModel 响应"""

    id: str
    name: str
    display_name: str
    description: Optional[str]
    official_url: Optional[str]
    icon_url: Optional[str]
    is_active: bool
    # 按次计费配置
    default_price_per_request: Optional[float] = Field(None, description="每次请求固定费用")
    # 阶梯计费配置
    default_tiered_pricing: TieredPricingConfig = Field(
        ..., description="阶梯计费配置"
    )
    # 默认能力配置
    default_supports_vision: Optional[bool]
    default_supports_function_calling: Optional[bool]
    default_supports_streaming: Optional[bool]
    default_supports_extended_thinking: Optional[bool]
    default_supports_image_generation: Optional[bool]
    # Key 能力配置 - 模型支持的能力列表
    supported_capabilities: Optional[List[str]] = Field(
        default=None, description="支持的 Key 能力列表"
    )
    # 统计数据（可选）
    provider_count: Optional[int] = Field(default=0, description="支持的 Provider 数量")
    alias_count: Optional[int] = Field(default=0, description="别名数量")
    usage_count: Optional[int] = Field(default=0, description="调用次数")
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class GlobalModelWithStats(GlobalModelResponse):
    """带统计信息的 GlobalModel"""

    total_models: int = Field(..., description="关联的 Model 数量")
    total_providers: int = Field(..., description="支持的 Provider 数量")
    price_range: ModelPriceRange


class GlobalModelListResponse(BaseModel):
    """GlobalModel 列表响应"""

    models: List[GlobalModelResponse]
    total: int


class BatchAssignToProvidersRequest(BaseModel):
    """批量为 Provider 添加 GlobalModel 实现"""

    provider_ids: List[str] = Field(..., min_items=1, description="Provider ID 列表")
    create_models: bool = Field(default=False, description="是否自动创建 Model 记录")


class BatchAssignToProvidersResponse(BaseModel):
    """批量分配响应"""

    success: List[dict]
    errors: List[dict]


class BatchAssignModelsToProviderRequest(BaseModel):
    """批量为 Provider 关联 GlobalModel"""

    global_model_ids: List[str] = Field(..., min_length=1, description="GlobalModel ID 列表")


class BatchAssignModelsToProviderResponse(BaseModel):
    """批量关联 GlobalModel 到 Provider 的响应"""

    success: List[dict]
    errors: List[dict]


class UpdateModelMappingRequest(BaseModel):
    """更新模型映射请求"""

    source_model: Optional[str] = Field(
        None, min_length=1, max_length=200, description="源模型名或别名"
    )
    target_global_model_id: Optional[str] = Field(None, description="目标 GlobalModel ID")
    provider_id: Optional[str] = Field(None, description="Provider ID（为空时为全局别名）")
    is_active: Optional[bool] = Field(None, description="是否启用")


class UpdateModelMappingResponse(BaseModel):
    """更新模型映射响应"""

    success: bool
    mapping_id: str
    message: Optional[str] = None


class DeleteModelMappingResponse(BaseModel):
    """删除模型映射响应"""

    success: bool
    message: Optional[str] = None


# ========== 远程模型拉取相关模型 ==========


class RemoteModelItem(BaseModel):
    """从远程 API 获取的模型条目"""

    id: str = Field(..., description="模型 ID（来自远程 API）")
    object: Optional[str] = Field(default="model", description="对象类型")
    created: Optional[int] = Field(default=None, description="创建时间戳")
    owned_by: Optional[str] = Field(default=None, description="所有者")


class FetchRemoteModelsResponse(BaseModel):
    """获取远程模型列表响应"""

    models: List[RemoteModelItem] = Field(..., description="远程模型列表")
    total: int = Field(..., description="总数")
    endpoint_id: str = Field(..., description="使用的端点 ID")
    endpoint_base_url: str = Field(..., description="使用的端点 Base URL")


class ImportRemoteModelsRequest(BaseModel):
    """导入远程模型请求"""

    model_ids: List[str] = Field(..., min_length=1, description="要导入的模型 ID 列表")


class ImportRemoteModelsResponse(BaseModel):
    """导入远程模型响应"""

    success: List[dict] = Field(..., description="成功导入的模型")
    errors: List[dict] = Field(..., description="导入失败的模型")

__all__ = [
    "BatchAssignError",
    "BatchAssignModelMappingRequest",
    "BatchAssignModelMappingResponse",
    "BatchAssignModelsToProviderRequest",
    "BatchAssignModelsToProviderResponse",
    "BatchAssignProviderConfig",
    "BatchAssignProviderResult",
    "BatchAssignToProvidersRequest",
    "BatchAssignToProvidersResponse",
    "DeleteModelMappingResponse",
    "FetchRemoteModelsResponse",
    "GlobalModelCreate",
    "GlobalModelListResponse",
    "GlobalModelResponse",
    "GlobalModelUpdate",
    "GlobalModelWithStats",
    "ImportRemoteModelsRequest",
    "ImportRemoteModelsResponse",
    "ModelCapabilities",
    "ModelCatalogItem",
    "ModelCatalogProviderDetail",
    "ModelCatalogResponse",
    "ModelPriceRange",
    "OrphanedModel",
    "ProviderAvailableSourceModel",
    "ProviderAvailableSourceModelsResponse",
    "ProviderModelPriceInfo",
    "RemoteModelItem",
    "UpdateModelMappingRequest",
    "UpdateModelMappingResponse",
]
