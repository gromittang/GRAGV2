"""
DataQueryGateway — 数据查询唯一入口

Phase 1: Gateway 骨架 + 本地路径收敛（MCP 未接入）
- LocalExecutor: 适配 graph_nl2sql
- QueryAgentExecutor: 适配 query_agent (deprecated, 受限兜底)
- 统一后处理: _translate_columns / _save_history / _generate_insight

Phase 2 将接入 McpExecutor，Phase 3 将实现完整 Clarification + 准入控制。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.config import get_settings
from app.core.logging import get_logger
from app.core.schema_manager import get_schema_manager
from app.models.query_history import save_history

_log = get_logger("gateway")

# ---------------------------------------------------------------------------
# Phase 1 统一结果模型
# ---------------------------------------------------------------------------


@dataclass
class ToolCall:
    """MCP Tool 调用记录（Phase 2 启用，Phase 1 为 stub）"""
    tool_name: str = ""
    arguments: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Insight:
    """AI 分析洞察"""
    summary: str = ""
    insights: List[str] = field(default_factory=list)
    follow_ups: List[str] = field(default_factory=list)


@dataclass
class UnifiedQueryResult:
    """数据查询统一返回结构

    Phase 1 必须字段: success, source, query_mode, question, sql, columns,
    rows, total, insight, confidence, error_code, error_message, trace_id, latency_ms
    Phase 1 stub 字段: normalized_question, tool_calls, clarification_needed,
    clarification_question
    """
    # ── 状态 ──
    success: bool = True

    # ── 路由信息 ──
    source: str = ""           # "local" | "queryagent"  (Phase 2 增加 "mcp")
    query_mode: str = ""       # "sql" | "fallback"      (Phase 2 增加 "tool")

    # ── 输入 ──
    question: str = ""
    normalized_question: Optional[str] = None   # Phase 3 实现

    # ── 查询结果 ──
    sql: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None  # Phase 2 启用
    columns: List[str] = field(default_factory=list)
    rows: List[List[Any]] = field(default_factory=list)
    total: int = 0

    # ── 洞察 ──
    insight: Optional[Insight] = None

    # ── 置信度 ──
    confidence: Optional[float] = None

    # ── 澄清（Phase 3 实现）──
    clarification_needed: bool = False
    clarification_question: Optional[str] = None

    # ── 错误 ──
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    # ── 持久化 ──
    history_id: Optional[int] = None

    # ── 可观测 ──
    trace_id: str = ""
    latency_ms: float = 0.0


@dataclass
class RawQueryResult:
    """Executor 返回给 Gateway 的原始结果"""
    success: bool = True
    source: str = ""
    query_mode: str = "sql"

    columns: List[str] = field(default_factory=list)
    rows: List[List[Any]] = field(default_factory=list)
    total: int = 0

    sql: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
    confidence: Optional[float] = None
    insight: Optional[Insight] = None

    clarification_needed: bool = False
    clarification_question: Optional[str] = None

    error_code: Optional[str] = None
    error_message: Optional[str] = None
    is_retryable: bool = True

    latency_ms: float = 0.0


# ---------------------------------------------------------------------------
# 错误分类辅助（Phase 1 最小版本，Phase 3 扩展为完整 Error Taxonomy）
# ---------------------------------------------------------------------------

def _classify_error(raw: Dict[str, Any]) -> str:
    """根据 Executor 原始返回推断 error_code"""
    error_msg = str(raw.get("error", "")).lower()
    if not error_msg:
        return "internal_error"

    # LangGraph 异常
    if any(kw in error_msg for kw in ["langgraph", "checkpoint", "serialize",
                                        "graph", "node", "state"]):
        return "langgraph_error"
    # LLM 不可用
    if any(kw in error_msg for kw in ["api key", "api_key", "llm", "openai",
                                        "deepseek", "anthropic", "rate limit"]):
        return "llm_api_error"
    # MySQL 不可用
    if any(kw in error_msg for kw in ["mysql", "database", "connection",
                                        "connect", "连接", "数据库"]):
        return "db_connection_failed"
    # SQL 安全违规
    if any(kw in error_msg for kw in ["drop", "delete", "insert", "update",
                                        "truncate", "alter", "create",
                                        "禁止", "安全", "dml", "ddl"]):
        return "sql_security_violation"
    # Schema 无匹配
    if any(kw in error_msg for kw in ["找不到", "无法找到", "表", "schema",
                                        "no table"]):
        return "schema_not_found"
    # SQL 执行错误
    if any(kw in error_msg for kw in ["sql", "syntax", "execute", "语法",
                                        "执行", "parse"]):
        return "sql_execution_error"

    return "internal_error"


def _is_retryable_error(raw: Dict[str, Any]) -> bool:
    """Phase 1 最小回退判断：哪些错误允许回退到下一级 Executor"""
    code = _classify_error(raw)
    # 不回退: LLM 或 MySQL 基础设施问题（下一级也用同样的基础设施，无意义）
    if code in ("llm_api_error", "db_connection_failed", "sql_security_violation"):
        return False
    # 允许回退: LangGraph 特有错误、Schema 差异、SQL 执行差异、未知错误
    return True


# ---------------------------------------------------------------------------
# Executor 接口（Phase 1: 协议，不强制 ABC）
# ---------------------------------------------------------------------------

class LocalExecutor:
    """适配 graph_nl2sql — 包裹现有 ainvoke() 调用，不重写内部逻辑"""

    name = "local"
    priority = 1

    async def execute(self, question: str, context: Dict[str, Any]) -> RawQueryResult:
        """调用 graph_nl2sql.ainvoke() 并映射为 RawQueryResult"""
        t0 = time.perf_counter()
        from app.agents.graph_nl2sql import get_query_graph

        graph = get_query_graph()

        # 构建 ainvoke 输入（兼容 dispatch 和 query_service 两种调用方式）
        ainvoke_input = {
            "question": question,
            "user_context": context.get("user_context", {}),
        }

        # 如果提供了 langgraph config 则传入（支持 tracing callback）
        config = context.get("langgraph_config")
        try:
            if config:
                raw = await graph.ainvoke(ainvoke_input, config=config)
            else:
                raw = await graph.ainvoke(ainvoke_input)
        except Exception as exc:
            _log.exception("LocalExecutor (graph_nl2sql) 执行异常: {}", exc)
            return RawQueryResult(
                success=False,
                source=self.name,
                query_mode="sql",
                error_code="langgraph_error",
                error_message=str(exc),
                is_retryable=True,
                latency_ms=(time.perf_counter() - t0) * 1000,
            )

        latency_ms = (time.perf_counter() - t0) * 1000
        query_result = raw.get("query_result", {}) or {}

        # 从 graph state 提取数据
        columns = raw.get("columns", [])
        rows = query_result.get("rows", [])
        if not rows:
            # query_result 可能是 dict 含 rows/columns
            rows = query_result if isinstance(query_result, list) else []

        if raw.get("error"):
            return RawQueryResult(
                success=False,
                source=self.name,
                query_mode="sql",
                sql=raw.get("sql", ""),
                error_code=_classify_error(raw),
                error_message=raw["error"],
                is_retryable=_is_retryable_error(raw),
                latency_ms=latency_ms,
            )

        # 解析 insight（graph state 中可能是 dict）
        insight = None
        raw_insight = raw.get("insight")
        if raw_insight and isinstance(raw_insight, dict):
            insight = Insight(
                summary=raw_insight.get("summary", ""),
                insights=raw_insight.get("insights", []),
                follow_ups=raw_insight.get("follow_ups", []),
            )

        return RawQueryResult(
            success=raw.get("success", True),
            source=self.name,
            query_mode="sql",
            columns=columns,
            rows=rows,
            total=raw.get("total", len(rows)),
            sql=raw.get("sql", ""),
            confidence=raw.get("confidence"),
            insight=insight,
            latency_ms=latency_ms,
        )

    async def is_available(self) -> bool:
        return True


class QueryAgentExecutor:
    """适配 query_agent — 包裹现有 query() 调用，不重写内部逻辑

    @deprecated: 计划 2 个 release 后删除。Phase 1 仅作为受限兜底。
    """

    name = "queryagent"
    priority = 2

    async def execute(self, question: str, context: Dict[str, Any]) -> RawQueryResult:
        """调用 QueryAgent.query() 并映射为 RawQueryResult"""
        t0 = time.perf_counter()
        from app.agents.query_agent import get_query_agent

        session_id = context.get("session_id", "gateway_fallback")
        agent = await get_query_agent(session_id)

        try:
            raw = await agent.query(question)
        except Exception as exc:
            _log.exception("QueryAgentExecutor 执行异常: {}", exc)
            return RawQueryResult(
                success=False,
                source=self.name,
                query_mode="fallback",
                error_code="internal_error",
                error_message=str(exc),
                is_retryable=False,
                latency_ms=(time.perf_counter() - t0) * 1000,
            )

        latency_ms = (time.perf_counter() - t0) * 1000

        if not raw.get("success"):
            return RawQueryResult(
                success=False,
                source=self.name,
                query_mode="fallback",
                sql=raw.get("sql", ""),
                error_code=_classify_error(raw),
                error_message=raw.get("error", "QueryAgent 查询失败"),
                is_retryable=False,  # 最后一级，不再回退
                latency_ms=latency_ms,
            )

        # 解析 insight
        insight = None
        raw_insight = raw.get("insight")
        if raw_insight and isinstance(raw_insight, dict):
            insight = Insight(
                summary=raw_insight.get("summary", ""),
                insights=raw_insight.get("insights", []),
                follow_ups=raw_insight.get("follow_ups", []),
            )

        return RawQueryResult(
            success=True,
            source=self.name,
            query_mode="fallback",
            columns=raw.get("columns", []),
            rows=raw.get("results", raw.get("rows", [])),
            total=raw.get("total", 0),
            sql=raw.get("sql", ""),
            confidence=raw.get("confidence"),
            insight=insight,
            latency_ms=latency_ms,
        )

    async def is_available(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# McpExecutor — Phase 2 Step 3
# ---------------------------------------------------------------------------


class McpExecutor:
    """MCP Data Copilot 执行器 — 最高优先级。

    Phase 2 Step 3: tool_select_node 使用规则版选择器，Step 4 替换为 LLM。
    Step 3.2: McpClientManager 在构造时创建，复用连接。
    """

    name = "mcp"
    priority = 0

    def __init__(self):
        settings = get_settings()
        from app.core.mcp_client import McpClientManager
        self._mcp_mgr = McpClientManager(
            base_url=settings.mcp_base_url,
            api_key=settings.mcp_api_key,
            timeout=settings.mcp_timeout,
        )

    async def execute(self, question: str, context: Dict[str, Any]) -> RawQueryResult:
        t0 = time.perf_counter()
        from app.agents.graph_mcp import get_mcp_graph

        settings = get_settings()
        if not settings.mcp_enabled:
            return RawQueryResult(
                success=False, source=self.name, query_mode="tool",
                error_code="mcp_disabled", error_message="MCP 未启用",
                is_retryable=False,
                latency_ms=(time.perf_counter() - t0) * 1000,
            )

        try:
            graph = get_mcp_graph()
            t_graph_start = time.perf_counter()
            state = await graph.ainvoke({
                "question": question,
                "domain_hint": context.get("domain_hint", ""),
                "session_id": context.get("session_id", ""),
                "tool_registry_raw": await self._mcp_mgr.get_tools(),
                "mcp_manager": self._mcp_mgr,
            })
            graph_latency_ms = (time.perf_counter() - t_graph_start) * 1000
        except Exception as exc:
            _log.exception("McpExecutor graph 执行异常: {}", exc)
            return RawQueryResult(
                success=False, source=self.name, query_mode="tool",
                error_code="mcp_unavailable",
                error_message=f"graph_mcp 执行失败: {exc}",
                is_retryable=True,
                latency_ms=(time.perf_counter() - t0) * 1000,
            )

        latency_ms = (time.perf_counter() - t0) * 1000

        # 提取调试信息（供 trace_json）
        mcp_debug = {
            "graph_latency_ms": graph_latency_ms,
            "selection_candidates": state.get("selection_candidates", []),
            "selection_reason": state.get("selection_reason", ""),
        }
        context["_mcp_debug"] = mcp_debug

        if state.get("error") or not state.get("success"):
            error_code = state.get("error_code", "internal_error")
            error_msg = state.get("error", "MCP 查询失败")
            from app.core.mcp_client import is_retryable_mcp_error
            is_retryable = is_retryable_mcp_error(error_code)
            return RawQueryResult(
                success=False, source=self.name, query_mode="tool",
                error_code=error_code, error_message=error_msg,
                is_retryable=is_retryable,
                latency_ms=latency_ms,
            )

        return RawQueryResult(
            success=True,
            source=self.name,
            query_mode="tool",
            columns=state.get("columns", []),
            rows=state.get("rows", []),
            total=state.get("total", 0),
            sql=None,
            tool_calls=[ToolCall(tool_name=tc.get("tool", tc.get("tool_name", "")),
                                 arguments=tc.get("arguments", {}))
                        for tc in state.get("tool_calls", [])],
            insight=None,
            latency_ms=latency_ms,
        )

    async def is_available(self) -> bool:
        settings = get_settings()
        if not settings.mcp_enabled:
            return False
        return await self._mcp_mgr.is_available()


# ---------------------------------------------------------------------------
# CircuitBreaker — Phase 2 Step 3
# ---------------------------------------------------------------------------


class CircuitBreaker:
    """MCP 熔断器。仅服务级故障计入。"""

    def __init__(self, threshold: int = 3, cooldown_seconds: float = 60.0):
        self._state = "CLOSED"
        self._failure_count = 0
        self._opened_at = 0.0
        self.threshold = threshold
        self.cooldown_seconds = cooldown_seconds

    @property
    def state(self) -> str:
        return self._state

    def allow_request(self) -> bool:
        now = time.monotonic()
        if self._state == "CLOSED":
            return True
        if self._state == "OPEN":
            if now - self._opened_at >= self.cooldown_seconds:
                self._state = "HALF_OPEN"
                _log.info("CircuitBreaker: OPEN → HALF_OPEN")
                return True
            return False
        return True  # HALF_OPEN

    def record_success(self):
        if self._state == "HALF_OPEN":
            _log.info("CircuitBreaker: HALF_OPEN → CLOSED")
        self._state = "CLOSED"
        self._failure_count = 0

    def record_failure(self, error_code: str = ""):
        """记录一次失败。仅服务级故障（mcp_unavailable/auth_error/timeout）计入。"""
        from app.core.mcp_client import is_circuit_breaker_error
        if not is_circuit_breaker_error(error_code):
            return  # 业务错误不计入 breaker
        self._failure_count += 1
        if self._failure_count >= self.threshold:
            self._state = "OPEN"
            self._opened_at = time.monotonic()
            _log.warning("CircuitBreaker: OPEN (%d 次失败)", self._failure_count)


# ---------------------------------------------------------------------------
# DataQueryGateway
# ---------------------------------------------------------------------------


class DataQueryGateway:
    """数据查询唯一入口

    Phase 2: McpExecutor → LocalExecutor → QueryAgentExecutor 三级回退
    """

    def __init__(self):
        self._executors: List[Any] = []
        self._mcp_breaker = CircuitBreaker()
        self._register_executors()

    def _register_executors(self):
        """注册执行器（按优先级排序）"""
        self._executors = [
            McpExecutor(),
            LocalExecutor(),
            QueryAgentExecutor(),
        ]
        self._executors.sort(key=lambda e: e.priority)

    async def execute(
        self,
        question: str,
        session_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> UnifiedQueryResult:
        t0 = time.perf_counter()
        ctx = context or {}
        ctx["session_id"] = session_id

        # Phase 2 Layer A: MCP eligibility 判断
        eligibility = self._check_mcp_eligibility(question)
        ctx["domain_hint"] = eligibility.get("domain_hint", "")
        ctx["mcp_eligible"] = eligibility.get("eligible", False)
        if not eligibility.get("eligible"):
            _log.info("Gateway: MCP not eligible — reason=%s", eligibility.get("reason"))

        _log.info(
            "Gateway.execute: question={:.100}, session_id={} mcp_eligible={}",
            question, session_id, eligibility.get("eligible"),
        )

        raw, executor_path = await self._execute_with_fallback(question, ctx)
        from app.core.tracing import get_current_trace_id
        trace_json = self._build_trace_json(question, raw, eligibility,
                                             executor_path,
                                             get_current_trace_id(),
                                             ctx.get("_mcp_debug"))
        result = await self._post_process(raw, question, session_id, trace_json)
        result.latency_ms = (time.perf_counter() - t0) * 1000

        _log.info(
            "Gateway.execute done: source={} success={} latency={:.0f}ms",
            result.source, result.success, result.latency_ms,
        )
        return result

    def _check_mcp_eligibility(self, question: str) -> Dict[str, Any]:
        """Layer A: 判断问题是否属于 Phase 2 MCP 能力边界。

        纯规则实现: 业务关键词 + 实体识别。
        analytics 和 product domain 无需实体也可 eligible（对应 Tool 全参数可选）。
        """
        import re

        # 无需实体的 domain（对应 Tool 全可选参数或无需数字编码）
        _NO_ENTITY_DOMAINS = {"analytics", "product"}

        # 业务关键词 → domain
        domain_map = [
            ("analytics", ["汇总", "summary", "预警", "warning", "临期",
                           "慢周转", "slow"]),
            ("product", ["商品", "product", "sku", "条码", "规格", "品牌", "品类"]),
            ("inbound", ["入库", "inbound", "收货", "验收", "receiving"]),
            ("outbound", ["出库", "outbound", "发货", "配送", "拣货"]),
            ("inventory", ["库存", "stock", "inventory", "批次", "batch",
                           "库位", "仓位"]),
        ]
        domain_hint = ""
        for domain, keywords in domain_map:
            if any(kw.lower() in question.lower() for kw in keywords):
                domain_hint = domain
                break

        if not domain_hint:
            return {"eligible": False, "reason": "no_business_keyword",
                    "domain_hint": ""}

        # 无需实体的 domain 直接 eligible
        if domain_hint in _NO_ENTITY_DOMAINS:
            return {"eligible": True, "reason": "ok",
                    "domain_hint": domain_hint}

        # 实体识别（inventory / inbound / outbound 需要实体避免全表扫描）
        # 使用 (?<!\d)...(?!\d) 替代 \b — Python 3 默认 Unicode 模式下
        # \b 将中文视为 \w，导致 "502620的库存" 中 "0的" 之间无边界
        has_entity = bool(
            re.search(r'(?<!\d)\d{4,8}(?!\d)', question)   # SKU 编码
            or re.search(r'(?<!\d)\d{8}(?!\d)', question)   # 库位
            or re.search(r'(?<!\d)\d{19}(?!\d)', question)  # 批次号
            or re.search(r'(?<!\d)\d{10,}(?!\d)', question) # 单号
        )

        if not has_entity:
            return {"eligible": False, "reason": "missing_entity",
                    "domain_hint": domain_hint}

        return {"eligible": True, "reason": "ok", "domain_hint": domain_hint}

    async def _execute_with_fallback(
        self, question: str, context: Dict[str, Any]
    ) -> tuple[RawQueryResult, list]:
        """按优先级尝试 Executor，失败时按规则回退。

        Returns: (RawQueryResult, executor_path)
          executor_path: [{executor, success, error_code}, ...]
        """
        last_error = None
        executor_path: list = []

        for executor in self._executors:
            # ── McpExecutor 特殊处理 ──
            if executor.name == "mcp":
                if not context.get("mcp_eligible"):
                    _log.info("MCP 跳过: not eligible")
                    continue
                if not self._mcp_breaker.allow_request():
                    _log.info("MCP 跳过: CircuitBreaker OPEN")
                    continue

            if not await executor.is_available():
                _log.info("Executor {} 不可用，跳过", executor.name)
                continue

            _log.info("尝试 Executor: {} (priority={})", executor.name, executor.priority)
            result = await executor.execute(question, context)

            if result.success:
                _log.info("Executor {} 成功", executor.name)
                if executor.name == "mcp":
                    self._mcp_breaker.record_success()
                executor_path.append({
                    "executor": executor.name, "success": True,
                    "error_code": None,
                })
                return (result, executor_path)

            _log.warning(
                "Executor {} 失败: code={} msg={} retryable={}",
                executor.name, result.error_code, result.error_message, result.is_retryable,
            )
            executor_path.append({
                "executor": executor.name, "success": False,
                "error_code": result.error_code,
            })
            last_error = result

            # MCP 失败 → CircuitBreaker 计数（内部按 error_code 过滤）
            if executor.name == "mcp":
                self._mcp_breaker.record_failure(result.error_code or "")

            if not result.is_retryable:
                _log.info("Executor {} 错误不可回退，终止回退链", executor.name)
                break

        # 所有执行器都失败
        if last_error:
            return (last_error, executor_path)

        return (RawQueryResult(
            success=False,
            source="gateway",
            query_mode="fallback",
            error_code="all_executors_failed",
            error_message="所有查询执行器均不可用",
            is_retryable=False,
        ), executor_path)

    def _build_trace_json(self, question: str, raw: RawQueryResult,
                          eligibility: dict, executor_path: list,
                          trace_id: str = "", mcp_debug: dict = None) -> str:
        """组装查询追踪 JSON（存储到 query_history.trace_json）"""

        source = raw.source
        source_label = {"mcp": "MCP 查询", "local": "本地查询",
                         "queryagent": "旧版兜底", "gateway": "网关"}.get(source, source)

        # leader_view
        label = "查询成功"
        if not raw.success:
            label = "查询失败"
        elif source == "mcp":
            label = "MCP查询成功"
        elif source == "local":
            label = "本地查询"
        one_liner = f"{source_label} · {raw.total} 条 · {raw.latency_ms/1000:.1f}s"

        # fallback
        fallback_from = None
        fallback_to = None
        fallback_reason = None
        if len(executor_path) >= 2:
            first = executor_path[0]
            last = executor_path[-1]
            if not first["success"] and last["success"]:
                fallback_from = first["executor"]
                fallback_to = last["executor"]
                fallback_reason = first.get("error_code")

        # pipeline path
        def _path_label(e: dict) -> str:
            name = e["executor"]
            status = "OK" if e["success"] else "FAIL"
            if name == "mcp" and raw.tool_calls:
                tool = raw.tool_calls[0].tool_name
                return f"MCP({tool})→{status}"
            return f"{name}→{status}"

        # timeline: 各 executor 的执行耗时
        timeline = []
        for e in executor_path:
            timeline.append({
                "executor": e["executor"],
                "success": e["success"],
                "error_code": e.get("error_code"),
            })

        # debug_view: 开发调试信息
        mcp_dbg = mcp_debug or {}
        debug_view = {
            "sql": raw.sql,
            "tool_calls": [{"tool": tc.tool_name, "args": tc.arguments}
                           for tc in (raw.tool_calls or [])],
            "eligibility": {
                "domain": eligibility.get("domain_hint", ""),
                "eligible": eligibility.get("eligible", False),
                "reason": eligibility.get("reason", ""),
            },
            "mcp_tool_selection": {
                "candidates": mcp_dbg.get("selection_candidates", []),
                "selected": raw.tool_calls[0].tool_name if raw.tool_calls else "",
                "reason": mcp_dbg.get("selection_reason", ""),
                "confidence": raw.confidence,
            },
            "latency_breakdown": {
                "total_ms": raw.latency_ms,
                "mcp_graph_ms": mcp_dbg.get("graph_latency_ms"),
            },
            "timeline": timeline,
        }

        trace = {
            "leader_view": {"label": label, "one_liner": one_liner},
            "pipeline": {
                "source": source, "source_label": source_label,
                "path": " → ".join(_path_label(e) for e in executor_path)
                        if executor_path else source_label,
                "success": raw.success,
                "total": raw.total,
                "total_latency_ms": raw.latency_ms,
                "error_code": raw.error_code,
                "error_message": raw.error_message,
            },
            "ops_view": {
                "circuit_breaker": f"{self._mcp_breaker.state}",
                "fallback_triggered": fallback_from is not None,
                "fallback_from": fallback_from,
                "fallback_to": fallback_to,
                "fallback_reason": fallback_reason,
                "trace_id": trace_id,
            },
            "debug_view": debug_view,
        }
        return json.dumps(trace, ensure_ascii=False)

    async def _post_process(
        self, raw: RawQueryResult, question: str, session_id: Optional[str],
        trace_json: str = "{}",
    ) -> UnifiedQueryResult:
        """后处理：字段翻译 + 洞察补全 + 历史记录"""
        # 1. 字段翻译（仅成功时）
        translated_columns = raw.columns
        if raw.success and raw.columns:
            translated_columns = await self._translate_columns(raw.columns)

        # 2. 洞察补全（Executor 未返回时）
        insight = raw.insight
        if raw.success and not insight and raw.rows:
            insight = await self._generate_insight(question, raw.rows[:10],
                                                    raw.columns)

        # 3. 历史记录（成功和失败都保存，方便排查）
        history_id = None
        if session_id:
            history_id = await self._save_history(
                question=question,
                sql=raw.sql or "",
                total=raw.total,
                insight=insight,
                session_id=session_id,
                trace_json=trace_json,
            )

        # 4. 组装 UnifiedQueryResult
        from app.core.tracing import get_current_trace_id
        trace_id = get_current_trace_id()

        return UnifiedQueryResult(
            success=raw.success,
            source=raw.source,
            query_mode=raw.query_mode,
            question=question,
            sql=raw.sql,
            columns=translated_columns,
            rows=raw.rows,
            total=raw.total,
            insight=insight,
            confidence=raw.confidence,
            error_code=raw.error_code,
            error_message=raw.error_message,
            history_id=history_id,
            trace_id=str(trace_id),
        )

    # ── 从 QueryService 迁移的后处理方法 ──

    async def _translate_columns(self, columns: List[str]) -> List[str]:
        """将英文字段名翻译为中文 display_name"""
        try:
            schema_manager = await get_schema_manager()
            col_map = schema_manager.get_column_display_map()
            return [col_map.get(c, c) for c in columns]
        except Exception:
            return columns

    async def _save_history(
        self, question: str, sql: str, total: int,
        insight: Optional[Insight], session_id: str,
        trace_json: str = "{}",
    ) -> Optional[int]:
        """保存查询历史，返回 history_id"""
        try:
            history_item = {
                "session_id": session_id,
                "question": question,
                "sql": sql,
                "result_count": total,
                "insight": insight.summary if insight else "",
                "tables_used": "[]",
                "trace_json": trace_json,
                "created_at": datetime.now().isoformat(),
            }
            return await save_history(history_item)
        except Exception:
            _log.exception("保存查询历史失败")
            return None

    async def _generate_insight(
        self, question: str, rows: List[Any], columns: List[str]
    ) -> Optional[Insight]:
        """生成 AI 洞察（Executor 未返回时补生成）"""
        if not rows:
            return Insight(summary="查询无结果")
        try:
            from app.core.llm_manager import get_llm
            from app.agents.prompts_sql import INSIGHT_GENERATION_PROMPT
            from app.core.semantic_rules import parse_insight

            # 将 rows 转成 dict 列表格式
            dict_rows = []
            for row in rows[:10]:
                if isinstance(row, dict):
                    dict_rows.append(row)
                elif isinstance(row, (list, tuple)):
                    dict_rows.append({columns[i]: v for i, v in enumerate(row)
                                       if i < len(columns)})

            result_text = json.dumps(dict_rows, ensure_ascii=False, indent=2)
            llm = get_llm()
            prompt = INSIGHT_GENERATION_PROMPT.format(
                user_question=question,
                query_result=result_text,
            )
            response = llm.invoke(prompt)
            content = response.content if hasattr(response, 'content') else str(response)
            parsed = parse_insight(content)
            return Insight(
                summary=parsed.get("summary", ""),
                insights=parsed.get("insights", []),
                follow_ups=parsed.get("follow_ups", []),
            )
        except Exception:
            _log.exception("洞察生成失败")
            return None


# ---------------------------------------------------------------------------
# 单例
# ---------------------------------------------------------------------------

_gateway: Optional[DataQueryGateway] = None


def get_gateway() -> DataQueryGateway:
    """获取 DataQueryGateway 单例"""
    global _gateway
    if _gateway is None:
        _gateway = DataQueryGateway()
    return _gateway
