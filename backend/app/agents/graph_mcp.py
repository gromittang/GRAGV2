"""
LangGraph MCP Agent — Phase 2 Step 2 骨架

三层路由模型:
  Layer A: Gateway._check_mcp_eligibility() — 判断是否尝试 MCP
  Layer B: tool_filter_node — 规则层，按 domain 缩小候选 Tool 集（纯规则，不调 LLM）
  Layer C: tool_select_node — LLM 从候选中选 1 个 Tool + 填参数（Step 4 完成）

Phase 2 Step 2 实现:
  ✅ Tool Registry (显式 Tool→Domain 映射)
  ✅ tool_filter_node (Layer B, 纯规则)
  ✅ 节点骨架: tool_select_node / mcp_call_node / result_format_node (占位)
Phase 2 Step 3 实现: mcp_call_node + result_format_node
Phase 2 Step 4 实现: tool_select_node (LLM 调用)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from langgraph.graph import StateGraph, END, START

from app.core.agent_state import MCPAgentState
from app.core.logging import get_logger

_log = get_logger("graph.mcp")

# ---------------------------------------------------------------------------
# Tool Registry — 显式 Tool→Domain 映射 (Constraint 1)
# ---------------------------------------------------------------------------


# Phase 2 接入的 15 个预构建 Tool（含 description 和 inputSchema 用于 LLM 选择）
_MCP_TOOLS: List[Dict[str, Any]] = [
    # ── 库存域 ──
    {"name": "query_inventory_by_sku", "domain": "inventory",
     "family": "inventory_detail",
     "description": "按 SKU 查库存分布（库位/批次/数量/日期）",
     "inputSchema": {"required": ["sku_code"], "properties": {
         "sku_code": {"type": "string", "description": "商品编码"},
         "org_code": {"type": "string", "description": "物流组织"},
         "store_code": {"type": "string", "description": "仓库(01=良品,02=不良品)"},
         "limit": {"type": "integer", "description": "返回行数上限"},
     }}},
    {"name": "query_inventory_by_location", "domain": "inventory",
     "family": "inventory_detail",
     "description": "按库位查库存（该库位下所有商品）",
     "inputSchema": {"required": ["location_code"], "properties": {
         "location_code": {"type": "string", "description": "库位编码"},
         "org_code": {"type": "string", "description": "物流组织"},
         "store_code": {"type": "string", "description": "仓库"},
         "limit": {"type": "integer", "description": "返回行数上限"},
     }}},
    {"name": "query_inventory_by_batch", "domain": "inventory",
     "family": "inventory_detail",
     "description": "按批次号查库存",
     "inputSchema": {"required": ["batch_no"], "properties": {
         "batch_no": {"type": "string", "description": "批次号(19位Snowflake ID)"},
         "sku_code": {"type": "string", "description": "可选: 限定商品"},
         "org_code": {"type": "string", "description": "物流组织"},
         "store_code": {"type": "string", "description": "仓库"},
         "limit": {"type": "integer", "description": "返回行数上限"},
     }}},
    # ── 商品域 ──
    {"name": "query_product", "domain": "product",
     "family": "product_master",
     "description": "商品主数据查询（含品牌/品类，已JOIN）",
     "inputSchema": {"required": [], "properties": {
         "sku_code": {"type": "string", "description": "商品编码(精确匹配)"},
         "sku_name": {"type": "string", "description": "商品名称(LIKE模糊)"},
         "bar_code": {"type": "string", "description": "条码"},
         "status": {"type": "string", "description": "状态(1=正常,0=未启用)"},
         "limit": {"type": "integer", "description": "返回行数上限"},
     }}},
    {"name": "query_product_spec", "domain": "product",
     "family": "product_master",
     "description": "商品规格详情（包装层级/条码列表）",
     "inputSchema": {"required": ["sku_code"], "properties": {
         "sku_code": {"type": "string", "description": "商品编码"},
         "limit": {"type": "integer", "description": "返回行数上限"},
     }}},
    {"name": "query_product_warehouse_config", "domain": "product",
     "family": "product_config",
     "description": "商品仓库配置（批次处理/抽检/补货策略）",
     "inputSchema": {"required": ["sku_code"], "properties": {
         "sku_code": {"type": "string", "description": "商品编码"},
         "org_code": {"type": "string", "description": "物流组织"},
         "log_area_code": {"type": "string", "description": "物理大区"},
     }}},
    # ── 入库域 ──
    {"name": "query_inbound_order", "domain": "inbound",
     "family": "inbound_doc",
     "description": "入库单头查询（日期自动UTC→UTC+8）",
     "inputSchema": {"required": [], "properties": {
         "bill_no": {"type": "string", "description": "入库单号(精确匹配)"},
         "org_code": {"type": "string", "description": "物流组织"},
         "store_code": {"type": "string", "description": "仓库"},
         "supplier_code": {"type": "string", "description": "供应商编码"},
         "date_from": {"type": "string", "description": "开始日期 YYYY-MM-DD"},
         "date_to": {"type": "string", "description": "结束日期 YYYY-MM-DD"},
         "limit": {"type": "integer", "description": "返回行数上限"},
     }}},
    {"name": "query_inbound_detail", "domain": "inbound",
     "family": "inbound_doc",
     "description": "入库单明细（按单号查明细行）",
     "inputSchema": {"required": ["bill_no"], "properties": {
         "bill_no": {"type": "string", "description": "入库单号"},
         "limit": {"type": "integer", "description": "返回行数上限"},
     }}},
    {"name": "query_receiving_record", "domain": "inbound",
     "family": "inbound_doc",
     "description": "收货验收记录（预约单→验收单对应关系）",
     "inputSchema": {"required": [], "properties": {
         "org_code": {"type": "string", "description": "物流组织"},
         "store_code": {"type": "string", "description": "仓库"},
         "supplier_code": {"type": "string", "description": "供应商编码"},
         "date_from": {"type": "string", "description": "开始日期"},
         "date_to": {"type": "string", "description": "结束日期"},
         "limit": {"type": "integer", "description": "返回行数上限"},
     }}},
    # ── 出库域 ──
    {"name": "query_outbound_order", "domain": "outbound",
     "family": "outbound_doc",
     "description": "出库单头查询（含ERP配送单号）",
     "inputSchema": {"required": [], "properties": {
         "bill_no": {"type": "string", "description": "出库单号(精确匹配)"},
         "org_code": {"type": "string", "description": "物流组织"},
         "store_code": {"type": "string", "description": "仓库"},
         "shop_code": {"type": "string", "description": "收货单位编码"},
         "date_from": {"type": "string", "description": "开始日期"},
         "date_to": {"type": "string", "description": "结束日期"},
         "limit": {"type": "integer", "description": "返回行数上限"},
     }}},
    {"name": "query_outbound_detail", "domain": "outbound",
     "family": "outbound_doc",
     "description": "出库单明细（来源库位/批次/数量）",
     "inputSchema": {"required": ["bill_no"], "properties": {
         "bill_no": {"type": "string", "description": "出库单号"},
         "limit": {"type": "integer", "description": "返回行数上限"},
     }}},
    # ── 分析域 ──
    {"name": "get_inventory_summary", "domain": "analytics",
     "family": "analytics_summary",
     "description": "库存汇总（按SKU聚合：总量/批次数/库位数）",
     "inputSchema": {"required": [], "properties": {
         "store_code": {"type": "string", "description": "仓库过滤"},
         "log_area_code": {"type": "string", "description": "物理大区过滤"},
         "limit": {"type": "integer", "description": "返回行数上限"},
     }}},
    {"name": "get_stock_warning", "domain": "analytics",
     "family": "analytics_warning",
     "description": "库存预警（低库存/临期商品）",
     "inputSchema": {"required": [], "properties": {
         "warning_type": {"type": "string", "description": "low_stock/near_expiry/all"},
         "low_stock_threshold": {"type": "integer", "description": "低库存阈值"},
         "near_expiry_days": {"type": "integer", "description": "临期天数"},
         "limit": {"type": "integer", "description": "返回行数上限"},
     }}},
    {"name": "get_slow_moving_inventory", "domain": "analytics",
     "family": "analytics_slow_moving",
     "description": "慢周转库存（长期未出库商品）",
     "inputSchema": {"required": [], "properties": {
         "dormant_days": {"type": "integer", "description": "静默天数(默认90)"},
         "limit": {"type": "integer", "description": "返回行数上限"},
     }}},
    {"name": "query_stock_flow", "domain": "analytics",
     "family": "analytics_flow",
     "description": "库存流水台账（出入库记录）",
     "inputSchema": {"required": [], "properties": {
         "sku_code": {"type": "string", "description": "商品编码"},
         "store_code": {"type": "string", "description": "仓库"},
         "date_from": {"type": "string", "description": "开始日期"},
         "date_to": {"type": "string", "description": "结束日期"},
         "limit": {"type": "integer", "description": "返回行数上限"},
     }}},
]

# 快速查找索引
_TOOL_BY_NAME: Dict[str, Dict[str, Any]] = {t["name"]: t for t in _MCP_TOOLS}
_TOOLS_BY_DOMAIN: Dict[str, List[Dict[str, Any]]] = {}
for _t in _MCP_TOOLS:
    _TOOLS_BY_DOMAIN.setdefault(_t["domain"], []).append(_t)


def get_tool_domain(tool_name: str) -> str:
    """获取 Tool 的 domain（显式 Registry，不为空时返回 domain）"""
    return _TOOL_BY_NAME.get(tool_name, {}).get("domain", "")


def get_tools_for_domain(domain: str) -> List[Dict[str, Any]]:
    """获取某 domain 下的所有 Tool（Layer B 使用）"""
    return _TOOLS_BY_DOMAIN.get(domain, [])


def get_all_registry_tools() -> List[Dict[str, Any]]:
    """获取 Registry 中所有 Tool"""
    return list(_MCP_TOOLS)


def get_candidate_tool_names(domain_hint: str) -> List[str]:
    """Layer B 核心: domain_hint → candidate tool names"""
    if not domain_hint:
        return []
    tools = _TOOLS_BY_DOMAIN.get(domain_hint, [])
    return [t["name"] for t in tools]


# ---------------------------------------------------------------------------
# 兼容层: _infer_domain() 仅在 Tool Registry 未命中时作为 fallback (Constraint 1)
# ---------------------------------------------------------------------------

def _infer_domain_fallback(tool_name: str) -> str:
    """从 Tool 名称推断 domain（仅 fallback，优先级最低）

    当 Tool 不在显式 Registry 中时使用（如 MCP Server 新增了 Tool）。
    正常路由不应走到这里。
    """
    from app.core.mcp_client import _infer_domain
    result = _infer_domain(tool_name)
    if result:
        _log.warning("Tool '%s' 不在显式 Registry 中，使用 _infer_domain fallback → '%s'",
                     tool_name, result)
    return result


# ---------------------------------------------------------------------------
# 图节点
# ---------------------------------------------------------------------------


async def tool_filter_node(state: MCPAgentState) -> dict:
    """Layer B: 按 domain_hint 缩小候选 Tool 集。

    纯规则实现，不调用 LLM。

    输入: state["domain_hint"] (来自 Layer A)
    输出: state["candidate_tool_names"]
    """
    domain_hint = state.get("domain_hint", "")
    if not domain_hint:
        _log.info("Layer B: domain_hint 为空，无法缩小候选 Tool")
        return {
            "candidate_tool_names": [],
            "error": "domain_hint 为空",
        }

    candidates = get_candidate_tool_names(domain_hint)
    _log.info("Layer B: domain_hint=%s → %d candidate tools: %s",
              domain_hint, len(candidates), candidates)

    return {"candidate_tool_names": candidates}


# ---------------------------------------------------------------------------
# Step 4: LLM Tool Selection
# ---------------------------------------------------------------------------


@dataclass
class ToolSelectionResult:
    """LLM Tool 选择的内部结果"""
    success: bool = False
    tool_name: str = ""
    arguments: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    reason: str = ""


class _LlmToolSelector:
    """LLM Tool 选择器 — 从候选集中选 1 个 Tool + 提取参数。

    通过 MCP_TOOL_SELECT_PROMPT 调用 LLM，解析 JSON 返回。
    Step 4 实现；Phase 3 扩展为支持 clarification。
    """

    def __init__(self):
        from app.core.llm_manager import get_llm
        self._llm = get_llm()

    def select(
        self, question: str, candidates: List[str], domain_hint: str
    ) -> ToolSelectionResult:
        """从候选 Tool 中选择最合适的 1 个，并提取参数。"""
        import json as _json
        import re as _re

        # 1. 构建候选 Tool 描述
        tool_descriptions = _build_candidate_descriptions(candidates)

        # 2. 填充 Prompt
        from app.agents.prompts_sql import MCP_TOOL_SELECT_PROMPT
        prompt = MCP_TOOL_SELECT_PROMPT.format(
            tool_descriptions=tool_descriptions,
            user_question=question,
            domain_hint=domain_hint,
        )

        # 3. 调用 LLM
        try:
            response = self._llm.invoke(prompt)
            content = response.content if hasattr(response, 'content') else str(response)
        except Exception as exc:
            _log.error("LLM Tool Selection 调用失败: %s", exc)
            return ToolSelectionResult(
                success=False,
                reason=f"LLM API 调用失败: {exc}",
            )

        # 4. 解析 JSON
        json_match = _re.search(r'\{[\s\S]*\}', content)
        if not json_match:
            _log.warning("LLM 返回非 JSON: %s", content[:200])
            return ToolSelectionResult(
                success=False,
                reason="LLM 返回格式异常（非JSON）",
            )

        try:
            parsed = _json.loads(json_match.group(0))
        except _json.JSONDecodeError as exc:
            _log.warning("LLM 返回 JSON 解析失败: %s", exc)
            return ToolSelectionResult(
                success=False,
                reason=f"JSON 解析失败: {exc}",
            )

        # 5. 提取字段
        tool_name = parsed.get("tool", "")
        if not tool_name:
            return ToolSelectionResult(
                success=False,
                reason="LLM 无法选择合适的 Tool（返回 null）",
            )

        # 6. 校验：tool_name 必须在候选集中
        if tool_name not in candidates:
            _log.warning(
                "LLM 选择了不在候选列表中的 Tool: %s, candidates=%s",
                tool_name, candidates,
            )
            return ToolSelectionResult(
                success=False,
                reason=f"LLM 选择了未知 Tool: {tool_name}",
            )

        args = parsed.get("args", {})
        if not isinstance(args, dict):
            _log.warning("LLM 返回的 args 类型错误: %s", type(args).__name__)
            return ToolSelectionResult(
                success=False,
                reason=f"LLM 返回的 args 类型错误: {type(args).__name__}",
            )

        confidence = float(parsed.get("confidence", 0.8))
        reason = parsed.get("reason", "")

        # 7. 校验必填参数
        reg = _TOOL_BY_NAME.get(tool_name, {})
        required = reg.get("inputSchema", {}).get("required", [])
        missing = [p for p in required if p not in args or not args[p]]
        if missing:
            _log.warning(
                "Tool %s 缺少必填参数: %s (LLM args=%s)",
                tool_name, missing, args,
            )
            return ToolSelectionResult(
                success=False,
                tool_name=tool_name,  # 记录已选 Tool（供调试）
                reason=f"缺少必填参数: {', '.join(missing)}",
            )

        return ToolSelectionResult(
            success=True,
            tool_name=tool_name,
            arguments=args,
            confidence=confidence,
            reason=reason,
        )


def _build_candidate_descriptions(candidate_names: List[str]) -> str:
    """从 Tool Registry 构建候选 Tool 的 LLM 友好描述文本。

    优先使用 Registry 中的 description 和 inputSchema。
    Phase 3: 扩展为优先使用 MCP Server list_tools() 返回的真实信息。
    """
    lines = []
    for name in candidate_names:
        reg = _TOOL_BY_NAME.get(name, {})
        desc = reg.get("description", name)
        schema = reg.get("inputSchema", {})
        required = schema.get("required", [])
        params = []
        for pname, pinfo in schema.get("properties", {}).items():
            req_mark = " *必填*" if pname in required else ""
            params.append(f"{pname}: {pinfo.get('type', 'any')}{req_mark}")
        lines.append(f"• **{name}**: {desc}")
        if params:
            lines.append(f"  参数: {', '.join(params)}")
        if required:
            lines.append(f"  [必填: {', '.join(required)}]")
    return "\n".join(lines) if lines else "(无可用 Tool)"


_llm_selector: Optional[_LlmToolSelector] = None


def _get_llm_selector() -> _LlmToolSelector:
    """获取 LLM Tool 选择器单例"""
    global _llm_selector
    if _llm_selector is None:
        _llm_selector = _LlmToolSelector()
    return _llm_selector


# ---------------------------------------------------------------------------
# 图节点
# ---------------------------------------------------------------------------


async def tool_select_node(state: MCPAgentState) -> dict:
    """Layer C: LLM 从候选集中选择 1 个 Tool + 提取参数。

    Step 4: LLM Tool Selection（替换 Step 3 规则版）。
    LLM 失败 → tool_selection_failed → Gateway 回退到 LocalExecutor。

    输入: state["question"], state["candidate_tool_names"], state["domain_hint"]
    输出: state["selected_tool"], state["tool_arguments"], state["confidence"]
    """
    candidates = state.get("candidate_tool_names", [])
    question = state.get("question", "")
    domain_hint = state.get("domain_hint", "")

    if not candidates:
        _log.info("Layer C: 无候选 Tool，跳过 LLM 选择")
        return {
            "selected_tool": "",
            "tool_arguments": {},
            "error": "tool_select_node: 无候选 Tool",
        }

    selector = _get_llm_selector()
    result = selector.select(question, candidates, domain_hint)

    # ── 可观测日志 ──
    _log.info(
        "Layer C LLM: question='%s' domain=%s candidates=%s → "
        "success=%s tool=%s args=%s confidence=%.2f reason='%s'",
        question[:80], domain_hint, candidates,
        result.success, result.tool_name, result.arguments,
        result.confidence, result.reason,
    )

    if result.success:
        return {
            "selected_tool": result.tool_name,
            "tool_arguments": result.arguments,
            "confidence": result.confidence,
            "selection_candidates": candidates,
            "selection_reason": result.reason,
        }

    # 失败 → 回退到 LocalExecutor
    # 区分: 缺必填参数 (Phase 3 升级为 clarification) vs 选不出 Tool
    if result.reason and "必填参数" in result.reason:
        error_code = "tool_validation_failed"  # Phase 3 → missing_required_param
    else:
        error_code = "tool_selection_failed"

    return {
        "selected_tool": "",
        "tool_arguments": {},
        "error": f"LLM Tool Selection 失败: {result.reason}",
        "error_code": error_code,
    }


async def mcp_call_node(state: MCPAgentState) -> dict:
    """调用 MCP Tool（通过 state 传入的 McpClientManager）。

    Phase 2 Step 3.2: McpClientManager 由 McpExecutor 通过 state["mcp_manager"] 传入，
    复用连接，不再每次创建。

    输入: state["selected_tool"], state["tool_arguments"], state["mcp_manager"]
    输出: state["mcp_raw_result"], state["tool_calls"], state["success"], state["error"]
    """
    from app.core.mcp_client import McpErrorCode

    tool_name = state.get("selected_tool", "")
    tool_args = state.get("tool_arguments", {})

    if not tool_name:
        _log.warning("mcp_call_node: selected_tool 为空")
        return {
            "success": False,
            "error": "未选择 Tool",
            "error_code": McpErrorCode.TOOL_SELECTION_FAILED,
        }

    # Step 3.2: 从 state 获取 manager（McpExecutor 注入）
    mgr = state.get("mcp_manager")
    if mgr is None:
        _log.error("mcp_call_node: mcp_manager 未注入到 state")
        return {
            "success": False,
            "error": "MCP 客户端未初始化",
            "error_code": McpErrorCode.INTERNAL_ERROR,
        }

    try:
        _log.info("mcp_call_node: tool=%s args=%s", tool_name, tool_args)
        raw = await mgr.call_tool(tool_name, tool_args)

        return {
            "mcp_raw_result": raw,
            "tool_calls": [{"tool": tool_name, "arguments": tool_args}],
            "success": True,
            "error": None,
            "error_code": None,
        }
    except Exception as exc:
        from app.core.mcp_client import WmsMcpError
        if isinstance(exc, WmsMcpError):
            error_code = exc.code
            error_msg = exc.message
        else:
            error_code = McpErrorCode.INTERNAL_ERROR
            error_msg = str(exc)

        _log.warning("mcp_call_node 失败: code=%s msg=%s", error_code, error_msg)
        return {
            "mcp_raw_result": {},
            "tool_calls": [],
            "success": False,
            "error": error_msg,
            "error_code": error_code,
        }


async def result_format_node(state: MCPAgentState) -> dict:
    """MCP 返回 → 统一 {columns, rows, total} 格式。

    Phase 2 Step 3: 完整实现。
    处理两种 MCP 返回格式:
      - 预构建 Tool: {"total": N, "items": [{...}, ...]}
      - execute_sql_readonly: {"columns": [...], "rows": [[...]], "row_count": N}

    输入: state["mcp_raw_result"], state["tool_calls"]
    输出: state["columns"], state["rows"], state["total"]
    """
    raw = state.get("mcp_raw_result", {}) or {}
    tool_calls = state.get("tool_calls", [])

    if not raw:
        return {
            "columns": [], "rows": [], "total": 0,
            "success": True, "error": None,
        }

    # MCP Tool 级错误: isError=true
    if raw.get("isError"):
        error_text = ""
        for item in raw.get("content", []):
            if isinstance(item, dict) and item.get("type") == "text":
                error_text += item.get("text", "")
        return {
            "columns": [], "rows": [], "total": 0,
            "success": False,
            "error": error_text or "MCP Tool 执行失败",
        }

    # 预构建 Tool 格式: items
    if "items" in raw:
        items = raw["items"]
        if items:
            columns = list(items[0].keys())
            rows = [[item.get(c) for c in columns] for item in items]
        else:
            columns = []
            rows = []
        total = raw.get("total", len(items))
        _log.info("result_format: items → %d columns, %d rows", len(columns), total)
        return {
            "columns": columns,
            "rows": rows,
            "total": total,
            "success": True,
            "error": None,
        }

    # execute_sql_readonly 格式: columns + rows
    if "columns" in raw and "rows" in raw:
        _log.info("result_format: sql → %d columns, %d rows",
                  len(raw["columns"]), raw.get("row_count", 0))
        return {
            "columns": raw["columns"],
            "rows": raw["rows"],
            "total": raw.get("row_count", len(raw["rows"])),
            "success": True,
            "error": None,
        }

    # 未知格式
    _log.warning("result_format: 无法识别的 MCP 返回格式 keys=%s", list(raw.keys()))
    return {
        "columns": [],
        "rows": [],
        "total": 0,
        "success": False,
        "error": f"无法识别的 MCP 返回格式: {list(raw.keys())[:5]}",
    }


# ---------------------------------------------------------------------------
# 条件边
# ---------------------------------------------------------------------------

def _check_layer_b(state: MCPAgentState) -> str:
    """Layer B → 有候选 Tool → Layer C，否则 → END"""
    if state.get("candidate_tool_names"):
        return "tool_select"
    return END


def _check_layer_c(state: MCPAgentState) -> str:
    """Layer C → 有选中 Tool → mcp_call，否则 → END"""
    if state.get("selected_tool"):
        return "mcp_call"
    return END


def _check_mcp_result(state: MCPAgentState) -> str:
    """MCP 调用 → 成功 → result_format，否则 → END"""
    if state.get("success"):
        return "result_format"
    return END


# ---------------------------------------------------------------------------
# 图构建
# ---------------------------------------------------------------------------


def build_mcp_graph() -> StateGraph:
    """构建 MCP LangGraph

    图结构:
      START → tool_filter (Layer B)
        → (有候选) → tool_select (Layer C)
          → (有选中) → mcp_call
            → (成功) → result_format → END
            → (失败) → END
          → (无选中) → END
        → (无候选) → END
    """
    graph = StateGraph(MCPAgentState)

    graph.add_node("tool_filter", tool_filter_node)
    graph.add_node("tool_select", tool_select_node)
    graph.add_node("mcp_call", mcp_call_node)
    graph.add_node("result_format", result_format_node)

    graph.add_edge(START, "tool_filter")

    graph.add_conditional_edges("tool_filter", _check_layer_b, {
        "tool_select": "tool_select",
        END: END,
    })

    graph.add_conditional_edges("tool_select", _check_layer_c, {
        "mcp_call": "mcp_call",
        END: END,
    })

    graph.add_conditional_edges("mcp_call", _check_mcp_result, {
        "result_format": "result_format",
        END: END,
    })

    graph.add_edge("result_format", END)

    return graph


# ---------------------------------------------------------------------------
# 编译后的 graph 单例
# ---------------------------------------------------------------------------

_compiled_mcp_graph = None


def get_mcp_graph():
    """获取编译后的 MCP LangGraph（单例）"""
    global _compiled_mcp_graph
    if _compiled_mcp_graph is None:
        _compiled_mcp_graph = build_mcp_graph().compile()
    return _compiled_mcp_graph
