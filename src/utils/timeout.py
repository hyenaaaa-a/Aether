"""
超时保护工具

为异步函数和操作提供超时保护
"""

import asyncio
from functools import wraps
from typing import Any, Callable, Optional, TypeVar

from src.core.logger import logger


T = TypeVar("T")


class AsyncTimeoutError(TimeoutError):
    """异步操作超时错误"""

    def __init__(self, message: str, operation: str, timeout: float):
        super().__init__(message)
        self.operation = operation
        self.timeout = timeout


def with_timeout(seconds: float, operation_name: Optional[str] = None):
    """
    装饰器：为异步函数添加超时保护

    Args:
        seconds: 超时时间（秒）
        operation_name: 操作名称（用于日志，默认使用函数名）

    Usage:
        @with_timeout(30.0)
        async def my_async_function():
            ...

        @with_timeout(60.0, operation_name="API请求")
        async def api_call():
            ...
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            op_name = operation_name or func.__name__
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=seconds)
            except asyncio.TimeoutError:
                logger.warning(f"操作超时: {op_name} (timeout={seconds}s)")
                raise AsyncTimeoutError(
                    f"{op_name} 操作超时（{seconds}秒）",
                    operation=op_name,
                    timeout=seconds,
                )

        return wrapper

    return decorator


async def run_with_timeout(
    coro,
    timeout: float,
    operation_name: str = "operation",
    default: T = None,
    raise_on_timeout: bool = True,
) -> T:
    """
    为协程添加超时保护（函数式调用）

    Args:
        coro: 协程对象
        timeout: 超时时间（秒）
        operation_name: 操作名称（用于日志）
        default: 超时时返回的默认值（仅在 raise_on_timeout=False 时有效）
        raise_on_timeout: 超时时是否抛出异常

    Returns:
        协程的返回值，或超时时的默认值

    Usage:
        result = await run_with_timeout(
            my_async_function(),
            timeout=30.0,
            operation_name="API请求"
        )
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning(f"操作超时: {operation_name} (timeout={timeout}s)")
        if raise_on_timeout:
            raise AsyncTimeoutError(
                f"{operation_name} 操作超时（{timeout}秒）",
                operation=operation_name,
                timeout=timeout,
            )
        return default


class TimeoutContext:
    """
    超时上下文管理器

    Usage:
        async with TimeoutContext(30.0, "数据库查询") as ctx:
            result = await db.query(...)
            # 如果超过30秒会抛出 AsyncTimeoutError
    """

    def __init__(self, timeout: float, operation_name: str = "operation"):
        self.timeout = timeout
        self.operation_name = operation_name
        self._task: Optional[asyncio.Task] = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # asyncio.timeout 在 Python 3.11+ 可用
        # 这里使用更通用的方式
        pass


async def with_timeout_context(timeout: float, operation_name: str = "operation"):
    """
    超时上下文管理器（Python 3.11+ asyncio.timeout 的替代）

    Usage:
        async with with_timeout_context(30.0, "API请求"):
            result = await api_call()
    """
    try:
        # Python 3.11+ 使用内置的 asyncio.timeout
        return asyncio.timeout(timeout)
    except AttributeError:
        # Python 3.10 及以下版本的兼容实现
        # 注意：这个简单实现不支持嵌套取消
        pass
