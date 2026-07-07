# Data Query Gateway 架构规范

> 本文档描述数据查询网关（DataQueryGateway）的完整架构——统一的查询入口、三级 Executor 回退链、后处理管线。

---

## 1. 概述

`backend/app/core/data_query_gateway.py` 是所有数据查询的**唯一入口**。它实现了一条三级 Executor 链：

```
用户问题
  │
  ▼
DataQueryGateway.execute()
  │
  ├── Layer A: _check_mcp_eligibility() — 规则判断 MCP 是否适用
  │
  ├── Layer B: _execute_with_fallback() — 三级 Executor 链
  │   ├── McpExecutor (priority=0) — MCP Data Copilot 预构建 Tool
  │   ├── LocalExecutor (priority=1) — LangGraph NL2SQL
  │   └── QueryAgentExecutor (priority=2) — 旧版兜底 (@deprecated)
  │
  └── _post_process() — 字段翻译 + 洞察补全 + 历史记录
      ▼
  UnifiedQueryResult
```

---

## 2. 统一结果模型

### 2.1 UnifiedQueryResult（对外）

所有查询路径返回统一结构，前端无需感知底层 Executor：

| 字段 | 类型 | 说明 |
|------|------|------|
| `success` | bool | 查询是否成功 |
| `source` | str | 实际执行的 Executor: `"mcp"` / `"local"` / `"queryagent"` |
| `query_mode` | str | 查询模式: `"tool"` / `"sql"` / `"fallback"` |
| `question` | str | 原始用户问题 |
| `sql` | str? | 生成的 SQL（MCP 模式下为 null） |
| `tool_calls` | list? | MCP Tool 调用记录 |
| `columns` | list | 翻译后的中文列名 |
| `rows` | list | 查询结果行 |
| `total` | int | 结果总数 |
| `insight` | Insight? | AI 洞察（summary + insights + follow_ups） |
| `confidence` | float? | 置信度 |
| `error_code` | str? | 错误码 |
| `error_message` | str? | 错误描述 |
| `trace_id` | str | 请求追踪 ID |
| `latency_ms` | float | 总耗时（毫秒） |
| `history_id` | int? | 查询历史记录 ID |

### 2.2 RawQueryResult（内部）

Executor 返回给 Gateway 的内部结果，包含回退决策所需字段：

额外字段: `is_retryable: bool` — Gateway 据此判断是否继续尝试下一级 Executor。

---

## 3. 执行器链

### 3.1 McpExecutor（priority=0）— MCP 预构建查询

**准入条件**:
1. `mcp_enabled=True`（配置项）
2. `_check_mcp_eligibility()` 返回 `eligible=true`
3. `CircuitBreaker.allow_request() == True`（熔断器未 OPEN）

**执行流程**:
```
McpExecutor.execute(question, context)
  ├── 获取 graph_mcp (LangGraph 状态图)
  ├── 注入 tool_registry_raw (Tool 列表)
  ├── 注入 mcp_manager (McpClientManager 单例)
  └── graph.ainvoke({
        question, domain_hint, session_id,
        tool_registry_raw, mcp_manager
      })
```

**失败处理**: 返回 `is_retryable` 由 `is_retryable_mcp_error(error_code)` 决定。

### 3.2 LocalExecutor（priority=1）— LangGraph NL2SQL

适配 `graph_nl2sql`，包裹现有 `ainvoke()` 调用：

```python
graph = get_query_graph()
raw = await graph.ainvoke({
    "question": question,
    "user_context": context.get("user_context", {}),
})
# 从 graph state 提取 columns, rows, sql, insight, confidence
```

**错误分类**（`_classify_error`）:
- `langgraph_error` — Graph 执行异常
- `llm_api_error` — LLM 不可用
- `db_connection_failed` — MySQL 不可用
- `sql_security_violation` — SQL 安全违规
- `schema_not_found` — 找不到匹配的表
- `sql_execution_error` — SQL 执行错误

### 3.3 QueryAgentExecutor（priority=2）— 旧版兜底

> **@deprecated** — 计划 2 个 release 后删除。

最后一级兜底，`is_retryable` 始终为 `False`（不再回退）。

---

## 4. MCP Eligibility 判断（Layer A）

纯规则实现，零 LLM 调用。在 `_check_mcp_eligibility()` 中：

### 4.1 领域关键词匹配

| domain | 关键词 |
|--------|--------|
| analytics | 汇总, summary, 预警, warning, 临期, 慢周转, slow |
| product | 商品, product, sku, 条码, 规格, 品牌, 品类 |
| inbound | 入库, inbound, 收货, 验收, receiving |
| outbound | 出库, outbound, 发货, 配送, 拣货 |
| inventory | 库存, stock, inventory, 批次, batch, 库位, 仓位 |

### 4.2 实体识别

对需要实体的领域（inventory/inbound/outbound），检测问题中是否包含：

```
SKU 编码:   (?<!\d)\d{4,8}(?!\d)
库位编码:   (?<!\d)\d{8}(?!\d)
批次号:     (?<!\d)\d{19}(?!\d)
单号:       (?<!\d)\d{10,}(?!\d)
```

> **关键实现细节**: 使用 `(?<!\d)...(?!\d)` 替代 `\b`。Python 3 默认 Unicode 模式下 `\b` 将中文字符视为 `\w`，导致 `"502620的库存"` 中 `"0的"` 之间无法识别单词边界。

### 4.3 免实体领域

`analytics` 和 `product` 领域的 Tool 参数全部可选，无需实体即可 eligible——避免因缺少编码而拒绝合法的汇总查询或商品搜索。

---

## 5. 回退策略

### 5.1 三级回退链

```
McpExecutor ──失败(可回退)──▶ LocalExecutor ──失败(可回退)──▶ QueryAgentExecutor
    │                              │                              │
    │ 不可回退 → 终止              │ 不可回退 → 终止              │ 最后一级，直接返回
```

### 5.2 不可回退的错误

| 错误码 | 不回退原因 |
|--------|-----------|
| `mcp_disabled` | 主动关闭，非故障 |
| `sql_security_violation` | 安全不可绕过 |
| `llm_api_error` | 基础设施问题，下一级用同样的 LLM，无意义 |
| `db_connection_failed` | 基础设施问题，下一级用同样的 MySQL，无意义 |

### 5.3 执行路径追踪

Gateway 记录完整的 executor_path：

```json
[
  {"executor": "mcp", "success": false, "error_code": "mcp_timeout"},
  {"executor": "local", "success": true, "error_code": null}
]
```

---

## 6. Trace JSON 结构

每次查询生成结构化 trace_json 存入 `query_history.trace_json`，包含三层视图：

| 视图 | 内容 | 受众 |
|------|------|------|
| **leader_view** | 一句话成功/失败描述 + one_liner | 管理层 |
| **pipeline** | source, path, total, latency, error | 运维 |
| **ops_view** | circuit_breaker 状态, fallback 触发情况, trace_id | SRE |
| **debug_view** | SQL, tool_calls, eligibility, timeline, latency breakdown | 开发 |

**示例**（MCP 成功，无回退）:
```json
{
  "leader_view": {"label": "MCP查询成功", "one_liner": "MCP 查询 · 42 条 · 0.8s"},
  "pipeline": {
    "source": "mcp", "source_label": "MCP 查询",
    "path": "MCP(query_inventory_by_sku)→OK",
    "success": true, "total": 42, "total_latency_ms": 823.5
  },
  "ops_view": {
    "circuit_breaker": "CLOSED",
    "fallback_triggered": false,
    "trace_id": "a1b2c3d4"
  },
  "debug_view": {
    "sql": null,
    "tool_calls": [{"tool": "query_inventory_by_sku", "args": {"sku_code": "502620"}}],
    "eligibility": {"domain": "inventory", "eligible": true, "reason": "ok"},
    "latency_breakdown": {"total_ms": 823.5, "mcp_graph_ms": 780.2},
    "timeline": [{"executor": "mcp", "success": true, "error_code": null}]
  }
}
```

---

## 7. 后处理管线

```
_post_process(raw, question, session_id, trace_json)
  │
  ├── 1. _translate_columns() — 英文列名 → 中文 display_name
  │     └── SchemaManager.get_column_display_map()
  │         优先级: MySQL tfrmdataprop > tfrmdataprop.json 兜底
  │
  ├── 2. _generate_insight() — Executor 未返回洞察时补生成
  │     └── LLM (INSIGHT_GENERATION_PROMPT) → parse_insight()
  │
  ├── 3. _save_history() — 写入 query_history 表
  │     └── 成功和失败都保存，方便排查
  │
  └── 4. 组装 UnifiedQueryResult
```

---

## 8. 错误分类辅助函数

`_classify_error(raw)` 从 Executor 返回的原始 dict 推断 error_code：

| 检测条件 | error_code |
|----------|-----------|
| 含 "langgraph"/"graph"/"node" | `langgraph_error` |
| 含 "api key"/"llm"/"openai"/"deepseek"/"rate limit" | `llm_api_error` |
| 含 "mysql"/"database"/"connection"/"连接" | `db_connection_failed` |
| 含 "drop"/"delete"/"insert"/"禁止"/"安全" | `sql_security_violation` |
| 含 "找不到"/"schema"/"no table" | `schema_not_found` |
| 含 "sql"/"syntax"/"execute"/"语法" | `sql_execution_error` |
| 其他 | `internal_error` |

---

## 9. 设计亮点

1. **Executor 协议而非 ABC** — 三个 Executor 都遵循 `execute(question, context) -> RawQueryResult` 协议，但不需要显式继承抽象基类。降低耦合，新增 Executor 只需实现相同签名。

2. **CircuitBreaker 区分故障类型** — 仅服务级故障（连接失败/超时/认证错误）计入断路器计数。业务错误（Tool 选择失败/参数错误）不计入——它们反映的是查询本身的问题而非 MCP Server 健康。

3. **MCP eligibility 零 LLM 开销** — 纯规则实现，包含 Unicode 安全的正则。快速、可测试、可解释。

4. **保守回退** — 未知错误默认允许回退（`is_retryable` 默认 `True`），避免因错误分类遗漏导致查询完全失败。

5. **Trace JSON 三层视图** — 一次查询生成面向管理/运维/开发三个角色的结构化追踪数据，存储在 `query_history` 表中，通过 LogsPage "查询追踪" Tab 可视化。

---

> **代码基准**: `backend/app/core/data_query_gateway.py`
> **关联文档**: [MCP Client Architecture](mcp-client-architecture.md), [ADR-010](../adr/adr-010-mcp-data-copilot-integration.md)
> **最后更新**: 2026-07-07
