"""分布式任务协调器，确保仅有一个 worker 执行特定任务"""

from __future__ import annotations

import asyncio
import os
import pathlib
import uuid
from typing import Dict, Optional

from src.core.logger import logger

try:
    import fcntl  # type: ignore
except ImportError:  # pragma: no cover - Windows 环境
    fcntl = None


class StartupTaskCoordinator:
    """利用 Redis 或文件锁，保证任务只在单个进程/实例中运行"""

    def __init__(self, redis_client=None, lock_dir: Optional[str] = None):
        self.redis = redis_client
        self._tokens: Dict[str, str] = {}
        self._file_handles: Dict[str, object] = {}
        self._lock_dir = pathlib.Path(lock_dir or os.getenv("TASK_LOCK_DIR", "./.locks"))
        if not self._lock_dir.exists():
            self._lock_dir.mkdir(parents=True, exist_ok=True)

    def _redis_key(self, name: str) -> str:
        return f"task_lock:{name}"

    async def acquire(self, name: str, ttl: Optional[int] = None) -> bool:
        ttl = ttl or int(os.getenv("TASK_COORDINATOR_LOCK_TTL", "86400"))

        if self.redis:
            token = str(uuid.uuid4())
            try:
                acquired = await self.redis.set(self._redis_key(name), token, nx=True, ex=ttl)
                if acquired:
                    self._tokens[name] = token
                    logger.info(f"任务 {name} 通过 Redis 锁独占执行")
                    return True
                return False
            except Exception as exc:  # pragma: no cover - Redis 异常回退
                logger.warning(f"Redis 锁获取失败，回退到文件锁: {exc}")

        return await self._acquire_file_lock(name)

    async def release(self, name: str):
        if self.redis and name in self._tokens:
            token = self._tokens.pop(name)
            script = """
            if redis.call('GET', KEYS[1]) == ARGV[1] then
                return redis.call('DEL', KEYS[1])
            end
            return 0
            """
            try:
                await self.redis.eval(script, 1, self._redis_key(name), token)
            except Exception as exc:  # pragma: no cover
                logger.warning(f"释放 Redis 锁失败: {exc}")

        handle = self._file_handles.pop(name, None)
        if handle and fcntl:
            try:
                fcntl.flock(handle, fcntl.LOCK_UN)
            finally:
                handle.close()

    async def _acquire_file_lock(self, name: str) -> bool:
        if fcntl is None:
            # 在不支持 fcntl 的平台上退化为单进程锁
            if name in self._file_handles:
                return False
            self._file_handles[name] = object()
            logger.warning("操作系统不支持文件锁，任务锁仅在当前进程生效")
            return True

        lock_path = self._lock_dir / f"{name}.lock"
        handle = open(lock_path, "a+")
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._file_handles[name] = handle
            logger.info(f"任务 {name} 使用文件锁独占执行")
            return True
        except BlockingIOError:
            handle.close()
            return False


async def ensure_singleton_task(name: str, redis_client=None, ttl: Optional[int] = None):
    """便捷协程，返回 (coordinator, acquired)"""

    coordinator = StartupTaskCoordinator(redis_client)
    acquired = await coordinator.acquire(name, ttl=ttl)
    return coordinator, acquired
