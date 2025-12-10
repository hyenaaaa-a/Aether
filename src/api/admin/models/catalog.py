"""
统一模型目录 Admin API

阶段一：基于 ModelMapping 和 Model 的聚合视图
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from src.api.base.admin_adapter import AdminApiAdapter
from src.api.base.pipeline import ApiRequestPipeline
from src.core.logger import logger
from src.database import get_db
from src.models.database import GlobalModel, Model, ModelMapping, Provider
from src.models.pydantic_models import (
    BatchAssignError,
    BatchAssignModelMappingRequest,
    BatchAssignModelMappingResponse,
    BatchAssignProviderResult,
    DeleteModelMappingResponse,
    ModelCapabilities,
    ModelCatalogItem,
    ModelCatalogProviderDetail,
    ModelCatalogResponse,
    ModelPriceRange,
    OrphanedModel,
    UpdateModelMappingRequest,
    UpdateModelMappingResponse,
)
from src.services.cache.invalidation import get_cache_invalidation_service
from src.services.model.service import ModelService

router = APIRouter(prefix="/catalog", tags=["Admin - Model Catalog"])
pipeline = ApiRequestPipeline()


@router.get("", response_model=ModelCatalogResponse)
async def get_model_catalog(
    request: Request,
    db: Session = Depends(get_db),
) -> ModelCatalogResponse:
    adapter = AdminGetModelCatalogAdapter()
    return await pipeline.run(adapter=adapter, http_request=request, db=db, mode=adapter.mode)


@router.post("/batch-assign", response_model=BatchAssignModelMappingResponse)
async def batch_assign_model_mappings(
    request: Request,
    payload: BatchAssignModelMappingRequest,
    db: Session = Depends(get_db),
) -> BatchAssignModelMappingResponse:
    adapter = AdminBatchAssignModelMappingsAdapter(payload=payload)
    return await pipeline.run(adapter=adapter, http_request=request, db=db, mode=adapter.mode)


@dataclass
class AdminGetModelCatalogAdapter(AdminApiAdapter):
    """管理员查询统一模型目录

    新架构说明：
    1. 以 GlobalModel 为中心聚合数据
    2. ModelMapping 表提供别名信息（provider_id=NULL 表示全局）
    3. Model 表提供关联提供商和价格
    """

    async def handle(self, context):  # type: ignore[override]
        db: Session = context.db

        # 1. 获取所有活跃的 GlobalModel
        global_models: List[GlobalModel] = (
            db.query(GlobalModel).filter(GlobalModel.is_active == True).all()
        )

        # 2. 获取所有活跃的别名（含全局和 Provider 特定）
        aliases_rows: List[ModelMapping] = (
            db.query(ModelMapping)
            .options(joinedload(ModelMapping.target_global_model))
            .filter(
                ModelMapping.is_active == True,
                ModelMapping.provider_id.is_(None),
            )
            .all()
        )

        # 按 GlobalModel ID 组织别名
        aliases_by_global_model: Dict[str, List[str]] = {}
        for alias_row in aliases_rows:
            if not alias_row.target_global_model_id:
                continue
            gm_id = alias_row.target_global_model_id
            if gm_id not in aliases_by_global_model:
                aliases_by_global_model[gm_id] = []
            if alias_row.source_model not in aliases_by_global_model[gm_id]:
                aliases_by_global_model[gm_id].append(alias_row.source_model)

        # 3. 获取所有活跃的 Model 实现（包含 global_model 以便计算有效价格）
        models: List[Model] = (
            db.query(Model)
            .options(joinedload(Model.provider), joinedload(Model.global_model))
            .filter(Model.is_active == True)
            .all()
        )

        # 按 GlobalModel ID 组织关联提供商
        models_by_global_model: Dict[str, List[Model]] = {}
        for model in models:
            if model.global_model_id:
                models_by_global_model.setdefault(model.global_model_id, []).append(model)

        # 4. 为每个 GlobalModel 构建 catalog item
        catalog_items: List[ModelCatalogItem] = []

        for gm in global_models:
            gm_id = gm.id
            provider_entries: List[ModelCatalogProviderDetail] = []
            capability_flags = {
                "supports_vision": gm.default_supports_vision or False,
                "supports_function_calling": gm.default_supports_function_calling or False,
                "supports_streaming": gm.default_supports_streaming or False,
            }

            # 遍历该 GlobalModel 的所有关联提供商
            for model in models_by_global_model.get(gm_id, []):
                provider = model.provider
                if not provider:
                    continue

                # 使用有效价格（考虑 GlobalModel 默认值）
                effective_input = model.get_effective_input_price()
                effective_output = model.get_effective_output_price()
                effective_tiered = model.get_effective_tiered_pricing()
                tier_count = len(effective_tiered.get("tiers", [])) if effective_tiered else 1

                # 使用有效能力值
                capability_flags["supports_vision"] = (
                    capability_flags["supports_vision"] or model.get_effective_supports_vision()
                )
                capability_flags["supports_function_calling"] = (
                    capability_flags["supports_function_calling"]
                    or model.get_effective_supports_function_calling()
                )
                capability_flags["supports_streaming"] = (
                    capability_flags["supports_streaming"]
                    or model.get_effective_supports_streaming()
                )

                provider_entries.append(
                    ModelCatalogProviderDetail(
                        provider_id=provider.id,
                        provider_name=provider.name,
                        provider_display_name=provider.display_name,
                        model_id=model.id,
                        target_model=model.provider_model_name,
                        # 显示有效价格
                        input_price_per_1m=effective_input,
                        output_price_per_1m=effective_output,
                        cache_creation_price_per_1m=model.get_effective_cache_creation_price(),
                        cache_read_price_per_1m=model.get_effective_cache_read_price(),
                        cache_1h_creation_price_per_1m=model.get_effective_1h_cache_creation_price(),
                        price_per_request=model.get_effective_price_per_request(),
                        effective_tiered_pricing=effective_tiered,
                        tier_count=tier_count,
                        supports_vision=model.get_effective_supports_vision(),
                        supports_function_calling=model.get_effective_supports_function_calling(),
                        supports_streaming=model.get_effective_supports_streaming(),
                        is_active=bool(model.is_active),
                        mapping_id=None,  # 新架构中不再有 mapping_id
                    )
                )

            # 模型目录显示 GlobalModel 的第一个阶梯价格（不是 Provider 聚合价格）
            tiered = gm.default_tiered_pricing or {}
            first_tier = tiered.get("tiers", [{}])[0] if tiered.get("tiers") else {}
            price_range = ModelPriceRange(
                min_input=first_tier.get("input_price_per_1m", 0),
                max_input=first_tier.get("input_price_per_1m", 0),
                min_output=first_tier.get("output_price_per_1m", 0),
                max_output=first_tier.get("output_price_per_1m", 0),
            )

            catalog_items.append(
                ModelCatalogItem(
                    global_model_name=gm.name,
                    display_name=gm.display_name,
                    description=gm.description,
                    aliases=aliases_by_global_model.get(gm_id, []),
                    providers=provider_entries,
                    price_range=price_range,
                    total_providers=len(provider_entries),
                    capabilities=ModelCapabilities(**capability_flags),
                )
            )

        # 5. 查找孤立的别名（别名指向的 GlobalModel 不存在或不活跃）
        orphaned_rows = (
            db.query(ModelMapping.source_model, GlobalModel.name, func.count(ModelMapping.id))
            .outerjoin(GlobalModel, ModelMapping.target_global_model_id == GlobalModel.id)
            .filter(
                ModelMapping.is_active == True,
                ModelMapping.provider_id.is_(None),
                or_(GlobalModel.id == None, GlobalModel.is_active == False),
            )
            .group_by(ModelMapping.source_model, GlobalModel.name)
            .all()
        )
        orphaned_models = [
            OrphanedModel(alias=row[0], global_model_name=row[1], mapping_count=row[2])
            for row in orphaned_rows
            if row[0]
        ]

        return ModelCatalogResponse(
            models=catalog_items,
            total=len(catalog_items),
            orphaned_models=orphaned_models,
        )


@dataclass
class AdminBatchAssignModelMappingsAdapter(AdminApiAdapter):
    payload: BatchAssignModelMappingRequest

    async def handle(self, context):  # type: ignore[override]
        db: Session = context.db
        created: List[BatchAssignProviderResult] = []
        errors: List[BatchAssignError] = []

        for provider_config in self.payload.providers:
            provider_id = provider_config.provider_id
            try:
                provider: Provider = db.query(Provider).filter(Provider.id == provider_id).first()
                if not provider:
                    errors.append(
                        BatchAssignError(provider_id=provider_id, error="Provider 不存在")
                    )
                    continue

                model_id: Optional[str] = None
                created_model = False

                if provider_config.create_model:
                    model_data = provider_config.model_data
                    if not model_data:
                        errors.append(
                            BatchAssignError(provider_id=provider_id, error="缺少 model_data 配置")
                        )
                        continue

                    existing_model = ModelService.get_model_by_name(
                        db, provider_id, model_data.provider_model_name
                    )
                    if existing_model:
                        model_id = existing_model.id
                        logger.info("模型 %s 已存在于 Provider %s，复用现有模型",
                            model_data.provider_model_name,
                            provider.name,
                        )
                    else:
                        model = ModelService.create_model(db, provider_id, model_data)
                        model_id = model.id
                        created_model = True
                else:
                    model_id = provider_config.model_id
                    if not model_id:
                        errors.append(
                            BatchAssignError(provider_id=provider_id, error="缺少 model_id")
                        )
                        continue
                    model = (
                        db.query(Model)
                        .filter(Model.id == model_id, Model.provider_id == provider_id)
                        .first()
                    )
                    if not model:
                        errors.append(
                            BatchAssignError(
                                provider_id=provider_id, error="模型不存在或不属于当前 Provider")
                        )
                        continue

                # 批量分配功能需要适配 GlobalModel 架构
                # 参见 docs/optimization-backlog.md 中的待办项
                errors.append(
                    BatchAssignError(
                        provider_id=provider_id,
                        error="批量分配功能暂时不可用，需要适配新的 GlobalModel 架构",
                    )
                )
                continue

            except Exception as exc:
                db.rollback()
                logger.error("批量添加模型映射失败（需要适配新架构）")
                errors.append(BatchAssignError(provider_id=provider_id, error=str(exc)))

        return BatchAssignModelMappingResponse(
            success=len(created) > 0,
            created_mappings=created,
            errors=errors,
        )


@router.put("/mappings/{mapping_id}", response_model=UpdateModelMappingResponse)
async def update_model_mapping(
    request: Request,
    mapping_id: str,
    payload: UpdateModelMappingRequest,
    db: Session = Depends(get_db),
) -> UpdateModelMappingResponse:
    """更新模型映射"""
    adapter = AdminUpdateModelMappingAdapter(mapping_id=mapping_id, payload=payload)
    return await pipeline.run(adapter=adapter, http_request=request, db=db, mode=adapter.mode)


@router.delete("/mappings/{mapping_id}", response_model=DeleteModelMappingResponse)
async def delete_model_mapping(
    request: Request,
    mapping_id: str,
    db: Session = Depends(get_db),
) -> DeleteModelMappingResponse:
    """删除模型映射"""
    adapter = AdminDeleteModelMappingAdapter(mapping_id=mapping_id)
    return await pipeline.run(adapter=adapter, http_request=request, db=db, mode=adapter.mode)


@dataclass
class AdminUpdateModelMappingAdapter(AdminApiAdapter):
    """更新模型映射"""

    mapping_id: str
    payload: UpdateModelMappingRequest

    async def handle(self, context):  # type: ignore[override]
        db: Session = context.db

        mapping: Optional[ModelMapping] = (
            db.query(ModelMapping).filter(ModelMapping.id == self.mapping_id).first()
        )

        if not mapping:
            raise HTTPException(status_code=404, detail="映射不存在")

        update_data = self.payload.model_dump(exclude_unset=True)

        if "provider_id" in update_data:
            new_provider_id = update_data["provider_id"]
            if new_provider_id:
                provider = db.query(Provider).filter(Provider.id == new_provider_id).first()
                if not provider:
                    raise HTTPException(status_code=404, detail="Provider 不存在")
            mapping.provider_id = new_provider_id

        if "target_global_model_id" in update_data:
            target_model = (
                db.query(GlobalModel)
                .filter(
                    GlobalModel.id == update_data["target_global_model_id"],
                    GlobalModel.is_active == True,
                )
                .first()
            )
            if not target_model:
                raise HTTPException(status_code=404, detail="目标 GlobalModel 不存在或未激活")
            mapping.target_global_model_id = update_data["target_global_model_id"]

        if "source_model" in update_data:
            new_source = update_data["source_model"].strip()
            if not new_source:
                raise HTTPException(status_code=400, detail="source_model 不能为空")
            mapping.source_model = new_source

        if "is_active" in update_data:
            mapping.is_active = update_data["is_active"]

        duplicate = (
            db.query(ModelMapping)
            .filter(
                ModelMapping.source_model == mapping.source_model,
                ModelMapping.provider_id == mapping.provider_id,
                ModelMapping.id != mapping.id,
            )
            .first()
        )
        if duplicate:
            raise HTTPException(status_code=400, detail="映射已存在")

        db.commit()
        db.refresh(mapping)

        cache_service = get_cache_invalidation_service()
        cache_service.on_model_mapping_changed(mapping.source_model, mapping.provider_id)

        return UpdateModelMappingResponse(
            success=True,
            mapping_id=mapping.id,
            message="映射更新成功",
        )


@dataclass
class AdminDeleteModelMappingAdapter(AdminApiAdapter):
    """删除模型映射"""

    mapping_id: str

    async def handle(self, context):  # type: ignore[override]
        db: Session = context.db

        mapping: Optional[ModelMapping] = (
            db.query(ModelMapping).filter(ModelMapping.id == self.mapping_id).first()
        )

        if not mapping:
            raise HTTPException(status_code=404, detail="映射不存在")

        source_model = mapping.source_model
        provider_id = mapping.provider_id

        db.delete(mapping)
        db.commit()

        cache_service = get_cache_invalidation_service()
        cache_service.on_model_mapping_changed(source_model, provider_id)

        return DeleteModelMappingResponse(
            success=True,
            message=f"映射 {self.mapping_id} 已删除",
        )
