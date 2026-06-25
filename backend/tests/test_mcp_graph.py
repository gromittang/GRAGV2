"""
Phase 2: MCP Graph + Tool Registry + LLM Tool Selection 单元测试
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Tool Registry 测试
# ---------------------------------------------------------------------------

class TestToolRegistry:
    """显式 Tool→Domain 映射"""

    def test_all_15_tools_registered(self):
        from app.agents.graph_mcp import get_all_registry_tools
        assert len(get_all_registry_tools()) == 15

    def test_get_tool_domain_explicit(self):
        from app.agents.graph_mcp import get_tool_domain
        assert get_tool_domain("query_inventory_by_sku") == "inventory"
        assert get_tool_domain("query_product") == "product"
        assert get_tool_domain("query_outbound_order") == "outbound"
        assert get_tool_domain("query_inbound_detail") == "inbound"
        assert get_tool_domain("get_stock_warning") == "analytics"

    def test_get_tool_domain_unknown(self):
        from app.agents.graph_mcp import get_tool_domain
        assert get_tool_domain("nonexistent_tool") == ""

    def test_get_tools_for_domain_inventory(self):
        from app.agents.graph_mcp import get_tools_for_domain
        tools = get_tools_for_domain("inventory")
        assert len(tools) == 3
        names = [t["name"] for t in tools]
        assert "query_inventory_by_sku" in names

    def test_get_tools_for_domain_product(self):
        from app.agents.graph_mcp import get_tools_for_domain
        assert len(get_tools_for_domain("product")) == 3

    def test_get_tools_for_domain_analytics(self):
        from app.agents.graph_mcp import get_tools_for_domain
        assert len(get_tools_for_domain("analytics")) == 4

    def test_get_tools_for_domain_empty(self):
        from app.agents.graph_mcp import get_tools_for_domain
        assert get_tools_for_domain("nonexistent") == []

    def test_get_candidate_tool_names(self):
        from app.agents.graph_mcp import get_candidate_tool_names
        names = get_candidate_tool_names("inventory")
        assert len(names) == 3
        assert "query_inventory_by_sku" in names

    def test_get_candidate_tool_names_empty(self):
        from app.agents.graph_mcp import get_candidate_tool_names
        assert get_candidate_tool_names("") == []
        assert get_candidate_tool_names("unknown") == []

    def test_registry_has_descriptions(self):
        """Step 4: 所有 Tool 有 description 和 inputSchema"""
        from app.agents.graph_mcp import get_all_registry_tools
        for t in get_all_registry_tools():
            assert t.get("description"), f"Tool {t['name']} 缺少 description"
            assert t.get("inputSchema"), f"Tool {t['name']} 缺少 inputSchema"


# ---------------------------------------------------------------------------
# 图节点测试
# ---------------------------------------------------------------------------

class TestGraphMcpNodes:
    """tool_filter / mcp_call / result_format 节点"""

    @pytest.mark.asyncio
    async def test_tool_filter_node_with_domain(self):
        from app.agents.graph_mcp import tool_filter_node
        from app.core.agent_state import MCPAgentState
        state: dict = MCPAgentState(question="502620的库存", domain_hint="inventory")
        result = await tool_filter_node(state)
        assert len(result["candidate_tool_names"]) == 3
        assert "query_inventory_by_sku" in result["candidate_tool_names"]

    @pytest.mark.asyncio
    async def test_tool_filter_node_empty_domain(self):
        from app.agents.graph_mcp import tool_filter_node
        from app.core.agent_state import MCPAgentState
        state: dict = MCPAgentState(domain_hint="")
        result = await tool_filter_node(state)
        assert result["candidate_tool_names"] == []
        assert "error" in result

    @pytest.mark.asyncio
    async def test_tool_select_node_empty_candidates(self):
        """无候选 → 不调 LLM，直接返回 error"""
        from app.agents.graph_mcp import tool_select_node
        from app.core.agent_state import MCPAgentState
        state: dict = MCPAgentState(candidate_tool_names=[], question="test")
        result = await tool_select_node(state)
        assert result["selected_tool"] == ""
        assert "error" in result

    @pytest.mark.asyncio
    async def test_mcp_call_node_step3(self):
        from app.agents.graph_mcp import mcp_call_node
        from app.core.agent_state import MCPAgentState
        state: dict = MCPAgentState(
            selected_tool="query_inventory_by_sku",
            tool_arguments={"sku_code": "502620"},
        )
        result = await mcp_call_node(state)
        assert result["success"] is False
        assert result.get("error_code") is not None

    @pytest.mark.asyncio
    async def test_result_format_node_items(self):
        from app.agents.graph_mcp import result_format_node
        from app.core.agent_state import MCPAgentState
        state: dict = MCPAgentState(
            mcp_raw_result={"total": 2, "items": [
                {"plu_code": "502620", "plu_name": "测试商品"},
                {"plu_code": "502621", "plu_name": "另一个"}]},
        )
        result = await result_format_node(state)
        assert result["success"] is True
        assert result["columns"] == ["plu_code", "plu_name"]
        assert result["total"] == 2

    @pytest.mark.asyncio
    async def test_result_format_node_empty(self):
        from app.agents.graph_mcp import result_format_node
        from app.core.agent_state import MCPAgentState
        state: dict = MCPAgentState(mcp_raw_result={"total": 0, "items": []})
        result = await result_format_node(state)
        assert result["columns"] == []
        assert result["total"] == 0


# ---------------------------------------------------------------------------
# Step 4: LLM Tool Selection 测试
# ---------------------------------------------------------------------------

class TestLlmToolSelector:
    """_LlmToolSelector — LLM Tool 选择器"""

    @staticmethod
    def _make_selector(invoke_return):
        """创建 selector，用 mock LLM 替换。DeepSeekLLM 是 Pydantic model，
        不能直接 setattr → 在构造前 patch get_llm。"""
        from app.agents.graph_mcp import _LlmToolSelector
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = invoke_return
        with patch("app.core.llm_manager.get_llm", return_value=mock_llm):
            return _LlmToolSelector()

    def test_select_success(self):
        mock_r = type('r', (object,), {
            'content': '{"tool": "query_inventory_by_sku", '
                       '"args": {"sku_code": "502620", "limit": 100}, '
                       '"confidence": 0.9, "reason": "匹配SKU"}'
        })()
        selector = self._make_selector(mock_r)
        result = selector.select(
            "502620的库存",
            ["query_inventory_by_sku", "query_inventory_by_location"],
            "inventory")
        assert result.success is True
        assert result.tool_name == "query_inventory_by_sku"
        assert result.arguments["sku_code"] == "502620"
        assert result.confidence == 0.9

    def test_select_returns_null(self):
        mock_r = type('r', (object,), {
            'content': '{"tool": "", "args": {}, "reason": "无法选择"}'
        })()
        selector = self._make_selector(mock_r)
        result = selector.select("测试", ["query_product"], "product")
        assert result.success is False
        assert "无法" in result.reason

    def test_select_unknown_tool(self):
        mock_r = type('r', (object,), {
            'content': '{"tool": "execute_sql_readonly", "args": {}, '
                       '"reason": "需要自定义SQL"}'
        })()
        selector = self._make_selector(mock_r)
        result = selector.select("测试", ["query_product"], "product")
        assert result.success is False
        assert "未知 Tool" in result.reason

    def test_select_malformed_json(self):
        mock_r = type('r', (object,), {
            'content': '这是一段非JSON文本没有花括号'
        })()
        selector = self._make_selector(mock_r)
        result = selector.select("测试", ["query_product"], "product")
        assert result.success is False
        assert "非JSON" in result.reason

    def test_select_missing_required_param(self):
        mock_r = type('r', (object,), {
            'content': '{"tool": "query_inventory_by_sku", '
                       '"args": {"limit": 100}, '
                       '"confidence": 0.5, "reason": "查库存"}'
        })()
        selector = self._make_selector(mock_r)
        result = selector.select(
            "库存情况", ["query_inventory_by_sku"], "inventory")
        assert result.success is False
        assert "必填参数" in result.reason

    def test_select_args_not_dict(self):
        """B2 修复: LLM 返回 args 为 list → success=False"""
        mock_r = type('r', (object,), {
            'content': '{"tool": "query_inventory_by_sku", '
                       '"args": [1, 2, 3], '
                       '"confidence": 0.5, "reason": "test"}'
        })()
        selector = self._make_selector(mock_r)
        result = selector.select("测试", ["query_inventory_by_sku"], "inventory")
        assert result.success is False
        assert "args 类型错误" in result.reason

    def test_select_llm_api_error(self):
        """G1: LLM 调用异常 → success=False"""
        from app.agents.graph_mcp import _LlmToolSelector
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = RuntimeError("LLM timeout")
        with patch("app.core.llm_manager.get_llm", return_value=mock_llm):
            selector = _LlmToolSelector()
        result = selector.select("测试", ["query_product"], "product")
        assert result.success is False
        assert "LLM API" in result.reason

    def test_select_extracts_params(self):
        mock_r = type('r', (object,), {
            'content': '{"tool": "get_stock_warning", '
                       '"args": {"warning_type": "near_expiry", '
                       '"near_expiry_days": 30, "limit": 50}, '
                       '"confidence": 0.85, "reason": "用户要查快过期"}'
        })()
        selector = self._make_selector(mock_r)
        result = selector.select(
            "有没有快过期的",
            ["get_stock_warning", "get_inventory_summary"],
            "analytics")
        assert result.success is True
        assert result.tool_name == "get_stock_warning"
        assert result.arguments["warning_type"] == "near_expiry"


class TestToolSelectNodeStep4:
    """tool_select_node Step 4: LLM 选择 → state 映射"""

    @staticmethod
    def _make_mock_selector(invoke_return):
        """创建 mock LLM selector"""
        from app.agents.graph_mcp import _LlmToolSelector
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = invoke_return
        with patch("app.core.llm_manager.get_llm", return_value=mock_llm):
            return _LlmToolSelector()

    @pytest.mark.asyncio
    async def test_tool_select_node_llm_success(self):
        from app.agents.graph_mcp import tool_select_node
        from app.core.agent_state import MCPAgentState
        state: dict = MCPAgentState(
            question="502620的库存",
            candidate_tool_names=["query_inventory_by_sku"],
            domain_hint="inventory")
        mock_r = type('r', (object,), {
            'content': '{"tool": "query_inventory_by_sku", '
                       '"args": {"sku_code": "502620", "limit": 100}, '
                       '"confidence": 0.9, "reason": "匹配SKU"}'
        })()
        selector = self._make_mock_selector(mock_r)
        with patch("app.agents.graph_mcp._get_llm_selector", return_value=selector):
            result = await tool_select_node(state)
        assert result["selected_tool"] == "query_inventory_by_sku"
        assert result["tool_arguments"]["sku_code"] == "502620"
        assert result["confidence"] == 0.9

    @pytest.mark.asyncio
    async def test_tool_select_node_llm_failure(self):
        from app.agents.graph_mcp import tool_select_node
        from app.core.agent_state import MCPAgentState
        state: dict = MCPAgentState(
            question="库存情况",
            candidate_tool_names=["query_inventory_by_sku"],
            domain_hint="inventory")
        mock_r = type('r', (object,), {
            'content': '{"tool": "", "args": {}, "reason": "缺少SKU编码"}'
        })()
        selector = self._make_mock_selector(mock_r)
        with patch("app.agents.graph_mcp._get_llm_selector", return_value=selector):
            result = await tool_select_node(state)
        assert result["selected_tool"] == ""
        assert "error" in result
        assert result.get("error_code") == "tool_selection_failed"

    @pytest.mark.asyncio
    async def test_tool_select_node_llm_unknown_tool(self):
        from app.agents.graph_mcp import tool_select_node
        from app.core.agent_state import MCPAgentState
        state: dict = MCPAgentState(
            question="测试", candidate_tool_names=["query_product"],
            domain_hint="product")
        mock_r = type('r', (object,), {
            'content': '{"tool": "execute_sql_readonly", "args": {}, '
                       '"reason": "需要自定义SQL"}'
        })()
        selector = self._make_mock_selector(mock_r)
        with patch("app.agents.graph_mcp._get_llm_selector", return_value=selector):
            result = await tool_select_node(state)
        assert result["selected_tool"] == ""
        assert "error" in result

    @pytest.mark.asyncio
    async def test_error_code_missing_param_vs_selection_failed(self):
        """B1 修复: 缺必填参数 → tool_validation_failed; 选不出 → tool_selection_failed"""
        from app.agents.graph_mcp import tool_select_node
        from app.core.agent_state import MCPAgentState

        # 缺必填参数场景
        mock_missing = type('r', (object,), {
            'content': '{"tool": "query_inventory_by_sku", '
                       '"args": {"limit": 100}, '
                       '"reason": "缺SKU编码"}'
        })()
        selector = self._make_mock_selector(mock_missing)
        state: dict = MCPAgentState(
            question="库存", candidate_tool_names=["query_inventory_by_sku"],
            domain_hint="inventory")
        with patch("app.agents.graph_mcp._get_llm_selector", return_value=selector):
            r1 = await tool_select_node(state)
        assert r1["error_code"] == "tool_validation_failed", \
            f"缺参应返回 tool_validation_failed，实际: {r1.get('error_code')}"

        # 选不出 Tool 场景
        mock_null = type('r', (object,), {
            'content': '{"tool": "", "args": {}, "reason": "无法选择"}'
        })()
        selector2 = self._make_mock_selector(mock_null)
        state2: dict = MCPAgentState(
            question="不知道问什么", candidate_tool_names=["query_product"],
            domain_hint="product")
        with patch("app.agents.graph_mcp._get_llm_selector", return_value=selector2):
            r2 = await tool_select_node(state2)
        assert r2["error_code"] == "tool_selection_failed", \
            f"选不出应返回 tool_selection_failed，实际: {r2.get('error_code')}"


class TestBuildCandidateDescriptions:
    """_build_candidate_descriptions — 候选 Tool 描述格式化"""

    def test_formats_single_candidate(self):
        from app.agents.graph_mcp import _build_candidate_descriptions
        text = _build_candidate_descriptions(["query_inventory_by_sku"])
        assert "query_inventory_by_sku" in text
        assert "按 SKU 查库存" in text
        assert "sku_code" in text
        assert "必填" in text

    def test_formats_multi_candidates(self):
        from app.agents.graph_mcp import _build_candidate_descriptions
        text = _build_candidate_descriptions(
            ["query_inventory_by_sku", "query_product"])
        assert "query_inventory_by_sku" in text
        assert "query_product" in text
        assert "商品主数据" in text

    def test_formats_empty(self):
        from app.agents.graph_mcp import _build_candidate_descriptions
        assert _build_candidate_descriptions([]) == "(无可用 Tool)"


# ---------------------------------------------------------------------------
# 图编译测试
# ---------------------------------------------------------------------------

class TestGraphCompilation:
    def test_build_graph_returns_state_graph(self):
        from app.agents.graph_mcp import build_mcp_graph
        from langgraph.graph import StateGraph
        assert isinstance(build_mcp_graph(), StateGraph)

    def test_get_mcp_graph_compiles(self):
        from app.agents.graph_mcp import get_mcp_graph
        graph = get_mcp_graph()
        assert graph is not None
        assert get_mcp_graph() is graph  # 单例


# ---------------------------------------------------------------------------
# Config + Prompt + Constraint 测试（不变）
# ---------------------------------------------------------------------------

class TestMcpConfig:
    def test_config_fields_exist(self):
        from app.config import Settings
        s = Settings()
        assert hasattr(s, "mcp_enabled")
        assert hasattr(s, "mcp_base_url")
        assert hasattr(s, "mcp_api_key")
        assert hasattr(s, "mcp_timeout")
        assert hasattr(s, "mcp_tool_cache_ttl")
        assert hasattr(s, "mcp_health_cache_ttl")

    def test_config_defaults(self):
        from app.config import Settings
        s = Settings()
        # mcp_enabled 默认值在代码中是 False，但 .env 可能覆盖
        assert s.mcp_base_url == "http://localhost:8922"
        assert s.mcp_timeout == 60.0


class TestMcpPrompt:
    def test_prompt_contains_placeholders(self):
        from app.agents.prompts_sql import MCP_TOOL_SELECT_PROMPT
        assert "{tool_descriptions}" in MCP_TOOL_SELECT_PROMPT
        assert "{user_question}" in MCP_TOOL_SELECT_PROMPT
        assert "{domain_hint}" in MCP_TOOL_SELECT_PROMPT

    def test_prompt_formats_correctly(self):
        from app.agents.prompts_sql import MCP_TOOL_SELECT_PROMPT
        formatted = MCP_TOOL_SELECT_PROMPT.format(
            tool_descriptions="query_inventory_by_sku",
            user_question="502620的库存",
            domain_hint="inventory")
        assert "query_inventory_by_sku" in formatted
        assert "502620的库存" in formatted
        assert "inventory" in formatted


class TestConstraint2:
    def test_tool_registry_excludes_execute_sql(self):
        from app.agents.graph_mcp import get_all_registry_tools
        names = [t["name"] for t in get_all_registry_tools()]
        assert "execute_sql_readonly" not in names

    def test_no_auto_fallback_to_execute_sql(self):
        from app.agents.graph_mcp import get_candidate_tool_names
        for domain in ["inventory", "product", "inbound", "outbound", "analytics"]:
            assert "execute_sql_readonly" not in get_candidate_tool_names(domain)


class TestConstraint1:
    def test_registry_is_primary_source(self):
        from app.agents.graph_mcp import get_tool_domain, get_all_registry_tools
        for t in get_all_registry_tools():
            assert get_tool_domain(t["name"]) != ""

    def test_registry_domain_matches_declaration(self):
        from app.agents.graph_mcp import get_tool_domain, get_tools_for_domain
        for domain in ["inventory", "product", "inbound", "outbound", "analytics"]:
            for t in get_tools_for_domain(domain):
                assert get_tool_domain(t["name"]) == domain
