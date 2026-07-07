# MCP Client 架构规范

> 本文档描述 WMS RAG V2 中 MCP Python 客户端层的完整架构设计。
> 决策背景参见 [ADR-010: MCP Data Copilot 接入](../adr/adr-010-mcp-data-copilot-integration.md)。

---

## 1. 概述

`backend/app/core/mcp_client.py` 是 WMS MCP Data Copilot Server 的 Python 客户端封装层，提供：

- **MCP 2024-11-05 Streamable HTTP 协议**的完整客户端实现
- **Phase 2 统一错误码体系**，区分服务级故障、业务错误、安全违规
- **连接管理 + 健康检查 + Tool 缓存**的 `McpClientManager`
- **熔断器（CircuitBreaker）**，自动隔离故障 MCP Server

### 设计约束

| 约束 | 说明 |
|------|------|
| Patch A | 错误码预留 `missing_required_param` / `invalid_param_value` 分支（Phase 3 启用） |
| Patch B | 不假设"所有查询必须有实体"（商品域全可选参数） |
| Patch C | `execute_sql_readonly` 必须是显式方法，不自动作为兜底 |

---

## 2. 架构分层

```
┌──────────────────────────────────────────────────────┐
│  DataQueryGateway (data_query_gateway.py)             │
│  ├── McpExecutor — 调用 graph_mcp + McpClientManager │
│  └── CircuitBreaker — MCP 熔断                        │
├──────────────────────────────────────────────────────┤
│  graph_mcp.py — LangGraph 状态图                      │
│  ├── tool_filter_node (Layer B: 规则 domain→候选Tool) │
│  ├── tool_select_node (Layer C: LLM 选 Tool+参数)     │
│  ├── mcp_call_node → McpClientManager.call_tool()     │
│  └── result_format_node                               │
├──────────────────────────────────────────────────────┤
│  McpClientManager (mcp_client.py)                     │
│  ├── WmsMcpClient 单例持有                            │
│  ├── Tool 列表缓存 (5min TTL)                         │
│  ├── 健康检查缓存 (30s TTL)                           │
│  └── get_tool_descriptions() → LLM Tool 选择 prompt    │
├──────────────────────────────────────────────────────┤
│  WmsMcpClient (mcp_client.py)                         │
│  ├── MCP Session 生命周期 (initialize → session)      │
│  ├── JSON-RPC + SSE 响应解析                          │
│  ├── call_tool / list_tools / ping / health           │
│  └── 错误映射 (_map_rpc_error)                        │
├──────────────────────────────────────────────────────┤
│  MCP Data Copilot Server (:8922)                      │
│  └── 15 个预构建 WMS Tool (inventory/product/...)     │
└──────────────────────────────────────────────────────┘
```

---

## 3. 错误码体系（McpErrorCode）

### 3.1 错误分类

```
服务级故障（计入 CircuitBreaker）:
  ├── mcp_unavailable   — 连接失败 / HTTP 错误
  ├── mcp_auth_error    — 401/403 认证失败
  └── mcp_timeout       — 请求超时

业务级错误（不计入 CircuitBreaker）:
  ├── tool_selection_failed   — LLM 未能选出合适的 Tool
  ├── tool_validation_failed  — 参数校验失败（Phase 3 拆分为更细粒度）
  ├── mcp_tool_error          — Tool 执行时业务错误
  ├── unsupported_query       — 查询超出 MCP 能力范围
  └── no_data                 — 查询无结果（不是错误）

安全 / 边界:
  ├── sql_security_violation  — SQL 安全检查拒绝
  └── internal_error          — 未知内部错误
```

### 3.2 回退决策矩阵

```python
# 允许回退到下一级 Executor 的错误
_RETRYABLE_ERRORS = {
    mcp_unavailable, mcp_auth_error, mcp_timeout,
    tool_selection_failed, tool_validation_failed,
    mcp_tool_error, unsupported_query, internal_error,
}

# 明确不可回退的错误
_NON_RETRYABLE_ERRORS = {
    mcp_disabled,          # 主动关闭，不应触发回退
    sql_security_violation, # 安全不可绕过
    no_data,               # 不是错误，不应回退
}
```

**保守回退原则**: 未知错误默认允许回退（`is_retryable_mcp_error` 对未识别错误码返回 `True`），避免因错误分类遗漏导致查询完全失败。

---

## 4. WmsMcpClient — 协议客户端

### 4.1 Session 生命周期

```
WmsMcpClient().__aenter__()
  │
  ├── call_tool("query_inventory_by_sku", {...})
  │     │
  │     ├── _ensure_session()  [懒初始化]
  │     │   ├── POST /mcp → initialize (JSON-RPC)
  │     │   ├── 提取 Mcp-Session-Id 响应头
  │     │   └── POST /mcp → notifications/initialized
  │     │
  │     └── _post_rpc("tools/call", {name, arguments})
  │           ├── 请求头: Mcp-Session-Id
  │           ├── 解析 SSE (text/event-stream) 或 JSON 响应
  │           ├── 提取 structuredContent (MCP 2024-11-05 新格式)
  │           └── 检测 isError → 抛出 WmsMcpError
  │
  └── close() → httpx.AsyncClient.aclose()
```

### 4.2 SSE 响应解析

MCP Streamable HTTP 返回 `text/event-stream` 格式：

```
event: message
data: {"jsonrpc":"2.0","result":{...},"id":1}

```

解析策略（`_parse_sse_body`）：
1. 按行扫描，提取 `data:` 行中的 JSON
2. Fallback: 尝试将整个文本作为 JSON 解析
3. 解析失败 → `WmsMcpError(code=internal_error)`

### 4.3 JSON-RPC 错误映射

`_map_rpc_error(rpc_code, message, tool_name)` 将 MCP 服务端错误映射为 Phase 2 统一错误码：

| 条件 | 映射 |
|------|------|
| rpc_code ∈ {-32001, -32002} 或含 "auth" | `mcp_auth_error` |
| 含 "validation"/"invalid"/"parameter" | `tool_validation_failed` |
| 含 "sql" + "rejected"/"disallowed"/"禁止" | `sql_security_violation` |
| 含 "not found"/"unknown" | `unsupported_query` |
| 含 "timeout"/"超时" | `mcp_timeout` |
| 其他 | `mcp_tool_error` |

**Patch A 预留**: Phase 3 将 `tool_validation_failed` 拆分为 `missing_required_param` 和 `invalid_param_value`，当前通过消息关键词预判但暂不拆分。

---

## 5. McpClientManager — 连接管理

### 5.1 缓存策略

| 缓存 | TTL | 说明 |
|------|-----|------|
| Tool 列表 | 300s (5min) | `list_tools()` 结果，减少 MCP Server 调用 |
| 健康检查 | 30s | `ping()` 结果，避免频繁健康探测 |

### 5.2 Tool 领域推断

`_infer_domain(tool_name)` 根据 Tool 名称自动归类到业务领域：

```python
domain_map = [
    ("analytics", ["summary", "warning", "slow_moving", "stock_flow"]),
    ("product",   ["product", "plu"]),
    ("inbound",   ["inbound", "receiving", "accept"]),
    ("outbound",  ["outbound", "send", "out_ware"]),
    ("inventory", ["inventory", "stock", "batch"]),
]
# analytics 优先匹配 — "stock_warning" 不应被 inventory 的 "stock" 误匹配
```

### 5.3 LLM Tool 选择 prompt 生成

`get_tool_descriptions(tools)` 生成结构化文本供 LLM 选择 Tool：

```
• query_inventory_by_sku: 按SKU编码查询库存 [必填: sku_code]
  参数: sku_code: string *必填* — SKU编码
• query_product_list: 查询商品列表 [全部可选]
  参数: page: integer — 页码, page_size: integer — 每页数量
```

---

## 6. CircuitBreaker — 熔断器

### 6.1 状态机

```
        record_failure() × N (threshold=3)
CLOSED ─────────────────────────────────▶ OPEN
  ▲                                         │
  │            cooldown_seconds (60s)       │
  │         ┌───────────────────────────────┘
  │         ▼
  └─── HALF_OPEN
        │
        ├── record_success() → CLOSED
        └── record_failure() → OPEN (重新计时)
```

### 6.2 计入规则

**仅服务级故障计入断路器计数**：`mcp_unavailable`, `mcp_auth_error`, `mcp_timeout`。

业务错误（`tool_selection_failed`, `tool_validation_failed` 等）不计入——它们反映的是查询本身的问题，不是 MCP Server 健康状态。

### 6.3 与 Gateway 的集成

```python
# Gateway._execute_with_fallback()
for executor in self._executors:
    if executor.name == "mcp":
        if not self._mcp_breaker.allow_request():
            continue  # 断路器 OPEN，跳过 MCP，直接走 LocalExecutor
    result = await executor.execute(question, context)
    if executor.name == "mcp":
        if result.success:
            self._mcp_breaker.record_success()
        else:
            self._mcp_breaker.record_failure(result.error_code)
```

---

## 7. 配置

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `MCP_ENABLED` | `true` | 是否启用 MCP 主路径 |
| `MCP_BASE_URL` | `http://localhost:8922` | MCP Server 地址 |
| `MCP_API_KEY` | — | MCP Server API Key（`X-API-Key` 请求头） |
| `MCP_TIMEOUT` | `60.0` | 请求超时（秒） |

---

## 8. 依赖

- **httpx** — 异步 HTTP 客户端（`AsyncClient`）
- **MCP Data Copilot Server** — 独立部署在 `:8922`，提供 15 个预构建 WMS Tool

---

> **代码基准**: `backend/app/core/mcp_client.py`
> **关联文档**: [ADR-010](../adr/adr-010-mcp-data-copilot-integration.md), [Data Query Gateway](data-query-gateway.md)
> **最后更新**: 2026-07-07
