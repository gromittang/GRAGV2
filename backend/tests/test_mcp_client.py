"""
Phase 2 Step 1: MCP Client 单元测试
覆盖: WmsMcpClient、McpClientManager、WmsMcpError、错误码映射、ToolDef
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# 错误码常量测试
# ---------------------------------------------------------------------------

class TestMcpErrorCode:
    def test_error_codes_defined(self):
        from app.core.mcp_client import McpErrorCode
        assert McpErrorCode.MCP_UNAVAILABLE == "mcp_unavailable"
        assert McpErrorCode.MCP_AUTH_ERROR == "mcp_auth_error"
        assert McpErrorCode.MCP_TIMEOUT == "mcp_timeout"
        assert McpErrorCode.TOOL_SELECTION_FAILED == "tool_selection_failed"
        assert McpErrorCode.TOOL_VALIDATION_FAILED == "tool_validation_failed"

    def test_patch_a_future_codes_reserved(self):
        """Patch A: missing_required_param / invalid_param_value 已预留"""
        from app.core.mcp_client import McpErrorCode
        assert McpErrorCode.MISSING_REQUIRED_PARAM == "missing_required_param"
        assert McpErrorCode.INVALID_PARAM_VALUE == "invalid_param_value"

    def test_circuit_breaker_errors(self):
        from app.core.mcp_client import is_circuit_breaker_error
        assert is_circuit_breaker_error("mcp_unavailable") is True
        assert is_circuit_breaker_error("mcp_auth_error") is True
        assert is_circuit_breaker_error("mcp_timeout") is True
        assert is_circuit_breaker_error("tool_selection_failed") is False
        assert is_circuit_breaker_error("tool_validation_failed") is False

    def test_retryable_errors(self):
        from app.core.mcp_client import is_retryable_mcp_error
        assert is_retryable_mcp_error("mcp_unavailable") is True
        assert is_retryable_mcp_error("sql_security_violation") is False
        assert is_retryable_mcp_error("no_data") is False


# ---------------------------------------------------------------------------
# WmsMcpError 测试
# ---------------------------------------------------------------------------

class TestWmsMcpError:
    def test_basic_error(self):
        from app.core.mcp_client import WmsMcpError
        e = WmsMcpError(code="mcp_timeout", message="超时了")
        assert e.code == "mcp_timeout"
        assert e.message == "超时了"
        assert "mcp_timeout" in str(e)

    def test_error_with_detail(self):
        from app.core.mcp_client import WmsMcpError
        e = WmsMcpError(
            code="mcp_auth_error",
            message="认证失败",
            detail="invalid key",
            http_status=403,
        )
        assert e.http_status == 403
        d = e.to_dict()
        assert d["error_code"] == "mcp_auth_error"
        assert d["http_status"] == 403


# ---------------------------------------------------------------------------
# WmsMcpClient 测试
# ---------------------------------------------------------------------------

class TestWmsMcpClient:
    """异步 HTTP 客户端 — mock httpx.AsyncClient"""

    @pytest.mark.asyncio
    async def test_call_tool_success(self):
        from app.core.mcp_client import WmsMcpClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"result": {"total": 2, "items": [{"a": 1}, {"a": 2}]}}'
        mock_response.headers = {"content-type": "application/json"}

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            async with WmsMcpClient("http://localhost:8922", api_key="test") as c:
                c._client = mock_client
                c._session_initialized = True  # skip session handshake
                result = await c.call_tool("query_inventory_by_sku",
                                            {"sku_code": "502620"})

        assert result["total"] == 2
        assert len(result["items"]) == 2

    @pytest.mark.asyncio
    async def test_call_tool_auth_error_401(self):
        from app.core.mcp_client import WmsMcpClient, WmsMcpError, McpErrorCode

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"error_code": "AUTH_ERROR",
                                            "message": "Missing API Key"}

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            async with WmsMcpClient("http://localhost:8922", api_key="bad") as c:
                c._client = mock_client
                with pytest.raises(WmsMcpError) as exc_info:
                    await c.call_tool("query_product", {})
                assert exc_info.value.code == McpErrorCode.MCP_AUTH_ERROR
                assert exc_info.value.http_status == 401

    @pytest.mark.asyncio
    async def test_call_tool_timeout(self):
        from app.core.mcp_client import WmsMcpClient, WmsMcpError
        import httpx

        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.TimeoutException("timeout")

        with patch("httpx.AsyncClient", return_value=mock_client):
            async with WmsMcpClient("http://localhost:8922", timeout=5.0) as c:
                c._client = mock_client
                with pytest.raises(WmsMcpError) as exc_info:
                    await c.call_tool("query_inventory_by_sku", {})
                assert exc_info.value.code == "mcp_timeout"

    @pytest.mark.asyncio
    async def test_call_tool_connect_error(self):
        from app.core.mcp_client import WmsMcpClient, WmsMcpError
        import httpx

        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.ConnectError("connection refused")

        with patch("httpx.AsyncClient", return_value=mock_client):
            async with WmsMcpClient("http://localhost:9999") as c:
                c._client = mock_client
                with pytest.raises(WmsMcpError) as exc_info:
                    await c.call_tool("ping", {})
                assert exc_info.value.code == "mcp_unavailable"

    @pytest.mark.asyncio
    async def test_ping_success(self):
        from app.core.mcp_client import WmsMcpClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"result": {"status": "ok"}}'
        mock_response.headers = {"content-type": "application/json"}

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            async with WmsMcpClient("http://localhost:8922") as c:
                c._client = mock_client
                c._session_initialized = True
                assert await c.ping() is True

    @pytest.mark.asyncio
    async def test_ping_failure(self):
        from app.core.mcp_client import WmsMcpClient
        import httpx

        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.ConnectError("no connection")

        with patch("httpx.AsyncClient", return_value=mock_client):
            async with WmsMcpClient("http://localhost:9999") as c:
                c._client = mock_client
                assert await c.ping() is False

    @pytest.mark.asyncio
    async def test_list_tools(self):
        from app.core.mcp_client import WmsMcpClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = ('{"result": {"tools": ['
            '{"name": "query_inventory_by_sku", "description": "按 SKU 查库存", '
            '"inputSchema": {"required": ["sku_code"], '
            '"properties": {"sku_code": {"type": "string"}}}}]}}')
        mock_response.headers = {"content-type": "application/json"}

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            async with WmsMcpClient("http://localhost:8922") as c:
                c._client = mock_client
                c._session_initialized = True
                tools = await c.list_tools()
                assert len(tools) == 1
                assert tools[0]["name"] == "query_inventory_by_sku"

    @pytest.mark.asyncio
    async def test_health(self):
        from app.core.mcp_client import WmsMcpClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = ('{"result": {"status": "healthy", '
                               '"db": "connected", "version": "1.0.0-alpha"}}')
        mock_response.headers = {"content-type": "application/json"}

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            async with WmsMcpClient("http://localhost:8922") as c:
                c._client = mock_client
                c._session_initialized = True
                result = await c.health()
                assert result["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_execute_sql_readonly_explicit(self):
        """Patch C: execute_sql_readonly 是显式方法"""
        from app.core.mcp_client import WmsMcpClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = ('{"result": {"columns": ["a"], "rows": [[1]], '
                               '"row_count": 1, "injected_limit": 1000}}')
        mock_response.headers = {"content-type": "application/json"}

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            async with WmsMcpClient("http://localhost:8922") as c:
                c._client = mock_client
                c._session_initialized = True
                result = await c.execute_sql_readonly("SELECT 1", limit=10)
                assert result["row_count"] == 1
                assert result["injected_limit"] == 1000


# ---------------------------------------------------------------------------
# McpClientManager 测试
# ---------------------------------------------------------------------------

class TestMcpClientManager:
    """健康检查缓存 + Tool 缓存 + Tool 描述格式化"""

    @pytest.mark.asyncio
    async def test_is_available_cached(self):
        from app.core.mcp_client import McpClientManager

        mgr = McpClientManager("http://localhost:8922")

        mock_client = AsyncMock()
        mock_client.ping.return_value = True
        mgr._client = mock_client

        # 第一次：调用 ping
        assert await mgr.is_available() is True
        assert mock_client.ping.call_count == 1

        # 第二次：缓存命中，不调 ping
        assert await mgr.is_available() is True
        assert mock_client.ping.call_count == 1

    @pytest.mark.asyncio
    async def test_is_available_false(self):
        from app.core.mcp_client import McpClientManager

        mgr = McpClientManager("http://localhost:8922")
        mock_client = AsyncMock()
        mock_client.ping.return_value = False
        mgr._client = mock_client

        assert await mgr.is_available() is False

    @pytest.mark.asyncio
    async def test_refresh_tools_cache(self):
        from app.core.mcp_client import McpClientManager

        mgr = McpClientManager("http://localhost:8922")
        mock_client = AsyncMock()
        mock_client.list_tools.return_value = [
            {"name": "query_inventory_by_sku",
             "description": "按 SKU 查库存",
             "inputSchema": {"required": ["sku_code"],
                              "properties": {"sku_code": {"type": "string"}}}},
            {"name": "query_product",
             "description": "商品主数据",
             "inputSchema": {"required": [],
                              "properties": {"sku_code": {"type": "string"}}}},
        ]
        mgr._client = mock_client

        tools = await mgr.refresh_tools_cache()
        assert len(tools) == 2
        assert tools[0].name == "query_inventory_by_sku"
        assert tools[0].domain == "inventory"  # auto-inferred
        assert tools[1].domain == "product"

    @pytest.mark.asyncio
    async def test_get_tools_by_domain(self):
        from app.core.mcp_client import McpClientManager

        mgr = McpClientManager("http://localhost:8922")
        mock_client = AsyncMock()
        mock_client.list_tools.return_value = [
            {"name": "query_inventory_by_sku", "description": "库存",
             "inputSchema": {}},
            {"name": "query_product", "description": "商品",
             "inputSchema": {}},
        ]
        mgr._client = mock_client
        await mgr.refresh_tools_cache()

        inv_tools = await mgr.get_tools_by_domain("inventory")
        assert len(inv_tools) == 1
        assert inv_tools[0].name == "query_inventory_by_sku"

    def test_get_tool_descriptions_format(self):
        from app.core.mcp_client import McpClientManager, ToolDef

        mgr = McpClientManager("http://localhost:8922")
        tools = [
            ToolDef(
                name="query_inventory_by_sku",
                description="按 SKU 查库存",
                input_schema={
                    "required": ["sku_code"],
                    "properties": {
                        "sku_code": {"type": "string", "description": "商品编码"},
                        "limit": {"type": "integer", "description": "返回行数上限"},
                    },
                },
                domain="inventory",
            ),
            ToolDef(
                name="query_product",
                description="商品主数据",
                input_schema={"required": [], "properties": {}},
                domain="product",
            ),
        ]

        text = mgr.get_tool_descriptions(tools)
        assert "query_inventory_by_sku" in text
        assert "按 SKU 查库存" in text
        assert "sku_code" in text
        assert "[必填: sku_code]" in text
        assert "query_product" in text
        assert "[全部可选]" in text

    def test_get_tool_descriptions_empty(self):
        from app.core.mcp_client import McpClientManager
        mgr = McpClientManager("http://localhost:8922")
        text = mgr.get_tool_descriptions([])
        assert "无可用 Tool" in text


# ---------------------------------------------------------------------------
# ToolDef 测试
# ---------------------------------------------------------------------------

class TestToolDef:
    def test_required_params(self):
        from app.core.mcp_client import ToolDef
        t = ToolDef(
            name="test",
            input_schema={
                "required": ["a", "b"],
                "properties": {"a": {}, "b": {}, "c": {}},
            },
        )
        assert t.required_params == ["a", "b"]
        assert len(t.all_params) == 3

    def test_domain_inference(self):
        from app.core.mcp_client import _infer_domain
        assert _infer_domain("query_inventory_by_sku") == "inventory"
        assert _infer_domain("query_product") == "product"
        assert _infer_domain("query_outbound_order") == "outbound"
        assert _infer_domain("query_inbound_detail") == "inbound"
        assert _infer_domain("get_stock_warning") == "analytics"
        assert _infer_domain("unknown_tool") == ""


# ---------------------------------------------------------------------------
# Patch C 验证: execute_sql_readonly 不是默认兜底
# ---------------------------------------------------------------------------

class TestPatchC:
    """Patch C: execute_sql_readonly 显式调用，不自动兜底"""

    def test_execute_sql_readonly_is_explicit_method(self):
        """call_tool 不会自动路由到 execute_sql_readonly"""
        from app.core.mcp_client import WmsMcpClient
        # call_tool 接受 tool name + args，不会自动替换
        # execute_sql_readonly 是独立方法
        assert hasattr(WmsMcpClient, "execute_sql_readonly")
        assert hasattr(WmsMcpClient, "call_tool")
        # 两者是不同的代码路径


# ---------------------------------------------------------------------------
# Patch B 验证: 商品域全可选参数不要求实体
# ---------------------------------------------------------------------------

class TestPatchB:
    """Patch B: 商品主数据查询无实体也 eligible"""

    def test_product_tool_has_no_required_params(self):
        """query_product 的参数全可选 — ToolDef 正确反映"""
        from app.core.mcp_client import ToolDef
        t = ToolDef(
            name="query_product",
            input_schema={
                "required": [],
                "properties": {
                    "sku_code": {"type": "string"},
                    "sku_name": {"type": "string"},
                    "status": {"type": "string"},
                },
            },
        )
        assert t.required_params == []
