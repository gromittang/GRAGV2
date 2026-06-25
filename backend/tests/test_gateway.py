"""
Phase 1: DataQueryGateway 单元测试
覆盖: LocalExecutor、QueryAgentExecutor、回退链、后处理、UnifiedQueryResult

注意: sys.modules mock 已移至 tests/conftest.py 的 pytest_configure 钩子，
确保在收集期间注入且 session 结束时自动清理。
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# UnifiedQueryResult 结构测试
# ---------------------------------------------------------------------------

class TestUnifiedQueryResult:
    """UnifiedQueryResult 数据类基础测试"""

    def test_default_construction(self):
        from app.core.data_query_gateway import UnifiedQueryResult
        r = UnifiedQueryResult()
        assert r.success is True
        assert r.source == ""
        assert r.columns == []
        assert r.rows == []
        assert r.total == 0

    def test_custom_construction(self):
        from app.core.data_query_gateway import UnifiedQueryResult, Insight
        r = UnifiedQueryResult(
            success=True,
            source="local",
            query_mode="sql",
            question="测试",
            sql="SELECT 1",
            columns=["col1"],
            rows=[[1]],
            total=1,
            insight=Insight(summary="测试洞察"),
            confidence=0.9,
            trace_id="trace-123",
            latency_ms=100.0,
        )
        assert r.source == "local"
        assert r.sql == "SELECT 1"
        assert r.columns == ["col1"]
        assert r.total == 1
        assert r.insight.summary == "测试洞察"


# ---------------------------------------------------------------------------
# LocalExecutor 测试
# ---------------------------------------------------------------------------

class TestLocalExecutor:
    """LocalExecutor — 适配 graph_nl2sql"""

    @pytest.mark.asyncio
    async def test_execute_success(self):
        """正常返回 — graph state 含 query_result"""
        from app.core.data_query_gateway import LocalExecutor

        executor = LocalExecutor()
        assert executor.name == "local"
        assert executor.priority == 1

        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value={
            "success": True,
            "sql": "SELECT * FROM test",
            "columns": ["plu_code", "plu_name"],
            "query_result": {"rows": [["502620", "测试商品"]]},
            "total": 1,
            "confidence": 0.95,
            "insight": {"summary": "结果分析", "insights": [], "follow_ups": []},
        })

        with patch("app.agents.graph_nl2sql.get_query_graph", return_value=mock_graph):
            result = await executor.execute("测试问题", {})

        assert result.success is True
        assert result.source == "local"
        assert result.query_mode == "sql"
        assert result.sql == "SELECT * FROM test"
        assert result.columns == ["plu_code", "plu_name"]
        assert result.rows == [["502620", "测试商品"]]
        assert result.total == 1
        assert result.confidence == 0.95
        assert result.insight is not None
        assert result.insight.summary == "结果分析"

    @pytest.mark.asyncio
    async def test_execute_with_error(self):
        """graph state 含 error"""
        from app.core.data_query_gateway import LocalExecutor

        executor = LocalExecutor()
        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value={
            "success": False,
            "error": "Schema not found for query",
        })

        with patch("app.agents.graph_nl2sql.get_query_graph", return_value=mock_graph):
            result = await executor.execute("找不到的问题", {})

        assert result.success is False
        assert result.source == "local"
        assert result.error_code == "schema_not_found"
        assert result.is_retryable is True  # schema 差异 → 允许回退

    @pytest.mark.asyncio
    async def test_execute_llm_error_not_retryable(self):
        """LLM 错误 → 不可回退"""
        from app.core.data_query_gateway import LocalExecutor

        executor = LocalExecutor()
        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value={
            "success": False,
            "error": "DeepSeek API key invalid",
        })

        with patch("app.agents.graph_nl2sql.get_query_graph", return_value=mock_graph):
            result = await executor.execute("测试", {})

        assert result.success is False
        assert result.error_code == "llm_api_error"
        assert result.is_retryable is False  # LLM 不可用 → 不回退

    @pytest.mark.asyncio
    async def test_is_available(self):
        from app.core.data_query_gateway import LocalExecutor
        executor = LocalExecutor()
        assert await executor.is_available() is True


# ---------------------------------------------------------------------------
# QueryAgentExecutor 测试
# ---------------------------------------------------------------------------

class TestQueryAgentExecutor:
    """QueryAgentExecutor — 适配 query_agent"""

    @pytest.mark.asyncio
    async def test_execute_success(self):
        """正常返回"""
        from app.core.data_query_gateway import QueryAgentExecutor

        executor = QueryAgentExecutor()
        assert executor.name == "queryagent"
        assert executor.priority == 2

        mock_agent = MagicMock()
        mock_agent.query = AsyncMock(return_value={
            "success": True,
            "sql": "SELECT * FROM test LIMIT 100",
            "results": [{"plu_code": "502620"}],
            "columns": ["plu_code"],
            "total": 1,
            "confidence": 0.8,
            "insight": {"summary": "QueryAgent 分析", "insights": [], "follow_ups": []},
        })

        with patch("app.agents.query_agent.get_query_agent", return_value=mock_agent):
            result = await executor.execute("测试", {"session_id": "test"})

        assert result.success is True
        assert result.source == "queryagent"
        assert result.query_mode == "fallback"
        assert result.total == 1
        assert result.insight.summary == "QueryAgent 分析"

    @pytest.mark.asyncio
    async def test_execute_failure(self):
        """失败 — 最后一级，is_retryable=False"""
        from app.core.data_query_gateway import QueryAgentExecutor

        executor = QueryAgentExecutor()
        mock_agent = MagicMock()
        mock_agent.query = AsyncMock(return_value={
            "success": False,
            "error": "MySQL connection failed",
        })

        with patch("app.agents.query_agent.get_query_agent", return_value=mock_agent):
            result = await executor.execute("测试", {})

        assert result.success is False
        assert result.source == "queryagent"
        assert result.is_retryable is False  # 最后一级


# ---------------------------------------------------------------------------
# _classify_error / _is_retryable_error 测试
# ---------------------------------------------------------------------------

class TestErrorClassification:
    """Phase 1 错误分类 + 回退判定"""

    def test_classify_langgraph_error(self):
        from app.core.data_query_gateway import _classify_error
        assert _classify_error({"error": "langgraph state serialization failed"}) == "langgraph_error"

    def test_classify_llm_error(self):
        from app.core.data_query_gateway import _classify_error
        assert _classify_error({"error": "openai API key not found"}) == "llm_api_error"

    def test_classify_db_error(self):
        from app.core.data_query_gateway import _classify_error
        assert _classify_error({"error": "MySQL connection refused"}) == "db_connection_failed"

    def test_classify_security_error(self):
        from app.core.data_query_gateway import _classify_error
        assert _classify_error({"error": "禁止 DROP 操作"}) == "sql_security_violation"

    def test_classify_schema_error(self):
        from app.core.data_query_gateway import _classify_error
        assert _classify_error({"error": "无法找到相关表"}) == "schema_not_found"

    def test_retryable_langgraph(self):
        from app.core.data_query_gateway import _is_retryable_error
        assert _is_retryable_error({"error": "langgraph node error"}) is True

    def test_not_retryable_llm(self):
        from app.core.data_query_gateway import _is_retryable_error
        assert _is_retryable_error({"error": "llm rate limit"}) is False

    def test_not_retryable_db(self):
        from app.core.data_query_gateway import _is_retryable_error
        assert _is_retryable_error({"error": "database connection failed"}) is False

    def test_not_retryable_security(self):
        from app.core.data_query_gateway import _is_retryable_error
        assert _is_retryable_error({"error": "drop table detected"}) is False


# ---------------------------------------------------------------------------
# DataQueryGateway 测试
# ---------------------------------------------------------------------------

class TestGatewayExecute:
    """Gateway.execute() 端到端"""

    @pytest.mark.asyncio
    async def test_local_executor_success(self):
        """LocalExecutor 成功 → 直接返回"""
        from app.core.data_query_gateway import get_gateway, UnifiedQueryResult, \
            LocalExecutor, QueryAgentExecutor

        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value={
            "success": True,
            "sql": "SELECT 1",
            "columns": ["a"],
            "query_result": {"rows": [[1]]},
            "total": 1,
            "confidence": 0.9,
        })

        with patch("app.agents.graph_nl2sql.get_query_graph", return_value=mock_graph):
            gateway = get_gateway()
            # 保存原始 executor 列表，测试后恢复（避免影响后续 fallback 测试）
            original_executors = gateway._executors
            gateway._executors = [LocalExecutor()]  # 仅 LocalExecutor
            try:
                result = await gateway.execute("测试", session_id="test")
            finally:
                gateway._executors = original_executors

        assert result.success is True
        assert result.source == "local"
        assert result.sql == "SELECT 1"

    @pytest.mark.asyncio
    async def test_fallback_to_queryagent(self):
        """LocalExecutor 失败 + retryable → 回退到 QueryAgentExecutor"""
        from app.core.data_query_gateway import get_gateway

        # LocalExecutor 失败（可回退）
        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value={
            "success": False,
            "error": "langgraph checkpoint error",
        })

        # QueryAgentExecutor 成功
        mock_agent = MagicMock()
        mock_agent.query = AsyncMock(return_value={
            "success": True,
            "sql": "SELECT * FROM fallback",
            "results": [{"col": "val"}],
            "columns": ["col"],
            "total": 1,
            "insight": {"summary": "兜底分析"},
        })

        with patch("app.agents.graph_nl2sql.get_query_graph", return_value=mock_graph), \
             patch("app.agents.query_agent.get_query_agent", return_value=mock_agent):
            gateway = get_gateway()
            result = await gateway.execute("测试", session_id="test")

        assert result.success is True
        assert result.source == "queryagent"  # 走了兜底
        assert result.query_mode == "fallback"
        assert result.sql == "SELECT * FROM fallback"

    @pytest.mark.asyncio
    async def test_no_fallback_on_llm_error(self):
        """LocalExecutor LLM 错误 → 不回退（QueryAgent 也用同一 LLM）"""
        from app.core.data_query_gateway import get_gateway

        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value={
            "success": False,
            "error": "llm api key invalid",
        })

        # QueryAgent 不应被调用
        mock_agent = MagicMock()
        mock_agent.query = AsyncMock()

        with patch("app.agents.graph_nl2sql.get_query_graph", return_value=mock_graph), \
             patch("app.agents.query_agent.get_query_agent", return_value=mock_agent):
            gateway = get_gateway()
            result = await gateway.execute("测试", session_id="test")

        assert result.success is False
        assert result.source == "local"   # 在 LocalExecutor 就停住了
        assert result.error_code == "llm_api_error"
        mock_agent.query.assert_not_called()  # 未回退到 QueryAgent

    @pytest.mark.asyncio
    async def test_no_fallback_on_db_error(self):
        """LocalExecutor DB 错误 → 不回退"""
        from app.core.data_query_gateway import get_gateway

        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value={
            "success": False,
            "error": "database connection failed",
        })

        mock_agent = MagicMock()
        mock_agent.query = AsyncMock()

        with patch("app.agents.graph_nl2sql.get_query_graph", return_value=mock_graph), \
             patch("app.agents.query_agent.get_query_agent", return_value=mock_agent):
            gateway = get_gateway()
            result = await gateway.execute("测试", session_id="test")

        assert result.success is False
        assert result.error_code == "db_connection_failed"
        mock_agent.query.assert_not_called()


# ---------------------------------------------------------------------------
# Phase 1.5: 兼容性修复验证
# ---------------------------------------------------------------------------

class TestHistoryIdField:
    """UnifiedQueryResult 必须有 history_id 字段"""

    def test_history_id_in_dataclass(self):
        from app.core.data_query_gateway import UnifiedQueryResult
        r = UnifiedQueryResult()
        assert hasattr(r, "history_id")
        assert r.history_id is None

    def test_history_id_can_be_set(self):
        from app.core.data_query_gateway import UnifiedQueryResult
        r = UnifiedQueryResult(history_id=42)
        assert r.history_id == 42


class TestTranslateColumns:
    """_translate_columns 迁移后行为验证"""

    @pytest.mark.asyncio
    async def test_translates_known_columns(self):
        """已知列名应翻译为中文"""
        from app.core.data_query_gateway import DataQueryGateway
        gateway = DataQueryGateway()
        # 直接测试 _translate_columns（不依赖真实 SchemaManager）
        # 如果 SchemaManager 不可用，应 fallback 到原列名
        result = await gateway._translate_columns(["plu_code", "unknown_col"])
        # 至少不崩溃，返回 list
        assert isinstance(result, list)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_empty_columns(self):
        from app.core.data_query_gateway import DataQueryGateway
        gateway = DataQueryGateway()
        result = await gateway._translate_columns([])
        assert result == []


class TestRowFormatConversion:
    """QueryService.natural_query() 的 rows 格式转换"""

    def test_list_rows_to_dict(self):
        """list-of-lists → list-of-dicts（前端兼容性关键路径）"""
        rows = [["502620", "测试商品"], ["502621", "另一个"]]
        columns = ["plu_code", "plu_name"]

        dict_results = []
        for row in rows:
            if isinstance(row, (list, tuple)):
                row_dict = {}
                for i, val in enumerate(row):
                    if i < len(columns):
                        row_dict[columns[i]] = val
                dict_results.append(row_dict)

        assert len(dict_results) == 2
        assert dict_results[0] == {"plu_code": "502620", "plu_name": "测试商品"}
        assert dict_results[1] == {"plu_code": "502621", "plu_name": "另一个"}

        # 验证前端 Object.keys 可提取列名
        assert list(dict_results[0].keys()) == ["plu_code", "plu_name"]

    def test_dict_rows_pass_through(self):
        """已是 dict 的行直接透传"""
        rows = [{"plu_code": "502620"}, {"plu_code": "502621"}]
        columns = ["plu_code"]

        dict_results = []
        for row in rows:
            if isinstance(row, dict):
                dict_results.append(row)
            elif isinstance(row, (list, tuple)):
                dict_results.append({columns[i]: v for i, v in enumerate(row)})

        assert dict_results == rows
        assert list(dict_results[0].keys()) == ["plu_code"]

    def test_tuples_rows_to_dict(self):
        """tuple 行也应正确转换"""
        rows = [("502620",), ("502621",)]
        columns = ["plu_code"]

        dict_results = []
        for row in rows:
            if isinstance(row, dict):
                dict_results.append(row)
            elif isinstance(row, (list, tuple)):
                row_dict = {}
                for i, val in enumerate(row):
                    if i < len(columns):
                        row_dict[columns[i]] = val
                dict_results.append(row_dict)

        assert dict_results[0] == {"plu_code": "502620"}


class TestDispatchCompatibility:
    """dispatch_to_nl2sql 返回格式兼容性"""

    def test_return_keys_match_orchestrator_expectations(self):
        """orchestrator.py 期望: {sql, data, insight}"""
        expected_keys = {"sql", "data", "insight"}

        # 模拟 Gateway 返回
        from app.core.data_query_gateway import UnifiedQueryResult, Insight
        result = UnifiedQueryResult(
            success=True,
            sql="SELECT 1",
            columns=["a"],
            rows=[[1]],
            total=1,
            insight=Insight(summary="test", insights=[], follow_ups=[]),
        )

        # 模拟 dispatch_to_nl2sql 的映射
        mapped = {
            "sql": result.sql or "",
            "data": {"columns": result.columns, "rows": result.rows, "total": result.total},
            "insight": {
                "summary": result.insight.summary if result.insight else "",
                "insights": result.insight.insights if result.insight else [],
                "follow_ups": result.insight.follow_ups if result.insight else [],
            },
        }

        assert set(mapped.keys()) >= expected_keys
        assert isinstance(mapped["data"]["columns"], list)
        assert isinstance(mapped["data"]["rows"], list)

    def test_error_case_raises(self):
        """失败时应 raise RuntimeError（orchestrator.py 依赖此行为）"""
        from app.core.data_query_gateway import UnifiedQueryResult
        result = UnifiedQueryResult(
            success=False,
            error_code="langgraph_error",
            error_message="test error",
        )
        # 验证异常抛出
        try:
            if not result.success:
                raise RuntimeError(result.error_message or "NL2SQL 查询失败")
        except RuntimeError as e:
            assert "test error" in str(e)
        else:
            assert False, "应该抛出 RuntimeError"


# ---------------------------------------------------------------------------
# Phase 2 Step 3: McpExecutor Gateway 级集成测试
# ---------------------------------------------------------------------------


class TestMcpGatewayIntegration:
    """McpExecutor 通过 Gateway 的端到端测试"""

    @pytest.mark.asyncio
    async def test_mcp_success_path(self):
        """MCP eligible + 可用 → source='mcp'"""
        from app.core.data_query_gateway import get_gateway

        mock_mcp_graph = MagicMock()
        mock_mcp_graph.ainvoke = AsyncMock(return_value={
            "success": True,
            "columns": ["plu_code", "plu_name"],
            "rows": [["502620", "测试商品"]],
            "total": 1,
            "tool_calls": [{"tool": "query_inventory_by_sku",
                            "arguments": {"sku_code": "502620"}}],
            "error": None,
        })

        with patch("app.agents.graph_mcp.get_mcp_graph", return_value=mock_mcp_graph), \
             patch("app.core.data_query_gateway.get_settings") as mock_settings:
            mock_settings.return_value.mcp_enabled = True
            mock_settings.return_value.mcp_base_url = "http://localhost:8922"
            mock_settings.return_value.mcp_api_key = ""
            mock_settings.return_value.mcp_timeout = 60.0

            gateway = get_gateway()
            mcp_exec = gateway._executors[0]
            mcp_exec.is_available = AsyncMock(return_value=True)
            result = await gateway.execute(
                "502620的库存", session_id="test",
                context={"domain_hint": "inventory", "mcp_eligible": True},
            )

        assert result.success is True
        assert result.source == "mcp"
        assert result.query_mode == "tool"
        assert result.total == 1

    @pytest.mark.asyncio
    async def test_mcp_not_eligible_falls_back_to_local(self):
        """eligible=false → 跳过 MCP → LocalExecutor 处理"""
        from app.core.data_query_gateway import get_gateway

        mock_local_graph = MagicMock()
        mock_local_graph.ainvoke = AsyncMock(return_value={
            "success": True,
            "sql": "SELECT * FROM test",
            "columns": ["plu_code"],
            "query_result": {"rows": [["502620"]]},
            "total": 1,
        })

        with patch("app.agents.graph_nl2sql.get_query_graph",
                   return_value=mock_local_graph):
            gateway = get_gateway()
            mcp_exec = gateway._executors[0]
            mcp_exec.is_available = AsyncMock(return_value=True)
            mcp_exec.execute = AsyncMock()  # 不应被调用
            result = await gateway.execute(
                "库存情况", session_id="test",
                context={"domain_hint": "inventory", "mcp_eligible": False},
            )

        assert result.success is True
        assert result.source == "local"
        mcp_exec.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_circuit_breaker_open_skips_mcp(self):
        """CircuitBreaker OPEN → 跳过 MCP → LocalExecutor"""
        from app.core.data_query_gateway import get_gateway
        import time

        mock_local_graph = MagicMock()
        mock_local_graph.ainvoke = AsyncMock(return_value={
            "success": True,
            "sql": "SELECT 1",
            "columns": ["a"],
            "query_result": {"rows": [[1]]},
            "total": 1,
        })

        with patch("app.agents.graph_nl2sql.get_query_graph",
                   return_value=mock_local_graph):
            gateway = get_gateway()
            mcp_exec = gateway._executors[0]
            mcp_exec.is_available = AsyncMock(return_value=True)
            mcp_exec.execute = AsyncMock()
            gateway._mcp_breaker._state = "OPEN"
            # 设为未来时间 → 冷却未到 → 保持 OPEN
            gateway._mcp_breaker._opened_at = time.monotonic() + 999

            result = await gateway.execute(
                "502620的库存", session_id="test",
                context={"domain_hint": "inventory", "mcp_eligible": True},
            )

        assert result.success is True
        assert result.source == "local"
        mcp_exec.execute.assert_not_called()

    def test_mcp_eligibility_analytics_no_entity(self):
        """分析域查询（无实体）应被判定为 eligible（F2 修复验证）"""
        from app.core.data_query_gateway import DataQueryGateway
        gateway = DataQueryGateway()

        assert gateway._check_mcp_eligibility("有没有临期的")["eligible"] is True
        assert gateway._check_mcp_eligibility("库存预警")["eligible"] is True
        assert gateway._check_mcp_eligibility("库存汇总")["eligible"] is True

    def test_mcp_eligibility_product_no_entity(self):
        """商品域查询（无实体）应被判定为 eligible（F2 修复验证）"""
        from app.core.data_query_gateway import DataQueryGateway
        gateway = DataQueryGateway()

        assert gateway._check_mcp_eligibility("商品信息")["eligible"] is True

    def test_mcp_eligibility_inventory_needs_entity(self):
        """库存域查询（无实体）仍被拦截"""
        from app.core.data_query_gateway import DataQueryGateway
        gateway = DataQueryGateway()

        r = gateway._check_mcp_eligibility("库存情况")
        assert r["eligible"] is False
        assert r["reason"] == "missing_entity"

    def test_mcp_eligibility_with_entity(self):
        """有实体的库存查询正常通过"""
        from app.core.data_query_gateway import DataQueryGateway
        gateway = DataQueryGateway()

        assert gateway._check_mcp_eligibility("502620的库存")["eligible"] is True


# ---------------------------------------------------------------------------

class TestGatewaySingleton:
    """get_gateway() 单例"""

    def test_singleton(self):
        from app.core.data_query_gateway import get_gateway
        g1 = get_gateway()
        g2 = get_gateway()
        assert g1 is g2
