"""
统一的插件中间件
负责协调所有插件的调用
"""

import time
from typing import Any, Awaitable, Callable, Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse

from src.config import config
from src.core.logger import logger
from src.database import get_db
from src.plugins.manager import get_plugin_manager
from src.plugins.rate_limit.base import RateLimitResult



class PluginMiddleware(BaseHTTPMiddleware):
    """
    统一的插件调用中间件

    职责:
    - 性能监控
    - 限流控制 (可选)

    注意: 认证由各路由通过 Depends() 显式声明，不在中间件层处理
    """

    def __init__(self, app: Any) -> None:
        super().__init__(app)
        self.plugin_manager = get_plugin_manager()

        # 从配置读取速率限制值
        self.llm_api_rate_limit = config.llm_api_rate_limit
        self.public_api_rate_limit = config.public_api_rate_limit

        # 完全跳过限流的路径（静态资源、文档等）
        self.skip_rate_limit_paths = [
            "/health",
            "/healthz",
            "/readyz",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/favicon.ico",
            "/static/",
            "/assets/",
            "/api/admin/",  # 管理后台已有JWT认证，不需要额外限流
            "/api/auth/",  # 认证端点（由路由层的 IPRateLimiter 处理）
            "/api/users/",  # 用户端点
            "/api/monitoring/",  # 监控端点
        ]

        # LLM API 端点（需要特殊的速率限制策略）
        self.llm_api_paths = [
            "/v1/messages",
            "/v1/chat/completions",
            "/v1/responses",
            "/v1/completions",
        ]

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[StarletteResponse]]
    ) -> StarletteResponse:
        """处理请求并调用相应插件"""

        # 健康检查/就绪检查必须永远可用：绕过 DB/限流/插件逻辑，避免被中间件拦截或拖慢
        if request.url.path in {"/healthz", "/healthz/", "/readyz", "/readyz/"}:
            return await call_next(request)

        # 记录请求开始时间
        start_time = time.time()
        request.state.request_id = request.headers.get("x-request-id", "")
        request.state.start_time = start_time

        # 从 request.app 获取 FastAPI 应用实例（而不是从 __init__ 的 app 参数）
        # 这样才能访问到真正的 FastAPI 实例和其 dependency_overrides
        db_func = get_db
        if hasattr(request, "app") and hasattr(request.app, "dependency_overrides"):
            if get_db in request.app.dependency_overrides:
                db_func = request.app.dependency_overrides[get_db]
                logger.debug("Using overridden get_db from app.dependency_overrides")

        # 创建数据库会话供需要的插件或后续处理使用
        db_gen = db_func()
        db = None
        response = None
        exception_to_raise = None

        try:
            # 获取数据库会话
            db = next(db_gen)
            request.state.db = db

            # 1. 限流插件调用（可选功能）
            rate_limit_result = await self._call_rate_limit_plugins(request)
            if rate_limit_result and not rate_limit_result.allowed:
                # 限流触发，返回429
                headers = rate_limit_result.headers or {}
                raise HTTPException(
                    status_code=429,
                    detail=rate_limit_result.message or "Rate limit exceeded",
                    headers=headers,
                )

            # 2. 预处理插件调用
            await self._call_pre_request_plugins(request)

            # 处理请求
            response = await call_next(request)

            # 由于禁用了 uvicorn access log，路由未命中（404）通常不会产生业务日志。
            # 对 Gemini v1beta 相关路径做一次轻量记录，便于排查客户端请求路径问题。
            try:
                if response.status_code == 404:
                    path = request.url.path
                    if path.startswith("/v1beta") or path.startswith("/v1/models"):
                        logger.warning(
                            f"[404] {request.method} {path} | request_id={getattr(request.state, 'request_id', '')}"
                        )
            except Exception:
                pass

            # 3. 提交关键数据库事务（在返回响应前）
            # 这确保了 Usage 记录、配额扣减等关键数据在响应返回前持久化
            try:
                db.commit()
            except Exception as commit_error:
                logger.error(f"关键事务提交失败: {commit_error}")
                db.rollback()
                # 返回 500 错误，因为数据可能不一致
                response = JSONResponse(
                    status_code=500,
                    content={
                        "type": "error",
                        "error": {
                            "type": "database_error",
                            "message": "数据保存失败，请重试",
                        },
                    },
                )
                # 跳过后处理插件，直接返回错误响应
                return response

            # 4. 后处理插件调用（监控等，非关键操作）
            # 这些操作失败不应影响用户响应
            await self._call_post_request_plugins(request, response, start_time)

            # 注意：不在此处添加限流响应头，因为在BaseHTTPMiddleware中
            # 响应返回后修改headers会导致Content-Length不匹配错误
            # 限流响应头已在返回429错误时正确包含（见上面的HTTPException）

        except RuntimeError as e:
            if str(e) == "No response returned.":
                if db:
                    db.rollback()

                logger.error("Downstream handler completed without returning a response")

                await self._call_error_plugins(request, e, start_time)

                if db:
                    try:
                        db.commit()
                    except Exception:
                        pass

                response = JSONResponse(
                    status_code=500,
                    content={
                        "type": "error",
                        "error": {
                            "type": "internal_error",
                            "message": "Internal server error: downstream handler returned no response.",
                        },
                    },
                )
            else:
                exception_to_raise = e

        except Exception as e:
            # 回滚数据库事务
            if db:
                db.rollback()

            # 错误处理插件调用
            await self._call_error_plugins(request, e, start_time)

            # 尝试提交错误日志
            if db:
                try:
                    db.commit()
                except:
                    pass

            exception_to_raise = e

        finally:
            # 确保数据库会话被正确关闭
            # 注意：需要安全地处理各种状态，避免 IllegalStateChangeError
            if db is not None:
                try:
                    # 检查会话是否可以安全地进行回滚
                    # 只有当没有进行中的事务操作时才尝试回滚
                    if db.is_active and not db.get_transaction().is_active:
                        # 事务不在活跃状态，可以安全回滚
                        pass
                    elif db.is_active:
                        # 事务在活跃状态，尝试回滚
                        try:
                            db.rollback()
                        except Exception as rollback_error:
                            # 回滚失败（可能是 commit 正在进行中），忽略错误
                            logger.debug(f"Rollback skipped: {rollback_error}")
                except Exception:
                    # 检查状态时出错，忽略
                    pass

            # 通过触发生成器的 finally 块来关闭会话（标准模式）
            # 这会调用 get_db() 的 finally 块，执行 db.close()
            try:
                next(db_gen, None)
            except StopIteration:
                # 正常情况：生成器已耗尽
                pass
            except Exception as cleanup_error:
                # 忽略 IllegalStateChangeError 等清理错误
                # 这些错误通常是由于事务状态不一致导致的，不影响业务逻辑
                if "IllegalStateChangeError" not in str(type(cleanup_error).__name__):
                    logger.warning(f"Database cleanup warning: {cleanup_error}")

        # 在 finally 块之后处理异常和响应
        if exception_to_raise:
            raise exception_to_raise

        return response

    def _get_client_ip(self, request: Request) -> str:
        """
        获取客户端 IP 地址，支持代理头
        """
        # 优先从代理头获取真实 IP
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            # X-Forwarded-For 可能包含多个 IP，取第一个
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()

        # 回退到直连 IP
        if request.client:
            return request.client.host

        return "unknown"

    def _is_llm_api_path(self, path: str) -> bool:
        """检查是否为 LLM API 端点"""
        for llm_path in self.llm_api_paths:
            if path.startswith(llm_path):
                return True
        return False

    async def _get_rate_limit_key_and_config(
        self, request: Request, db: Session
    ) -> tuple[Optional[str], Optional[int]]:
        """
        获取速率限制的key和配置

        策略说明:
        - /v1/messages, /v1/chat/completions 等 LLM API: 按 API Key 限流
        - /api/public/* 端点: 使用服务器级别 IP 限制
        - /api/admin/* 端点: 跳过（在 skip_rate_limit_paths 中跳过）
        - /api/auth/* 端点: 跳过（由路由层的 IPRateLimiter 处理）

        Returns:
            (key, rate_limit_value) - key用于标识限制对象，rate_limit_value是限制值
        """
        path = request.url.path

        # LLM API 端点: 按 API Key 或 IP 限流
        if self._is_llm_api_path(path):
            # 尝试从请求头获取 API Key
            auth_header = request.headers.get("authorization", "")
            api_key = request.headers.get("x-api-key", "")

            if auth_header.startswith("Bearer "):
                api_key = auth_header[7:]

            if api_key:
                # 使用 API Key 的哈希作为限制 key（避免日志泄露完整 key）
                import hashlib

                key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:16]
                key = f"llm_api_key:{key_hash}"
                request.state.rate_limit_key_type = "api_key"
            else:
                # 无 API Key 时使用 IP 限制（更严格）
                client_ip = self._get_client_ip(request)
                key = f"llm_ip:{client_ip}"
                request.state.rate_limit_key_type = "ip"

            rate_limit = self.llm_api_rate_limit
            request.state.rate_limit_value = rate_limit
            return key, rate_limit

        # /api/public/* 端点: 使用服务器级别 IP 地址作为限制 key
        if path.startswith("/api/public/"):
            client_ip = self._get_client_ip(request)
            key = f"public_ip:{client_ip}"
            rate_limit = self.public_api_rate_limit
            request.state.rate_limit_key_type = "public_ip"
            request.state.rate_limit_value = rate_limit
            return key, rate_limit

        # 其他端点不应用速率限制（或已在 skip_rate_limit_paths 中跳过）
        return None, None

    async def _call_rate_limit_plugins(self, request: Request) -> Optional[RateLimitResult]:
        """调用限流插件"""

        # 跳过不需要限流的路径（支持前缀匹配）
        for skip_path in self.skip_rate_limit_paths:
            if request.url.path == skip_path or request.url.path.startswith(skip_path):
                return None

        # 获取限流插件
        rate_limit_plugin = self.plugin_manager.get_plugin("rate_limit")
        if not rate_limit_plugin or not rate_limit_plugin.enabled:
            # 如果没有限流插件，允许通过
            return None

        # 获取数据库会话
        db = getattr(request.state, "db", None)
        if not db:
            logger.warning("速率限制检查：无法获取数据库会话")
            return None

        # 获取速率限制的key和配置（从数据库）
        key, rate_limit_value = await self._get_rate_limit_key_and_config(request, db)
        if not key:
            # 不需要限流的端点（如未分类路径），静默跳过
            return None

        try:
            # 检查速率限制，传入数据库配置的限制值
            result = await rate_limit_plugin.check_limit(
                key=key,
                endpoint=request.url.path,
                method=request.method,
                rate_limit=rate_limit_value,  # 传入数据库配置的限制值
            )
            # 类型检查：确保返回的是RateLimitResult类型
            if isinstance(result, RateLimitResult):
                # 如果检查通过，实际消耗令牌
                if result.allowed:
                    await rate_limit_plugin.consume(
                        key=key,
                        amount=1,
                        rate_limit=rate_limit_value,
                    )
                else:
                    # 限流触发，记录日志
                    logger.warning(f"速率限制触发: {getattr(request.state, 'rate_limit_key_type', 'unknown')}")
                return result
            return None
        except Exception as e:
            logger.error(f"Rate limit error: {e}")
            # 发生错误时允许请求通过
            return None

    async def _call_pre_request_plugins(self, request: Request) -> None:
        """调用请求前的插件（当前保留扩展点）"""
        pass

    async def _call_post_request_plugins(
        self, request: Request, response: StarletteResponse, start_time: float
    ) -> None:
        """调用请求后的插件"""

        duration = time.time() - start_time

        # 监控插件 - 记录指标
        monitor_plugin = self.plugin_manager.get_plugin("monitor")
        if monitor_plugin and monitor_plugin.enabled:
            try:
                monitor_labels = {
                    "method": request.method,
                    "endpoint": request.url.path,
                    "status": str(response.status_code),
                    "status_class": f"{response.status_code // 100}xx",
                }

                # 记录请求计数
                await monitor_plugin.increment(
                    "http_requests_total",
                    labels=monitor_labels,
                )

                # 记录请求时长
                await monitor_plugin.timing(
                    "http_request_duration",
                    duration,
                    labels=monitor_labels,
                )
            except Exception as e:
                logger.error(f"Monitor plugin failed: {e}")

    async def _call_error_plugins(
        self, request: Request, error: Exception, start_time: float
    ) -> None:
        """调用错误处理插件"""

        duration = time.time() - start_time

        # 通知插件 - 发送严重错误通知
        if not isinstance(error, HTTPException) or error.status_code >= 500:
            notification_plugin = self.plugin_manager.get_plugin("notification")
            if notification_plugin and notification_plugin.enabled:
                try:
                    await notification_plugin.send_error(
                        error=error,
                        context={
                            "endpoint": f"{request.method} {request.url.path}",
                            "request_id": request.state.request_id,
                            "duration": duration,
                        },
                    )
                except Exception as e:
                    logger.error(f"Notification plugin failed: {e}")
