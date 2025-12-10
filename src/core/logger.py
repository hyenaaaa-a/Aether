"""
统一日志系统 - 基于 loguru

日志级别策略:
- DEBUG: 开发调试，详细执行流程、变量值、缓存操作
- INFO:  生产环境，关键业务操作、状态变更、请求处理
- WARNING: 潜在问题、降级处理、资源警告
- ERROR: 异常错误、需要关注的故障

输出策略:
- 控制台: 开发环境=DEBUG, 生产环境=INFO (通过 LOG_LEVEL 控制)
- 文件: 始终保存 DEBUG 级别，保留30天，每日轮转

使用方式:
    from src.core.logger import logger

    logger.info("消息")
    logger.debug("调试信息")
    logger.warning("警告")
    logger.error("错误")
    logger.exception("异常，带堆栈")
"""

import logging
import os
import sys
from pathlib import Path

from loguru import logger

# ============================================================================
# 环境检测
# ============================================================================

IS_DOCKER = (
    os.path.exists("/.dockerenv")
    or os.environ.get("DOCKER_CONTAINER", "false").lower() == "true"
)

# 日志级别: 默认开发环境 DEBUG, 生产环境 INFO
LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG" if not IS_DOCKER else "INFO").upper()

# 是否禁用文件日志 (用于测试或特殊场景)
DISABLE_FILE_LOG = os.getenv("LOG_DISABLE_FILE", "false").lower() == "true"

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# ============================================================================
# 日志格式定义
# ============================================================================

CONSOLE_FORMAT_DEV = (
    "<green>{time:HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{message}</cyan>"
)

CONSOLE_FORMAT_PROD = "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}"

FILE_FORMAT = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}"

# ============================================================================
# 日志配置
# ============================================================================

logger.remove()


def _log_filter(record):
    return "watchfiles" not in record["name"]


if IS_DOCKER:
    logger.add(
        sys.stdout,
        format=CONSOLE_FORMAT_PROD,
        level=LOG_LEVEL,
        filter=_log_filter,
        colorize=False,
    )
else:
    logger.add(
        sys.stdout,
        format=CONSOLE_FORMAT_DEV,
        level=LOG_LEVEL,
        filter=_log_filter,
        colorize=True,
    )

if not DISABLE_FILE_LOG:
    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)

    # 主日志文件 - 所有级别
    logger.add(
        log_dir / "app.log",
        format=FILE_FORMAT,
        level="DEBUG",
        filter=_log_filter,
        rotation="00:00",
        retention="30 days",
        compression="gz",
        enqueue=True,
        encoding="utf-8",
    )

    # 错误日志文件 - 仅 ERROR 及以上
    logger.add(
        log_dir / "error.log",
        format=FILE_FORMAT,
        level="ERROR",
        filter=_log_filter,
        rotation="00:00",
        retention="30 days",
        compression="gz",
        enqueue=True,
        encoding="utf-8",
    )

# ============================================================================
# 禁用第三方库噪音日志
# ============================================================================

logging.getLogger("watchfiles").setLevel(logging.ERROR)
logging.getLogger("watchfiles.main").setLevel(logging.ERROR)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

# ============================================================================
# 导出
# ============================================================================

__all__ = ["logger"]
