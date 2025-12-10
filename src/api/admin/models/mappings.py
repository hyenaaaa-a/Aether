"""模型映射管理 API

提供模型映射的 CRUD 操作。

模型映射（Mapping）用于将源模型映射到目标模型，例如：
- 请求 gpt-5.1 → Provider A 映射到 gpt-4
- 用于处理 Provider 不支持请求模型的情况

映射必须关联到特定的 Provider。
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from src.core.logger import logger
from src.database import get_db
from src.models.api import (
    ModelMappingCreate,
    ModelMappingResponse,
    ModelMappingUpdate,
)
from src.models.database import GlobalModel, ModelMapping, Provider, User
from src.services.cache.invalidation import get_cache_invalidation_service


router = APIRouter(prefix="/mappings", tags=["Model Mappings"])


def _serialize_mapping(mapping: ModelMapping) -> ModelMappingResponse:
    target = mapping.target_global_model
    provider = mapping.provider
    scope = "provider" if mapping.provider_id else "global"
    return ModelMappingResponse(
        id=mapping.id,
        source_model=mapping.source_model,
        target_global_model_id=mapping.target_global_model_id,
        target_global_model_name=target.name if target else None,
        target_global_model_display_name=target.display_name if target else None,
        provider_id=mapping.provider_id,
        provider_name=provider.name if provider else None,
        scope=scope,
        mapping_type=mapping.mapping_type,
        is_active=mapping.is_active,
        created_at=mapping.created_at,
        updated_at=mapping.updated_at,
    )


@router.get("", response_model=List[ModelMappingResponse])
async def list_mappings(
    provider_id: Optional[str] = Query(None, description="按 Provider 筛选"),
    source_model: Optional[str] = Query(None, description="按源模型名筛选"),
    target_global_model_id: Optional[str] = Query(None, description="按目标模型筛选"),
    scope: Optional[str] = Query(None, description="global 或 provider"),
    mapping_type: Optional[str] = Query(None, description="映射类型: alias 或 mapping"),
    is_active: Optional[bool] = Query(None, description="按状态筛选"),
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=1000, description="返回记录数"),
    db: Session = Depends(get_db),
):
    """获取模型映射列表"""
    query = db.query(ModelMapping).options(
        joinedload(ModelMapping.target_global_model),
        joinedload(ModelMapping.provider),
    )

    if provider_id is not None:
        query = query.filter(ModelMapping.provider_id == provider_id)
    if scope == "global":
        query = query.filter(ModelMapping.provider_id.is_(None))
    elif scope == "provider":
        query = query.filter(ModelMapping.provider_id.isnot(None))
    if mapping_type is not None:
        query = query.filter(ModelMapping.mapping_type == mapping_type)
    if source_model:
        query = query.filter(ModelMapping.source_model.ilike(f"%{source_model}%"))
    if target_global_model_id is not None:
        query = query.filter(ModelMapping.target_global_model_id == target_global_model_id)
    if is_active is not None:
        query = query.filter(ModelMapping.is_active == is_active)

    mappings = query.offset(skip).limit(limit).all()
    return [_serialize_mapping(mapping) for mapping in mappings]


@router.get("/{mapping_id}", response_model=ModelMappingResponse)
async def get_mapping(
    mapping_id: str,
    db: Session = Depends(get_db),
):
    """获取单个模型映射"""
    mapping = (
        db.query(ModelMapping)
        .options(
            joinedload(ModelMapping.target_global_model),
            joinedload(ModelMapping.provider),
        )
        .filter(ModelMapping.id == mapping_id)
        .first()
    )

    if not mapping:
        raise HTTPException(status_code=404, detail=f"映射 {mapping_id} 不存在")

    return _serialize_mapping(mapping)


@router.post("", response_model=ModelMappingResponse, status_code=201)
async def create_mapping(
    data: ModelMappingCreate,
    db: Session = Depends(get_db),
):
    """创建模型映射"""
    source_model = data.source_model.strip()
    if not source_model:
        raise HTTPException(status_code=400, detail="source_model 不能为空")

    # 验证 mapping_type
    if data.mapping_type not in ("alias", "mapping"):
        raise HTTPException(status_code=400, detail="mapping_type 必须是 'alias' 或 'mapping'")

    # 验证目标 GlobalModel 存在
    target_model = (
        db.query(GlobalModel)
        .filter(GlobalModel.id == data.target_global_model_id, GlobalModel.is_active == True)
        .first()
    )
    if not target_model:
        raise HTTPException(
            status_code=404, detail=f"目标模型 {data.target_global_model_id} 不存在或未激活"
        )

    # 验证 Provider 存在
    provider = None
    provider_id = data.provider_id
    if provider_id:
        provider = db.query(Provider).filter(Provider.id == provider_id).first()
        if not provider:
            raise HTTPException(status_code=404, detail=f"Provider {provider_id} 不存在")

    # 检查映射是否已存在（全局或同一 Provider 下不可重复）
    existing = (
        db.query(ModelMapping)
        .filter(
            ModelMapping.source_model == source_model,
            ModelMapping.provider_id == provider_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="映射已存在")

    # 创建映射
    mapping = ModelMapping(
        id=str(uuid.uuid4()),
        source_model=source_model,
        target_global_model_id=data.target_global_model_id,
        provider_id=provider_id,
        mapping_type=data.mapping_type,
        is_active=data.is_active,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    db.add(mapping)
    db.commit()
    mapping = (
        db.query(ModelMapping)
        .options(
            joinedload(ModelMapping.target_global_model),
            joinedload(ModelMapping.provider),
        )
        .filter(ModelMapping.id == mapping.id)
        .first()
    )

    logger.info(f"创建模型映射: {source_model} -> {target_model.name} "
        f"(Provider: {provider.name if provider else 'global'}, ID: {mapping.id})")

    cache_service = get_cache_invalidation_service()
    cache_service.on_model_mapping_changed(source_model, provider_id)

    return _serialize_mapping(mapping)


@router.patch("/{mapping_id}", response_model=ModelMappingResponse)
async def update_mapping(
    mapping_id: str,
    data: ModelMappingUpdate,
    db: Session = Depends(get_db),
):
    """更新模型映射"""
    mapping = db.query(ModelMapping).filter(ModelMapping.id == mapping_id).first()
    if not mapping:
        raise HTTPException(status_code=404, detail=f"映射 {mapping_id} 不存在")

    update_data = data.model_dump(exclude_unset=True)

    # 更新 Provider
    if "provider_id" in update_data:
        new_provider_id = update_data["provider_id"]
        if new_provider_id:
            provider = db.query(Provider).filter(Provider.id == new_provider_id).first()
            if not provider:
                raise HTTPException(status_code=404, detail=f"Provider {new_provider_id} 不存在")
        mapping.provider_id = new_provider_id

    # 更新目标模型
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
            raise HTTPException(
                status_code=404,
                detail=f"目标模型 {update_data['target_global_model_id']} 不存在或未激活",
            )
        mapping.target_global_model_id = update_data["target_global_model_id"]

    # 更新源模型名
    if "source_model" in update_data:
        new_source = update_data["source_model"].strip()
        if not new_source:
            raise HTTPException(status_code=400, detail="source_model 不能为空")
        mapping.source_model = new_source

    # 检查唯一约束
    duplicate = (
        db.query(ModelMapping)
        .filter(
            ModelMapping.source_model == mapping.source_model,
            ModelMapping.provider_id == mapping.provider_id,
            ModelMapping.id != mapping_id,
        )
        .first()
    )
    if duplicate:
        raise HTTPException(status_code=400, detail="映射已存在")

    # 更新映射类型
    if "mapping_type" in update_data:
        if update_data["mapping_type"] not in ("alias", "mapping"):
            raise HTTPException(status_code=400, detail="mapping_type 必须是 'alias' 或 'mapping'")
        mapping.mapping_type = update_data["mapping_type"]

    # 更新状态
    if "is_active" in update_data:
        mapping.is_active = update_data["is_active"]

    mapping.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(mapping)

    logger.info(f"更新模型映射 (ID: {mapping.id})")

    mapping = (
        db.query(ModelMapping)
        .options(
            joinedload(ModelMapping.target_global_model),
            joinedload(ModelMapping.provider),
        )
        .filter(ModelMapping.id == mapping.id)
        .first()
    )

    cache_service = get_cache_invalidation_service()
    cache_service.on_model_mapping_changed(mapping.source_model, mapping.provider_id)

    return _serialize_mapping(mapping)


@router.delete("/{mapping_id}", status_code=204)
async def delete_mapping(
    mapping_id: str,
    db: Session = Depends(get_db),
):
    """删除模型映射"""
    mapping = db.query(ModelMapping).filter(ModelMapping.id == mapping_id).first()

    if not mapping:
        raise HTTPException(status_code=404, detail=f"映射 {mapping_id} 不存在")

    source_model = mapping.source_model
    provider_id = mapping.provider_id

    logger.info(f"删除模型映射: {source_model} -> {mapping.target_global_model_id} (ID: {mapping.id})")

    db.delete(mapping)
    db.commit()

    cache_service = get_cache_invalidation_service()
    cache_service.on_model_mapping_changed(source_model, provider_id)

    return None
