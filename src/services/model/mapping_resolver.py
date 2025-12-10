"""
模型映射解析服务

负责统一的模型别名/降级解析，按优先级顺序：
1. 映射（mapping）：Provider 特定 → 全局
2. 别名（alias）：Provider 特定 → 全局
3. 直接匹配 GlobalModel.name

支持特性：
- 带缓存（本地或 Redis），减少数据库访问
- 提供模糊匹配能力，用于提示相似模型
"""

from __future__ import annotations

import os
from typing import List, Optional, Tuple

from src.core.logger import logger
from sqlalchemy.orm import Session

from src.config.constants import CacheSize, CacheTTL
from src.core.logger import logger
from src.models.database import GlobalModel, ModelMapping
from src.services.cache.backend import BaseCacheBackend, get_cache_backend


class ModelMappingResolver:
    """统一的 ModelMapping 解析服务（可跨进程共享缓存）。"""

    def __init__(self, cache_ttl: int = CacheTTL.MODEL_MAPPING, cache_backend_type: str = "auto"):
        self._cache_ttl = cache_ttl
        self._cache_backend_type = cache_backend_type
        self._mapping_cache: Optional[BaseCacheBackend] = None
        self._global_model_cache: Optional[BaseCacheBackend] = None
        self._initialized = False
        self._stats = {
            "mapping_hits": 0,
            "mapping_misses": 0,
            "global_hits": 0,
            "global_misses": 0,
        }

    async def _ensure_initialized(self):
        if self._initialized:
            return

        self._mapping_cache = await get_cache_backend(
            name="model_mapping_resolver:mapping",
            backend_type=self._cache_backend_type,
            max_size=CacheSize.MODEL_MAPPING,
            ttl=self._cache_ttl,
        )
        self._global_model_cache = await get_cache_backend(
            name="model_mapping_resolver:global",
            backend_type=self._cache_backend_type,
            max_size=CacheSize.MODEL_MAPPING,
            ttl=self._cache_ttl,
        )
        self._initialized = True
        logger.debug(f"[ModelMappingResolver] 缓存后端已初始化: {self._mapping_cache.get_stats()['backend']}")

    def _cache_key(self, source_model: str, provider_id: Optional[str]) -> str:
        return f"{provider_id or 'global'}:{source_model}"

    async def _lookup_target_global_model_id(
        self,
        db: Session,
        source_model: str,
        provider_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        按优先级查找目标 GlobalModel ID：
        1. 映射（mapping_type='mapping'）：Provider 特定 → 全局
        2. 别名（mapping_type='alias'）：Provider 特定 → 全局
        3. 直接匹配 GlobalModel.name
        """
        await self._ensure_initialized()
        cache_key = self._cache_key(source_model, provider_id)
        cached = await self._mapping_cache.get(cache_key)
        if cached is not None:
            self._stats["mapping_hits"] += 1
            return cached or None

        self._stats["mapping_misses"] += 1

        target_id: Optional[str] = None

        # 优先级 1：查找映射（mapping_type='mapping'）
        # 1.1 Provider 特定映射
        if provider_id:
            mapping = (
                db.query(ModelMapping)
                .filter(
                    ModelMapping.source_model == source_model,
                    ModelMapping.provider_id == provider_id,
                    ModelMapping.mapping_type == "mapping",
                    ModelMapping.is_active == True,
                )
                .first()
            )
            if mapping:
                target_id = mapping.target_global_model_id
                logger.debug(f"[MappingResolver] 命中 Provider 映射: {source_model} -> {target_id[:8]}...")

        # 1.2 全局映射
        if not target_id:
            mapping = (
                db.query(ModelMapping)
                .filter(
                    ModelMapping.source_model == source_model,
                    ModelMapping.provider_id.is_(None),
                    ModelMapping.mapping_type == "mapping",
                    ModelMapping.is_active == True,
                )
                .first()
            )
            if mapping:
                target_id = mapping.target_global_model_id
                logger.debug(f"[MappingResolver] 命中全局映射: {source_model} -> {target_id[:8]}...")

        # 优先级 2：查找别名（mapping_type='alias'）
        # 2.1 Provider 特定别名
        if not target_id and provider_id:
            alias = (
                db.query(ModelMapping)
                .filter(
                    ModelMapping.source_model == source_model,
                    ModelMapping.provider_id == provider_id,
                    ModelMapping.mapping_type == "alias",
                    ModelMapping.is_active == True,
                )
                .first()
            )
            if alias:
                target_id = alias.target_global_model_id
                logger.debug(f"[MappingResolver] 命中 Provider 别名: {source_model} -> {target_id[:8]}...")

        # 2.2 全局别名
        if not target_id:
            alias = (
                db.query(ModelMapping)
                .filter(
                    ModelMapping.source_model == source_model,
                    ModelMapping.provider_id.is_(None),
                    ModelMapping.mapping_type == "alias",
                    ModelMapping.is_active == True,
                )
                .first()
            )
            if alias:
                target_id = alias.target_global_model_id
                logger.debug(f"[MappingResolver] 命中全局别名: {source_model} -> {target_id[:8]}...")

        # 优先级 3：直接匹配 GlobalModel.name
        if not target_id:
            global_model = (
                db.query(GlobalModel)
                .filter(
                    GlobalModel.name == source_model,
                    GlobalModel.is_active == True,
                )
                .first()
            )
            if global_model:
                target_id = global_model.id
                logger.debug(f"[MappingResolver] 直接匹配 GlobalModel: {source_model}")

        cached_value = target_id if target_id is not None else ""
        await self._mapping_cache.set(cache_key, cached_value, self._cache_ttl)
        return target_id

    async def resolve_to_global_model_name(
        self,
        db: Session,
        source_model: str,
        provider_id: Optional[str] = None,
    ) -> str:
        """解析模型名/别名为 GlobalModel.name。未找到时返回原始输入。"""
        target_id = await self._lookup_target_global_model_id(db, source_model, provider_id)
        if not target_id:
            return source_model

        await self._ensure_initialized()
        cached_name = await self._global_model_cache.get(target_id)
        if cached_name:
            self._stats["global_hits"] += 1
            return cached_name

        self._stats["global_misses"] += 1
        global_model = (
            db.query(GlobalModel)
            .filter(GlobalModel.id == target_id, GlobalModel.is_active == True)
            .first()
        )
        if global_model:
            await self._global_model_cache.set(target_id, global_model.name, self._cache_ttl)
            return global_model.name

        return source_model

    async def get_global_model_by_request(
        self,
        db: Session,
        source_model: str,
        provider_id: Optional[str] = None,
    ) -> Optional[GlobalModel]:
        """解析并返回 GlobalModel 对象（绑定当前 Session）。"""
        target_id = await self._lookup_target_global_model_id(db, source_model, provider_id)
        if not target_id:
            return None

        global_model = (
            db.query(GlobalModel)
            .filter(GlobalModel.id == target_id, GlobalModel.is_active == True)
            .first()
        )
        return global_model

    async def get_global_model_with_mapping_info(
        self,
        db: Session,
        source_model: str,
        provider_id: Optional[str] = None,
    ) -> Tuple[Optional[GlobalModel], bool]:
        """
        解析并返回 GlobalModel 对象，同时返回是否发生了映射。

        Args:
            db: 数据库会话
            source_model: 用户请求的模型名
            provider_id: Provider ID（可选）

        Returns:
            (global_model, is_mapped) - GlobalModel 对象和是否发生了映射
            is_mapped=True 表示 source_model 通过 mapping 规则映射到了不同的模型
            is_mapped=False 表示 source_model 直接匹配或通过 alias 匹配
        """
        await self._ensure_initialized()

        # 先检查是否存在 mapping 类型的映射规则
        has_mapping = False

        # 检查 Provider 特定映射
        if provider_id:
            mapping = (
                db.query(ModelMapping)
                .filter(
                    ModelMapping.source_model == source_model,
                    ModelMapping.provider_id == provider_id,
                    ModelMapping.mapping_type == "mapping",
                    ModelMapping.is_active == True,
                )
                .first()
            )
            if mapping:
                has_mapping = True

        # 检查全局映射
        if not has_mapping:
            mapping = (
                db.query(ModelMapping)
                .filter(
                    ModelMapping.source_model == source_model,
                    ModelMapping.provider_id.is_(None),
                    ModelMapping.mapping_type == "mapping",
                    ModelMapping.is_active == True,
                )
                .first()
            )
            if mapping:
                has_mapping = True

        # 获取 GlobalModel
        global_model = await self.get_global_model_by_request(db, source_model, provider_id)

        return global_model, has_mapping

    async def get_global_model_direct(
        self,
        db: Session,
        source_model: str,
    ) -> Optional[GlobalModel]:
        """
        直接通过模型名获取 GlobalModel，不应用任何映射规则。
        仅查找 alias 和直接匹配。

        Args:
            db: 数据库会话
            source_model: 模型名

        Returns:
            GlobalModel 对象或 None
        """
        # 优先级 1：查找别名（alias）
        # 全局别名
        alias = (
            db.query(ModelMapping)
            .filter(
                ModelMapping.source_model == source_model,
                ModelMapping.provider_id.is_(None),
                ModelMapping.mapping_type == "alias",
                ModelMapping.is_active == True,
            )
            .first()
        )
        if alias:
            global_model = (
                db.query(GlobalModel)
                .filter(GlobalModel.id == alias.target_global_model_id, GlobalModel.is_active == True)
                .first()
            )
            if global_model:
                return global_model

        # 优先级 2：直接匹配 GlobalModel.name
        global_model = (
            db.query(GlobalModel)
            .filter(
                GlobalModel.name == source_model,
                GlobalModel.is_active == True,
            )
            .first()
        )
        return global_model

    def find_similar_models(
        self,
        db: Session,
        invalid_model: str,
        limit: int = 3,
        threshold: float = 0.4,
    ) -> List[Tuple[str, float]]:
        """用于提示相似的 GlobalModel.name。"""
        from difflib import SequenceMatcher

        all_models = db.query(GlobalModel.name).filter(GlobalModel.is_active == True).all()
        similarities: List[Tuple[str, float]] = []
        invalid_lower = invalid_model.lower()

        for model in all_models:
            model_name = model.name
            ratio = SequenceMatcher(None, invalid_lower, model_name.lower()).ratio()
            if invalid_lower in model_name.lower() or model_name.lower() in invalid_lower:
                ratio += 0.2
            if ratio >= threshold:
                similarities.append((model_name, ratio))

        similarities.sort(key=lambda item: item[1], reverse=True)
        return similarities[:limit]

    async def invalidate_mapping_cache(self, source_model: str, provider_id: Optional[str] = None):
        await self._ensure_initialized()
        keys = [self._cache_key(source_model, provider_id)]
        if provider_id:
            keys.append(self._cache_key(source_model, None))
        for key in keys:
            await self._mapping_cache.delete(key)

    async def invalidate_global_model_cache(self, global_model_id: Optional[str] = None):
        await self._ensure_initialized()
        if global_model_id:
            await self._global_model_cache.delete(global_model_id)
        else:
            await self._global_model_cache.clear()

    async def clear_cache(self):
        await self._ensure_initialized()
        await self._mapping_cache.clear()
        await self._global_model_cache.clear()

    def get_stats(self) -> dict:
        total_mapping = self._stats["mapping_hits"] + self._stats["mapping_misses"]
        total_global = self._stats["global_hits"] + self._stats["global_misses"]
        stats = {
            "mapping_hit_rate": (
                self._stats["mapping_hits"] / total_mapping if total_mapping else 0.0
            ),
            "global_hit_rate": self._stats["global_hits"] / total_global if total_global else 0.0,
            "stats": self._stats,
        }
        if self._initialized:
            stats["mapping_cache_backend"] = self._mapping_cache.get_stats()
            stats["global_cache_backend"] = self._global_model_cache.get_stats()
        return stats


_model_mapping_resolver: Optional[ModelMappingResolver] = None


def get_model_mapping_resolver(
    cache_ttl: int = 300, cache_backend_type: Optional[str] = None
) -> ModelMappingResolver:
    global _model_mapping_resolver

    if _model_mapping_resolver is None:
        if cache_backend_type is None:
            cache_backend_type = os.getenv("ALIAS_CACHE_BACKEND", "auto")
        _model_mapping_resolver = ModelMappingResolver(
            cache_ttl=cache_ttl,
            cache_backend_type=cache_backend_type,
        )
        logger.debug(f"[ModelMappingResolver] 初始化（cache_ttl={cache_ttl}s, backend={cache_backend_type})")

        # 注册到缓存失效服务
        try:
            from src.services.cache.invalidation import get_cache_invalidation_service

            cache_service = get_cache_invalidation_service()
            cache_service.set_mapping_resolver(_model_mapping_resolver)
        except Exception as exc:
            logger.warning(f"[ModelMappingResolver] 注册缓存失效服务失败: {exc}")

    return _model_mapping_resolver


async def resolve_model_to_global_name(
    db: Session,
    source_model: str,
    provider_id: Optional[str] = None,
) -> str:
    resolver = get_model_mapping_resolver()
    return await resolver.resolve_to_global_model_name(db, source_model, provider_id)


async def get_global_model_by_request(
    db: Session,
    source_model: str,
    provider_id: Optional[str] = None,
) -> Optional[GlobalModel]:
    resolver = get_model_mapping_resolver()
    return await resolver.get_global_model_by_request(db, source_model, provider_id)
