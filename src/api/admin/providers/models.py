"""
Provider 模型管理 API
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from src.api.base.admin_adapter import AdminApiAdapter
from src.api.base.pipeline import ApiRequestPipeline
from src.core.exceptions import InvalidRequestException, NotFoundException
from src.core.logger import logger
from src.database import get_db
from src.models.api import (
    ModelCreate,
    ModelResponse,
    ModelUpdate,
)
from src.models.pydantic_models import (
    BatchAssignModelsToProviderRequest,
    BatchAssignModelsToProviderResponse,
    FetchRemoteModelsResponse,
    ImportRemoteModelsRequest,
    ImportRemoteModelsResponse,
    RemoteModelItem,
)
from src.models.database import (
    GlobalModel,
    Model,
    ModelMapping,
    Provider,
    ProviderAPIKey,
    ProviderEndpoint,
)
from src.models.pydantic_models import (
    ProviderAvailableSourceModel,
    ProviderAvailableSourceModelsResponse,
)
from src.services.model.service import ModelService
from src.core.crypto import crypto_service

router = APIRouter(tags=["Model Management"])
pipeline = ApiRequestPipeline()


@router.get("/{provider_id}/models", response_model=List[ModelResponse])
async def list_provider_models(
    provider_id: str,
    request: Request,
    is_active: Optional[bool] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> List[ModelResponse]:
    """获取提供商的所有模型（管理员）"""
    adapter = AdminListProviderModelsAdapter(
        provider_id=provider_id,
        is_active=is_active,
        skip=skip,
        limit=limit,
    )
    return await pipeline.run(adapter=adapter, http_request=request, db=db, mode=adapter.mode)


@router.post("/{provider_id}/models", response_model=ModelResponse)
async def create_provider_model(
    provider_id: str,
    model_data: ModelCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> ModelResponse:
    """创建模型（管理员）"""
    adapter = AdminCreateProviderModelAdapter(provider_id=provider_id, model_data=model_data)
    return await pipeline.run(adapter=adapter, http_request=request, db=db, mode=adapter.mode)


@router.get("/{provider_id}/models/{model_id}", response_model=ModelResponse)
async def get_provider_model(
    provider_id: str,
    model_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> ModelResponse:
    """获取模型详情（管理员）"""
    adapter = AdminGetProviderModelAdapter(provider_id=provider_id, model_id=model_id)
    return await pipeline.run(adapter=adapter, http_request=request, db=db, mode=adapter.mode)


@router.patch("/{provider_id}/models/{model_id}", response_model=ModelResponse)
async def update_provider_model(
    provider_id: str,
    model_id: str,
    model_data: ModelUpdate,
    request: Request,
    db: Session = Depends(get_db),
) -> ModelResponse:
    """更新模型（管理员）"""
    adapter = AdminUpdateProviderModelAdapter(
        provider_id=provider_id,
        model_id=model_id,
        model_data=model_data,
    )
    return await pipeline.run(adapter=adapter, http_request=request, db=db, mode=adapter.mode)


@router.delete("/{provider_id}/models/{model_id}")
async def delete_provider_model(
    provider_id: str,
    model_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """删除模型（管理员）"""
    adapter = AdminDeleteProviderModelAdapter(provider_id=provider_id, model_id=model_id)
    return await pipeline.run(adapter=adapter, http_request=request, db=db, mode=adapter.mode)


@router.post("/{provider_id}/models/batch", response_model=List[ModelResponse])
async def batch_create_provider_models(
    provider_id: str,
    models_data: List[ModelCreate],
    request: Request,
    db: Session = Depends(get_db),
) -> List[ModelResponse]:
    """批量创建模型（管理员）"""
    adapter = AdminBatchCreateModelsAdapter(provider_id=provider_id, models_data=models_data)
    return await pipeline.run(adapter=adapter, http_request=request, db=db, mode=adapter.mode)


@router.get(
    "/{provider_id}/available-source-models",
    response_model=ProviderAvailableSourceModelsResponse,
)
async def get_provider_available_source_models(
    provider_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    获取该 Provider 支持的所有统一模型名（source_model）

    包括：
    1. 通过 ModelMapping 映射的模型
    2. 直连模型（Model.provider_model_name 直接作为统一模型名）
    """
    adapter = AdminGetProviderAvailableSourceModelsAdapter(provider_id=provider_id)
    return await pipeline.run(adapter=adapter, http_request=request, db=db, mode=adapter.mode)


@router.post(
    "/{provider_id}/assign-global-models",
    response_model=BatchAssignModelsToProviderResponse,
)
async def batch_assign_global_models_to_provider(
    provider_id: str,
    payload: BatchAssignModelsToProviderRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> BatchAssignModelsToProviderResponse:
    """批量为 Provider 关联 GlobalModels（自动继承价格和能力配置）"""
    adapter = AdminBatchAssignModelsToProviderAdapter(
        provider_id=provider_id, payload=payload
    )
    return await pipeline.run(adapter=adapter, http_request=request, db=db, mode=adapter.mode)


@router.get(
    "/{provider_id}/fetch-remote-models",
    response_model=FetchRemoteModelsResponse,
)
async def fetch_remote_models(
    provider_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> FetchRemoteModelsResponse:
    """
    从 Provider 的远程 API 获取可用模型列表
    
    通过 Provider 的 Endpoint 发送 GET /v1/models 请求
    """
    adapter = AdminFetchRemoteModelsAdapter(provider_id=provider_id)
    return await pipeline.run(adapter=adapter, http_request=request, db=db, mode=adapter.mode)


@router.post(
    "/{provider_id}/import-remote-models",
    response_model=ImportRemoteModelsResponse,
)
async def import_remote_models(
    provider_id: str,
    payload: ImportRemoteModelsRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> ImportRemoteModelsResponse:
    """
    导入远程模型（自动创建 GlobalModel 和 Provider Model）
    
    对于每个要导入的模型：
    1. 如果 GlobalModel 不存在，创建一个价格为 0 的 GlobalModel
    2. 创建 Provider 的 Model 记录关联到该 GlobalModel
    """
    adapter = AdminImportRemoteModelsAdapter(provider_id=provider_id, payload=payload)
    return await pipeline.run(adapter=adapter, http_request=request, db=db, mode=adapter.mode)


# -------- Adapters --------


@dataclass
class AdminListProviderModelsAdapter(AdminApiAdapter):
    provider_id: str
    is_active: Optional[bool]
    skip: int
    limit: int

    async def handle(self, context):  # type: ignore[override]
        db = context.db
        provider = db.query(Provider).filter(Provider.id == self.provider_id).first()
        if not provider:
            raise NotFoundException("Provider not found", "provider")

        models = ModelService.get_models_by_provider(
            db, self.provider_id, self.skip, self.limit, self.is_active
        )
        return [ModelService.convert_to_response(model) for model in models]


@dataclass
class AdminCreateProviderModelAdapter(AdminApiAdapter):
    provider_id: str
    model_data: ModelCreate

    async def handle(self, context):  # type: ignore[override]
        db = context.db
        provider = db.query(Provider).filter(Provider.id == self.provider_id).first()
        if not provider:
            raise NotFoundException("Provider not found", "provider")

        try:
            model = ModelService.create_model(db, self.provider_id, self.model_data)
            logger.info(f"Model created: {model.provider_model_name} for provider {provider.name} by {context.user.username}")
            
            # 自动创建模型别名：格式为 provider_name/global_model_name
            if model.global_model:
                alias_name = f"{provider.name}/{model.global_model.name}"
                existing_alias = db.query(ModelMapping).filter(
                    ModelMapping.source_model == alias_name,
                    ModelMapping.provider_id == self.provider_id
                ).first()
                if not existing_alias:
                    new_alias = ModelMapping(
                        source_model=alias_name,
                        target_global_model_id=model.global_model_id,
                        provider_id=self.provider_id,
                        mapping_type="alias",
                        is_active=True
                    )
                    db.add(new_alias)
                    db.commit()
                    logger.info(f"Auto-created alias '{alias_name}' for model {model.provider_model_name}")
            
            return ModelService.convert_to_response(model)
        except Exception as exc:
            raise InvalidRequestException(str(exc))


@dataclass
class AdminGetProviderModelAdapter(AdminApiAdapter):
    provider_id: str
    model_id: str

    async def handle(self, context):  # type: ignore[override]
        db = context.db
        model = (
            db.query(Model)
            .filter(Model.id == self.model_id, Model.provider_id == self.provider_id)
            .first()
        )
        if not model:
            raise NotFoundException("Model not found", "model")

        return ModelService.convert_to_response(model)


@dataclass
class AdminUpdateProviderModelAdapter(AdminApiAdapter):
    provider_id: str
    model_id: str
    model_data: ModelUpdate

    async def handle(self, context):  # type: ignore[override]
        db = context.db
        model = (
            db.query(Model)
            .filter(Model.id == self.model_id, Model.provider_id == self.provider_id)
            .first()
        )
        if not model:
            raise NotFoundException("Model not found", "model")

        try:
            updated_model = ModelService.update_model(db, self.model_id, self.model_data)
            logger.info(f"Model updated: {updated_model.provider_model_name} by {context.user.username}")
            return ModelService.convert_to_response(updated_model)
        except Exception as exc:
            raise InvalidRequestException(str(exc))


@dataclass
class AdminDeleteProviderModelAdapter(AdminApiAdapter):
    provider_id: str
    model_id: str

    async def handle(self, context):  # type: ignore[override]
        db = context.db
        model = (
            db.query(Model)
            .filter(Model.id == self.model_id, Model.provider_id == self.provider_id)
            .first()
        )
        if not model:
            raise NotFoundException("Model not found", "model")

        model_name = model.provider_model_name
        try:
            ModelService.delete_model(db, self.model_id)
            logger.info(f"Model deleted: {model_name} by {context.user.username}")
            return {"message": f"Model '{model_name}' deleted successfully"}
        except Exception as exc:
            raise InvalidRequestException(str(exc))


@dataclass
class AdminBatchCreateModelsAdapter(AdminApiAdapter):
    provider_id: str
    models_data: List[ModelCreate]

    async def handle(self, context):  # type: ignore[override]
        db = context.db
        provider = db.query(Provider).filter(Provider.id == self.provider_id).first()
        if not provider:
            raise NotFoundException("Provider not found", "provider")

        try:
            models = ModelService.batch_create_models(db, self.provider_id, self.models_data)
            logger.info(f"Batch created {len(models)} models for provider {provider.name} by {context.user.username}")
            return [ModelService.convert_to_response(model) for model in models]
        except Exception as exc:
            raise InvalidRequestException(str(exc))


@dataclass
class AdminGetProviderAvailableSourceModelsAdapter(AdminApiAdapter):
    provider_id: str

    async def handle(self, context):  # type: ignore[override]
        """
        返回 Provider 支持的所有 GlobalModel

        方案 A 逻辑：
        1. 查询该 Provider 的所有 Model
        2. 通过 Model.global_model_id 获取 GlobalModel
        3. 查询所有指向该 GlobalModel 的别名（ModelMapping.alias）
        """
        db = context.db
        provider = db.query(Provider).filter(Provider.id == self.provider_id).first()
        if not provider:
            raise NotFoundException("Provider not found", "provider")

        # 1. 查询该 Provider 的所有活跃 Model（预加载 GlobalModel）
        models = (
            db.query(Model)
            .options(joinedload(Model.global_model))
            .filter(Model.provider_id == self.provider_id, Model.is_active == True)
            .all()
        )

        # 2. 构建以 GlobalModel 为主键的字典
        global_models_dict: Dict[str, Dict[str, Any]] = {}

        for model in models:
            global_model = model.global_model
            if not global_model or not global_model.is_active:
                continue

            global_model_name = global_model.name

            # 如果该 GlobalModel 还未处理，初始化
            if global_model_name not in global_models_dict:
                # 查询指向该 GlobalModel 的所有别名/映射
                alias_rows = (
                    db.query(ModelMapping.source_model)
                    .filter(
                        ModelMapping.target_global_model_id == global_model.id,
                        ModelMapping.is_active == True,
                        or_(
                            ModelMapping.provider_id == self.provider_id,
                            ModelMapping.provider_id.is_(None),
                        ),
                    )
                    .all()
                )
                alias_list = [alias[0] for alias in alias_rows]

                global_models_dict[global_model_name] = {
                    "global_model_name": global_model_name,
                    "display_name": global_model.display_name,
                    "provider_model_name": model.provider_model_name,
                    "has_alias": len(alias_list) > 0,
                    "aliases": alias_list,
                    "model_id": model.id,
                    "price": {
                        "input_price_per_1m": model.get_effective_input_price(),
                        "output_price_per_1m": model.get_effective_output_price(),
                        "cache_creation_price_per_1m": model.get_effective_cache_creation_price(),
                        "cache_read_price_per_1m": model.get_effective_cache_read_price(),
                        "price_per_request": model.get_effective_price_per_request(),
                    },
                    "capabilities": {
                        "supports_vision": bool(model.supports_vision),
                        "supports_function_calling": bool(model.supports_function_calling),
                        "supports_streaming": bool(model.supports_streaming),
                    },
                    "is_active": bool(model.is_active),
                }

        models_list = [
            ProviderAvailableSourceModel(**global_models_dict[name])
            for name in sorted(global_models_dict.keys())
        ]

        return ProviderAvailableSourceModelsResponse(models=models_list, total=len(models_list))


@dataclass
class AdminBatchAssignModelsToProviderAdapter(AdminApiAdapter):
    """批量为 Provider 关联 GlobalModels"""

    provider_id: str
    payload: BatchAssignModelsToProviderRequest

    async def handle(self, context):  # type: ignore[override]
        db = context.db
        provider = db.query(Provider).filter(Provider.id == self.provider_id).first()
        if not provider:
            raise NotFoundException("Provider not found", "provider")

        success = []
        errors = []

        for global_model_id in self.payload.global_model_ids:
            try:
                global_model = (
                    db.query(GlobalModel).filter(GlobalModel.id == global_model_id).first()
                )
                if not global_model:
                    errors.append(
                        {"global_model_id": global_model_id, "error": "GlobalModel not found"}
                    )
                    continue

                # 检查是否已存在关联
                existing = (
                    db.query(Model)
                    .filter(
                        Model.provider_id == self.provider_id,
                        Model.global_model_id == global_model_id,
                    )
                    .first()
                )
                if existing:
                    errors.append(
                        {
                            "global_model_id": global_model_id,
                            "global_model_name": global_model.name,
                            "error": "Already associated",
                        }
                    )
                    continue

                # 创建新的 Model 记录，继承 GlobalModel 的配置
                new_model = Model(
                    provider_id=self.provider_id,
                    global_model_id=global_model_id,
                    provider_model_name=global_model.name,
                    is_active=True,
                )
                db.add(new_model)
                db.flush()

                # 自动创建模型别名：格式为 provider_name/global_model_name
                alias_name = f"{provider.name}/{global_model.name}"
                existing_alias = db.query(ModelMapping).filter(
                    ModelMapping.source_model == alias_name,
                    ModelMapping.provider_id == self.provider_id
                ).first()
                if not existing_alias:
                    new_alias = ModelMapping(
                        source_model=alias_name,
                        target_global_model_id=global_model_id,
                        provider_id=self.provider_id,
                        mapping_type="alias",
                        is_active=True
                    )
                    db.add(new_alias)

                success.append(
                    {
                        "global_model_id": global_model_id,
                        "global_model_name": global_model.name,
                        "model_id": new_model.id,
                        "auto_alias": alias_name,
                    }
                )
            except Exception as e:
                errors.append({"global_model_id": global_model_id, "error": str(e)})

        db.commit()
        logger.info(
            f"Batch assigned {len(success)} GlobalModels to provider {provider.name} by {context.user.username}"
        )

        return BatchAssignModelsToProviderResponse(success=success, errors=errors)


@dataclass
class AdminFetchRemoteModelsAdapter(AdminApiAdapter):
    """从远程 API 获取模型列表"""

    provider_id: str

    async def handle(self, context):  # type: ignore[override]
        db = context.db
        provider = db.query(Provider).filter(Provider.id == self.provider_id).first()
        if not provider:
            raise NotFoundException("Provider not found", "provider")

        # 获取第一个活跃的 Endpoint
        endpoint = (
            db.query(ProviderEndpoint)
            .filter(
                ProviderEndpoint.provider_id == self.provider_id,
                ProviderEndpoint.is_active == True,
            )
            .first()
        )
        if not endpoint:
            raise InvalidRequestException("No active endpoint found for this provider")

        # 获取该 Endpoint 的第一个活跃 API Key
        api_key_record = (
            db.query(ProviderAPIKey)
            .filter(
                ProviderAPIKey.endpoint_id == endpoint.id,
                ProviderAPIKey.is_active == True,
            )
            .first()
        )
        if not api_key_record:
            raise InvalidRequestException("No active API key found for this endpoint")

        # 解密 API Key
        try:
            decrypted_key = crypto_service.decrypt(api_key_record.api_key)
        except Exception as e:
            logger.error(f"Failed to decrypt API key: {e}")
            raise InvalidRequestException("Failed to decrypt API key")

        # 构建请求 URL 列表（尝试多种端点格式）
        base_url = endpoint.base_url.rstrip("/")
        
        # 对于不同的 API 格式使用不同的认证方式
        # OpenAI 格式: Authorization: Bearer <key>
        # Gemini 格式: ?key=<key> 查询参数
        endpoints_to_try = [
            {"url": f"{base_url}/v1/models", "auth_type": "bearer"},
            {"url": f"{base_url}/v1beta/models", "auth_type": "gemini"},
        ]

        all_models_dict: Dict[str, RemoteModelItem] = {}
        errors_list = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            for endpoint_config in endpoints_to_try:
                models_url = endpoint_config["url"]
                auth_type = endpoint_config["auth_type"]
                
                try:
                    # 根据认证类型构建请求
                    if auth_type == "gemini":
                        # Gemini API 使用查询参数认证
                        request_url = f"{models_url}?key={decrypted_key}"
                        headers = {"Content-Type": "application/json"}
                    else:
                        # OpenAI 格式使用 Bearer token
                        request_url = models_url
                        headers = {
                            "Authorization": f"Bearer {decrypted_key}",
                            "Content-Type": "application/json",
                        }
                    
                    response = await client.get(request_url, headers=headers)
                    response.raise_for_status()
                    data = response.json()

                    # 解析响应 - 支持 OpenAI 格式 (data 数组) 和 Gemini 格式 (models 数组)
                    models_data = data.get("data", []) or data.get("models", [])

                    for m in models_data:
                        # Gemini 格式使用 "name" 字段（如 "models/gemini-pro"），OpenAI 使用 "id"
                        model_id = m.get("id") or m.get("name", "")
                        # 去除 "models/" 前缀（Gemini 格式）
                        if model_id.startswith("models/"):
                            model_id = model_id[7:]

                        if model_id and model_id not in all_models_dict:
                            all_models_dict[model_id] = RemoteModelItem(
                                id=model_id,
                                object=m.get("object", "model"),
                                created=m.get("created"),
                                owned_by=m.get("owned_by") or m.get("owner"),
                            )

                    logger.info(f"Fetched {len(models_data)} models from {models_url}")

                except httpx.HTTPStatusError as e:
                    logger.warning(f"HTTP error fetching models from {models_url}: {e.response.status_code}")
                    errors_list.append(f"{models_url}: HTTP {e.response.status_code}")
                except httpx.RequestError as e:
                    logger.warning(f"Request error fetching models from {models_url}: {e}")
                    errors_list.append(f"{models_url}: {str(e)}")
                except Exception as e:
                    logger.warning(f"Error fetching models from {models_url}: {e}")
                    errors_list.append(f"{models_url}: {str(e)}")

        # 如果没有获取到任何模型，抛出错误
        if not all_models_dict:
            error_details = "; ".join(errors_list) if errors_list else "No models found"
            raise InvalidRequestException(f"Failed to fetch models from any endpoint: {error_details}")

        models = list(all_models_dict.values())
        logger.info(f"Fetched {len(models)} unique models for provider {provider.name}")

        return FetchRemoteModelsResponse(
            models=models,
            total=len(models),
            endpoint_id=endpoint.id,
            endpoint_base_url=endpoint.base_url,
        )


@dataclass
class AdminImportRemoteModelsAdapter(AdminApiAdapter):
    """导入远程模型（创建 GlobalModel 和 Provider Model）"""

    provider_id: str
    payload: ImportRemoteModelsRequest

    async def handle(self, context):  # type: ignore[override]
        db = context.db
        provider = db.query(Provider).filter(Provider.id == self.provider_id).first()
        if not provider:
            raise NotFoundException("Provider not found", "provider")

        success = []
        errors = []

        for model_id in self.payload.model_ids:
            try:
                # 检查是否已存在同名的 GlobalModel
                existing_global = (
                    db.query(GlobalModel)
                    .filter(GlobalModel.name == model_id)
                    .first()
                )

                if existing_global:
                    global_model = existing_global
                else:
                    # 创建新的 GlobalModel（价格默认为 0）
                    global_model = GlobalModel(
                        name=model_id,
                        display_name=model_id,
                        description=f"Auto-imported from {provider.display_name}",
                        default_tiered_pricing={
                            "tiers": [
                                {
                                    "up_to": None,
                                    "input_price_per_1m": 0.0,
                                    "output_price_per_1m": 0.0,
                                }
                            ]
                        },
                        is_active=True,
                    )
                    db.add(global_model)
                    db.flush()

                # 检查该 Provider 是否已有该模型
                existing_model = (
                    db.query(Model)
                    .filter(
                        Model.provider_id == self.provider_id,
                        Model.global_model_id == global_model.id,
                    )
                    .first()
                )

                if existing_model:
                    errors.append({
                        "model_id": model_id,
                        "error": "Already exists in this provider",
                    })
                    continue

                # 创建 Provider Model
                new_model = Model(
                    provider_id=self.provider_id,
                    global_model_id=global_model.id,
                    provider_model_name=model_id,
                    is_active=True,
                )
                db.add(new_model)
                db.flush()

                # 自动创建模型别名：格式为 provider_name/model_id
                alias_name = f"{provider.name}/{model_id}"
                existing_alias = db.query(ModelMapping).filter(
                    ModelMapping.source_model == alias_name,
                    ModelMapping.provider_id == self.provider_id
                ).first()
                if not existing_alias:
                    new_alias = ModelMapping(
                        source_model=alias_name,
                        target_global_model_id=global_model.id,
                        provider_id=self.provider_id,
                        mapping_type="alias",
                        is_active=True
                    )
                    db.add(new_alias)

                success.append({
                    "model_id": model_id,
                    "global_model_id": global_model.id,
                    "global_model_name": global_model.name,
                    "provider_model_id": new_model.id,
                    "created_global_model": not bool(existing_global),
                    "auto_alias": alias_name,
                })
            except Exception as e:
                logger.error(f"Error importing model {model_id}: {e}")
                errors.append({"model_id": model_id, "error": str(e)})

        db.commit()
        logger.info(
            f"Imported {len(success)} models to provider {provider.name} by {context.user.username}"
        )

        return ImportRemoteModelsResponse(success=success, errors=errors)

