"""
Provider Query API 端点
用于查询提供商的余额、使用记录等信息
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logger import logger
from src.database.database import get_db
from src.models.database import Provider, ProviderAPIKey, ProviderEndpoint, User

# 初始化适配器注册
from src.plugins.provider_query import init  # noqa
from src.plugins.provider_query import get_query_registry
from src.plugins.provider_query.base import QueryCapability
from src.utils.auth_utils import get_current_user

router = APIRouter(prefix="/provider-query", tags=["Provider Query"])


# ============ Request/Response Models ============


class BalanceQueryRequest(BaseModel):
    """余额查询请求"""

    provider_id: str
    api_key_id: Optional[str] = None  # 如果不指定，使用提供商的第一个可用 API Key


class UsageSummaryQueryRequest(BaseModel):
    """使用汇总查询请求"""

    provider_id: str
    api_key_id: Optional[str] = None
    period: str = "month"  # day, week, month, year


class ModelsQueryRequest(BaseModel):
    """模型列表查询请求"""

    provider_id: str
    api_key_id: Optional[str] = None


# ============ API Endpoints ============


@router.get("/adapters")
async def list_adapters(
    current_user: User = Depends(get_current_user),
):
    """
    获取所有可用的查询适配器

    Returns:
        适配器列表
    """
    registry = get_query_registry()
    adapters = registry.list_adapters()

    return {"success": True, "data": adapters}


@router.get("/capabilities/{provider_id}")
async def get_provider_capabilities(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取提供商支持的查询能力

    Args:
        provider_id: 提供商 ID

    Returns:
        支持的查询能力列表
    """
    # 获取提供商
    from sqlalchemy import select

    result = await db.execute(select(Provider).where(Provider.id == provider_id))
    provider = result.scalar_one_or_none()

    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    registry = get_query_registry()
    capabilities = registry.get_capabilities_for_provider(provider.name)

    if capabilities is None:
        return {
            "success": True,
            "data": {
                "provider_id": provider_id,
                "provider_name": provider.name,
                "capabilities": [],
                "has_adapter": False,
                "message": "No query adapter available for this provider",
            },
        }

    return {
        "success": True,
        "data": {
            "provider_id": provider_id,
            "provider_name": provider.name,
            "capabilities": [c.name for c in capabilities],
            "has_adapter": True,
        },
    }


@router.post("/balance")
async def query_balance(
    request: BalanceQueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    查询提供商余额

    Args:
        request: 查询请求

    Returns:
        余额信息
    """
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    # 获取提供商及其端点
    result = await db.execute(
        select(Provider)
        .options(selectinload(Provider.endpoints).selectinload(ProviderEndpoint.api_keys))
        .where(Provider.id == request.provider_id)
    )
    provider = result.scalar_one_or_none()

    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    # 获取 API Key
    api_key_value = None
    endpoint_config = None

    if request.api_key_id:
        # 查找指定的 API Key
        for endpoint in provider.endpoints:
            for api_key in endpoint.api_keys:
                if api_key.id == request.api_key_id:
                    api_key_value = api_key.api_key
                    endpoint_config = {
                        "base_url": endpoint.base_url,
                        "api_format": endpoint.api_format if endpoint.api_format else None,
                    }
                    break
            if api_key_value:
                break

        if not api_key_value:
            raise HTTPException(status_code=404, detail="API Key not found")
    else:
        # 使用第一个可用的 API Key
        for endpoint in provider.endpoints:
            if endpoint.is_active and endpoint.api_keys:
                for api_key in endpoint.api_keys:
                    if api_key.is_active:
                        api_key_value = api_key.api_key
                        endpoint_config = {
                            "base_url": endpoint.base_url,
                            "api_format": endpoint.api_format if endpoint.api_format else None,
                        }
                        break
                if api_key_value:
                    break

        if not api_key_value:
            raise HTTPException(status_code=400, detail="No active API Key found for this provider")

    # 查询余额
    registry = get_query_registry()
    query_result = await registry.query_provider_balance(
        provider_type=provider.name, api_key=api_key_value, endpoint_config=endpoint_config
    )

    if not query_result.success:
        logger.warning(f"Balance query failed for provider {provider.name}: {query_result.error}")

    return {
        "success": query_result.success,
        "data": query_result.to_dict(),
        "provider": {
            "id": provider.id,
            "name": provider.name,
            "display_name": provider.display_name,
        },
    }


@router.post("/usage-summary")
async def query_usage_summary(
    request: UsageSummaryQueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    查询提供商使用汇总

    Args:
        request: 查询请求

    Returns:
        使用汇总信息
    """
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    # 获取提供商及其端点
    result = await db.execute(
        select(Provider)
        .options(selectinload(Provider.endpoints).selectinload(ProviderEndpoint.api_keys))
        .where(Provider.id == request.provider_id)
    )
    provider = result.scalar_one_or_none()

    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    # 获取 API Key（逻辑同上）
    api_key_value = None
    endpoint_config = None

    if request.api_key_id:
        for endpoint in provider.endpoints:
            for api_key in endpoint.api_keys:
                if api_key.id == request.api_key_id:
                    api_key_value = api_key.api_key
                    endpoint_config = {"base_url": endpoint.base_url}
                    break
            if api_key_value:
                break

        if not api_key_value:
            raise HTTPException(status_code=404, detail="API Key not found")
    else:
        for endpoint in provider.endpoints:
            if endpoint.is_active and endpoint.api_keys:
                for api_key in endpoint.api_keys:
                    if api_key.is_active:
                        api_key_value = api_key.api_key
                        endpoint_config = {"base_url": endpoint.base_url}
                        break
                if api_key_value:
                    break

        if not api_key_value:
            raise HTTPException(status_code=400, detail="No active API Key found for this provider")

    # 查询使用汇总
    registry = get_query_registry()
    query_result = await registry.query_provider_usage(
        provider_type=provider.name,
        api_key=api_key_value,
        period=request.period,
        endpoint_config=endpoint_config,
    )

    return {
        "success": query_result.success,
        "data": query_result.to_dict(),
        "provider": {
            "id": provider.id,
            "name": provider.name,
            "display_name": provider.display_name,
        },
    }


@router.post("/models")
async def query_available_models(
    request: ModelsQueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    查询提供商可用模型

    Args:
        request: 查询请求

    Returns:
        模型列表
    """
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    # 获取提供商及其端点
    result = await db.execute(
        select(Provider)
        .options(selectinload(Provider.endpoints).selectinload(ProviderEndpoint.api_keys))
        .where(Provider.id == request.provider_id)
    )
    provider = result.scalar_one_or_none()

    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    # 获取 API Key
    api_key_value = None
    endpoint_config = None

    if request.api_key_id:
        for endpoint in provider.endpoints:
            for api_key in endpoint.api_keys:
                if api_key.id == request.api_key_id:
                    api_key_value = api_key.api_key
                    endpoint_config = {"base_url": endpoint.base_url}
                    break
            if api_key_value:
                break

        if not api_key_value:
            raise HTTPException(status_code=404, detail="API Key not found")
    else:
        for endpoint in provider.endpoints:
            if endpoint.is_active and endpoint.api_keys:
                for api_key in endpoint.api_keys:
                    if api_key.is_active:
                        api_key_value = api_key.api_key
                        endpoint_config = {"base_url": endpoint.base_url}
                        break
                if api_key_value:
                    break

        if not api_key_value:
            raise HTTPException(status_code=400, detail="No active API Key found for this provider")

    # 查询模型
    registry = get_query_registry()
    adapter = registry.get_adapter_for_provider(provider.name)

    if not adapter:
        raise HTTPException(
            status_code=400, detail=f"No query adapter available for provider: {provider.name}"
        )

    query_result = await adapter.query_available_models(
        api_key=api_key_value, endpoint_config=endpoint_config
    )

    return {
        "success": query_result.success,
        "data": query_result.to_dict(),
        "provider": {
            "id": provider.id,
            "name": provider.name,
            "display_name": provider.display_name,
        },
    }


@router.delete("/cache/{provider_id}")
async def clear_query_cache(
    provider_id: str,
    api_key_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    清除查询缓存

    Args:
        provider_id: 提供商 ID
        api_key_id: 可选，指定清除某个 API Key 的缓存

    Returns:
        清除结果
    """
    from sqlalchemy import select

    # 获取提供商
    result = await db.execute(select(Provider).where(Provider.id == provider_id))
    provider = result.scalar_one_or_none()

    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    registry = get_query_registry()
    adapter = registry.get_adapter_for_provider(provider.name)

    if adapter:
        if api_key_id:
            # 获取 API Key 值来清除缓存
            from sqlalchemy.orm import selectinload

            result = await db.execute(select(ProviderAPIKey).where(ProviderAPIKey.id == api_key_id))
            api_key = result.scalar_one_or_none()
            if api_key:
                adapter.clear_cache(api_key.api_key)
        else:
            adapter.clear_cache()

    return {"success": True, "message": "Cache cleared successfully"}
