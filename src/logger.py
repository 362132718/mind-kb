"""
日志模块 - 同时输出到控制台和文件
"""
import logging
import sys
from pathlib import Path

from src.config import LOG_LEVEL, LOG_FILE, BASE_DIR

_initialized = False


def get_logger(name: str = "kb") -> logging.Logger:
    """获取配置好的 logger，首次调用时初始化"""
    global _initialized
    logger = logging.getLogger(name)

    if not _initialized:
        _initialized = True
        logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

        # 格式
        fmt = logging.Formatter(
            "[%(asctime)s] %(levelname)-7s %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # 控制台 handler
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(fmt)
        logger.addHandler(console)

        # 文件 handler
        log_path = BASE_DIR / LOG_FILE
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(str(log_path), encoding="utf-8")
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)

    return logger
