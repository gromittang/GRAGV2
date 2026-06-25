"""
本地 Trace/Span 系统
JSON Lines 输出到 data/traces/，按日轮转
同时支持 async（LangGraph 节点）和 sync（asyncio.to_thread 内部）使用
"""
import os
import json
import time
import uuid
import asyncio
from datetime import datetime, timezone
from contextvars import ContextVar
from typing import Optional, Any, Dict

from app.config import get_settings
from app.core.logging import get_logger

_settings = get_settings()
_log = get_logger("core.tracing")

# contextvar 传播 trace_id（线程+异步安全）
_trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")
_parent_span_id_var: ContextVar[str] = ContextVar("parent_span_id", default="")

# 后台写入队列
_write_queue: Optional[asyncio.Queue] = None
_writer_task: Optional[asyncio.Task] = None

TRACES_DIR = os.path.join(_settings.data_dir, "traces")


def get_current_trace_id() -> str:
    return _trace_id_var.get()


class Span:
    """单个 Span，由 TraceContext 管理生命周期"""

    def __init__(self, name: str, parent_span_id: str = "", **inputs):
        self.name = name
        self.span_id = uuid.uuid4().hex[:16]
        self.parent_span_id = parent_span_id or _parent_span_id_var.get()
        self.trace_id = _trace_id_var.get() or uuid.uuid4().hex[:16]
        self.start_time = time.time()
        self.start_iso = datetime.now(timezone.utc).isoformat()
        self.input = inputs or {}
        self.output: Dict[str, Any] = {}
        self.metadata: Dict[str, Any] = {}
        self.error: Optional[str] = None
        self.status = "ok"
        self._ended = False

    def set_output(self, **kwargs):
        self.output.update(kwargs)

    def set_metadata(self, **kwargs):
        self.metadata.update(kwargs)

    def set_error(self, error: str):
        self.error = error
        self.status = "error"

    def end(self) -> dict:
        if self._ended:
            return {}
        self._ended = True
        elapsed = (time.time() - self.start_time) * 1000
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "start_time": self.start_iso,
            "duration_ms": round(elapsed, 2),
            "status": self.status,
            "error": self.error,
            "input": self.input,
            "output": self.output,
            "metadata": self.metadata,
        }


class TraceContext:
    """Span 上下文管理器，同时支持 sync 和 async"""

    def __init__(self, name: str, parent_span_id: str = "", **inputs):
        self._name = name
        self._parent_span_id = parent_span_id
        self._inputs = inputs
        self._token = None
        self._span: Optional[Span] = None

    def __enter__(self) -> Span:
        self._span = Span(self._name, self._parent_span_id, **self._inputs)
        # 将当前 span_id 设为子 span 的 parent
        self._token = _parent_span_id_var.set(self._span.span_id)
        return self._span

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._span is None:
            return
        if exc_type is not None:
            self._span.set_error(f"{exc_type.__name__}: {exc_val}")
        span_dict = self._span.end()
        _parent_span_id_var.reset(self._token)
        self._enqueue(span_dict)
        return False

    async def __aenter__(self) -> Span:
        return self.__enter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.__exit__(exc_type, exc_val, exc_tb)

    @staticmethod
    def _enqueue(span_dict: dict):
        """将完成的 span 入队到后台 writer"""
        if span_dict and _write_queue is not None:
            try:
                _write_queue.put_nowait(span_dict)
            except asyncio.QueueFull:
                pass


async def _trace_writer():
    """后台任务：从队列批量写 JSON lines 到文件"""
    batch: list = []
    last_flush = time.time()

    while True:
        try:
            span = await asyncio.wait_for(_write_queue.get(), timeout=1.0)
            batch.append(span)
        except asyncio.TimeoutError:
            pass

        now = time.time()
        if batch and (len(batch) >= 10 or (now - last_flush) >= 1.0):
            await _flush_batch(batch)
            batch.clear()
            last_flush = now


async def _flush_batch(batch: list):
    """将一批 span 写入当日文件"""
    os.makedirs(TRACES_DIR, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    filepath = os.path.join(TRACES_DIR, f"trace.{date_str}.jsonl")

    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _write_lines, filepath, batch)
    except Exception as e:
        _log.error("写入 trace 文件失败: {}", e)


def _write_lines(filepath: str, batch: list):
    """同步写入（在 executor 中运行）"""
    with open(filepath, "a", encoding="utf-8") as f:
        for span in batch:
            f.write(json.dumps(span, ensure_ascii=False, default=str) + "\n")


async def start_trace_writer():
    """启动后台 trace writer（在 lifespan 中调用）"""
    global _write_queue, _writer_task
    if _write_queue is None:
        _write_queue = asyncio.Queue(maxsize=500)
    if _writer_task is None or _writer_task.done():
        _writer_task = asyncio.create_task(_trace_writer())
        _log.info("Trace writer 已启动，输出目录: {}", TRACES_DIR)


async def stop_trace_writer():
    """停止后台 trace writer"""
    global _writer_task
    if _writer_task and not _writer_task.done():
        _writer_task.cancel()
        try:
            await _writer_task
        except asyncio.CancelledError:
            pass
        _log.info("Trace writer 已停止")


def set_trace_context(trace_id: str):
    """设置当前请求的 trace_id（HTTP 中间件调用）"""
    _trace_id_var.set(trace_id)


# ---- LangChain Callback Handler ----

from typing import Dict as DictType, Any as AnyType
from uuid import UUID
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult


class TracingCallbackHandler(BaseCallbackHandler):
    """LangChain/LangGraph 回调，自动为 graph 节点创建 span"""

    def __init__(self):
        self._active_spans: dict = {}  # run_id -> Span

    def on_chain_start(
        self,
        serialized: DictType[str, AnyType],
        inputs: DictType[str, AnyType],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list] = None,
        metadata: Optional[DictType[str, AnyType]] = None,
        **kwargs: AnyType,
    ) -> None:
        # serialized can be None in newer LangChain versions; extract name from multiple sources
        if serialized and isinstance(serialized, dict):
            name = serialized.get("name", "") or serialized.get("id", ["unknown"])[-1]
        else:
            name = ""
        # Prefer explicit name from kwargs (LangGraph node name) or metadata
        name = kwargs.get("name", "") or (metadata or {}).get("langgraph_node", "") or name or "unknown"
        parent_span_id = ""
        if parent_run_id and str(parent_run_id) in self._active_spans:
            parent_span_id = self._active_spans[str(parent_run_id)].span_id

        # 提取有意义的 input
        span_inputs = {}
        if isinstance(inputs, dict):
            for k in ("question", "query", "messages", "context"):
                if k in inputs:
                    v = inputs[k]
                    if isinstance(v, str):
                        span_inputs[k] = v[:200]
                    elif isinstance(v, list):
                        span_inputs[k] = f"[{len(v)} items]"
                    else:
                        span_inputs[k] = str(v)[:200]

        span = Span(name, parent_span_id, **span_inputs)
        self._active_spans[str(run_id)] = span

    def on_chain_end(
        self,
        outputs: DictType[str, AnyType],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: AnyType,
    ) -> None:
        run_key = str(run_id)
        if run_key not in self._active_spans:
            return

        span = self._active_spans.pop(run_key)
        # 提取有意义的 output
        if isinstance(outputs, dict):
            for k, v in outputs.items():
                if k == "answer" and isinstance(v, str):
                    span.set_output(answer_preview=v[:200], answer_length=len(v))
                elif k == "sources" and isinstance(v, list):
                    span.set_output(num_sources=len(v))
                elif k == "has_documents":
                    span.set_output(has_documents=v)
                elif k == "token_usage" and v:
                    span.set_output(token_usage=v)
                elif isinstance(v, (str, int, float, bool)):
                    span.set_output(**{k: v})

        span_dict = span.end()
        TraceContext._enqueue(span_dict)

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: AnyType,
    ) -> None:
        run_key = str(run_id)
        if run_key in self._active_spans:
            span = self._active_spans.pop(run_key)
            span.set_error(f"{type(error).__name__}: {error}")
            span_dict = span.end()
            TraceContext._enqueue(span_dict)

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: AnyType,
    ) -> None:
        """捕获 LLM 调用的 token 用量（LangChain LLM 直接调用时有效）"""
        run_key = str(run_id)
        if run_key not in self._active_spans:
            return
        span = self._active_spans[run_key]
        if response.llm_output and "token_usage" in response.llm_output:
            span.set_output(token_usage=response.llm_output["token_usage"])
        if response.generations:
            span.set_output(num_generations=len(response.generations))


# 单例
_tracing_handler: Optional[TracingCallbackHandler] = None


def get_tracing_callback_handler() -> TracingCallbackHandler:
    global _tracing_handler
    if _tracing_handler is None:
        _tracing_handler = TracingCallbackHandler()
    return _tracing_handler
