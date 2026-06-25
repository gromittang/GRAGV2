"""
WMS MCP Client — Data Copilot MCP Server 的 Python 客户端封装

Phase 2 Step 1: 独立于 Gateway 的 HTTP 客户端层。
为后续 Step 3 的 McpExecutor 提供稳定接口。

设计约束:
  - Patch A: 错误码预留 missing_required_param / invalid_param_value 分支（Phase 3 启用）
  - Patch B: 不假设"所有查询必须有实体"（商品域全可选参数）
  - Patch C: execute_sql_readonly 必须是显式方法，不自动作为兜底
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

import logging

_log = logging.getLogger("mcp_client")

# ---------------------------------------------------------------------------
# Phase 2 错误码常量
# ---------------------------------------------------------------------------


class McpErrorCode:
    """MCP 调用统一错误码

    Phase 2 激活的: 前 6 个 + internal_error
    Phase 3 激活的: missing_required_param, invalid_param_value
    """

    # 服务级故障（计入 CircuitBreaker）
    MCP_UNAVAILABLE = "mcp_unavailable"
    MCP_AUTH_ERROR = "mcp_auth_error"
    MCP_TIMEOUT = "mcp_timeout"

    # 业务级错误（不计入 CircuitBreaker）
    TOOL_SELECTION_FAILED = "tool_selection_failed"
    TOOL_VALIDATION_FAILED = "tool_validation_failed"
    TOOL_EXECUTION_ERROR = "mcp_tool_error"

    # 安全 / 边界
    SQL_SECURITY_VIOLATION = "sql_security_violation"
    UNSUPPORTED_QUERY = "unsupported_query"
    NO_DATA = "no_data"  # 不是错误

    # Patch A: Phase 3 拆分 tool_validation_failed
    MISSING_REQUIRED_PARAM = "missing_required_param"  # Phase 3
    INVALID_PARAM_VALUE = "invalid_param_value"  # Phase 3

    # 兜底
    INTERNAL_ERROR = "internal_error"


# 计入 CircuitBreaker 的错误码集合
_CIRCUIT_BREAKER_ERRORS = frozenset({
    McpErrorCode.MCP_UNAVAILABLE,
    McpErrorCode.MCP_AUTH_ERROR,
    McpErrorCode.MCP_TIMEOUT,
})

# 允许回退到下一级 Executor 的错误码
_RETRYABLE_ERRORS = frozenset({
    McpErrorCode.MCP_UNAVAILABLE,
    McpErrorCode.MCP_AUTH_ERROR,
    McpErrorCode.MCP_TIMEOUT,
    McpErrorCode.TOOL_SELECTION_FAILED,
    McpErrorCode.TOOL_VALIDATION_FAILED,
    McpErrorCode.TOOL_EXECUTION_ERROR,
    McpErrorCode.UNSUPPORTED_QUERY,
    McpErrorCode.INTERNAL_ERROR,
})

# 明确不可回退的错误码
_NON_RETRYABLE_ERRORS = frozenset({
    "mcp_disabled",
    McpErrorCode.SQL_SECURITY_VIOLATION,
    McpErrorCode.NO_DATA,  # 不是错误，不应触发回退
})


def is_circuit_breaker_error(code: str) -> bool:
    """是否计入 CircuitBreaker 计数"""
    return code in _CIRCUIT_BREAKER_ERRORS


def is_retryable_mcp_error(code: str) -> bool:
    """是否允许回退到下一级 Executor。

    排除: mcp_disabled(主动关闭), sql_security_violation(安全不可绕过)。
    未知错误: 保守回退(True)。
    """
    if code in _NON_RETRYABLE_ERRORS:
        return False
    if code in _RETRYABLE_ERRORS:
        return True
    return True  # 未知错误保守回退


# ---------------------------------------------------------------------------
# WmsMcpError
# ---------------------------------------------------------------------------


class WmsMcpError(Exception):
    """WMS MCP 调用错误

    携带 Phase 2 统一错误码，供 Gateway 做回退决策。
    """

    def __init__(
        self,
        code: str,
        message: str,
        detail: Optional[str] = None,
        http_status: Optional[int] = None,
    ):
        self.code = code
        self.message = message
        self.detail = detail
        self.http_status = http_status
        super().__init__(f"[{code}] {message}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_code": self.code,
            "error_message": self.message,
            "detail": self.detail,
            "http_status": self.http_status,
        }


# ---------------------------------------------------------------------------
# ToolDef — 类型化的 Tool 定义
# ---------------------------------------------------------------------------


@dataclass
class ToolDef:
    """MCP Tool 的客户端表示"""
    name: str
    description: str = ""
    input_schema: Dict[str, Any] = field(default_factory=dict)
    domain: str = ""  # inventory / product / inbound / outbound / analytics

    @property
    def required_params(self) -> List[str]:
        return self.input_schema.get("required", [])

    @property
    def all_params(self) -> Dict[str, Any]:
        return self.input_schema.get("properties", {})


# ---------------------------------------------------------------------------
# WmsMcpClient — 异步 HTTP 客户端
# ---------------------------------------------------------------------------


class WmsMcpClient:
    """WMS MCP Server 的异步 Python 客户端。

    基于 httpx.AsyncClient，MCP 2024-11-05 Streamable HTTP 协议。
    管理 session 生命周期: initialize → session → call_tool → close。

    Usage:
        async with WmsMcpClient("http://localhost:8922", api_key="xxx") as client:
            result = await client.call_tool("query_inventory_by_sku",
                                             {"sku_code": "502620"})
    """

    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        timeout: float = 60.0,
    ):
        self._url = base_url.rstrip("/") + "/mcp"
        self._api_key = api_key
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._request_id = 0
        self._session_id: Optional[str] = None
        self._session_initialized: bool = False

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            }
            if self._api_key:
                headers["X-API-Key"] = self._api_key
            self._client = httpx.AsyncClient(
                headers=headers,
                timeout=httpx.Timeout(self._timeout),
            )
        return self._client

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    # -- MCP Session 生命周期 (Step 5.1) --

    async def _ensure_session(self):
        """确保 MCP session 已初始化。"""
        if self._session_initialized:
            return
        client = await self._ensure_client()

        # Step 1: initialize
        try:
            response = await client.post(self._url, json={
                "jsonrpc": "2.0",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "wmsrag-client", "version": "1.0"},
                },
                "id": self._next_id(),
            })
        except httpx.HTTPError as e:
            _log.warning("MCP initialize 失败: %s", e)
            return  # 后续调用会因缺 session 而失败

        # 提取 session ID
        self._session_id = response.headers.get("Mcp-Session-Id")
        if not self._session_id:
            _log.warning("MCP initialize 未返回 session ID")
            return

        # Step 2: send initialized notification
        try:
            await client.post(self._url, json={
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            }, headers={"Mcp-Session-Id": self._session_id})
        except httpx.HTTPError:
            _log.warning("MCP initialized notification 发送失败")

        self._session_initialized = True
        _log.info("MCP session 已建立: %s", self._session_id[:16])

    @staticmethod
    def _parse_sse_body(text: str) -> Dict[str, Any]:
        """解析 SSE (Server-Sent Events) 格式的响应体。

        MCP Streamable HTTP 返回: event: message\\ndata: {json}\\n\\n
        """
        import json as _json
        # 提取 data: 行中的 JSON
        for line in text.strip().split("\n"):
            line = line.strip()
            if line.startswith("data:"):
                data_str = line[5:].strip()
                try:
                    return _json.loads(data_str)
                except _json.JSONDecodeError:
                    pass
        # fallback: 尝试直接解析整个文本为 JSON
        try:
            return _json.loads(text)
        except _json.JSONDecodeError:
            raise WmsMcpError(
                code=McpErrorCode.INTERNAL_ERROR,
                message=f"无法解析 MCP 响应: {text[:200]}",
            )

    @staticmethod
    def _serialize_sse(payload: Dict[str, Any]) -> str:
        """将 JSON-RPC payload 序列化为 SSE 格式（如需要）。"""
        import json as _json
        body = _json.dumps(payload, ensure_ascii=False)
        return f"data: {body}\n\n"

    async def _post_rpc(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """发送 JSON-RPC 请求，处理 SSE 响应和 session 管理。"""
        import json as _json

        await self._ensure_session()
        client = await self._ensure_client()
        headers: Dict[str, str] = {}
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id

        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": self._next_id(),
        }

        try:
            response = await client.post(self._url, json=payload, headers=headers)
        except httpx.TimeoutException:
            raise WmsMcpError(
                code=McpErrorCode.MCP_TIMEOUT,
                message=f"MCP 调用超时 ({self._timeout}s): {method}",
            )
        except httpx.ConnectError as e:
            raise WmsMcpError(
                code=McpErrorCode.MCP_UNAVAILABLE,
                message=f"无法连接 MCP Server: {self._url}",
                detail=str(e),
            )
        except httpx.HTTPError as e:
            raise WmsMcpError(
                code=McpErrorCode.MCP_UNAVAILABLE,
                message=f"MCP HTTP 错误: {e}",
                detail=str(e),
            )

        # HTTP 层认证错误
        if response.status_code in (401, 403):
            try:
                error_body = response.json()
            except Exception:
                error_body = {}
            raise WmsMcpError(
                code=McpErrorCode.MCP_AUTH_ERROR,
                message=error_body.get("message", f"HTTP {response.status_code}"),
                detail=error_body.get("detail"),
                http_status=response.status_code,
            )

        if response.status_code >= 400:
            raise WmsMcpError(
                code=McpErrorCode.INTERNAL_ERROR,
                message=f"MCP Server 返回 HTTP {response.status_code}",
                http_status=response.status_code,
            )

        # 解析 SSE 或 JSON 响应
        content_type = response.headers.get("content-type", "")
        text = response.text

        if "text/event-stream" in content_type or text.startswith("event:"):
            body = self._parse_sse_body(text)
        else:
            try:
                body = _json.loads(text)
            except _json.JSONDecodeError:
                raise WmsMcpError(
                    code=McpErrorCode.INTERNAL_ERROR,
                    message=f"MCP 返回非 JSON/SSE 响应: {text[:200]}",
                )

        # JSON-RPC 层错误
        if "error" in body:
            err = body["error"]
            rpc_message = err.get("message", "")
            mapped = _map_rpc_error(err.get("code", -1), rpc_message, method)
            raise WmsMcpError(
                code=mapped,
                message=rpc_message,
                detail=str(err.get("data", "")),
            )

        result = body.get("result", body)
        # MCP 2024-11-05 新格式: 如果 result 含 structuredContent，提取之
        if isinstance(result, dict) and "structuredContent" in result:
            return result["structuredContent"]
        # Tool 级别错误: {"content": [...], "isError": true}
        if isinstance(result, dict) and result.get("isError"):
            error_text = ""
            if result.get("content"):
                for item in result["content"]:
                    if isinstance(item, dict) and item.get("type") == "text":
                        error_text += item.get("text", "")
            raise WmsMcpError(
                code=McpErrorCode.TOOL_EXECUTION_ERROR,
                message=error_text or "MCP Tool 执行失败",
            )
        return result

    # -- 核心方法 --

    async def call_tool(
        self, name: str, arguments: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """调用一个 MCP Tool。"""
        return await self._post_rpc("tools/call", {
            "name": name,
            "arguments": arguments or {},
        })

    async def list_tools(self) -> List[Dict[str, Any]]:
        """列出所有可用的 MCP Tool。"""
        try:
            result = await self._post_rpc("tools/list", {})
            return result.get("tools", [])
        except Exception as e:
            _log.warning("list_tools 失败: %s", e)
            return []

    async def ping(self) -> bool:
        """快速健康检查。"""
        try:
            result = await self._post_rpc("tools/call", {
                "name": "ping", "arguments": {},
            })
            return result.get("status") == "ok"
        except Exception:
            return False

    async def health(self) -> Dict[str, Any]:
        """深度健康检查（验证数据库连通性）。"""
        try:
            return await self._post_rpc("tools/call", {
                "name": "health", "arguments": {},
            })
        except WmsMcpError as e:
            return {"status": "unhealthy", "error": e.message}

    # -- Patch C: execute_sql_readonly 显式方法 --

    async def execute_sql_readonly(
        self, sql: str, params: Optional[Dict[str, Any]] = None,
        limit: int = 1000,
    ) -> Dict[str, Any]:
        """受控只读 SQL 执行。Phase 2 不自动使用。"""
        args: Dict[str, Any] = {"sql": sql, "limit": limit}
        if params:
            args["params"] = params
        return await self.call_tool("execute_sql_readonly", args)

    # -- 生命周期 --

    async def close(self):
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self._session_initialized = False
        self._session_id = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()


# ---------------------------------------------------------------------------
# JSON-RPC 错误 → Phase 2 错误码映射
# ---------------------------------------------------------------------------


def _map_rpc_error(rpc_code: int, message: str, tool_name: str) -> str:
    """将 MCP JSON-RPC 错误码映射为 Phase 2 统一错误码"""
    msg_lower = message.lower()

    # 认证/授权
    if rpc_code in (-32001, -32002) or "auth" in msg_lower or "unauthorized" in msg_lower:
        return McpErrorCode.MCP_AUTH_ERROR

    # 参数校验
    if "validation" in msg_lower or "invalid" in msg_lower or "parameter" in msg_lower:
        # Patch A: 目前统一为 TOOL_VALIDATION_FAILED
        # Phase 3 拆分为 MISSING_REQUIRED_PARAM / INVALID_PARAM_VALUE
        if "required" in msg_lower or "missing" in msg_lower or "缺少" in message:
            return McpErrorCode.TOOL_VALIDATION_FAILED  # Phase 3 → MISSING_REQUIRED_PARAM
        return McpErrorCode.TOOL_VALIDATION_FAILED  # Phase 3 → INVALID_PARAM_VALUE

    # SQL 安全
    if "sql" in msg_lower and ("rejected" in msg_lower or "disallowed" in msg_lower
                                or "not allowed" in msg_lower or "禁止" in message):
        return McpErrorCode.SQL_SECURITY_VIOLATION

    # Tool 不存在
    if "not found" in msg_lower or "unknown" in msg_lower:
        return McpErrorCode.UNSUPPORTED_QUERY

    # 超时（服务端超时）
    if "timeout" in msg_lower or "超时" in message:
        return McpErrorCode.MCP_TIMEOUT

    return McpErrorCode.TOOL_EXECUTION_ERROR


# ---------------------------------------------------------------------------
# McpClientManager — 连接管理 + 健康检查 + Tool 缓存
# ---------------------------------------------------------------------------


@dataclass
class _ToolCache:
    """Tool 列表缓存"""
    tools: List[ToolDef] = field(default_factory=list)
    fetched_at: float = 0.0
    ttl_seconds: float = 300.0  # 5 分钟

    @property
    def is_valid(self) -> bool:
        return bool(self.tools) and (time.monotonic() - self.fetched_at) < self.ttl_seconds


class McpClientManager:
    """MCP 客户端管理器

    职责:
      - 持有 WmsMcpClient 单例
      - 缓存 Tool 列表（5 分钟 TTL）
      - 缓存健康检查结果（30 秒 TTL）
      - 提供 get_tool_descriptions() 供 LLM Tool 选择

    Usage:
        mgr = McpClientManager("http://localhost:8922", api_key="xxx")
        if await mgr.is_available():
            tools_text = mgr.get_tool_descriptions()
            # 传给 LLM 选择 Tool
    """

    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        timeout: float = 60.0,
    ):
        self._base_url = base_url
        self._api_key = api_key
        self._timeout = timeout
        self._client: Optional[WmsMcpClient] = None
        self._tool_cache = _ToolCache()
        self._health_cache: Optional[bool] = None
        self._health_cache_time: float = 0.0
        self._health_ttl: float = 30.0

    async def _get_client(self) -> WmsMcpClient:
        if self._client is None:
            self._client = WmsMcpClient(
                base_url=self._base_url,
                api_key=self._api_key,
                timeout=self._timeout,
            )
        return self._client

    async def call_tool(self, name: str, arguments: Dict[str, Any] = None) -> Dict[str, Any]:
        """调用 MCP Tool（公共接口，供 graph_mcp 使用）"""
        client = await self._get_client()
        return await client.call_tool(name, arguments)

    async def is_available(self) -> bool:
        """MCP Server 是否可用（缓存 30 秒）"""
        now = time.monotonic()
        if self._health_cache is not None and (now - self._health_cache_time) < self._health_ttl:
            return self._health_cache

        client = await self._get_client()
        self._health_cache = await client.ping()
        self._health_cache_time = now
        if not self._health_cache:
            _log.warning("MCP Server 不可用: %s", self._base_url)
        return self._health_cache

    async def refresh_tools_cache(self) -> List[ToolDef]:
        """强制刷新 Tool 列表缓存"""
        client = await self._get_client()
        try:
            raw_tools = await client.list_tools()
        except Exception:
            _log.exception("刷新 Tool 列表失败")
            raw_tools = []

        tools = [_raw_to_tool_def(t) for t in raw_tools]
        self._tool_cache = _ToolCache(
            tools=tools,
            fetched_at=time.monotonic(),
        )
        _log.info("Tool 缓存已刷新: %d 个 Tool", len(tools))
        return tools

    async def _ensure_tool_cache(self) -> List[ToolDef]:
        """确保 Tool 缓存有效"""
        if not self._tool_cache.is_valid:
            await self.refresh_tools_cache()
        return self._tool_cache.tools

    async def get_tools(self) -> List[ToolDef]:
        """获取当前 Tool 列表（带缓存）"""
        return await self._ensure_tool_cache()

    async def get_tools_by_domain(self, domain: str) -> List[ToolDef]:
        """按领域获取 Tool 列表"""
        tools = await self._ensure_tool_cache()
        if not domain:
            return tools
        return [t for t in tools if t.domain == domain]

    def get_tool_descriptions(self, tools: Optional[List[ToolDef]] = None) -> str:
        """生成 LLM Tool 选择用的描述文本

        Args:
            tools: 候选 Tool 列表。如果为 None，使用缓存的全部 Tool。

        Returns:
            格式化文本，每行一个 Tool 的 name + description + 参数信息
        """
        tool_list = tools if tools is not None else self._tool_cache.tools
        if not tool_list:
            return "(无可用 Tool)"

        lines = []
        for t in tool_list:
            params_desc = _format_params(t.input_schema)
            required = t.required_params
            req_str = f" [必填: {', '.join(required)}]" if required else " [全部可选]"
            lines.append(
                f"• **{t.name}**: {t.description}{req_str}\n"
                f"  参数: {params_desc}"
            )
        return "\n".join(lines)

    async def close(self):
        if self._client is not None:
            await self._client.close()
            self._client = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _raw_to_tool_def(raw: Dict[str, Any]) -> ToolDef:
    """将 MCP tools/list 返回的原始 dict 转为 ToolDef"""
    name = raw.get("name", "")
    return ToolDef(
        name=name,
        description=raw.get("description", ""),
        input_schema=raw.get("inputSchema", {}),
        domain=_infer_domain(name),
    )


def _infer_domain(tool_name: str) -> str:
    """根据 Tool 名称推断领域

    优先级: analytics > product > inbound > outbound > inventory
    （analytics 优先避免 "stock_warning" 被 inventory 的 "stock" 误匹配）
    """
    domain_map = [
        ("analytics", ["summary", "warning", "slow_moving", "stock_flow"]),
        ("product", ["product", "plu"]),
        ("inbound", ["inbound", "receiving", "accept"]),
        ("outbound", ["outbound", "send", "out_ware"]),
        ("inventory", ["inventory", "stock", "batch"]),
    ]
    name_lower = tool_name.lower()
    for domain, keywords in domain_map:
        if any(kw in name_lower for kw in keywords):
            return domain
    return ""


def _format_params(schema: Dict[str, Any]) -> str:
    """格式化 Tool 参数信息为简洁文本"""
    props = schema.get("properties", {})
    required = schema.get("required", [])
    if not props:
        return "(无参数)"

    parts = []
    for name, info in props.items():
        ptype = info.get("type", "any")
        desc = info.get("description", "")
        marker = " *必填*" if name in required else ""
        parts.append(f"{name}: {ptype}{marker}" + (f" — {desc}" if desc else ""))
    return ", ".join(parts)
