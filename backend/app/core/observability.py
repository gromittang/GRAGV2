"""
可观测性层 — 双通道输出
- 本地 Trace: 始终启用，通过 TracingCallbackHandler 输出到 data/traces/
- LangFuse: 可选，有凭证时作为云 observability 附加通道
"""
from typing import Optional
from langfuse.langchain import CallbackHandler

from app.config import get_settings
from app.core.logging import get_logger
from app.core.tracing import get_tracing_callback_handler

_settings = get_settings()
_log = get_logger("core.observability")

_langfuse_handler: Optional[CallbackHandler] = None
_langfuse_init_attempted: bool = False


def get_langfuse_handler() -> Optional[CallbackHandler]:
    """获取 LangFuse CallbackHandler 单例，未配置则返回 None"""
    global _langfuse_handler, _langfuse_init_attempted

    if _langfuse_init_attempted:
        return _langfuse_handler

    _langfuse_init_attempted = True

    if not _settings.langfuse_enabled:
        return None

    try:
        _langfuse_handler = CallbackHandler(
            public_key=_settings.langfuse_public_key,
            secret_key=_settings.langfuse_secret_key,
            host=_settings.langfuse_host,
        )
        _log.info("LangFuse 已启用")
        return _langfuse_handler
    except Exception as e:
        _log.warning("LangFuse 初始化失败: {}", e)
        return None


def get_langgraph_config(session_id: str = "default") -> dict:
    """构建 LangGraph invoke 用的 config dict

    双通道: 本地 TracingCallbackHandler（始终启用） + LangFuse（可选）
    """
    config: dict = {
        "configurable": {
            "thread_id": session_id,
        }
    }

    callbacks = []

    # 本地 trace 始终启用
    callbacks.append(get_tracing_callback_handler())

    # LangFuse 可选
    handler = get_langfuse_handler()
    if handler:
        callbacks.append(handler)

    config["callbacks"] = callbacks
    return config
