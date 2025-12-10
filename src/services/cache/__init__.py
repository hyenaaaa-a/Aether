"""
缓存服务模块

包含缓存后端、缓存亲和性、缓存同步等功能。

注意：由于循环依赖问题，部分类需要直接从子模块导入：
    from src.services.cache.affinity_manager import CacheAffinityManager
    from src.services.cache.aware_scheduler import CacheAwareScheduler
"""

# 只导出不会导致循环依赖的基础类
from src.services.cache.backend import BaseCacheBackend, LocalCache, RedisCache, get_cache_backend

__all__ = [
    "BaseCacheBackend",
    "LocalCache",
    "RedisCache",
    "get_cache_backend",
]
