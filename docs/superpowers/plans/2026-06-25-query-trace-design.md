# 查询追踪信息设计 v2 — 系统日志模块增强

> **修订**: v1→v2 — 将 MCP/LLM 调试字段延后至 Phase 3，本期优先管线 + 运维 + 已有数据。
> **目标**: 现有系统日志页新增"查询追踪"Tab，每次查询一条可展开记录。
> 领导看一句话，运维看状态，开发看细节。中文标注，分层展示。

---

## 1. 展示位置

`LogsPage.vue` (`/logs`) 现有两个 Tab：

```
[应用日志]  [调用追踪]  [查询追踪] ← 新增
```

---

## 2. 列表行（折叠状态）

| 时间 | 问题 | 管线 | 耗时 | 结果 |
|------|------|------|------|:--:|
| 14:30 | 有没有临期的商品 | `MCP 查询` | 2.3s | ✅ |
| 14:32 | 库存情况 | `本地查询` | 4.1s | ✅ |
| 14:33 | 各SKU库存总量 | `回退查询` | 6.2s | ✅ |
| 14:34 | 不存在的SKU999 | `本地查询` | 3.5s | ❌ |

管线标签颜色：MCP=绿 / 本地=灰 / 回退=橙 / 旧版=红

---

## 3. 展开详情（点击展开后三层卡片）

```
┌─────────────────────────────────────────────┐
│  📊 查询概览                                  │
│  MCP 查询 · 23 条 · 2.3 秒                   │
│  管线: MCP → get_stock_warning → 成功        │
│  问题: "有没有临期的商品"                      │
│  错误: (无)                                   │
├─────────────────────────────────────────────┤
│  🔧 运维信息                                  │
│  熔断器: 正常 (CLOSED)                        │
│  触发回退: 否                                  │
│  追踪ID: a1b2c3d4                             │
├─────────────────────────────────────────────┤
│  🔬 开发详情                                  │
│  SQL: (MCP 预构建查询，无 SQL)                │
│  MCP Tool 调用: [get_stock_warning]           │
│  耗时分解: 总 2340ms                          │
│  (更多 MCP/LLM 细节将在下期上线)               │
└─────────────────────────────────────────────┘
```

如果触发回退，运维卡片变为：

```
│  触发回退: 是 ⚠️                              │
│  尝试: MCP → 失败 (tool_selection_failed)     │
│  接管: 本地 NL2SQL                            │
```

---

## 4. 数据来源与缺口分析

| 字段组 | 本期可输出 (v2) | 延期至 Phase 3 |
|--------|:---:|:---:|
| pipeline.source/label/path | ✅ | |
| pipeline.total_latency_ms | ✅ | |
| pipeline.total | ✅ | |
| pipeline.success | ✅ | |
| pipeline.error_code/message | ✅ | |
| ops_view.circuit_breaker | ✅ | |
| ops_view.fallback_triggered | ✅ | |
| ops_view.trace_id | ✅ | |
| debug_view.sql | ✅ | |
| debug_view.tool_calls | ✅ | |
| ops_view.mcp_eligible/domain | ❌ (在 Gateway 内部,未记录) | Phase 3 |
| ops_view.mcp_available | ❌ | Phase 3 |
| debug_view.llm_tool_selection 详情 | ❌ | Phase 3 |
| pipeline.llm_latency_ms | ❌ | Phase 3 |
| pipeline.mcp_latency_ms | ❌ | Phase 3 |

> 本期输出的所有字段都来自 `UnifiedQueryResult` 和 Gateway 已有内部状态（CircuitBreaker、回退链路径），不需要新增任何数据采集代码——只需要在 `_save_history` 之前组装成结构化 JSON。

---

## 5. 数据结构 (trace_json)

```json
{
  "leader_view": {
    "label": "MCP查询成功",
    "one_liner": "MCP 查询 · 23 条 · 2.3s"
  },
  "pipeline": {
    "source": "mcp",
    "source_label": "MCP 查询",
    "path": "MCP(get_stock_warning)", "success": true,
    "total": 23,
    "total_latency_ms": 2340,
    "error_code": null, "error_message": null
  },
  "ops_view": {
    "circuit_breaker": "正常 (CLOSED)",
    "fallback_triggered": false,
    "fallback_from": null, "fallback_to": null,
    "fallback_reason": null,
    "trace_id": "a1b2c3d4"
  },
  "debug_view": {
    "sql": null,
    "tool_calls": [{"tool": "get_stock_warning", "args": {...}}]
  }
}
```

---

## 6. 任务拆分

### Task 1: 后端 — 存储 + 组装 trace (含 query_history 迁移)

**改动**:
- `models/query_history.py`: `query_history` 表新增 `trace_json TEXT` 列 (ALTER TABLE + CREATE TABLE 同步)
- `data_query_gateway.py`: `_post_process` 中从 `RawQueryResult` + `self._mcp_breaker` + executor 执行结果组装 `trace_json`；`_save_history` 写入
- `data_query_gateway.py`: `_execute_with_fallback` 中跟踪 fallback 路径

**验收**: 查询后 `query_history` 表的 `trace_json` 列有数据

### Task 2: 后端 — 查询追踪 API

**改动**:
- `api/logs.py`: 新增 `GET /logs/recent?type=queries` 分支，从 SQLite `query_history` 读取最近 N 条（按 `created_at DESC`）
- `api/logs.js` (前端): 新增 `getQueries(limit, minutes)` 方法

**验收**: `curl /api/v1/logs/recent?type=queries` 返回查询追踪列表

### Task 3: 前端 — LogsPage 新增"查询追踪"Tab + 列表行

**改动**:
- `LogsPage.vue`: 新增 `activeTab === 'queries'` 分支
- 列表: 时间 / 问题(截断) / 管线标签(颜色) / 耗时 / 成功/失败图标
- 复用现有样式和自动刷新逻辑

**验收**: 页面第三 Tab 可切换，列表显示查询记录

### Task 4: 前端 — 展开详情卡片

**改动**:
- `LogsPage.vue`: 点击行展开三层卡片 (📊 概览 / 🔧 运维 / 🔬 开发)
- 卡片用中文标注所有字段

**验收**: 点击行可展开/收起，三个卡片内容正确

### Task 5 (Phase 3): 丰富 trace 细节

**改动**:
- `data_query_gateway.py`: 在 Gateway 执行路径中记录 `mcp_eligible`、`domain_hint`、`mcp_available`
- `graph_mcp.py`: `tool_select_node` 输出携带 `candidates`、`selection_reason`
- `McpExecutor`: 记录 `llm_latency_ms`、`mcp_latency_ms`

**验收**: trace_json 中 `ops_view` 和 `debug_view` 字段完整

---

## 7. 不改的内容

- `UnifiedQueryResult` 结构 — trace 数据旁路写入，不影响主链路
- 现有的 JSON lines 日志 (`data/logs/app.*.jsonl`)
- 现有的 trace span (`data/traces/trace.*.jsonl`)
- QueryPage / OrchestratorPage 的查询入口

---

> **设计版本**: v2 (2026-06-25 修订)
> **修订内容**: v1→v2 — 将 MCP/LLM 调试字段延后至 Phase 3 Task 5；本期 (Task 1-4) 仅输出已有数据
