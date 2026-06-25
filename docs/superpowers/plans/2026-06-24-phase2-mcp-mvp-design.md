# Phase 2：MCP MVP 设计与实施计划

> **状态**: 冻结设计 v1.1 — 审核后进入编码
> **修订**: v1.0 → v1.1: 新增 MCP 路由三层模型、收紧单Tool调用、CircuitBreaker 细化、指标精确定义、Tool Registry、字段契约矩阵
> **基线**:
> - Phase 1: `docs/superpowers/plans/2026-06-24-phase1-implementation-plan.md`
> - Phase 1.5: `docs/superpowers/plans/2026-06-24-phase1.5-acceptance-report.md`
> - MCP Guide: `docs/data-copilot-integration-guide.md`
> **约束**: 不写代码，不进入实现，输出可执行的设计文档

---

## 1. Phase 2 目标与边界

### 1.1 目标

在 Phase 1 稳定基座之上，以最小改动接入 MCP Data Copilot Server，使以下高频 WMS 查询优先通过 MCP 预构建 Tool 执行：

- SKU 库存查询（`query_inventory_by_sku`）
- 仓库/库位库存查询（`query_inventory_by_location`）
- 商品主数据查询（`query_product`）
- 入库/出库单查询（`query_inbound_order` / `query_outbound_order`）
- 库存预警（`get_stock_warning`）
- 库存汇总（`get_inventory_summary`）
- 慢周转分析（`get_slow_moving_inventory`）

**"完全接入 MCP"在 Phase 2 MVP 中的含义**：
MCP 成为 Gateway 执行器链的最高优先级执行器。MCP 可用且问题匹配 MCP Tool 覆盖范围时，优先走 MCP。MCP 不可用或不适用时，自动回退到 LocalExecutor。

### 1.2 Phase 2 明确不做什么

| 不做 | 原因 |
|------|------|
| ❌ 不做完整 Clarification Policy | Phase 3 范围 |
| ❌ 不做 QueryAgent 准入条件优化 | Phase 3 范围 |
| ❌ 不做复杂自由分析查询的 MCP 路由 | `execute_sql_readonly` 不在此阶段作为主路径 |
| ❌ 不做前端 MCP source 展示 | Phase 4 范围 |
| ❌ 不做 MCP 性能调优 / 缓存 | 过早优化 |
| ❌ 不做 MCP Tool 的参数自动补全/歧义消除 | Phase 3 的 Clarification 前置 |
| ❌ **不做多 Tool 并行编排** | Phase 2 每次查询最多调用 **1 个 MCP Tool**；多 Tool fan-out / merge 延后到 Phase 3+ |
| ❌ 不做 Tool 返回结果的跨 Tool 聚合/合并 | 单 Tool 模式不需要 |

### 1.3 查询类型边界

**Phase 2 优先由 MCP 处理（预构建 Tool 覆盖）**:

| 问题类型 | 对应 MCP Tool | 优先级 |
|---------|-------------|:-----:|
| "XX商品的库存" | `query_inventory_by_sku` | P0 |
| "XX仓位有哪些货" | `query_inventory_by_location` | P0 |
| "XX批次库存" | `query_inventory_by_batch` | P1 |
| "商品XX的基本信息" | `query_product` | P0 |
| "XX商品的规格/条码" | `query_product_spec` | P1 |
| "XX商品的仓库配置" | `query_product_warehouse_config` | P1 |
| "最近的入库单" | `query_inbound_order` | P0 |
| "XX入库单明细" | `query_inbound_detail` | P1 |
| "出库单查询" | `query_outbound_order` | P0 |
| "XX出库单明细" | `query_outbound_detail` | P1 |
| "收货验收记录" | `query_receiving_record` | P1 |
| "各SKU库存总量" | `get_inventory_summary` | P0 |
| "有没有快过期的" | `get_stock_warning` | P0 |
| "XX商品库存流水" | `query_stock_flow` | P1 |
| "哪些库存太久没动" | `get_slow_moving_inventory` | P1 |

**Phase 2 暂不强制走 MCP**:

| 问题类型 | 处理方式 | 原因 |
|---------|---------|------|
| 缺少实体/时间范围 → 歧义 | 走 LocalExecutor（有 NEED_CLARIFICATION） | MCP 无澄清能力 |
| 跨多域复杂自由查询 | 走 LocalExecutor（LLM 生成 SQL） | 预构建 Tool 无法覆盖 |
| "帮我看看数据" 之类模糊问题 | 走 LocalExecutor | 无法映射到具体 Tool |
| 超出上述 15 种 Tool 覆盖范围 | LocalExecutor → QueryAgent 回退 | MCP 无法处理 |

---

## 2. MCP 接入架构设计

### 2.1 新增模块

| 文件 | 模块 | 说明 |
|------|------|------|
| `backend/app/core/mcp_client.py` | `WmsMcpClient` + `McpClientManager` | 复用 MCP Guide 第 4 节 Python 客户端代码 |
| `backend/app/agents/graph_mcp.py` | MCP Tool 选择的 LangGraph 图 | `tool_select_node` → `mcp_call_node` → `result_format_node` |
| `backend/app/agents/prompts_sql.py` | 新增 `MCP_TOOL_SELECT_PROMPT` | LLM 选择 Tool + 填参数的 Prompt |

### 2.2 修改模块

| 文件 | 变更 | 说明 |
|------|------|------|
| `backend/app/core/data_query_gateway.py` | 新增 `McpExecutor`；更新 `_register_executors()` 注册 McpExecutor(priority=0)；新增 `CircuitBreaker` 内部类 | Gateway 核心变更 |
| `backend/app/core/config.py` | 新增 `mcp_enabled`, `mcp_base_url`, `mcp_api_key`, `mcp_timeout` | MCP 连接配置 |
| `backend/app/core/agent_state.py` | 新增 `MCPAgentState` | LangGraph 状态定义 |
| `.env.example` | 新增 MCP 配置项 | 部署文档 |

### 2.3 不修改的模块

| 文件 | 原因 |
|------|------|
| `services/query_service.py` | Gateway 透明新增 Executor，QueryService 无感知 |
| `orchestrator/dispatch.py` | `dispatch_to_nl2sql` 仍委托 Gateway，MCP 自动成为最高优先级 |
| `api/query.py` / `api/orchestrator.py` | 同上，入口不变 |
| `agents/query_agent.py` | 不动 |
| `agents/graph_nl2sql.py` | 不动 |

### 2.4 目录职责

```
backend/app/
├── core/
│   ├── data_query_gateway.py   # Gateway + McpExecutor + LocalExecutor + QueryAgentExecutor + CircuitBreaker
│   ├── mcp_client.py           # WmsMcpClient (HTTP) + McpClientManager (健康检查+Tool缓存)
│   └── config.py               # MCP 配置项
├── agents/
│   ├── graph_mcp.py            # MCP Tool 选择 + 调用 LangGraph
│   ├── graph_nl2sql.py         # 不动
│   ├── query_agent.py          # 不动
│   └── prompts_sql.py          # + MCP_TOOL_SELECT_PROMPT
└── core/
    └── agent_state.py          # + MCPAgentState
```

### 2.5 Phase 2 执行链路图

```
用户问题
  │
  ▼
DataQueryGateway.execute(question, session_id)
  │
  ├── [Step 0] CircuitBreaker 检查
  │     ├── OPEN → 跳过 MCP → 直接到 [3]
  │     └── CLOSED / HALF_OPEN → 继续 [1]
  │
  ├── [1] MCP 路由判断 (Phase 2 规则层)
  │     基于关键词+领域匹配，判断问题是否属于 MCP Tool 覆盖范围
  │     ├── 不属于 → 跳过 MCP → 直接到 [3]
  │     └── 属于 → 继续 [2]
  │
  ├── [2] McpExecutor.execute(question, context)
  │     │
  │     ├── tool_select_node: LLM 从候选 Tool 中选择 **1 个** + 填参数
  │     │   Phase 2 仅做单 Tool 选择，不做多 Tool 并行
  │     │   输入: question + MCP Tool 列表(按 domain 过滤后) + domain_hint
  │     │   输出: {tool_name, arguments}  或  null（无法选择）
  │     │
  │     ├── mcp_call_node: 调用选中的 MCP Tool
  │     │   通过 WmsMcpClient.call_tool(tool_name, arguments)
  │     │   Phase 2 不在此节点做并行 fan-out
  │     │
  │     ├── result_format_node: items → {columns, rows, total}
  │     │
  │     ├── 成功 → CircuitBreaker.record_success() → 跳到后处理 [5]
  │     │
  │     └── 失败 → CircuitBreaker.record_failure()
  │               → 检查阈值 (≥3次 → OPEN, 60s冷却)
  │               → 继续 [3]
  │
  ├── [3] LocalExecutor.execute(question, context)  ← 现有，不动
  │     ├── 成功 → 跳到后处理 [5]
  │     └── 失败 + retryable → 继续 [4]
  │
  ├── [4] QueryAgentExecutor.execute(question, context)  ← 现有，不动
  │
  └── [5] _post_process()  ← 现有，不动
        • _translate_columns()
        • _save_history()
        • _generate_insight()
        → UnifiedQueryResult
```

---

## 3. MCP 查询路由策略

### 3.1 路由决策表

采用 **规则优先 + LLM 辅助**策略。规则层做"是否适合 MCP"的二元判断，LLM 做"选哪个 Tool + 填什么参数"。

| 问题类型 | 识别方式 | MCP 路由 | 允许 Local | 允许 QueryAgent | 备注 |
|---------|---------|:-------:|:--------:|:-------------:|------|
| 明确实体 + 库存关键词 | 规则: `库存关键词` + `SKU/商品名` | ✅ 首选 | ✅ MCP失败后 | ✅ 双重失败后 | |
| 明确实体 + 商品关键词 | 规则: `商品/规格/条码/品牌/品类` | ✅ 首选 | ✅ MCP失败后 | ✅ 双重失败后 | |
| 入库/出库 + 时间范围 | 规则: `入库/出库` + 日期模式 | ✅ 首选 | ✅ MCP失败后 | ✅ 双重失败后 | |
| 预警/汇总/慢周转 | 规则: `预警/汇总/临期/慢周转/库存不够` | ✅ 首选 | ✅ MCP失败后 | ✅ 双重失败后 | |
| 收货/验收 | 规则: `收货/验收/采购入库` | ✅ 首选 | ✅ MCP失败后 | ✅ 双重失败后 | |
| 缺实体（"库存情况"） | 规则: 关键词存在但无实体 | ❌ 跳过 MCP | ✅ 首选 | ✅ Local失败后 | Local 有 NEED_CLARIFICATION |
| 缺时间（"出库记录"） | 规则: 关键词存在但无时间 | ❌ 跳过 MCP | ✅ 首选 | ✅ Local失败后 | Local 有 LIMIT 强制 |
| 跨域复杂自由查询 | 规则: 无单域匹配 | ❌ 跳过 MCP | ✅ 首选 | ✅ Local失败后 | MCP Tool 无法覆盖 |
| 模糊闲聊 | 规则: 无业务关键词 | ❌ 跳过所有 | ❌ | ❌ | Phase 3 处理 |

### 3.2 MCP 路由三层模型 **[v1.1 新增]**

将 MCP 路由决策拆为三层，避免 `_is_mcp_candidate()` 与 `tool_select_node` 职责重叠：

```
用户问题
  │
  ▼
┌─────────────────────────────────────────────────────────────┐
│ Layer A: MCP Eligibility (Gateway._check_mcp_eligibility)   │
│ 职责: 判断"这个 query 是否属于 Phase 2 MCP 能力边界内"        │
│ 方式: 纯规则（关键词 + 实体识别 + 领域匹配）                  │
│ 输出: {eligible: bool, reason: str, domain_hint: str}       │
│                                                              │
│ eligible=true  → 进入 Layer B                                │
│ eligible=false → 跳过 MCP，直接走 LocalExecutor              │
└─────────────────────────────────────────────────────────────┘
  │ eligible=true
  ▼
┌─────────────────────────────────────────────────────────────┐
│ Layer B: Tool Family Routing (graph_mcp.tool_filter_node)   │
│ 职责: 将 eligible query 路由到较小的 Tool 候选集             │
│ 方式: 规则 (DomainClassifier + Tool Registry domain 映射)    │
│ 输入: domain_hint (来自 Layer A) + full Tool Registry        │
│ 输出: candidate_tools (3-5 个)                               │
│                                                              │
│ candidate_tools 非空 → 进入 Layer C                          │
│ candidate_tools 为空 → 返回 tool_selection_failed → Local    │
└─────────────────────────────────────────────────────────────┘
  │ candidate_tools
  ▼
┌─────────────────────────────────────────────────────────────┐
│ Layer C: Final Tool Selection + Param Extraction             │
│         (graph_mcp.tool_select_node)                        │
│ 职责: 从候选集中选择 **1 个** Tool + 提取/填充参数           │
│ 方式: LLM（MCP_TOOL_SELECT_PROMPT）                          │
│ 输入: question + candidate_tools(含参数schema)                │
│ 输出: {tool_name, arguments}  或  null（无法选择）           │
│                                                              │
│ 成功 → mcp_call_node                                         │
│ 失败 → tool_selection_failed → 回退到 LocalExecutor         │
└─────────────────────────────────────────────────────────────┘
```

#### Layer A 详细规则 **[v1.1 新增]**

**位置**: `DataQueryGateway._check_mcp_eligibility(question) → McpEligibility`

```text
class McpEligibility:
    eligible: bool
    reason: str
    domain_hint: str | None       # inventory / outbound / product / analytics / none
    intent_hint: str | None       # query_inventory / query_order / query_product / etc.

规则:
  1. 业务关键词匹配 → 确定 domain_hint
     库存域: ["库存", "stock", "inventory", "批次", "batch", "库位", "仓位"]
     商品域: ["商品", "product", "sku", "条码", "规格", "品牌", "品类"]
     入库域: ["入库", "inbound", "收货", "验收", "receiving"]
     出库域: ["出库", "outbound", "发货", "配送", "拣货"]
     分析域: ["汇总", "summary", "预警", "warning", "临期", "慢周转", "slow"]

  2. 实体识别（简单正则）
     SKU 编码: \d{4,8}
     商品名: 中文名词短语
     单号: 长数字串
     批次号: 19位数字

  3. 判定:
     有业务关键词 AND 有实体 → eligible=true
     有业务关键词 BUT 无实体 → eligible=false, reason="missing_entity"
     无业务关键词 → eligible=false, reason="no_business_keyword"
```

#### Layer B 详细规则 **[v1.1 新增]**

**位置**: `graph_mcp.py` 的 `tool_filter_node`

```text
输入: domain_hint + Tool Registry (见附录 C)

映射规则（内置在 Tool Registry 的 domain 字段）:
  domain_hint="inventory" → [query_inventory_by_sku, query_inventory_by_location,
                              query_inventory_by_batch, get_inventory_summary,
                              get_stock_warning, get_slow_moving_inventory,
                              query_stock_flow]
  domain_hint="product"   → [query_product, query_product_spec,
                              query_product_warehouse_config]
  domain_hint="outbound"  → [query_outbound_order, query_outbound_detail]
  domain_hint="inbound"   → [query_inbound_order, query_inbound_detail,
                              query_receiving_record]
  domain_hint="analytics" → [get_inventory_summary, get_stock_warning,
                              get_slow_moving_inventory]

输出: candidate_tools (list[ToolDef])  — 含 name, description, inputSchema
```

> **设计要点**: Layer B 是纯规则层，**不调用 LLM**。映射表硬编码在 Tool Registry 中。这确保：
> 1. 测试可精确控制候选集
> 2. LLM 只在缩小后的 3-5 个候选中选择，准确率更高
> 3. 职责边界清晰 — Layer A/B 是规则，Layer C 是 LLM

#### Layer C: Tool Selection Prompt 修订 **[v1.1]**

```text
System:
你是 WMS 数据查询 Tool 选择器。根据用户问题，从候选 Tool 中选出最合适的 **1 个**。

规则:
1. 只从候选列表中选，不要编造 Tool 名称
2. 参数必须从用户问题中提取，不要编造
3. 如果问题缺少 Tool 的必填参数，返回 null
4. Phase 2 只选 1 个 Tool

候选 Tool 列表（仅候选，已按领域过滤）:
{tool_descriptions}

用户问题:
{user_question}

领域提示:
{domain_hint}

输出 JSON 对象（单个 Tool）:
{{"tool": "query_inventory_by_sku", "args": {{"sku_code": "502620", "limit": 100}}}}
如果无法选择，输出: null
```

**参数校验** (不变):
- Phase 2 不做复杂校验，依赖 MCP Server 返回的 `VALIDATION_ERROR`
- LLM 提取的参数直接传给 MCP Tool
- MCP 返回参数错误 → 不重试，直接回退到 LocalExecutor

**失败处理** (不变):
- LLM 返回 `null` → `is_retryable=true` → 回退到 Local
- Tool 调用返回错误 → `is_retryable` 取决于错误类型（见第 5 节）

### 3.4 为什么不在此阶段用 `execute_sql_readonly` 作为 MCP 主路径

Phase 2 MVP 只使用预构建 Tool。理由:
1. 预构建 Tool 精准、安全，LLM 只需选择 + 填参数
2. `execute_sql_readonly` 需要 LLM 生成 SQL → 复杂度等同于 graph_nl2sql
3. 如果预构建 Tool 覆盖不足 → 回退到 LocalExecutor 生成 SQL 更合理

`execute_sql_readonly` 在 Phase 2 作为 McpExecutor 的**最后备选 Tool**（当 LLM 判断预构建 Tool 不足时），但默认不使用。

---

## 4. MCP 结果映射契约

### 4.1 McpExecutor → RawQueryResult 映射

MCP 预构建 Tool 返回格式（通用）:
```json
{"total": N, "limit": M, "offset": 0, "items": [{...}, ...]}
```

MCP `execute_sql_readonly` 返回格式:
```json
{"columns": [...], "rows": [[...], ...], "row_count": N, "injected_limit": M}
```

**适配层（`result_format_node`）统一映射**:

```text
function _mcp_to_raw_query_result(mcp_response, tool_calls) → RawQueryResult:

    if mcp_response has "items":
        // 预构建 Tool 返回
        columns = extract_keys_from_first_item(mcp_response.items)
        rows = [list(item.values()) for item in mcp_response.items]
        total = len(rows)
    elif mcp_response has "columns" and "rows":
        // execute_sql_readonly 返回
        columns = mcp_response.columns
        rows = mcp_response.rows
        total = mcp_response.row_count
    else:
        // 无法识别的格式
        return RawQueryResult(success=False, error_code="mcp_format_error")

    return RawQueryResult(
        success=True,
        source="mcp",
        query_mode="tool",     // 或 "sql" (execute_sql_readonly)
        columns=columns,       // 英文原始列名
        rows=rows,
        total=total,
        sql=None,              // 预构建 Tool 无 SQL，execute_sql_readonly 有
        tool_calls=tool_calls,
        insight=None,          // MCP 不返回 insight，由 Gateway 补生成
    )
```

### 4.2 UnifiedQueryResult 字段契约矩阵 **[v1.1 修订]**

明确每个字段的**责任归属**（McpExecutor / Gateway / 无需填充）和**默认值策略**。

#### 4.2.1 成功场景 (success=true)

| 字段 | 填充者 | 来源 | 默认值策略 | 必填? |
|------|:-----:|------|-----------|:----:|
| `success` | McpExecutor | `True` | — | ✅ |
| `source` | McpExecutor | 固定 `"mcp"` | — | ✅ |
| `query_mode` | McpExecutor | `"tool"`(预构建) / `"sql"`(execute_sql_readonly) | Phase 2 固定 `"tool"` | ✅ |
| `question` | Gateway | 用户原始输入 | — | ✅ |
| `normalized_question` | Gateway | — | `None` (Phase 3) | ❌ |
| `sql` | McpExecutor | 预构建: `None` | 默认 `None` — 预构建 Tool 不暴露 SQL | ❌ |
| `tool_calls` | McpExecutor | `[{tool_name, arguments}]` (单Tool) | — | ✅ |
| `columns` | Gateway `_post_process` | McpExecutor 返回英文列名 → `_translate_columns()` 翻译 | — | ✅ |
| `rows` | McpExecutor | MCP items → `list[list]` | — | ✅ |
| `total` | McpExecutor | MCP `total` 或 `len(rows)` | — | ✅ |
| `insight` | Gateway `_post_process` | 补生成 (MCP 不返回 insight) | 无数据时 `Insight(summary="查询无结果")` | ✅ |
| `confidence` | McpExecutor | LLM Tool 选择置信度 (可选) | `None` | ❌ |
| `clarification_needed` | Gateway | — | 固定 `False` (Phase 3) | ✅ |
| `clarification_question` | — | — | `None` (Phase 3) | ❌ |
| `history_id` | Gateway `_post_process` | `_save_history()` 返回值 | 保存失败时 `None` | ❌ |
| `tables_used` | — | Phase 2 不填充 | 固定 `[]` — MCP Tool 不暴露底层表 | ❌ |
| `explanation` | — | Phase 2 不填充 | 固定 `""` | ❌ |
| `error_code` | — | 成功场景 | `None` | ❌ |
| `error_message` | — | 成功场景 | `None` | ❌ |
| `trace_id` | Gateway | `get_current_trace_id()` | — | ✅ |
| `latency_ms` | Gateway | `time.perf_counter()` 计算 | — | ✅ |

#### 4.2.2 失败场景 (success=false)

| 字段 | 填充者 | 说明 |
|------|:-----:|------|
| `success` | McpExecutor | `False` |
| `source` | McpExecutor | 仍为 `"mcp"`（表示 MCP 被尝试但失败） |
| `error_code` | McpExecutor | 枚举值（见第 5 节） |
| `error_message` | McpExecutor | 面向用户的中文描述 |
| `sql` | McpExecutor | 如果有（如 execute_sql_readonly 的 SQL），否则 `None` |
| `tool_calls` | McpExecutor | 如果 Tool 选择成功但调用失败，仍记录已选的 Tool |
| `columns` / `rows` / `total` | — | 默认空值 |
| `insight` | — | `None` |
| `history_id` | Gateway | `None`（失败不写历史） |

#### 4.2.3 关键字段责任总结 **[v1.1 新增]**

```text
McpExecutor 负责:
  success, source, query_mode, sql(如有), tool_calls, columns(英文), rows, total,
  error_code, error_message

Gateway._post_process() 负责:
  columns(翻译), insight(补生成), history_id(写历史), trace_id, latency_ms,
  question, normalized_question(None), clarification_*(Phase 3)

Phase 2 明确不填充(默认值兜底):
  tables_used → [], explanation → "", normalized_question → None,
  clarification_* → False/None

QueryService.natural_query() 负责(不变):
  results → list[dict] 转换, insight → dict 转换
```

#### 4.2.4 Phase 1.5 修复字段的 Phase 2 继承策略

| 字段 | Phase 1.5 修复 | Phase 2 MCP 路径策略 |
|------|---------------|---------------------|
| `history_id` | Gateway 捕获 `_save_history()` 返回值 | 同 Phase 1: Gateway `_post_process` 填充 |
| `tables_used` | QueryService 固定返回 `[]` | MCP 路径同: 固定 `[]` |
| `explanation` | QueryService 固定返回 `""` | MCP 路径同: 固定 `""` |
| `results` (dict vs list) | QueryService 做 list→dict 转换 | MCP 路径同: QueryService 做相同转换

### 4.3 适配层位置

`graph_mcp.py` 的 `result_format_node` 负责 MCP → RawQueryResult 的格式转换。Gateway 的 `_post_process()` 无需感知 MCP 差异——它只处理 RawQueryResult。

---

## 5. MCP 回退策略与错误处理

### 5.1 错误分类与回退规则

| 错误场景 | error_code | 回退到 Local? | CircuitBreaker计数? | 备注 |
|---------|-----------|:-----------:|:-----------------:|------|
| MCP Server 连接失败 | `mcp_unavailable` | ✅ 是 | ✅ 是 | 网络/DNS/端口不通 |
| MCP 认证失败 (401/403) | `mcp_auth_error` | ✅ 是（首次） | ✅ 是 | 需人工处理 API Key |
| MCP 超时 | `mcp_timeout` | ✅ 是 | ✅ 是 | 重试1次后再回退 |
| Tool 选择失败（LLM 返回[]） | `tool_selection_failed` | ✅ 是 | ❌ 否 | 不表示 MCP 不可用 |
| Tool 参数校验失败 | `tool_validation_failed` | ✅ 是 | ❌ 否 | MCP 可用,只是参数不对 |
| Tool 执行错误（MCP 内部） | `mcp_tool_error` | ✅ 是 | ❌ 否 | 同上 |
| 无数据（total=0） | `no_data` | ❌ 不回退 | ❌ 否 | 不是错误,正常返回 |
| SQL 安全拒绝 | `sql_security_violation` | ❌ 不回退 | ❌ 否 | 安全问题不绕过 |
| 不支持查询类型 | `unsupported_query` | ✅ 是 | ❌ 否 | MCP 能力边界内正常 |
| 未分类内部错误 | `internal_error` | ✅ 是 | ⚠️ 弱计数 | 保守:回退但记录 |

### 5.2 防止 MCP 失败被掩盖

**问题**: 如果 MCP 因配置错误（如 API Key 不对）持续失败，每次都回退到 Local，MCP 问题永远不会暴露。

**Phase 2 缓解措施**:

1. **CircuitBreaker**: 连续 3 次 MCP 失败 → OPEN（60s 冷却）。冷却期间直接走 Local，不浪费时间尝试 MCP。

2. **告警日志**: `mcp_auth_error` 记录 ERROR 级别日志（需人工处理）。`mcp_unavailable` 连续 5 次记录 ERROR。

3. **Source 透传**: `UnifiedQueryResult.source` 展示实际执行器。如果 MCP 持续回退，前端（Phase 4）或日志可见 source 始终为 `"local"`。

4. **启动时健康检查**: 应用启动时（`lifespan`），如果 `mcp_enabled=True`，尝试 `ping()`。如果 ping 失败，记录 WARNING 但不阻止启动。

### 5.3 Phase 2 不做的错误处理

- ❌ 错误自动恢复（Phase 3 CircuitBreaker 增强）
- ❌ MCP 错误转 Clarification（Phase 3）
- ❌ 错误重试策略优化（Phase 3）
- ❌ MCP 降级通知用户（Phase 4 前端）

---

## 6. Phase 2 测试计划与验收标准

### 6.1 L1: McpExecutor / MCP Client / Tool Selection 单测

| 测试 | 覆盖点 |
|------|--------|
| `test_mcp_client_call_tool_success` | `WmsMcpClient.call_tool()` mock 返回成功 |
| `test_mcp_client_ping` | `ping()` 返回 True/False |
| `test_mcp_client_list_tools` | `list_tools()` 返回 Tool 列表 |
| `test_mcp_client_auth_error` | 401/403 → `WmsMcpError` |
| `test_mcp_client_timeout` | 超时 → `httpx.ReadTimeout` |
| `test_mcp_executor_success` | McpExecutor 完整流程 mock（单 Tool） |
| `test_mcp_executor_tool_selection_null` | LLM 返回 null → `tool_selection_failed` |
| `test_mcp_eligibility_inventory_query` | Layer A: 库存查询 → eligible=true |
| `test_mcp_eligibility_ambiguous_query` | Layer A: "库存情况" → eligible=false |
| `test_mcp_eligibility_non_business` | Layer A: "你好" → eligible=false |
| `test_tool_filter_by_domain` | Layer B: domain_hint="inventory" → 候选 7 个 Tool |
| `test_tool_filter_unknown_domain` | Layer B: 未知 domain → 空候选 |
| `test_result_format_items_to_raw` | items → RawQueryResult 映射 |
| `test_result_format_sql_to_raw` | execute_sql_readonly 格式映射 |
| `test_tool_select_prompt_format` | `MCP_TOOL_SELECT_PROMPT` 格式化正确 |

### 6.2 L2: Gateway 路由与回退测试 **[v1.1 修订]**

| 测试 | 覆盖点 |
|------|--------|
| `test_mcp_route_on_inventory_query` | 库存查询 → _check_mcp_eligibility → eligible=true → McpExecutor 被调用 |
| `test_mcp_skip_on_ambiguous_query` | "库存情况" → eligible=false (missing_entity) → 直接走 Local |
| `test_mcp_skip_on_non_business_query` | "你好" → eligible=false → 直接走 Local |
| `test_layer_b_filters_candidates` | eligible=true → tool_filter_node 返回正确候选集 |
| `test_circuit_breaker_open_after_failures` | 3 次 mcp_unavailable → OPEN |
| `test_circuit_breaker_does_not_count_tool_error` | tool_selection_failed 3 次 → 仍为 CLOSED |
| `test_circuit_breaker_half_open_recovery` | 60s 后 → HALF_OPEN → 成功 → CLOSED |
| `test_mcp_fallback_to_local` | MCP 失败(retryable) → LocalExecutor 接管 |
| `test_mcp_auth_error_fallback_and_alert` | 401 → 回退到 Local + ERROR 日志 |
| `test_mcp_disabled_config` | `mcp_enabled=False` → 跳过 MCP 整个链路 |

### 6.3 L3: 高频问题集 E2E（需集成环境）

| # | 问题 | 预期路径 | 验收点 |
|---|------|---------|--------|
| E1 | `"502620的库存情况"` | MCP: `query_inventory_by_sku` | source="mcp", query_mode="tool" |
| E2 | `"06080816仓位有什么货"` | MCP: `query_inventory_by_location` | source="mcp" |
| E3 | `"商品502620的基本信息"` | MCP: `query_product` | source="mcp" |
| E4 | `"最近的入库单"` | MCP: `query_inbound_order` | source="mcp" |
| E5 | `"有没有快过期的商品"` | MCP: `get_stock_warning` | source="mcp" |
| E6 | `"各SKU库存总量"` | MCP: `get_inventory_summary` | source="mcp" |
| E7 | `"哪些库存超过90天没动"` | MCP: `get_slow_moving_inventory` | source="mcp" |
| E8 | `"库存情况"` (无实体) | LocalExecutor | source="local"（MCP 跳过） |
| E9 | MCP 不可用时 `"502620的库存"` | LocalExecutor | source="local"（回退成功） |
| E10 | Phase 1 黄金 Case C1-C5 回归 | 与 Phase 1 一致 | 不退化 |

### 6.4 验收标准 **[v1.1 修订]**

#### 6.4.1 MCP 命中率 (MCP Hit Rate)

```text
定义: Phase 2 目标高频场景测试集中，MCP 被正确路由并尝试调用的比例。

分母: "Phase 2 MCP 目标测试集"（约 15-20 条查询，涵盖 15 种 Tool）
分子: 分母中 _check_mcp_eligibility() 返回 eligible=true 且 McpExecutor 被调用的查询数

目标: ≥ 80%
测量: E2E case E1-E7 + 额外 MCP 目标场景 case

不纳入分母:
  - 非 MCP 目标场景的查询（如 E8 "库存情况"）
  - 闲聊/非业务查询
```

#### 6.4.2 MCP 执行成功率 (MCP Execution Success Rate)

```text
定义: 已路由到 MCP 的请求中，McpExecutor 成功返回数据的比例。

分母: MCP 被尝试调用的请求数（即 "命中 MCP" 的请求）
分子: 分母中 McpExecutor 返回 success=true 的请求数

目标: ≥ 90%
测量: MCP 健康时 E1-E7
```

#### 6.4.3 端到端成功率 (End-to-End Success Rate)

```text
定义: 所有 MCP 目标场景测试集中，最终返回 success=true 的比例（含回退后成功的）。

分母: "Phase 2 MCP 目标测试集"
分子: 分母中 UnifiedQueryResult.success=true 的查询数

目标: ≥ 95%（MCP 失败但 Local 回退成功 = 端到端成功）
测量: 所有 L3 E2E case
```

#### 6.4.4 回退率 (Fallback Rate)

```text
定义: MCP 被尝试调用但失败、回退到 Local/QueryAgent 的比例。

分母: MCP 被尝试调用的请求数
分子: 分母中因 MCP 失败而触发回退、最终由 Local/QueryAgent 返回的请求数

目标: < 10%
测量: E9 + 模拟 MCP 不可用场景
```

#### 6.4.5 路由准确率 (Routing Accuracy)

```text
定义: _check_mcp_eligibility() 判断正确的比例。

分母: "Phase 2 MCP 目标测试集" + "Phase 2 非 MCP 场景测试集"
分子: 正确判断的查询数:
  - MCP 目标场景 → eligible=true  ✓
  - 非 MCP 场景   → eligible=false ✓

目标: ≥ 85%
测量: E1-E8
```

#### 6.4.6 Phase 1 黄金 Case 零退化

```text
定义: Phase 1 的 12 条黄金 Case 在 Phase 2 部署后行为不变。

要求:
  - MCP 目标场景的 Case（如"502620的库存"）: MCP 优先，source="mcp"
  - 非 MCP 场景的 Case（如空字符串、闲聊）: 仍走 Local，source="local"
  - 所有 Case 的 UnifiedQueryResult 结构与 Phase 1 兼容

验证:
  - 完整重跑 Phase 1 黄金 Case 套件
  - 对比 source 字段值
  - 对比 success / columns / rows / total / insight 字段值
```

### 6.5 Phase 2 完成的 Definition of Done **[v1.1 修订]**

- [ ] `McpExecutor` 已注册到 Gateway，优先级 0
- [ ] 三层路由模型完整实现：`_check_mcp_eligibility()`（Layer A）+ `tool_filter_node`（Layer B）+ `tool_select_node`（Layer C）
- [ ] Tool Registry 包含全部 15 个 Tool，含 domain 映射
- [ ] CircuitBreaker 正常工作（OPEN/CLOSED/HALF_OPEN），仅服务级故障计入
- [ ] `MCP_TOOL_SELECT_PROMPT` 格式化正确（Phase 2 单 Tool 选择）
- [ ] L1 单测 12+ 条通过（mock MCP Server + mock LLM）
- [ ] L2 Gateway 路由回退测试 10 条通过
- [ ] L3 E2E 7 条 MCP 场景通过（集成环境）
- [ ] Phase 1 黄金 Case 全部回归通过
- [ ] QueryPage / OrchestratorPage 行为不变
- [ ] `mcp_enabled=False` 时系统行为与 Phase 1 完全一致
- [ ] 所有 `source="mcp"` 的 UnifiedQueryResult 字段符合契约矩阵（4.2 节）

---

## 7. Phase 2 实施顺序

### Step 1: MCP Client 封装

| 项目 | 内容 |
|------|------|
| **改哪些文件** | 新增 `backend/app/core/mcp_client.py`（`WmsMcpClient` + `WmsMcpError` + `McpClientManager`） |
| **不改什么** | 不改 Gateway、不改任何现有模块 |
| **验收点** | `WmsMcpClient.call_tool()` mock 通过；`McpClientManager.is_available()` 缓存逻辑正确；`get_tool_descriptions()` 格式化输出可用 |
| **风险点** | `httpx` 依赖确认（已有）；API Key 为空时行为正确 |

### Step 2: MCP Config + Graph 骨架

| 项目 | 内容 |
|------|------|
| **改哪些文件** | `config.py`（新增 MCP 配置）；`agent_state.py`（新增 `MCPAgentState`）；新增 `graph_mcp.py`（3 节点 LangGraph 骨架，暂不接 LLM Tool 选择）；`prompts_sql.py`（新增 `MCP_TOOL_SELECT_PROMPT` 占位） |
| **不改什么** | Gateway 不动；graph_nl2sql 不动 |
| **验收点** | `graph_mcp.py` 可 import；`MCPAgentState` 结构正确；`MCP_TOOL_SELECT_PROMPT` 模板变量齐全 |
| **风险点** | `MCPAgentState` 字段设计需与 Phase 3 扩展兼容 |

### Step 3: McpExecutor + Gateway 接线

| 项目 | 内容 |
|------|------|
| **改哪些文件** | `data_query_gateway.py`（新增 `McpExecutor` 类、`CircuitBreaker` 内部类、`_is_mcp_candidate()` 规则方法、更新 `_register_executors()` 注册 McpExecutor(priority=0)、更新 `_execute_with_fallback()` 增加 CircuitBreaker 检查） |
| **不改什么** | LocalExecutor、QueryAgentExecutor、`_post_process()` 不动 |
| **验收点** | McpExecutor 可通过 mock 完成 tool_select → mcp_call → result_format → RawQueryResult；`_is_mcp_candidate("502620的库存")` → True；`_is_mcp_candidate("库存情况")` → False |
| **风险点** | `_is_mcp_candidate()` 规则覆盖不足 → 保守策略：不确定时返回 False（跳过 MCP） |

### Step 4: LLM Tool 选择实现

| 项目 | 内容 |
|------|------|
| **改哪些文件** | `graph_mcp.py`（实现 `tool_select_node`：DomainClassifier → 候选 Tool 过滤 → LLM 选择）；`prompts_sql.py`（完善 `MCP_TOOL_SELECT_PROMPT`） |
| **不改什么** | Gateway 的 McpExecutor 调用不变 |
| **验收点** | mock DomainClassifier + mock LLM → tool_select_node 返回正确 Tool 列表；LLM 返回 [] → 正确传播错误 |
| **风险点** | Prompt 质量直接影响 Tool 选择准确率 → 需要 E2E 调优 |

### Step 5: 测试与回归

| 项目 | 内容 |
|------|------|
| **改哪些文件** | 新增 `backend/tests/test_mcp_client.py`；新增 `backend/tests/test_mcp_gateway.py`；修改 `backend/tests/test_gateway.py`（如需） |
| **不改什么** | 不删除任何现有测试 |
| **验收点** | L1+L2 测试全部通过；L3 E2E 在有 MCP Server 的环境通过 |
| **风险点** | 集成环境依赖 MCP Server 可用 → staging 环境需提前部署 MCP Server |

---

## 附录 A: 与 Phase 0/1 设计的差异跟踪

| Phase 0 设计 | Phase 2 实际范围 | 差异说明 |
|-------------|----------------|---------|
| "MCP 接入包括 execute_sql_readonly" | Phase 2 仅预构建 Tool | MVP 范围收敛，execute_sql_readonly 仅作备选 |
| "完整 Tool 选择 + Clarification" | 仅 Tool 选择，无 Clarification | 澄清延后到 Phase 3 |
| "18 种 error_code" | 10 种 MCP 相关 error_code | Phase 3 统一 Error Taxonomy |
| "QueryAgent 准入 6 条件" | Phase 1 的 3 类排除 | 准入条件不在此阶段变化 |

## 附录 B: CircuitBreaker 设计（Gateway 内部）**[v1.1 修订]**

### B.1 核心结构

```text
class CircuitBreaker:
    state: "CLOSED" | "OPEN" | "HALF_OPEN"
    failure_count: int
    last_failure_time: float
    threshold: int = 3
    cooldown_seconds: float = 60.0

    def record_success(): ...
    def record_failure(): ...
    def allow_request() → bool: ...
```

### B.2 粒度: 全局 Breaker **[v1.1 新增]**

Phase 2 使用 **1 个全局 CircuitBreaker**（不是按 Tool 粒度）。

理由:
1. Phase 2 只接入 1 个 MCP Server（单一端点 `:8922/mcp`），所有 Tool 共享同一连接
2. MCP 不可用通常是**服务级故障**（进程挂了、网络不通），而非单个 Tool 故障
3. 全局 Breaker 实现简单，Phase 2 MVP 不需要 Tool 级粒度
4. Phase 3+ 如果需要区分"服务故障"和"Tool 特定故障"，可以升级为 per-Tool Breaker

### B.3 OPEN 状态时 Gateway 行为 **[v1.1 新增]**

当 CircuitBreaker 为 OPEN 时:

1. Gateway **直接跳过 McpExecutor**，走 LocalExecutor → QueryAgentExecutor
2. `UnifiedQueryResult.source` = `"local"`（不是 `"mcp"`）
3. 日志记录: `"MCP bypassed: circuit_breaker=OPEN, cooldown_remaining=Xs"`
4. 不尝试调用 MCP（节省超时等待时间）

**可观测性保障**: 即使 Breaker OPEN 导致 MCP 被绕过:
- 日志中记录 `mcp_bypassed_reason=circuit_open`
- `source` 字段反映实际执行器
- 可选: 暴露 `Gateway.get_circuit_state()` 供健康检查端点查询（Phase 4）

### B.4 哪些错误计入 Breaker **[v1.1 新增]**

| 错误类型 | 计入 Breaker? | 理由 |
|---------|:-----------:|------|
| `mcp_unavailable` (连接失败) | ✅ 是 | 服务级故障，需要熔断 |
| `mcp_timeout` (超时) | ✅ 是 | 服务级故障，可能过载 |
| `mcp_auth_error` (401/403) | ✅ 是 | 配置故障，持续重试无意义 |
| `mcp_tool_error` (内部异常) | ❌ **否** | 可能是单 Tool 特定问题，不应全局熔断 |
| `tool_selection_failed` | ❌ **否** | LLM 问题，与 MCP 服务无关 |
| `tool_validation_failed` | ❌ **否** | 参数问题，与 MCP 服务无关 |
| `unsupported_query` | ❌ **否** | 正常的"不适用"响应 |
| `no_data` | ❌ **否** | 正常结果，不是错误 |
| `sql_security_violation` | ❌ **否** | 安全拒绝，不应绕过 |
| `internal_error` | ⚠️ **弱计数** | 计为 0.5 次（两次 internal_error = 1 次失败） |

> **核心原则**: 只有**服务级故障**（network/availability/auth）才会计入 Breaker。业务级错误（参数/选择/不支持）不计入，因为 MCP 服务本身是健康的。

---

## 附录 C: Tool Registry — Phase 2 接入的 15 个 MCP Tool **[v1.1 新增]**

### C.1 库存域 (Inventory)

| Tool 名称 | 必填参数 | 允许缺参 | 返回类型 | Phase 2 | Fallback Expectation |
|----------|---------|:------:|:------:|:------:|---------------------|
| `query_inventory_by_sku` | `sku_code` | 可选: org_code, store_code, location_code, batch_no, limit | 明细表 | ✅ | 缺 SKU → 不回退, 应由 Layer A 拦截; 超时/不可用 → 回退 Local |
| `query_inventory_by_location` | `location_code` | 可选: org_code, store_code, limit | 明细表 | ✅ | 同上 |
| `query_inventory_by_batch` | `batch_no` | 可选: sku_code, org_code, store_code, limit | 明细表 | ✅ | 同上 |

### C.2 商品域 (Product)

| Tool 名称 | 必填参数 | 允许缺参 | 返回类型 | Phase 2 | Fallback Expectation |
|----------|---------|:------:|:------:|:------:|---------------------|
| `query_product` | 无 (至少一个可选) | 可选: sku_code, sku_name, bar_code, brand_code, cls_code | 明细表 | ✅ | 全缺参 → 正常(返回全部商品, 有 LIMIT); 超时/不可用 → 回退 Local |
| `query_product_spec` | `sku_code` | 可选: limit, offset | 明细表(笛卡尔积) | ✅ | 缺 SKU → Layer A 拦截; 超时 → 回退 Local |
| `query_product_warehouse_config` | `sku_code` | 可选: org_code, log_area_code | 明细表 | ✅ | 同上 |

### C.3 入库域 (Inbound)

| Tool 名称 | 必填参数 | 允许缺参 | 返回类型 | Phase 2 | Fallback Expectation |
|----------|---------|:------:|:------:|:------:|---------------------|
| `query_inbound_order` | 无 (至少一个可选) | 可选: bill_no, org_code, store_code, supplier_code, date_from, date_to, bill_type, status | 明细表 | ✅ | 无时间范围 → Layer A 应标记 eligible=false; 超时 → 回退 Local |
| `query_inbound_detail` | `bill_no` | 可选: limit, offset | 明细表 | ✅ | 缺单号 → Layer A 拦截 |
| `query_receiving_record` | 无 (全可选) | 可选: org_code, store_code, supplier_code, date_from, date_to, status | 明细表 | ✅ | 无时间范围 → Layer A 标记 eligible=false |

### C.4 出库域 (Outbound)

| Tool 名称 | 必填参数 | 允许缺参 | 返回类型 | Phase 2 | Fallback Expectation |
|----------|---------|:------:|:------:|:------:|---------------------|
| `query_outbound_order` | 无 (至少一个可选) | 可选: bill_no, org_code, store_code, shop_code, date_from, date_to, wave_code, out_ware_type | 明细表 | ✅ | 无时间范围 → eligible=false |
| `query_outbound_detail` | `bill_no` | 可选: limit, offset | 明细表 | ✅ | 缺单号 → Layer A 拦截 |

### C.5 分析域 (Analytics)

| Tool 名称 | 必填参数 | 允许缺参 | 返回类型 | Phase 2 | Fallback Expectation |
|----------|---------|:------:|:------:|:------:|---------------------|
| `get_inventory_summary` | 无 (全可选) | 可选: store_code, log_area_code, limit, offset | 汇总表 | ✅ | 超时 → 回退 Local; 缺参时返回全量汇总(有 LIMIT) |
| `get_stock_warning` | 无 | 可选: warning_type, low_stock_threshold, near_expiry_days, limit | 汇总表 | ✅ | 超时 → 回退 Local |
| `get_slow_moving_inventory` | 无 | 可选: dormant_days, limit, offset | 明细表 | ✅ | 超时 → 回退 Local |
| `query_stock_flow` | 无 (全可选) | 可选: sku_code, store_code, date_from, date_to, limit, offset | 流水表 | ✅ | 无时间+无SKU → eligible=false (数据量巨大) |

### C.6 Fallback Expectation 速查

| 失败原因 | 处理 |
|---------|------|
| Tool 不支持该场景 (unsupported_query) | → 回退 Local |
| 必填参数缺失 (missing_required_param) | → **Phase 2: 不回退**, 直接返回错误。Phase 3 转为 clarification |
| 可选参数缺失 (missing_optional_param) | → 正常调用(使用 MCP 默认值) |
| MCP 超时 / 不可用 (mcp_timeout / mcp_unavailable) | → 回退 Local |
| MCP 认证失败 (mcp_auth_error) | → 回退 Local (首次) + 记录 ERROR |
| MCP Tool 内部错误 (mcp_tool_error) | → 回退 Local |
| 无数据 (no_data) | → 正常返回,不回退 |
| SQL 安全拒绝 (sql_security_violation) | → **禁止回退**,直接返回错误 |

---

> **文档版本**: v1.1
> **设计完成时间**: 2026-06-24
> **修订记录**: v1.0 → v1.1: 新增 MCP 路由三层模型、收紧单Tool调用、CircuitBreaker 细化、指标精确定义、Tool Registry、字段契约矩阵
> **设计完成时间**: 2026-06-24
> **关联文档**:
> - `docs/superpowers/plans/2026-06-24-mcp-migration-analysis.md`
> - `docs/superpowers/plans/2026-06-24-data-query-convergence-design.md`
> - `docs/superpowers/plans/2026-06-24-gateway-phase0-design.md`
> - `docs/superpowers/plans/2026-06-24-phase1-implementation-plan.md`
> - `docs/superpowers/plans/2026-06-24-phase1.5-acceptance-report.md`
> - `docs/data-copilot-integration-guide.md`
> **下一步**: 审核设计，确认后按 Step 1~5 进入编码
