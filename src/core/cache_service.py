"""
缓存服务 - 统一的缓存抽象层
"""

import json
from datetime import timedelta
from typing import Any, Optional

from src.clients.redis_client import get_redis_client
from src.core.logger import logger



class CacheService:
    """缓存服务"""

    @staticmethod
    async def get(key: str) -> Optional[Any]:
        """
        从缓存获取数据

        Args:
            key: 缓存键

        Returns:
            缓存的值，如果不存在则返回 None
        """
        try:
            redis = await get_redis_client(require_redis=False)
            if not redis:
                return None

            value = await redis.get(key)
            if value:
                # 尝试 JSON 反序列化
                try:
                    return json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    return value

            return None

        except Exception as e:
            logger.warning(f"缓存读取失败: {key} - {e}")
            return None

    @staticmethod
    async def set(key: str, value: Any, ttl_seconds: int = 60) -> bool:
        """
        设置缓存

        Args:
            key: 缓存键
            value: 缓存值
            ttl_seconds: 过期时间（秒），默认 60 秒

        Returns:
            是否设置成功
        """
        try:
            redis = await get_redis_client(require_redis=False)
            if not redis:
                return False

            # JSON 序列化
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            elif not isinstance(value, (str, bytes)):
                value = str(value)

            await redis.setex(key, ttl_seconds, value)
            return True

        except Exception as e:
            logger.warning(f"缓存写入失败: {key} - {e}")
            return False

    @staticmethod
    async def delete(key: str) -> bool:
        """
        删除缓存

        Args:
            key: 缓存键

        Returns:
            是否删除成功
        """
        try:
            redis = await get_redis_client(require_redis=False)
            if not redis:
                return False

            await redis.delete(key)
            return True

        except Exception as e:
            logger.warning(f"缓存删除失败: {key} - {e}")
            return False

    @staticmethod
    async def exists(key: str) -> bool:
        """
        检查缓存是否存在

        Args:
            key: 缓存键

        Returns:
            是否存在
        """
        try:
            redis = await get_redis_client(require_redis=False)
            if not redis:
                return False

            return await redis.exists(key) > 0

        except Exception as e:
            logger.warning(f"缓存检查失败: {key} - {e}")
            return False


# 缓存键前缀
class CacheKeys:
    """缓存键定义"""

    # User 缓存（TTL 60秒）
    USER_BY_ID = "user:id:{user_id}"
    USER_BY_EMAIL = "user:email:{email}"

    # API Key 缓存（TTL 30秒）
    APIKEY_HASH = "apikey:hash:{key_hash}"
    APIKEY_AUTH = "apikey:auth:{key_hash}"  # 认证结果缓存

    # Provider 配置缓存（TTL 300秒）
    PROVIDER_BY_ID = "provider:id:{provider_id}"
    ENDPOINT_BY_ID = "endpoint:id:{endpoint_id}"
    API_KEY_BY_ID = "api_key:id:{api_key_id}"

    @staticmethod
    def user_by_id(user_id: str) -> str:
        """User ID 缓存键"""
        return CacheKeys.USER_BY_ID.format(user_id=user_id)

    @staticmethod
    def user_by_email(email: str) -> str:
        """User Email 缓存键"""
        return CacheKeys.USER_BY_EMAIL.format(email=email)

    @staticmethod
    def apikey_hash(key_hash: str) -> str:
        """API Key Hash 缓存键"""
        return CacheKeys.APIKEY_HASH.format(key_hash=key_hash)

    @staticmethod
    def apikey_auth(key_hash: str) -> str:
        """API Key 认证结果缓存键"""
        return CacheKeys.APIKEY_AUTH.format(key_hash=key_hash)

    @staticmethod
    def provider_by_id(provider_id: str) -> str:
        """Provider ID 缓存键"""
        return CacheKeys.PROVIDER_BY_ID.format(provider_id=provider_id)

    @staticmethod
    def endpoint_by_id(endpoint_id: str) -> str:
        """Endpoint ID 缓存键"""
        return CacheKeys.ENDPOINT_BY_ID.format(endpoint_id=endpoint_id)

    @staticmethod
    def api_key_by_id(api_key_id: str) -> str:
        """API Key ID 缓存键"""
        return CacheKeys.API_KEY_BY_ID.format(api_key_id=api_key_id)
