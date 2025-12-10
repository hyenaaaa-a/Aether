"""
健康监控器 - Endpoint 和 Key 的健康度追踪

功能：
1. 基于滑动窗口的错误率计算
2. 三态熔断器：关闭 -> 打开 -> 半开 -> 关闭
3. 半开状态允许少量请求验证服务恢复
4. 提供健康度查询和管理 API
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from src.config.constants import CircuitBreakerDefaults
from src.core.batch_committer import get_batch_committer
from src.core.logger import logger
from src.core.metrics import health_open_circuits
from src.models.database import ProviderAPIKey, ProviderEndpoint


class CircuitState:
    """熔断器状态"""

    CLOSED = "closed"  # 关闭（正常）
    OPEN = "open"  # 打开（熔断）
    HALF_OPEN = "half_open"  # 半开（验证恢复）


class HealthMonitor:
    """健康监控器（滑动窗口 + 半开状态模式）"""

    # === 滑动窗口配置 ===
    WINDOW_SIZE = int(os.getenv("HEALTH_WINDOW_SIZE", str(CircuitBreakerDefaults.WINDOW_SIZE)))
    WINDOW_SECONDS = int(
        os.getenv("HEALTH_WINDOW_SECONDS", str(CircuitBreakerDefaults.WINDOW_SECONDS))
    )
    MIN_REQUESTS = int(
        os.getenv("HEALTH_MIN_REQUESTS", str(CircuitBreakerDefaults.MIN_REQUESTS_FOR_DECISION))
    )
    ERROR_RATE_THRESHOLD = float(
        os.getenv("HEALTH_ERROR_RATE_THRESHOLD", str(CircuitBreakerDefaults.ERROR_RATE_THRESHOLD))
    )

    # === 半开状态配置 ===
    HALF_OPEN_DURATION = int(
        os.getenv(
            "HEALTH_HALF_OPEN_DURATION", str(CircuitBreakerDefaults.HALF_OPEN_DURATION_SECONDS)
        )
    )
    HALF_OPEN_SUCCESS_THRESHOLD = int(
        os.getenv(
            "HEALTH_HALF_OPEN_SUCCESS", str(CircuitBreakerDefaults.HALF_OPEN_SUCCESS_THRESHOLD)
        )
    )
    HALF_OPEN_FAILURE_THRESHOLD = int(
        os.getenv(
            "HEALTH_HALF_OPEN_FAILURE", str(CircuitBreakerDefaults.HALF_OPEN_FAILURE_THRESHOLD)
        )
    )

    # === 恢复配置 ===
    INITIAL_RECOVERY_SECONDS = int(
        os.getenv(
            "HEALTH_INITIAL_RECOVERY_SECONDS", str(CircuitBreakerDefaults.INITIAL_RECOVERY_SECONDS)
        )
    )
    RECOVERY_BACKOFF = int(
        os.getenv(
            "HEALTH_RECOVERY_BACKOFF", str(CircuitBreakerDefaults.RECOVERY_BACKOFF_MULTIPLIER)
        )
    )
    MAX_RECOVERY_SECONDS = int(
        os.getenv("HEALTH_MAX_RECOVERY_SECONDS", str(CircuitBreakerDefaults.MAX_RECOVERY_SECONDS))
    )

    # === 兼容旧参数（用于健康度展示）===
    SUCCESS_INCREMENT = float(
        os.getenv("HEALTH_SUCCESS_INCREMENT", str(CircuitBreakerDefaults.SUCCESS_INCREMENT))
    )
    FAILURE_DECREMENT = float(
        os.getenv("HEALTH_FAILURE_DECREMENT", str(CircuitBreakerDefaults.FAILURE_DECREMENT))
    )
    PROBE_RECOVERY_SCORE = float(
        os.getenv("HEALTH_PROBE_RECOVERY_SCORE", str(CircuitBreakerDefaults.PROBE_RECOVERY_SCORE))
    )

    # === 其他配置 ===
    ALLOW_AUTO_RECOVER = os.getenv("HEALTH_AUTO_RECOVER_ENABLED", "true").lower() == "true"
    CIRCUIT_HISTORY_LIMIT = int(os.getenv("HEALTH_CIRCUIT_HISTORY_LIMIT", "200"))

    # 进程级别状态缓存
    _circuit_history: List[Dict[str, Any]] = []
    _open_circuit_keys: int = 0

    # ==================== 核心方法 ====================

    @classmethod
    def record_success(
        cls,
        db: Session,
        key_id: Optional[str] = None,
        response_time_ms: Optional[int] = None,
    ) -> None:
        """记录成功请求"""
        try:
            if not key_id:
                return

            key = db.query(ProviderAPIKey).filter(ProviderAPIKey.id == key_id).first()
            if not key:
                return

            now = datetime.now(timezone.utc)
            now_ts = now.timestamp()

            # 1. 更新滑动窗口
            cls._add_to_window(key, now_ts, success=True)

            # 2. 更新健康度（用于展示）
            new_score = min(float(key.health_score or 0) + cls.SUCCESS_INCREMENT, 1.0)
            key.health_score = new_score  # type: ignore[assignment]

            # 3. 更新统计
            key.consecutive_failures = 0  # type: ignore[assignment]
            key.last_failure_at = None  # type: ignore[assignment]
            key.success_count = int(key.success_count or 0) + 1  # type: ignore[assignment]
            key.request_count = int(key.request_count or 0) + 1  # type: ignore[assignment]
            if response_time_ms:
                key.total_response_time_ms = int(key.total_response_time_ms or 0) + response_time_ms  # type: ignore[assignment]

            # 4. 处理熔断器状态
            state = cls._get_circuit_state(key, now)

            if state == CircuitState.HALF_OPEN:
                # 半开状态：记录成功
                key.half_open_successes = int(key.half_open_successes or 0) + 1  # type: ignore[assignment]

                if int(key.half_open_successes or 0) >= cls.HALF_OPEN_SUCCESS_THRESHOLD:
                    # 达到成功阈值，关闭熔断器
                    cls._close_circuit(key, now, reason="半开状态验证成功")

            elif state == CircuitState.OPEN:
                # 打开状态下的成功（探测成功），进入半开状态
                cls._enter_half_open(key, now)

            db.flush()
            get_batch_committer().mark_dirty(db)

        except Exception as e:
            logger.error(f"记录成功请求失败: {e}")
            db.rollback()

    @classmethod
    def record_failure(
        cls,
        db: Session,
        key_id: Optional[str] = None,
        error_type: Optional[str] = None,
    ) -> None:
        """记录失败请求"""
        try:
            if not key_id:
                return

            key = db.query(ProviderAPIKey).filter(ProviderAPIKey.id == key_id).first()
            if not key:
                return

            now = datetime.now(timezone.utc)
            now_ts = now.timestamp()

            # 1. 更新滑动窗口
            cls._add_to_window(key, now_ts, success=False)

            # 2. 更新健康度（用于展示）
            new_score = max(float(key.health_score or 1) - cls.FAILURE_DECREMENT, 0.0)
            key.health_score = new_score  # type: ignore[assignment]

            # 3. 更新统计
            key.consecutive_failures = int(key.consecutive_failures or 0) + 1  # type: ignore[assignment]
            key.last_failure_at = now  # type: ignore[assignment]
            key.error_count = int(key.error_count or 0) + 1  # type: ignore[assignment]
            key.request_count = int(key.request_count or 0) + 1  # type: ignore[assignment]

            # 4. 处理熔断器状态
            state = cls._get_circuit_state(key, now)

            if state == CircuitState.HALF_OPEN:
                # 半开状态：记录失败
                key.half_open_failures = int(key.half_open_failures or 0) + 1  # type: ignore[assignment]

                if int(key.half_open_failures or 0) >= cls.HALF_OPEN_FAILURE_THRESHOLD:
                    # 达到失败阈值，重新打开熔断器
                    cls._open_circuit(key, now, reason="半开状态验证失败")

            elif state == CircuitState.CLOSED:
                # 关闭状态：检查是否需要打开熔断器
                error_rate = cls._calculate_error_rate(key, now_ts)
                window = key.request_results_window or []

                if len(window) >= cls.MIN_REQUESTS and error_rate >= cls.ERROR_RATE_THRESHOLD:
                    cls._open_circuit(
                        key, now, reason=f"错误率 {error_rate:.0%} 超过阈值 {cls.ERROR_RATE_THRESHOLD:.0%}"
                    )

            logger.debug(
                f"[WARN] Key 健康度下降: {key_id[:8]}... -> {new_score:.2f} "
                f"(连续失败 {key.consecutive_failures} 次, error_type={error_type})"
            )

            db.flush()
            get_batch_committer().mark_dirty(db)

        except Exception as e:
            logger.error(f"记录失败请求失败: {e}")
            db.rollback()

    # ==================== 滑动窗口方法 ====================

    @classmethod
    def _add_to_window(cls, key: ProviderAPIKey, now_ts: float, success: bool) -> None:
        """添加请求结果到滑动窗口"""
        window: List[Dict[str, Any]] = key.request_results_window or []

        # 添加新记录
        window.append({"ts": now_ts, "ok": success})

        # 清理过期记录
        cutoff_ts = now_ts - cls.WINDOW_SECONDS
        window = [r for r in window if r["ts"] > cutoff_ts]

        # 限制窗口大小
        if len(window) > cls.WINDOW_SIZE:
            window = window[-cls.WINDOW_SIZE :]

        key.request_results_window = window  # type: ignore[assignment]

    @classmethod
    def _calculate_error_rate(cls, key: ProviderAPIKey, now_ts: float) -> float:
        """计算滑动窗口内的错误率"""
        window: List[Dict[str, Any]] = key.request_results_window or []
        if not window:
            return 0.0

        # 过滤过期记录
        cutoff_ts = now_ts - cls.WINDOW_SECONDS
        valid_records = [r for r in window if r["ts"] > cutoff_ts]

        if not valid_records:
            return 0.0

        failures = sum(1 for r in valid_records if not r["ok"])
        return failures / len(valid_records)

    # ==================== 熔断器状态方法 ====================

    @classmethod
    def _get_circuit_state(cls, key: ProviderAPIKey, now: datetime) -> str:
        """获取当前熔断器状态"""
        if not key.circuit_breaker_open:
            return CircuitState.CLOSED

        # 检查是否在半开状态
        if key.half_open_until and now < key.half_open_until:
            return CircuitState.HALF_OPEN

        # 检查是否到了探测时间（进入半开）
        if key.next_probe_at and now >= key.next_probe_at:
            return CircuitState.HALF_OPEN

        return CircuitState.OPEN

    @classmethod
    def _open_circuit(cls, key: ProviderAPIKey, now: datetime, reason: str) -> None:
        """打开熔断器"""
        was_open = key.circuit_breaker_open

        key.circuit_breaker_open = True  # type: ignore[assignment]
        key.circuit_breaker_open_at = now  # type: ignore[assignment]
        key.half_open_until = None  # type: ignore[assignment]
        key.half_open_successes = 0  # type: ignore[assignment]
        key.half_open_failures = 0  # type: ignore[assignment]

        # 计算下次探测时间（进入半开状态的时间）
        consecutive = int(key.consecutive_failures or 0)
        recovery_seconds = cls._calculate_recovery_seconds(consecutive)
        key.next_probe_at = now + timedelta(seconds=recovery_seconds)  # type: ignore[assignment]

        if not was_open:
            cls._open_circuit_keys += 1
            health_open_circuits.set(cls._open_circuit_keys)

        logger.warning(
            f"[OPEN] Key 熔断器打开: {key.id[:8]}... | 原因: {reason} | "
            f"{recovery_seconds}秒后进入半开状态"
        )

        cls._push_circuit_event(
            {
                "event": "opened",
                "key_id": key.id,
                "reason": reason,
                "recovery_seconds": recovery_seconds,
                "timestamp": now.isoformat(),
            }
        )

    @classmethod
    def _enter_half_open(cls, key: ProviderAPIKey, now: datetime) -> None:
        """进入半开状态"""
        key.half_open_until = now + timedelta(seconds=cls.HALF_OPEN_DURATION)  # type: ignore[assignment]
        key.half_open_successes = 0  # type: ignore[assignment]
        key.half_open_failures = 0  # type: ignore[assignment]

        logger.info(
            f"[HALF-OPEN] Key 进入半开状态: {key.id[:8]}... | "
            f"需要 {cls.HALF_OPEN_SUCCESS_THRESHOLD} 次成功关闭熔断器"
        )

        cls._push_circuit_event(
            {
                "event": "half_open",
                "key_id": key.id,
                "timestamp": now.isoformat(),
            }
        )

    @classmethod
    def _close_circuit(cls, key: ProviderAPIKey, now: datetime, reason: str) -> None:
        """关闭熔断器"""
        key.circuit_breaker_open = False  # type: ignore[assignment]
        key.circuit_breaker_open_at = None  # type: ignore[assignment]
        key.next_probe_at = None  # type: ignore[assignment]
        key.half_open_until = None  # type: ignore[assignment]
        key.half_open_successes = 0  # type: ignore[assignment]
        key.half_open_failures = 0  # type: ignore[assignment]

        # 快速恢复健康度
        key.health_score = max(float(key.health_score or 0), cls.PROBE_RECOVERY_SCORE)  # type: ignore[assignment]

        cls._open_circuit_keys = max(0, cls._open_circuit_keys - 1)
        health_open_circuits.set(cls._open_circuit_keys)

        logger.info(f"[CLOSED] Key 熔断器关闭: {key.id[:8]}... | 原因: {reason}")

        cls._push_circuit_event(
            {
                "event": "closed",
                "key_id": key.id,
                "reason": reason,
                "timestamp": now.isoformat(),
            }
        )

    @classmethod
    def _calculate_recovery_seconds(cls, consecutive_failures: int) -> int:
        """计算恢复等待时间（指数退避）"""
        # 指数退避：30s -> 60s -> 120s -> 240s -> 300s（上限）
        exponent = min(consecutive_failures // 5, 4)  # 每5次失败增加一级
        seconds = cls.INITIAL_RECOVERY_SECONDS * (cls.RECOVERY_BACKOFF**exponent)
        return min(int(seconds), cls.MAX_RECOVERY_SECONDS)

    # ==================== 状态查询方法 ====================

    @classmethod
    def is_circuit_breaker_closed(cls, resource: ProviderAPIKey) -> bool:
        """检查熔断器是否允许请求通过"""
        if not resource.circuit_breaker_open:
            return True

        now = datetime.now(timezone.utc)
        state = cls._get_circuit_state(resource, now)

        # 半开状态允许请求通过
        if state == CircuitState.HALF_OPEN:
            return True

        # 检查是否到了探测时间
        if resource.next_probe_at and now >= resource.next_probe_at:
            # 自动进入半开状态
            cls._enter_half_open(resource, now)
            return True

        return False

    @classmethod
    def get_circuit_breaker_status(
        cls, resource: ProviderAPIKey
    ) -> Tuple[bool, Optional[str]]:
        """获取熔断器详细状态"""
        if not resource.circuit_breaker_open:
            return True, None

        now = datetime.now(timezone.utc)
        state = cls._get_circuit_state(resource, now)

        if state == CircuitState.HALF_OPEN:
            successes = int(resource.half_open_successes or 0)
            return True, f"半开状态({successes}/{cls.HALF_OPEN_SUCCESS_THRESHOLD}成功)"

        if resource.next_probe_at:
            if now >= resource.next_probe_at:
                return True, None

            remaining = resource.next_probe_at - now
            remaining_seconds = int(remaining.total_seconds())
            if remaining_seconds >= 60:
                time_str = f"{remaining_seconds // 60}min{remaining_seconds % 60}s"
            else:
                time_str = f"{remaining_seconds}s"
            return False, f"熔断中({time_str}后半开)"

        return False, "熔断中"

    @classmethod
    def get_key_health(cls, db: Session, key_id: str) -> Optional[Dict[str, Any]]:
        """获取 Key 健康状态"""
        try:
            key = db.query(ProviderAPIKey).filter(ProviderAPIKey.id == key_id).first()
            if not key:
                return None

            now = datetime.now(timezone.utc)
            now_ts = now.timestamp()

            # 计算当前错误率
            error_rate = cls._calculate_error_rate(key, now_ts)
            window = key.request_results_window or []
            valid_window = [r for r in window if r["ts"] > now_ts - cls.WINDOW_SECONDS]

            avg_response_time_ms = (
                int(key.total_response_time_ms or 0) / int(key.success_count or 1)
                if key.success_count
                else 0
            )

            return {
                "key_id": key.id,
                "health_score": float(key.health_score or 1.0),
                "error_rate": error_rate,
                "window_size": len(valid_window),
                "consecutive_failures": int(key.consecutive_failures or 0),
                "last_failure_at": key.last_failure_at.isoformat() if key.last_failure_at else None,
                "is_active": key.is_active,
                "statistics": {
                    "request_count": int(key.request_count or 0),
                    "success_count": int(key.success_count or 0),
                    "error_count": int(key.error_count or 0),
                    "success_rate": (
                        int(key.success_count or 0) / int(key.request_count or 1)
                        if key.request_count
                        else 0.0
                    ),
                    "avg_response_time_ms": round(avg_response_time_ms, 2),
                },
                "circuit_breaker": {
                    "state": cls._get_circuit_state(key, now),
                    "open": key.circuit_breaker_open,
                    "open_at": (
                        key.circuit_breaker_open_at.isoformat()
                        if key.circuit_breaker_open_at
                        else None
                    ),
                    "next_probe_at": (
                        key.next_probe_at.isoformat() if key.next_probe_at else None
                    ),
                    "half_open_until": (
                        key.half_open_until.isoformat() if key.half_open_until else None
                    ),
                    "half_open_successes": int(key.half_open_successes or 0),
                    "half_open_failures": int(key.half_open_failures or 0),
                },
            }

        except Exception as e:
            logger.error(f"获取 Key 健康状态失败: {e}")
            return None

    @classmethod
    def get_endpoint_health(cls, db: Session, endpoint_id: str) -> Optional[Dict[str, Any]]:
        """获取 Endpoint 健康状态"""
        try:
            endpoint = (
                db.query(ProviderEndpoint).filter(ProviderEndpoint.id == endpoint_id).first()
            )
            if not endpoint:
                return None

            return {
                "endpoint_id": endpoint.id,
                "health_score": float(endpoint.health_score or 1.0),
                "consecutive_failures": int(endpoint.consecutive_failures or 0),
                "last_failure_at": (
                    endpoint.last_failure_at.isoformat() if endpoint.last_failure_at else None
                ),
                "is_active": endpoint.is_active,
            }

        except Exception as e:
            logger.error(f"获取 Endpoint 健康状态失败: {e}")
            return None

    # ==================== 管理方法 ====================

    @classmethod
    def reset_health(cls, db: Session, key_id: Optional[str] = None) -> bool:
        """重置健康度"""
        try:
            if key_id:
                key = db.query(ProviderAPIKey).filter(ProviderAPIKey.id == key_id).first()
                if key:
                    key.health_score = 1.0  # type: ignore[assignment]
                    key.consecutive_failures = 0  # type: ignore[assignment]
                    key.last_failure_at = None  # type: ignore[assignment]
                    key.request_results_window = []  # type: ignore[assignment]
                    key.circuit_breaker_open = False  # type: ignore[assignment]
                    key.circuit_breaker_open_at = None  # type: ignore[assignment]
                    key.next_probe_at = None  # type: ignore[assignment]
                    key.half_open_until = None  # type: ignore[assignment]
                    key.half_open_successes = 0  # type: ignore[assignment]
                    key.half_open_failures = 0  # type: ignore[assignment]
                    logger.info(f"[RESET] 重置 Key 健康度: {key_id}")

            db.flush()
            get_batch_committer().mark_dirty(db)
            return True

        except Exception as e:
            logger.error(f"重置健康度失败: {e}")
            db.rollback()
            return False

    @classmethod
    def manually_enable(cls, db: Session, key_id: Optional[str] = None) -> bool:
        """手动启用 Key"""
        try:
            if key_id:
                key = db.query(ProviderAPIKey).filter(ProviderAPIKey.id == key_id).first()
                if key and not key.is_active:
                    key.is_active = True  # type: ignore[assignment]
                    key.consecutive_failures = 0  # type: ignore[assignment]
                    logger.info(f"[OK] 手动启用 Key: {key_id}")

            db.flush()
            get_batch_committer().mark_dirty(db)
            return True

        except Exception as e:
            logger.error(f"手动启用失败: {e}")
            db.rollback()
            return False

    @classmethod
    def get_all_health_status(cls, db: Session) -> Dict[str, Any]:
        """获取所有健康状态摘要"""
        try:
            endpoint_stats = db.query(
                func.count(ProviderEndpoint.id).label("total"),
                func.sum(case((ProviderEndpoint.is_active == True, 1), else_=0)).label("active"),
                func.sum(case((ProviderEndpoint.health_score < 0.5, 1), else_=0)).label(
                    "unhealthy"
                ),
            ).first()

            key_stats = db.query(
                func.count(ProviderAPIKey.id).label("total"),
                func.sum(case((ProviderAPIKey.is_active == True, 1), else_=0)).label("active"),
                func.sum(case((ProviderAPIKey.health_score < 0.5, 1), else_=0)).label("unhealthy"),
                func.sum(case((ProviderAPIKey.circuit_breaker_open == True, 1), else_=0)).label(
                    "circuit_open"
                ),
            ).first()

            return {
                "endpoints": {
                    "total": endpoint_stats.total or 0 if endpoint_stats else 0,
                    "active": int(endpoint_stats.active or 0) if endpoint_stats else 0,
                    "unhealthy": int(endpoint_stats.unhealthy or 0) if endpoint_stats else 0,
                },
                "keys": {
                    "total": key_stats.total or 0 if key_stats else 0,
                    "active": int(key_stats.active or 0) if key_stats else 0,
                    "unhealthy": int(key_stats.unhealthy or 0) if key_stats else 0,
                    "circuit_open": int(key_stats.circuit_open or 0) if key_stats else 0,
                },
            }

        except Exception as e:
            logger.error(f"获取健康状态摘要失败: {e}")
            return {
                "endpoints": {"total": 0, "active": 0, "unhealthy": 0},
                "keys": {"total": 0, "active": 0, "unhealthy": 0, "circuit_open": 0},
            }

    # ==================== 历史记录方法 ====================

    @classmethod
    def _push_circuit_event(cls, event: Dict[str, Any]) -> None:
        cls._circuit_history.append(event)
        if len(cls._circuit_history) > cls.CIRCUIT_HISTORY_LIMIT:
            cls._circuit_history.pop(0)

    @classmethod
    def get_circuit_history(cls, limit: int = 50) -> List[Dict[str, Any]]:
        if limit <= 0:
            return []
        return cls._circuit_history[-limit:]

    # ==================== 兼容旧方法 ====================

    @classmethod
    def is_eligible_for_probe(
        cls,
        db: Session,
        endpoint_id: Optional[str] = None,
        key_id: Optional[str] = None,
    ) -> bool:
        """检查是否有资格进行探测（兼容旧接口）"""
        if not cls.ALLOW_AUTO_RECOVER:
            return False

        if endpoint_id:
            return False  # Endpoint 不支持探测

        if key_id:
            key = db.query(ProviderAPIKey).filter(ProviderAPIKey.id == key_id).first()
            if key and key.circuit_breaker_open:
                now = datetime.now(timezone.utc)
                state = cls._get_circuit_state(key, now)
                return state == CircuitState.HALF_OPEN

        return False


# 全局健康监控器实例
health_monitor = HealthMonitor()
health_open_circuits.set(0)
