"""日志系统 — loguru 配置，按天轮转，保留30天."""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger


def setup_logging(
    log_dir: str = "./logs",
    level: str = "INFO",
    retention: int = 30,
) -> None:
    """初始化 loguru 日志系统.

    Args:
        log_dir: 日志目录路径.
        level: 日志级别.
        retention: 日志保留天数.
    """
    # 移除默认 handler
    logger.remove()

    # 控制台输出 — 彩色
    logger.add(
        sys.stderr,
        level=level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    # 确保日志目录存在
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # 文件输出 — 按天轮转
    logger.add(
        log_path / "crawler_{time:YYYY-MM-DD}.log",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
        rotation="00:00",          # 每天午夜轮转
        retention=f"{retention} days",
        compression="gz",          # 压缩旧日志
        encoding="utf-8",
        enqueue=True,              # 线程安全
    )

    logger.info("日志系统已初始化 (级别={}, 保留={}天)", level, retention)


def get_logger():
    """获取 loguru logger（直接返回，方便兼容现有代码风格）."""
    return logger
