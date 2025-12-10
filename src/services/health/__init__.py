"""
健康监控服务模块

包含健康监控相关功能：
- health_monitor: 健康度监控单例
- HealthMonitor: 健康监控类
"""

from .monitor import HealthMonitor, health_monitor

__all__ = [
    "health_monitor",
    "HealthMonitor",
]
