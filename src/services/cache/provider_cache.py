"""
Provider 配置缓存服务 - 减少 Provider/Endpoint/APIKey 查询
"""

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from src.config.constants import CacheTTL
from src.core.cache_service import CacheKeys, CacheService
from src.core.logger import logger
from src.models.database import Provider, ProviderAPIKey, ProviderEndpoint



class ProviderCacheService:
    """Provider 配置缓存服务"""

    # 缓存 TTL（秒）- 使用统一常量
    CACHE_TTL = CacheTTL.PROVIDER

    @staticmethod
    async def get_provider_by_id(db: Session, provider_id: str) -> Optional[Provider]:
        """
        获取 Provider（带缓存）

        Args:
            db: 数据库会话
            provider_id: Provider ID

        Returns:
            Provider 对象或 None
        """
        cache_key = CacheKeys.provider_by_id(provider_id)

        # 1. 尝试从缓存获取
        cached_data = await CacheService.get(cache_key)
        if cached_data:
            logger.debug(f"Provider 缓存命中: {provider_id}")
            return ProviderCacheService._dict_to_provider(cached_data)

        # 2. 缓存未命中，查询数据库
        provider = db.query(Provider).filter(Provider.id == provider_id).first()

        # 3. 写入缓存
        if provider:
            provider_dict = ProviderCacheService._provider_to_dict(provider)
            await CacheService.set(
                cache_key, provider_dict, ttl_seconds=ProviderCacheService.CACHE_TTL
            )
            logger.debug(f"Provider 已缓存: {provider_id}")

        return provider

    @staticmethod
    async def get_endpoint_by_id(db: Session, endpoint_id: str) -> Optional[ProviderEndpoint]:
        """
        获取 Endpoint（带缓存）

        Args:
            db: 数据库会话
            endpoint_id: Endpoint ID

        Returns:
            ProviderEndpoint 对象或 None
        """
        cache_key = CacheKeys.endpoint_by_id(endpoint_id)

        # 1. 尝试从缓存获取
        cached_data = await CacheService.get(cache_key)
        if cached_data:
            logger.debug(f"Endpoint 缓存命中: {endpoint_id}")
            return ProviderCacheService._dict_to_endpoint(cached_data)

        # 2. 缓存未命中，查询数据库
        endpoint = db.query(ProviderEndpoint).filter(ProviderEndpoint.id == endpoint_id).first()

        # 3. 写入缓存
        if endpoint:
            endpoint_dict = ProviderCacheService._endpoint_to_dict(endpoint)
            await CacheService.set(
                cache_key, endpoint_dict, ttl_seconds=ProviderCacheService.CACHE_TTL
            )
            logger.debug(f"Endpoint 已缓存: {endpoint_id}")

        return endpoint

    @staticmethod
    async def get_api_key_by_id(db: Session, api_key_id: str) -> Optional[ProviderAPIKey]:
        """
        获取 API Key（带缓存）

        Args:
            db: 数据库会话
            api_key_id: API Key ID

        Returns:
            ProviderAPIKey 对象或 None
        """
        cache_key = CacheKeys.api_key_by_id(api_key_id)

        # 1. 尝试从缓存获取
        cached_data = await CacheService.get(cache_key)
        if cached_data:
            logger.debug(f"API Key 缓存命中: {api_key_id}")
            return ProviderCacheService._dict_to_api_key(cached_data)

        # 2. 缓存未命中，查询数据库
        api_key = db.query(ProviderAPIKey).filter(ProviderAPIKey.id == api_key_id).first()

        # 3. 写入缓存
        if api_key:
            api_key_dict = ProviderCacheService._api_key_to_dict(api_key)
            await CacheService.set(
                cache_key, api_key_dict, ttl_seconds=ProviderCacheService.CACHE_TTL
            )
            logger.debug(f"API Key 已缓存: {api_key_id}")

        return api_key

    @staticmethod
    async def invalidate_provider_cache(provider_id: str):
        """
        清除 Provider 缓存

        Args:
            provider_id: Provider ID
        """
        await CacheService.delete(CacheKeys.provider_by_id(provider_id))
        logger.debug(f"Provider 缓存已清除: {provider_id}")

    @staticmethod
    async def invalidate_endpoint_cache(endpoint_id: str):
        """
        清除 Endpoint 缓存

        Args:
            endpoint_id: Endpoint ID
        """
        await CacheService.delete(CacheKeys.endpoint_by_id(endpoint_id))
        logger.debug(f"Endpoint 缓存已清除: {endpoint_id}")

    @staticmethod
    async def invalidate_api_key_cache(api_key_id: str):
        """
        清除 API Key 缓存

        Args:
            api_key_id: API Key ID
        """
        await CacheService.delete(CacheKeys.api_key_by_id(api_key_id))
        logger.debug(f"API Key 缓存已清除: {api_key_id}")

    @staticmethod
    def _provider_to_dict(provider: Provider) -> dict:
        """将 Provider 对象转换为字典（用于缓存）"""
        return {
            "id": provider.id,
            "name": provider.name,
            "api_format": provider.api_format,
            "base_url": provider.base_url,
            "is_active": provider.is_active,
            "priority": provider.priority,
            "rpm_limit": provider.rpm_limit,
            "rpm_used": provider.rpm_used,
            "rpm_reset_at": provider.rpm_reset_at.isoformat() if provider.rpm_reset_at else None,
            "config": provider.config,
            "description": provider.description,
        }

    @staticmethod
    def _dict_to_provider(provider_dict: dict) -> Provider:
        """从字典重建 Provider 对象（分离的对象，不在 Session 中）"""
        from datetime import datetime

        provider = Provider(
            id=provider_dict["id"],
            name=provider_dict["name"],
            api_format=provider_dict["api_format"],
            base_url=provider_dict.get("base_url"),
            is_active=provider_dict["is_active"],
            priority=provider_dict.get("priority", 0),
            rpm_limit=provider_dict.get("rpm_limit"),
            rpm_used=provider_dict.get("rpm_used", 0),
            config=provider_dict.get("config"),
            description=provider_dict.get("description"),
        )

        if provider_dict.get("rpm_reset_at"):
            provider.rpm_reset_at = datetime.fromisoformat(provider_dict["rpm_reset_at"])

        return provider

    @staticmethod
    def _endpoint_to_dict(endpoint: ProviderEndpoint) -> dict:
        """将 Endpoint 对象转换为字典"""
        return {
            "id": endpoint.id,
            "provider_id": endpoint.provider_id,
            "name": endpoint.name,
            "base_url": endpoint.base_url,
            "is_active": endpoint.is_active,
            "priority": endpoint.priority,
            "weight": endpoint.weight,
            "custom_path": endpoint.custom_path,
            "config": endpoint.config,
        }

    @staticmethod
    def _dict_to_endpoint(endpoint_dict: dict) -> ProviderEndpoint:
        """从字典重建 Endpoint 对象"""
        endpoint = ProviderEndpoint(
            id=endpoint_dict["id"],
            provider_id=endpoint_dict["provider_id"],
            name=endpoint_dict["name"],
            base_url=endpoint_dict["base_url"],
            is_active=endpoint_dict["is_active"],
            priority=endpoint_dict.get("priority", 0),
            weight=endpoint_dict.get("weight", 1.0),
            custom_path=endpoint_dict.get("custom_path"),
            config=endpoint_dict.get("config"),
        )
        return endpoint

    @staticmethod
    def _api_key_to_dict(api_key: ProviderAPIKey) -> dict:
        """将 API Key 对象转换为字典"""
        return {
            "id": api_key.id,
            "endpoint_id": api_key.endpoint_id,
            "key_value": api_key.key_value,
            "is_active": api_key.is_active,
            "max_rpm": api_key.max_rpm,
            "current_rpm": api_key.current_rpm,
            "health_score": api_key.health_score,
            "circuit_breaker_state": api_key.circuit_breaker_state,
            "adaptive_concurrency_limit": api_key.adaptive_concurrency_limit,
        }

    @staticmethod
    def _dict_to_api_key(api_key_dict: dict) -> ProviderAPIKey:
        """从字典重建 API Key 对象"""
        api_key = ProviderAPIKey(
            id=api_key_dict["id"],
            endpoint_id=api_key_dict["endpoint_id"],
            key_value=api_key_dict["key_value"],
            is_active=api_key_dict["is_active"],
            max_rpm=api_key_dict.get("max_rpm"),
            current_rpm=api_key_dict.get("current_rpm", 0),
            health_score=api_key_dict.get("health_score", 1.0),
            circuit_breaker_state=api_key_dict.get("circuit_breaker_state"),
            adaptive_concurrency_limit=api_key_dict.get("adaptive_concurrency_limit"),
        )
        return api_key
