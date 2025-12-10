"""
异步数据库工具
提供在异步上下文中安全使用同步数据库操作的工具
"""

import asyncio
from functools import wraps
from typing import Any, Callable, TypeVar

T = TypeVar("T")


async def run_in_executor(func: Callable[..., T], *args, **kwargs) -> T:
    """
    在线程池中运行同步函数,避免阻塞事件循环

    用法:
        result = await run_in_executor(some_sync_function, arg1, arg2)
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


def async_wrap_sync_db(func: Callable[..., T]) -> Callable[..., Any]:
    """
    装饰器:包装同步数据库函数为异步函数

    用法:
        @async_wrap_sync_db
        def get_user(db: Session, user_id: int):
            return db.query(User).filter(User.id == user_id).first()

        # 现在可以在异步上下文中调用
        user = await get_user(db, 123)
    """

    @wraps(func)
    async def wrapper(*args, **kwargs):
        return await run_in_executor(func, *args, **kwargs)

    return wrapper
