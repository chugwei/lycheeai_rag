"""
日志初始化 - 使 config/settings.yaml 中的 logging 配置生效

功能：
1. 读取 logging.level / logging.file 配置
2. 添加 loguru 文件 sink（轮转、保留）
3. 安装 InterceptHandler 将 stdlib logging 桥接到 loguru
   （chromadb / urllib3 / httpx / sentence_transformers 等库的日志统一格式）
4. 设置全局日志级别
"""
import logging
import sys
from pathlib import Path

from loguru import logger

from config.settings import get_config


class InterceptHandler(logging.Handler):
    """
    将 stdlib logging 消息桥接到 loguru

    用法: logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    """

    def emit(self, record: logging.LogRecord) -> None:
        # 获取对应的 loguru 级别
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # 查找调用帧
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def setup_logging():
    """根据配置初始化日志系统"""
    log_level = get_config("logging.level", "INFO").upper()
    log_file = get_config("logging.file", "./logs/lycheeai.log")

    # 移除默认 sink（避免控制台重复输出）
    logger.remove()

    # 控制台 sink（保留 stderr 输出）
    logger.add(
        sys.stderr,
        level=log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <7}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
        colorize=True,
        backtrace=False,
        diagnose=False,
    )

    # 文件 sink（轮转：10MB，保留 5 份）
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger.add(
        str(log_path),
        level=log_level,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <7} | {name}:{function}:{line} - {message}",
        rotation="10 MB",
        retention=5,
        encoding="utf-8",
        backtrace=False,
        diagnose=False,
    )

    # 将 stdlib logging 桥接到 loguru
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    # 关闭一些第三方库的冗长日志
    for noisy_logger in (
        "chromadb.segment.impl.metadata",
        "chromadb.segment.impl.vector",
        "chromadb.db.impl.sqlite",
        "chromadb.telemetry",
        "urllib3.connectionpool",
        "httpx",
        "sentence_transformers.SentenceTransformer",
        "matplotlib",
        "PIL",
    ):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)

    logger.info(f"日志初始化完成: level={log_level}, file={log_path}")