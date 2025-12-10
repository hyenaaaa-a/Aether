"""
封装请求执行逻辑，包含并发控制与链路追踪。
"""

import time
from dataclasses import dataclass
from typing import Any, Callable, Optional, Union

from sqlalchemy.orm import Session

from src.core.enums import APIFormat
from src.core.exceptions import ConcurrencyLimitError
from src.core.logger import logger
from src.services.health.monitor import health_monitor
from src.services.rate_limit.adaptive_reservation import get_adaptive_reservation_manager
from src.services.request.candidate import RequestCandidateService



@dataclass
class ExecutionContext:
    candidate_id: str
    candidate_index: int
    provider_id: str
    endpoint_id: str
    key_id: str
    user_id: Optional[str]
    api_key_id: Optional[str]
    is_cached_user: bool
    start_time: Optional[float] = None
    elapsed_ms: Optional[int] = None
    concurrent_requests: Optional[int] = None


@dataclass
class ExecutionResult:
    response: Any
    context: ExecutionContext


class ExecutionError(Exception):
    def __init__(self, cause: Exception, context: ExecutionContext):
        super().__init__(str(cause))
        self.cause = cause
        self.context = context


class RequestExecutor:
    def __init__(self, db: Session, concurrency_manager, adaptive_manager):
        self.db = db
        self.concurrency_manager = concurrency_manager
        self.adaptive_manager = adaptive_manager

    async def execute(
        self,
        *,
        candidate,
        candidate_id: str,
        candidate_index: int,
        user_api_key,
        request_func: Callable,
        request_id: Optional[str],
        api_format: Union[str, APIFormat],
        model_name: str,
        is_stream: bool = False,
    ) -> ExecutionResult:
        provider = candidate.provider
        endpoint = candidate.endpoint
        key = candidate.key
        is_cached_user = bool(candidate.is_cached)

        # 标记候选开始执行
        RequestCandidateService.mark_candidate_started(
            db=self.db,
            candidate_id=candidate_id,
        )

        context = ExecutionContext(
            candidate_id=candidate_id,
            candidate_index=candidate_index,
            provider_id=provider.id,
            endpoint_id=endpoint.id,
            key_id=key.id,
            user_id=user_api_key.user_id,
            api_key_id=user_api_key.id,
            is_cached_user=is_cached_user,
        )

        try:
            # 计算动态预留比例
            reservation_manager = get_adaptive_reservation_manager()
            # 获取当前并发数用于计算负载
            try:
                _, current_key_concurrent = await self.concurrency_manager.get_current_concurrency(
                    endpoint_id=endpoint.id,
                    key_id=key.id,
                )
            except Exception as e:
                logger.debug(f"获取并发数失败（用于预留计算）: {e}")
                current_key_concurrent = 0

            # 获取有效的并发限制（自适应或固定）
            effective_key_limit = (
                key.learned_max_concurrent if key.max_concurrent is None else key.max_concurrent
            )

            reservation_result = reservation_manager.calculate_reservation(
                key=key,
                current_concurrent=current_key_concurrent,
                effective_limit=effective_key_limit,
            )
            dynamic_reservation_ratio = reservation_result.ratio

            logger.debug(f"[Executor] 动态预留: key={key.id[:8]}..., "
                f"ratio={dynamic_reservation_ratio:.0%}, phase={reservation_result.phase}, "
                f"confidence={reservation_result.confidence:.0%}")

            async with self.concurrency_manager.concurrency_guard(
                endpoint_id=endpoint.id,
                endpoint_max_concurrent=endpoint.max_concurrent,
                key_id=key.id,
                key_max_concurrent=effective_key_limit,
                is_cached_user=is_cached_user,
                cache_reservation_ratio=dynamic_reservation_ratio,
            ):
                try:
                    _, key_concurrent = await self.concurrency_manager.get_current_concurrency(
                        endpoint_id=endpoint.id,
                        key_id=key.id,
                    )
                except Exception as e:
                    logger.debug(f"获取并发数失败（guard 内）: {e}")
                    key_concurrent = None

                context.concurrent_requests = key_concurrent
                context.start_time = time.time()

                response = await request_func(provider, endpoint, key)

                context.elapsed_ms = int((time.time() - context.start_time) * 1000)

                health_monitor.record_success(
                    db=self.db,
                    key_id=key.id,
                    response_time_ms=context.elapsed_ms,
                )

                # 自适应模式：max_concurrent = NULL
                if key.max_concurrent is None and key_concurrent is not None:
                    self.adaptive_manager.handle_success(
                        db=self.db,
                        key=key,
                        current_concurrent=key_concurrent,
                    )

                # 根据是否为流式请求，标记不同状态
                if is_stream:
                    # 流式请求：标记为 streaming 状态
                    # 此时连接已建立但流传输尚未完成
                    # success 状态会在流完成后由 _record_stream_stats 方法标记
                    RequestCandidateService.mark_candidate_streaming(
                        db=self.db,
                        candidate_id=candidate_id,
                        status_code=200,
                        concurrent_requests=key_concurrent,
                    )
                else:
                    # 非流式请求：标记为 success 状态
                    RequestCandidateService.mark_candidate_success(
                        db=self.db,
                        candidate_id=candidate_id,
                        status_code=200,
                        latency_ms=context.elapsed_ms,
                        concurrent_requests=key_concurrent,
                        extra_data={
                            "is_cached_user": is_cached_user,
                            "model_name": model_name,
                            "api_format": (
                                api_format.value if isinstance(api_format, APIFormat) else api_format
                            ),
                        },
                    )

                return ExecutionResult(response=response, context=context)
        except ConcurrencyLimitError as exc:
            raise ExecutionError(exc, context) from exc
        except Exception as exc:
            context.elapsed_ms = (
                int((time.time() - context.start_time) * 1000)
                if context.start_time is not None
                else None
            )
            raise ExecutionError(exc, context) from exc
