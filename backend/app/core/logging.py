"""
Loguru 结构化日志配置
控制台: 彩色可读格式
文件: JSON lines，按日轮转
"""
import os
import sys
import logging
from contextvars import ContextVar
from loguru import logger

from app.config import get_settings

_settings = get_settings()

# contextvar 存储当前请求的 trace_id，所有日志自动绑定
_trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")


def set_trace_id(trace_id: str) -> None:
    _trace_id_var.set(trace_id)


def get_trace_id() -> str:
    return _trace_id_var.get()


def _console_format(record: dict) -> str:
    """控制台输出格式，比默认的 extended 更紧凑"""
    trace_id = record["extra"].get("trace_id", "")
    module = record["extra"].get("module", "")
    tid = f"[{trace_id[:8]}] " if trace_id else ""
    return (
        f"<green>{{time:HH:mm:ss.SSS}}</green> | "
        f"<level>{{level: <5}}</level> | "
        f"<cyan>{{extra[module]: <20}}</cyan> | "
        f"{tid}"
        f"<level>{{message}}</level>\n"
    )


def setup_logging():
    """初始化 Loguru 配置，移除默认 handler 并添加自定义"""
    logger.remove()

    # 控制台输出
    logger.add(
        sys.stdout,
        format=_console_format,
        level=_settings.log_level,
        colorize=True,
    )

    # JSON 文件输出
    data_dir = _settings.data_dir
    log_dir = os.path.join(data_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)

    logger.add(
        os.path.join(log_dir, "app.{time:YYYY-MM-DD}.jsonl"),
        serialize=True,
        level="DEBUG",
        rotation="00:00",
        retention="30 days",
        compression="gz",
        encoding="utf-8",
    )

    # 错误文件（仅 WARNING 及以上）
    logger.add(
        os.path.join(log_dir, "error.{time:YYYY-MM-DD}.jsonl"),
        serialize=True,
        level="WARNING",
        rotation="00:00",
        retention="90 days",
        compression="gz",
        encoding="utf-8",
    )

    # 拦截标准 logging 库，转发到 Loguru
    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)

    return logger


class _InterceptHandler(logging.Handler):
    """将 Python 标准 logging 转发到 Loguru"""

    def emit(self, record: logging.LogRecord) -> None:
        level = logger.level(record.levelname).name
        frame = logging.currentframe()
        depth = 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def get_logger(module: str = "") -> "logger":
    """获取带模块名绑定的 logger 实例"""
    _log = logger.bind(module=module)
    # 每次调用时动态读取 trace_id，因为 contextvar 可能在 logger 创建后才设置
    return _log.patch(lambda r: r["extra"].update(trace_id=get_trace_id()))


# 模块初始化时执行
setup_logging()
