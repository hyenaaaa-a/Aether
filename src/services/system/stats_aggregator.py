"""统计数据聚合服务

实现预聚合统计，避免每次请求都全表扫描。
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from src.core.logger import logger
from src.models.database import (
    ApiKey,
    RequestCandidate,
    StatsDaily,
    StatsSummary,
    StatsUserDaily,
    Usage,
)
from src.models.database import User as DBUser


class StatsAggregatorService:
    """统计数据聚合服务"""

    @staticmethod
    def aggregate_daily_stats(db: Session, date: datetime) -> StatsDaily:
        """聚合指定日期的统计数据

        Args:
            db: 数据库会话
            date: 要聚合的日期 (会自动转为 UTC 当天开始)

        Returns:
            StatsDaily 记录
        """
        # 确保日期是 UTC 当天开始
        day_start = date.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)

        # 检查是否已存在该日期的记录
        existing = db.query(StatsDaily).filter(StatsDaily.date == day_start).first()
        if existing:
            stats = existing
        else:
            stats = StatsDaily(id=str(uuid.uuid4()), date=day_start)

        # 基础请求统计
        base_query = db.query(Usage).filter(
            and_(Usage.created_at >= day_start, Usage.created_at < day_end)
        )

        total_requests = base_query.count()

        # 如果没有请求，直接返回空记录
        if total_requests == 0:
            stats.total_requests = 0
            stats.success_requests = 0
            stats.error_requests = 0
            stats.input_tokens = 0
            stats.output_tokens = 0
            stats.cache_creation_tokens = 0
            stats.cache_read_tokens = 0
            stats.total_cost = 0.0
            stats.actual_total_cost = 0.0
            stats.input_cost = 0.0
            stats.output_cost = 0.0
            stats.cache_creation_cost = 0.0
            stats.cache_read_cost = 0.0
            stats.avg_response_time_ms = 0.0
            stats.fallback_count = 0

            if not existing:
                db.add(stats)
            db.commit()
            return stats

        # 错误请求数
        error_requests = (
            base_query.filter(
                (Usage.status_code >= 400) | (Usage.error_message.isnot(None))
            ).count()
        )

        # Token 和成本聚合
        aggregated = (
            db.query(
                func.sum(Usage.input_tokens).label("input_tokens"),
                func.sum(Usage.output_tokens).label("output_tokens"),
                func.sum(Usage.cache_creation_input_tokens).label("cache_creation_tokens"),
                func.sum(Usage.cache_read_input_tokens).label("cache_read_tokens"),
                func.sum(Usage.total_cost_usd).label("total_cost"),
                func.sum(Usage.actual_total_cost_usd).label("actual_total_cost"),
                func.sum(Usage.input_cost_usd).label("input_cost"),
                func.sum(Usage.output_cost_usd).label("output_cost"),
                func.sum(Usage.cache_creation_cost_usd).label("cache_creation_cost"),
                func.sum(Usage.cache_read_cost_usd).label("cache_read_cost"),
                func.avg(Usage.response_time_ms).label("avg_response_time"),
            )
            .filter(and_(Usage.created_at >= day_start, Usage.created_at < day_end))
            .first()
        )

        # Fallback 统计 (执行候选数 > 1 的请求数)
        fallback_subquery = (
            db.query(
                RequestCandidate.request_id,
                func.count(RequestCandidate.id).label("executed_count"),
            )
            .filter(
                and_(
                    RequestCandidate.created_at >= day_start,
                    RequestCandidate.created_at < day_end,
                    RequestCandidate.status.in_(["success", "failed"]),
                )
            )
            .group_by(RequestCandidate.request_id)
            .subquery()
        )
        fallback_count = (
            db.query(func.count())
            .select_from(fallback_subquery)
            .filter(fallback_subquery.c.executed_count > 1)
            .scalar()
            or 0
        )

        # 使用维度统计
        unique_models = (
            db.query(func.count(func.distinct(Usage.model)))
            .filter(and_(Usage.created_at >= day_start, Usage.created_at < day_end))
            .scalar()
            or 0
        )
        unique_providers = (
            db.query(func.count(func.distinct(Usage.provider)))
            .filter(and_(Usage.created_at >= day_start, Usage.created_at < day_end))
            .scalar()
            or 0
        )

        # 更新统计记录
        stats.total_requests = total_requests
        stats.success_requests = total_requests - error_requests
        stats.error_requests = error_requests
        stats.input_tokens = int(aggregated.input_tokens or 0)
        stats.output_tokens = int(aggregated.output_tokens or 0)
        stats.cache_creation_tokens = int(aggregated.cache_creation_tokens or 0)
        stats.cache_read_tokens = int(aggregated.cache_read_tokens or 0)
        stats.total_cost = float(aggregated.total_cost or 0)
        stats.actual_total_cost = float(aggregated.actual_total_cost or 0)
        stats.input_cost = float(aggregated.input_cost or 0)
        stats.output_cost = float(aggregated.output_cost or 0)
        stats.cache_creation_cost = float(aggregated.cache_creation_cost or 0)
        stats.cache_read_cost = float(aggregated.cache_read_cost or 0)
        stats.avg_response_time_ms = float(aggregated.avg_response_time or 0)
        stats.fallback_count = fallback_count
        stats.unique_models = unique_models
        stats.unique_providers = unique_providers

        if not existing:
            db.add(stats)
        db.commit()

        logger.info(f"[StatsAggregator] 聚合日期 {day_start.date()} 完成: {total_requests} 请求")
        return stats

    @staticmethod
    def aggregate_user_daily_stats(
        db: Session, user_id: str, date: datetime
    ) -> StatsUserDaily:
        """聚合指定用户指定日期的统计数据"""
        day_start = date.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)

        existing = (
            db.query(StatsUserDaily)
            .filter(and_(StatsUserDaily.user_id == user_id, StatsUserDaily.date == day_start))
            .first()
        )

        if existing:
            stats = existing
        else:
            stats = StatsUserDaily(id=str(uuid.uuid4()), user_id=user_id, date=day_start)

        # 用户请求统计
        base_query = db.query(Usage).filter(
            and_(
                Usage.user_id == user_id,
                Usage.created_at >= day_start,
                Usage.created_at < day_end,
            )
        )

        total_requests = base_query.count()

        if total_requests == 0:
            stats.total_requests = 0
            stats.success_requests = 0
            stats.error_requests = 0
            stats.input_tokens = 0
            stats.output_tokens = 0
            stats.cache_creation_tokens = 0
            stats.cache_read_tokens = 0
            stats.total_cost = 0.0

            if not existing:
                db.add(stats)
            db.commit()
            return stats

        error_requests = (
            base_query.filter(
                (Usage.status_code >= 400) | (Usage.error_message.isnot(None))
            ).count()
        )

        aggregated = (
            db.query(
                func.sum(Usage.input_tokens).label("input_tokens"),
                func.sum(Usage.output_tokens).label("output_tokens"),
                func.sum(Usage.cache_creation_input_tokens).label("cache_creation_tokens"),
                func.sum(Usage.cache_read_input_tokens).label("cache_read_tokens"),
                func.sum(Usage.total_cost_usd).label("total_cost"),
            )
            .filter(
                and_(
                    Usage.user_id == user_id,
                    Usage.created_at >= day_start,
                    Usage.created_at < day_end,
                )
            )
            .first()
        )

        stats.total_requests = total_requests
        stats.success_requests = total_requests - error_requests
        stats.error_requests = error_requests
        stats.input_tokens = int(aggregated.input_tokens or 0)
        stats.output_tokens = int(aggregated.output_tokens or 0)
        stats.cache_creation_tokens = int(aggregated.cache_creation_tokens or 0)
        stats.cache_read_tokens = int(aggregated.cache_read_tokens or 0)
        stats.total_cost = float(aggregated.total_cost or 0)

        if not existing:
            db.add(stats)
        db.commit()
        return stats

    @staticmethod
    def update_summary(db: Session) -> StatsSummary:
        """更新全局统计汇总

        汇总截止到昨天的所有数据。
        """
        now = datetime.now(timezone.utc)
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        cutoff_date = today  # 不含今天

        # 获取或创建 summary 记录
        summary = db.query(StatsSummary).first()
        if not summary:
            summary = StatsSummary(id=str(uuid.uuid4()), cutoff_date=cutoff_date)

        # 从 stats_daily 聚合历史数据
        daily_aggregated = (
            db.query(
                func.sum(StatsDaily.total_requests).label("total_requests"),
                func.sum(StatsDaily.success_requests).label("success_requests"),
                func.sum(StatsDaily.error_requests).label("error_requests"),
                func.sum(StatsDaily.input_tokens).label("input_tokens"),
                func.sum(StatsDaily.output_tokens).label("output_tokens"),
                func.sum(StatsDaily.cache_creation_tokens).label("cache_creation_tokens"),
                func.sum(StatsDaily.cache_read_tokens).label("cache_read_tokens"),
                func.sum(StatsDaily.total_cost).label("total_cost"),
                func.sum(StatsDaily.actual_total_cost).label("actual_total_cost"),
            )
            .filter(StatsDaily.date < cutoff_date)
            .first()
        )

        # 用户/API Key 统计
        total_users = db.query(func.count(DBUser.id)).scalar() or 0
        active_users = (
            db.query(func.count(DBUser.id)).filter(DBUser.is_active.is_(True)).scalar() or 0
        )
        total_api_keys = db.query(func.count(ApiKey.id)).scalar() or 0
        active_api_keys = (
            db.query(func.count(ApiKey.id)).filter(ApiKey.is_active.is_(True)).scalar() or 0
        )

        # 更新 summary
        summary.cutoff_date = cutoff_date
        summary.all_time_requests = int(daily_aggregated.total_requests or 0)
        summary.all_time_success_requests = int(daily_aggregated.success_requests or 0)
        summary.all_time_error_requests = int(daily_aggregated.error_requests or 0)
        summary.all_time_input_tokens = int(daily_aggregated.input_tokens or 0)
        summary.all_time_output_tokens = int(daily_aggregated.output_tokens or 0)
        summary.all_time_cache_creation_tokens = int(daily_aggregated.cache_creation_tokens or 0)
        summary.all_time_cache_read_tokens = int(daily_aggregated.cache_read_tokens or 0)
        summary.all_time_cost = float(daily_aggregated.total_cost or 0)
        summary.all_time_actual_cost = float(daily_aggregated.actual_total_cost or 0)
        summary.total_users = total_users
        summary.active_users = active_users
        summary.total_api_keys = total_api_keys
        summary.active_api_keys = active_api_keys

        db.add(summary)
        db.commit()

        logger.info(f"[StatsAggregator] 更新全局汇总完成，截止日期: {cutoff_date.date()}")
        return summary

    @staticmethod
    def get_today_realtime_stats(db: Session) -> dict:
        """获取今日实时统计（用于与预聚合数据合并）"""
        now = datetime.now(timezone.utc)
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        base_query = db.query(Usage).filter(Usage.created_at >= today)

        total_requests = base_query.count()

        if total_requests == 0:
            return {
                "total_requests": 0,
                "success_requests": 0,
                "error_requests": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_creation_tokens": 0,
                "cache_read_tokens": 0,
                "total_cost": 0.0,
                "actual_total_cost": 0.0,
            }

        error_requests = (
            base_query.filter(
                (Usage.status_code >= 400) | (Usage.error_message.isnot(None))
            ).count()
        )

        aggregated = (
            db.query(
                func.sum(Usage.input_tokens).label("input_tokens"),
                func.sum(Usage.output_tokens).label("output_tokens"),
                func.sum(Usage.cache_creation_input_tokens).label("cache_creation_tokens"),
                func.sum(Usage.cache_read_input_tokens).label("cache_read_tokens"),
                func.sum(Usage.total_cost_usd).label("total_cost"),
                func.sum(Usage.actual_total_cost_usd).label("actual_total_cost"),
            )
            .filter(Usage.created_at >= today)
            .first()
        )

        return {
            "total_requests": total_requests,
            "success_requests": total_requests - error_requests,
            "error_requests": error_requests,
            "input_tokens": int(aggregated.input_tokens or 0),
            "output_tokens": int(aggregated.output_tokens or 0),
            "cache_creation_tokens": int(aggregated.cache_creation_tokens or 0),
            "cache_read_tokens": int(aggregated.cache_read_tokens or 0),
            "total_cost": float(aggregated.total_cost or 0),
            "actual_total_cost": float(aggregated.actual_total_cost or 0),
        }

    @staticmethod
    def get_combined_stats(db: Session) -> dict:
        """获取合并后的统计数据（预聚合 + 今日实时）"""
        summary = db.query(StatsSummary).first()
        today_stats = StatsAggregatorService.get_today_realtime_stats(db)

        if not summary:
            # 如果没有预聚合数据，返回今日数据
            return today_stats

        return {
            "total_requests": summary.all_time_requests + today_stats["total_requests"],
            "success_requests": summary.all_time_success_requests
            + today_stats["success_requests"],
            "error_requests": summary.all_time_error_requests + today_stats["error_requests"],
            "input_tokens": summary.all_time_input_tokens + today_stats["input_tokens"],
            "output_tokens": summary.all_time_output_tokens + today_stats["output_tokens"],
            "cache_creation_tokens": summary.all_time_cache_creation_tokens
            + today_stats["cache_creation_tokens"],
            "cache_read_tokens": summary.all_time_cache_read_tokens
            + today_stats["cache_read_tokens"],
            "total_cost": summary.all_time_cost + today_stats["total_cost"],
            "actual_total_cost": summary.all_time_actual_cost + today_stats["actual_total_cost"],
            "total_users": summary.total_users,
            "active_users": summary.active_users,
            "total_api_keys": summary.total_api_keys,
            "active_api_keys": summary.active_api_keys,
        }

    @staticmethod
    def backfill_historical_data(db: Session, days: int = 365) -> int:
        """回填历史数据（首次部署时使用）

        Args:
            db: 数据库会话
            days: 要回填的天数

        Returns:
            回填的天数
        """
        now = datetime.now(timezone.utc)
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # 找到最早的 Usage 记录
        earliest = db.query(func.min(Usage.created_at)).scalar()
        if not earliest:
            logger.info("[StatsAggregator] 没有历史数据需要回填")
            return 0

        # 计算需要回填的日期范围
        earliest_date = earliest.replace(hour=0, minute=0, second=0, microsecond=0)
        start_date = max(earliest_date, today - timedelta(days=days))

        count = 0
        current_date = start_date
        while current_date < today:
            StatsAggregatorService.aggregate_daily_stats(db, current_date)
            count += 1
            current_date += timedelta(days=1)

        # 更新汇总
        if count > 0:
            StatsAggregatorService.update_summary(db)

        logger.info(f"[StatsAggregator] 回填历史数据完成，共 {count} 天")
        return count
