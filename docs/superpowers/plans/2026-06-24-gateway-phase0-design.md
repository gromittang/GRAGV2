# DataQueryGateway 实施约束与 Phase 0 设计补充

> **状态**: 冻结设计 — 下一轮开发任务书
> **基线文档**:
> - `docs/superpowers/plans/2026-06-24-mcp-migration-analysis.md` (迁移分析)
> - `docs/superpowers/plans/2026-06-24-data-query-convergence-design.md` (收敛设计)
> **约束**: 不写代码，不进入实现，只输出可执行的冻结设计

---

## 1. Gateway 最终职责定义

### 1.1 它负责什么

| # | 职责 | 说明 |
|---|------|------|
| R1 | **唯一入口** | 所有数据查询请求（来自 QueryPage API / Orchestrator / 未来任何调用方）都经过 `DataQueryGateway.execute(question, session_id)` |
| R2 | **澄清判断** | 在调用任何 Executor 之前，判断问题是否需要先追问用户。如果需要，直接返回 `clarification_needed=true`，不执行查询 |
| R3 | **执行器选择** | 根据 MCP 可用性 + 问题类型 + CircuitBreaker 状态，选择 Executor（MCP / Local / QueryAgent） |
| R4 | **回退编排** | Executor 失败时，按规则决定是回退到下一级还是 fail-fast。回退规则见第 7 节 |
| R5 | **CircuitBreaker** | 管理 MCP 的熔断状态（CLOSED → OPEN → HALF_OPEN），内聚在 Gateway 内部，不暴露为独立模块 |
| R6 | **结果统一** | 将所有 Executor 的返回统一为 `UnifiedQueryResult`。包含字段翻译（英→中）、source 标记 |
| R7 | **后处理** | 调用 `_translate_columns()`、`_save_history()`、`_generate_insight()`（如果 Executor 未返回） |
| R8 | **可观测** | 创建 Trace span、记录 latency、记录 source 和 error_code（见第 7 节） |

### 1.2 它不负责什么

| # | 不负责 | 交给谁 |
|---|--------|--------|
| ~R1 | SQL 生成 | Executor 内部（Local Executor 的 graph_nl2sql 节点 / MCP Server） |
| ~R2 | Schema 发现 | SchemaManager（被 Local Executor 使用）/ MCP Tool 描述（被 MCP Executor 使用） |
| ~R3 | SQL 执行 | Executor 内部（MySQL 直连 / MCP Server） |
| ~R4 | 意图路由 | Orchestrator Router — Gateway 只处理已确定为 `data_query` 的请求 |
| ~R5 | RAG / PM / Chat | 各自的模块，Gateway 不感知 |
| ~R6 | 用户会话管理 | API 层 / 前端 |
| ~R7 | LLM 调用细节 | LLMManager（被 Executor 使用） |

### 1.3 与周边模块的关系

```
Orchestrator (Router)
  │ intent=data_query
  ▼
Orchestrator API ──► DataQueryGateway.execute(question) ◄── QueryPage API
                             │
                             │ 内部调用
                             ▼
                    ┌─────────────────┐
                    │ Executor Chain  │
                    │ (Gateway 内部)  │
                    └─────────────────┘
                             │
                    ┌────────┼────────┐
                    ▼        ▼        ▼
                 MCP      Local   QueryAgent
                 Exec     Exec     Exec

QueryService → 退化为 API 层的薄适配器:
  natural_query(question) → gateway.execute(question) → 格式化 HTTP Response

Orchestrator dispatch:
  dispatch_to_nl2sql → 删除
  Planner 的 nl2sql step → 改为调用 gateway.execute()
```

---

## 2. 统一结果模型设计

### 2.1 UnifiedQueryResult 字段定义

```text
UnifiedQueryResult {
    // ── 状态 ──
    success: bool
    //    true  = 查询成功返回数据
    //    false = 出现不可恢复的错误

    // ── 路由信息 ──
    source: "mcp" | "local" | "queryagent"
    //    实际执行查询的 Executor。前端用此展示路由来源标记
    //    消费方: 前端UI, 可观测/Trace, 测试断言

    query_mode: "tool" | "sql" | "fallback"
    //    tool     = MCP 预构建 Tool（无需生成 SQL）
    //    sql      = 通过 execute_sql_readonly 或本地 SQL 生成执行
    //    fallback = QueryAgent 旧管线
    //    消费方: 可观测（分析 MCP 覆盖率）, 测试

    // ── 输入 ──
    question: str
    //    用户原始输入，原样保留
    //    消费方: 查询历史, 反馈系统

    normalized_question: str | null
    //    经过标准化的问题（实体提取、时间规范化后的版本）
    //    如果 Gateway 进行了澄清判断后的问题重写，此处记录
    //    消费方: 查询历史, 调试

    // ── 查询结果 ──
    sql: str | null
    //    实际执行的 SQL 语句。预构建 Tool 模式时可以是 MCP Tool 的描述
    //    消费方: 前端 SqlDisplay, 查询历史, 测试/Eval

    tool_calls: list[ToolCall] | null
    //    MCP 模式下记录调用了哪些 Tool 及参数
    //    ToolCall = {tool_name: str, arguments: dict}
    //    消费方: 可观测, 调试, 测试/Eval

    columns: list[str]
    //    返回数据的列名列表（已翻译为中文）
    //    消费方: 前端 ResultTable, 导出

    rows: list[list[any]]
    //    数据行，二维数组
    //    消费方: 前端 ResultTable, 导出, Insight 生成

    total: int
    //    实际返回行数
    //    消费方: 前端展示, 查询历史

    // ── 洞察 ──
    insight: Insight | null
    //    Insight = {summary: str, insights: list[str], follow_ups: list[str]}
    //    消费方: 前端 InsightCard, 查询历史

    // ── 置信度 ──
    confidence: float | null
    //    0.0 ~ 1.0。SQL 生成的自信度 或 Tool 选择的匹配置信度
    //    消费方: 前端展示（可选）, Eval

    // ── 澄清 ──
    clarification_needed: bool
    //    true = 问题不明确，需要用户补充信息后才能执行
    //    此时除 clarification_question 外其他字段可能为空
    //    消费方: 前端（展示追问）、Orchestrator（可能需要重路由）

    clarification_question: str | null
    //    对用户的追问文本，如 "请问您要查询哪个商品编码的库存？"
    //    消费方: 前端 UI

    // ── 错误 ──
    error_code: str | null
    //    统一错误码，见第 7 节 Error Taxonomy
    //    消费方: 前端错误提示, 可观测, 告警

    error_message: str | null
    //    面向用户的中文错误描述
    //    消费方: 前端错误提示

    // ── 可观测 ──
    trace_id: str
    //    Trace ID，关联到 tracing.py 的 span
    //    消费方: 日志, Trace 查询, 调试

    latency_ms: float
    //    端到端耗时（Gateway 入口到出口）
    //    消费方: 可观测, 性能监控, Eval
}
```

### 2.2 字段依赖矩阵

| 字段 | 前端 | 查询历史 | Eval/测试 | 可观测 | 导出 |
|------|:---:|:-------:|:--------:|:-----:|:---:|
| `success` | ✅ | ✅ | ✅ | ✅ | - |
| `source` | ✅ | ✅ | ✅ | ✅ | - |
| `query_mode` | - | ✅ | ✅ | ✅ | - |
| `question` | - | ✅ | - | - | - |
| `normalized_question` | - | ✅ | ✅ | ✅ | - |
| `sql` | ✅ | ✅ | ✅ | - | - |
| `tool_calls` | - | - | ✅ | ✅ | - |
| `columns` | ✅ | ✅ | ✅ | - | ✅ |
| `rows` | ✅ | - | ✅ | - | ✅ |
| `total` | ✅ | ✅ | - | - | - |
| `insight` | ✅ | ✅ | - | - | - |
| `confidence` | ✅(可选) | ✅ | ✅ | - | - |
| `clarification_needed` | ✅ | - | - | ✅ | - |
| `clarification_question` | ✅ | - | - | - | - |
| `error_code` | ✅ | ✅ | ✅ | ✅ | - |
| `error_message` | ✅ | ✅ | - | - | - |
| `trace_id` | - | - | ✅ | ✅ | - |
| `latency_ms` | - | - | ✅ | ✅ | - |

---

## 3. 执行器接口设计

### 3.1 Executor 统一接口

所有 Executor 必须实现同一接口：

```text
interface DataQueryExecutor {
    // 标识
    name: str                          // "mcp" | "local" | "queryagent"
    priority: int                      // 0=最高, 数字越大优先级越低

    // 查询执行
    async execute(question: str, context: QueryContext) → RawQueryResult

    // 可用性检查
    async is_available() → bool

    // 能力声明
    supports_clarification() → bool    // 该 Executor 是否能返回 clarification
    supports_tool_mode() → bool        // 是否能走预构建 Tool（只有 MCP 支持）
}
```

### 3.2 QueryContext（Gateway 传给 Executor 的上下文）

```text
QueryContext {
    question: str                 // 原始问题
    normalized_question: str|null // Gateway 标准化后的问题（如有）
    session_id: str|null          // 会话 ID（用于 trace）
    domain_hint: str|null         // DomainClassifier 的分类结果（辅助信号）
    force_tables: list[str]|null  // HARD_RULES 匹配的强制表
    max_tools: int                // 最大 Tool 调用数，默认 3
}
```

### 3.3 RawQueryResult（Executor 返回给 Gateway 的原始结果）

```text
RawQueryResult {
    success: bool
    source: str                       // Executor 的 name
    query_mode: "tool"|"sql"|"fallback"

    // 数据
    columns: list[str]                // 英文原始列名
    rows: list[list[any]]
    total: int

    // 元信息
    sql: str|null
    tool_calls: list[ToolCall]|null
    confidence: float|null
    insight: Insight|null

    // 澄清
    clarification_needed: bool
    clarification_question: str|null

    // 错误
    error_code: str|null
    error_message: str|null
    is_retryable: bool               // Gateway 是否应回退到下一级 Executor

    // 耗时
    latency_ms: float
}
```

### 3.4 各 Executor 详细设计

#### 3.4.1 McpExecutor

| 属性 | 值 |
|------|-----|
| **name** | `"mcp"` |
| **priority** | `0` |
| **内部实现** | `graph_mcp.py`（LangGraph: tool_select → mcp_call → result_format） |
| **依赖** | `McpClientManager`, `WmsMcpClient`, LLM (Tool 选择) |
| **supports_clarification** | `false` — MCP 不判断澄清，由 Gateway 前置处理 |
| **supports_tool_mode** | `true` |

**输入**: `QueryContext`，其中 `domain_hint` 和 `force_tables` 作为 LLM Tool 选择的辅助信号。

**执行流程**:
1. `tool_select_node`: LLM 根据 `MCP_TOOL_SELECT_PROMPT` + Tool 列表 + `domain_hint` + `force_tables` 选择 Tool + 填参数
2. `mcp_call_node`: 并行调用选中的 MCP Tools
3. `result_format_node`: 将 MCP 的 `items` 格式转为 `{columns, rows, total}`

**失败处理**:
- MCP 连接失败 → `is_retryable=true` → Gateway 回退到 LocalExecutor
- Tool 选择失败（LLM 未选出任何 Tool）→ `is_retryable=false, clarification_needed=true` → Gateway 返回澄清
- Tool 调用返回空 → `success=true, total=0`（空数据不是错误）
- MCP 返回 VALIDATION_ERROR → `is_retryable=false` → Gateway 返回错误给用户

**适配器角色**: `graph_mcp.py` 只是 McpExecutor 的内部实现细节。Gateway 不直接依赖 graph_mcp — 通过 Executor 接口调用。

#### 3.4.2 LocalExecutor

| 属性 | 值 |
|------|-----|
| **name** | `"local"` |
| **priority** | `1` |
| **内部实现** | `graph_nl2sql.py`（LangGraph: domain_classify → schema_search → sql_generate → sql_validate → sql_execute → insight_generate） |
| **依赖** | `SchemaManager`, `DomainClassifier`, `MySQLManager`, `SemanticRules`, `SQLPostProcess`, LLM |
| **supports_clarification** | `true` — `sql_generate_node` 可以返回 `NEED_CLARIFICATION` |
| **supports_tool_mode** | `false` |

**输入**: `QueryContext`，其中 `domain_hint` 和 `force_tables` 直接注入 schema_search_node。

**执行流程**: 现有 6 节点 LangGraph 管线，保持不变。改动仅限于：
- 添加 `clarification_needed` 检查（`sql_generate_node` 已支持 `NEED_CLARIFICATION`，需要正确传递到 RawQueryResult）
- 确保 `is_retryable` 正确设置

**失败处理**:
- Schema 搜索无结果 → `is_retryable=true`（可回退到 QueryAgent）
- SQL 生成返回 `NEED_CLARIFICATION` → `clarification_needed=true, is_retryable=false` → Gateway 返回澄清
- SQL 验证失败 → `is_retryable=false` → Gateway 返回错误
- SQL 执行失败 → `is_retryable=true`（可回退到 QueryAgent 尝试）
- 全部成功但 `total=0` → `success=true`，由 Gateway 判断是否需要 clarification

**适配器角色**: 同 McpExecutor。`graph_nl2sql.py` 保留现有实现，Gateway 通过 Executor 接口调用。不需要为 Gateway 修改 graph_nl2sql 的内部逻辑。

#### 3.4.3 QueryAgentExecutor

| 属性 | 值 |
|------|-----|
| **name** | `"queryagent"` |
| **priority** | `2` |
| **内部实现** | `query_agent.py`（旧版 5 步硬编码管线） |
| **依赖** | 同 LocalExecutor |
| **supports_clarification** | `true`（同 LocalExecutor 的 NEED_CLARIFICATION 检查） |
| **supports_tool_mode** | `false` |
| **状态** | ⚠️ `@deprecated` — 计划 2 个 release 后删除 |

**输入**: 同 LocalExecutor。

**与 LocalExecutor 的区别**:
- 不依赖 LangGraph 库（无 graph 编译、无 checkpoint）
- 硬编码顺序执行（无图的条件边）
- 功能等价，但代码结构不同

**准入条件**: 见第 5 节。**QueryAgent 不是无条件兜底**。

---

## 4. Gateway 执行策略决策表

### 4.1 核心决策矩阵

Gateway 在调用 Executor 之前先做两件事：(A) 判断是否需要澄清 (B) 选择合适的 Executor。

| 问题类型 | 示例 | 澄清判断 | MCP 路径 | Local 路径 | QueryAgent | Fail-fast |
|---------|------|:-------:|:--------:|:----------:|:---------:|:---------:|
| **明确实体 + 预构建 Tool** | "502620 的库存情况" | 不需要 | ✅ 首选 | ✅ MCP 不可用时 | ❌ | - |
| **明确实体 + 预警分析** | "有没有快过期的商品" | 不需要 | ✅ 首选 | ✅ MCP 不可用时 | ❌ | - |
| **明确实体 + 跨表复杂查询** | "上月出库超过 1000 件的商品的供应商" | 不需要 | ✅ execute_sql_readonly | ✅ MCP 不可用时 | ❌ | - |
| **实体缺失** | "库存情况"（不知道查哪个 SKU） | **必须澄清** | - | - | - | ✅ 直接返回澄清 |
| **时间范围缺失且必要** | "出库记录"（没有时间范围，数据量巨大） | **必须澄清** | - | - | - | ✅ 直接返回澄清 |
| **实体模糊** | "那个货还有多少" | **必须澄清** | - | - | - | ✅ 直接返回澄清 |
| **粒度不明确** | "各仓库库存"（按 SKU? 按品类?） | **建议澄清** | 可尝试 | 可尝试 | ❌ | - |
| **指标不明确但有默认** | "商品 502620"（默认查库存） | 不需要 | ✅ 默认 Tool | ✅ 默认 schema | ❌ | - |
| **纯闲聊/问候** | "你好" | - | - | - | - | ✅ 返回提示 |
| **超出数据范围** | "这个商品的利润是多少"（无利润字段） | **建议澄清** | 尝试→失败→返回澄清 | 尝试→失败→返回澄清 | ❌ | - |

### 4.2 决策流程

```
Gateway.execute(question)
  │
  ├── [Step 0] 快速检查
  │     • 纯闲聊? → success=false, error_code="not_a_query"
  │     • 空字符串? → clarification_needed=true
  │
  ├── [Step 1] 澄清判断 (见第 6 节 Clarification Policy)
  │     ├── 必须澄清 (missing_entity / missing_timerange / ambiguous_entity)
  │     │   → 直接返回 clarification_needed=true
  │     │   → 不调用任何 Executor
  │     │
  │     ├── 建议澄清 (unclear_granularity / unclear_metric)
  │     │   → 继续执行，但在结果中附加 clarification_hint
  │     │
  │     └── 不需要澄清 → 继续 [Step 2]
  │
  ├── [Step 2] 选择 Executor
  │     ├── MCP CircuitBreaker CLOSED/HALF_OPEN
  │     │   → 选择 McpExecutor
  │     │   → 成功 → 跳到 [Step 4]
  │     │   → 失败 + is_retryable=true → 继续尝试 LocalExecutor
  │     │   → 失败 + is_retryable=false → 跳到 [Step 4] 返回结果
  │     │
  │     └── MCP CircuitBreaker OPEN
  │         → 跳过 MCP，选择 LocalExecutor
  │         → 成功 → 跳到 [Step 4]
  │         → 失败 + is_retryable=true → 继续 [Step 3]
  │         → 失败 + is_retryable=false → 跳到 [Step 4] 返回结果
  │
  ├── [Step 3] QueryAgent 准入判断 (见第 5 节)
  │     ├── 满足准入条件 → 调用 QueryAgentExecutor
  │     │   → 任意结果 → 跳到 [Step 4]
  │     │
  │     └── 不满足准入条件
  │         → success=false, error_code="all_executors_failed"
  │         → 如果适用: clarification_needed=true
  │
  └── [Step 4] 后处理 + 返回 UnifiedQueryResult
        • _translate_columns()
        • _save_history()
        • _generate_insight() (如果未返回)
        • 附加 trace_id, latency_ms
```

---

## 5. QueryAgent 的准入条件

### 5.1 设计原则

> **QueryAgent 不是"自动最后一级回退"，而是"受限兜底执行器"。**
> 它在特定条件下才被允许接管。不满足条件时，Gateway 返回错误或澄清，而不是回退到 QueryAgent。

### 5.2 允许 QueryAgent 处理的场景

| # | 场景 | 判定逻辑 |
|---|------|---------|
| A1 | **基础设施故障** | MCP CircuitBreaker OPEN **且** LocalExecutor 抛出基础设施异常（MySQL 连接失败、LLM API 不可用） |
| A2 | **LangGraph 运行时错误** | LocalExecutor 因 LangGraph 编译/序列化异常而失败（不是业务逻辑错误） |
| A3 | **明确查询 + 前两级意外失败** | 问题通过了 Step 1 澄清判断（问题本身是明确的），但 MCP 和 Local 都因非业务原因失败 |

### 5.3 不允许 QueryAgent 处理的场景

| # | 场景 | 替代处理 |
|---|------|---------|
| D1 | **问题需要澄清** | 直接返回 clarification，不回退到任何 Executor |
| D2 | **SQL 安全违规** | 返回 `error_code="sql_security_violation"`，不回退 |
| D3 | **MCP 和 Local 都返回 `no_data`** | 返回 `success=true, total=0` + clarification_hint（不是错误，不需要回退） |
| D4 | **连续 2 次 QueryAgent 也失败**（同一 session 内） | 该 session 禁用 QueryAgent，返回错误 + 建议联系管理员 |

### 5.4 准入判定规则（Gateway 内部实现）

```text
function can_use_queryagent(question, mcp_result, local_result, session_stats) → bool:

    // 条件 1: 问题必须是明确的（通过了 Step 1 澄清判断）
    if clarification_was_needed(question):
        return false

    // 条件 2: 前两级都尝试过且失败
    if mcp_result is not None and mcp_result.success:
        return false  // MCP 成功了，不需要
    if local_result is not None and local_result.success:
        return false  // Local 成功了，不需要

    // 条件 3: 不是"无数据"情况（那是正常结果，不是失败）
    if is_no_data_result(local_result) or is_no_data_result(mcp_result):
        return false

    // 条件 4: 不是安全违规
    if is_security_violation(local_result) or is_security_violation(mcp_result):
        return false

    // 条件 5: 失败原因是基础设施问题（不是业务逻辑问题）
    if not is_infrastructure_error(local_result) and not is_infrastructure_error(mcp_result):
        return false  // 业务逻辑错误重试也不会好

    // 条件 6: 当前 session 没有过度使用 QueryAgent
    if session_stats.queryagent_failures >= 2:
        return false

    return true
```

**关键**: `is_infrastructure_error()` 判断 error_code 是否属于 `db_connection_failed` / `llm_api_error` / `langgraph_error` / `mcp_unavailable`。SQL 语法错误、schema 不匹配等业务错误不会触发回退到 QueryAgent。

---

## 6. Clarification Policy

### 6.1 设计原则

> **模糊问题先追问，不要硬查。** 硬查的结果即使能执行，SQL 也可能是不合理的（如全表扫描、缺少时间过滤），造成性能问题和错误数据。

### 6.2 必须澄清的维度

| 维度 | 缺失判定 | 追问模板 |
|------|---------|---------|
| **实体 (entity)** | 问题中没有可识别的 SKU 编码、商品名、订单号、供应商等实体 | "请问您要查询哪个商品/订单/供应商？请提供编码或名称。" |
| **时间范围 (timerange)** | 查询可能返回大量数据但未指定时间范围（如"出库记录"），且数据量预估 > 1000 行 | "请问您要查询哪个时间范围的记录？（如：最近 7 天、上个月）" |
| **仓库/组织 (scope)** | 系统有多个仓库/组织，但问题未指定 | "请问要查询哪个仓库的数据？（良品仓 / 不良品仓 / 全部）" |

### 6.3 建议澄清的维度

| 维度 | 缺失判定 | 处理方式 |
|------|---------|---------|
| **粒度 (granularity)** | "各仓库库存" — 不清楚按什么粒度（SKU/品类/库位） | 执行默认粒度 + 结果中附加 `clarification_hint` |
| **指标 (metric)** | "看一下 502620" — 不知道看库存/出库/基本信息 | 执行默认（库存）+ 结果中附加 `clarification_hint` |

### 6.4 Clarification 返回结构

```text
// 在 UnifiedQueryResult 中:
{
    success: false,                     // 未执行查询
    clarification_needed: true,
    clarification_question: str,        // 面向用户的中文追问
    clarification_dimensions: [         // 缺失的具体维度
        {
            dimension: "entity" | "timerange" | "scope" | "granularity" | "metric",
            missing: true,
            hint: str | null,           // 可选的填写提示
            options: list[str] | null   // 可选的选项（如仓库列表）
        }
    ],
    suggested_question: str | null,     // 补全后的建议问题（方便用户一键确认）
    error_code: "clarification_required",
    trace_id: str
}
```

### 6.5 澄清判断的实现位置

澄清判断分为两个层次：

| 层次 | 位置 | 方法 | 能力 |
|------|------|------|------|
| **L1: 规则层** | Gateway 内部 | 关键词 + 实体识别正则 + 数据量估算 | 必须澄清的硬性缺失（无实体、无时间范围） |
| **L2: Executor 层** | Executor 内部 | LLM 判断（`NEED_CLARIFICATION`） | 语义层面的模糊（SQL 生成时发现歧义） |

Gateway 先做 L1 判断。如果通过 L1，Executor 在执行过程中可能返回 L2 澄清。最终的 `clarification_needed` 是 L1 || L2。

---

## 7. 错误模型与回退规则

### 7.1 Error Taxonomy

```text
error_code 分类:

── 客户端错误（4xx 语义，用户可修复）
│
├── clarification_required      # 问题不明确，需要追问
│      回退: ❌ 不允许回退
│      返回: 直接返回澄清给用户
│
├── sql_security_violation      # SQL 包含被禁操作
│      回退: ❌ 不允许回退（安全问题不应通过换 Executor 绕过）
│      返回: 直接返回错误给用户
│
├── invalid_parameters          # 查询参数不合法（如 SKU 格式不对）
│      回退: ❌ 不允许回退
│      返回: 直接返回错误给用户
│
├── no_data                     # 查询执行成功但没有匹配数据
│      回退: ❌ 这不是错误，不需要回退
│      返回: success=true, total=0 + 可选 clarification_hint
│
│
── 服务端错误（5xx 语义，系统问题）
│
├── mcp_unavailable             # MCP Server 连接失败 / ping 失败
│      回退: ✅ 允许回退到 LocalExecutor
│      触发 CircuitBreaker: 是
│
├── mcp_auth_error              # MCP 认证失败 (401/403)
│      回退: ✅ 允许回退到 LocalExecutor（首次）
│      触发 CircuitBreaker: 是（连续 3 次 auth error = OPEN）
│      告警: 需要人工处理
│
├── mcp_timeout                 # MCP 调用超时
│      回退: ✅ 允许回退到 LocalExecutor
│      触发 CircuitBreaker: 是
│
├── mcp_tool_error              # MCP Tool 执行错误（参数正确但 Tool 内部异常）
│      回退: ✅ 允许回退到 LocalExecutor（尝试本地生成 SQL）
│      触发 CircuitBreaker: 否（Tool 错误不代表服务不可用）
│
├── db_connection_failed        # MySQL 连接失败
│      回退: ✅ 允许回退到 QueryAgent（如果满足准入条件）
│      注意: MCP 和 Local 共享同一个 MySQL → MCP 失败后 Local 也可能失败
│
├── llm_api_error               # LLM API 不可用
│      回退: ✅ 允许回退到 QueryAgent（如果满足准入条件）
│
├── langgraph_error             # LangGraph 运行时错误（编译、序列化）
│      回退: ✅ 允许回退到 QueryAgent（QueryAgent 不依赖 LangGraph）
│
├── sql_execution_error         # SQL 语法错误或执行错误
│      回退: ⚠️ 仅允许回退一次（MCP 的 SQL 出错 → 尝试 Local 重新生成 SQL）
│      Local 也失败 → fail-fast
│
├── schema_not_found            # 无法找到匹配的表/字段
│      回退: ⚠️ 允许回退一次
│      两次都找不到 → clarification_needed=true
│
├── tool_selection_failed       # LLM 无法选择合适的 MCP Tool
│      回退: ✅ 允许回退到 LocalExecutor（发挥其 SQL 生成能力）
│
├── all_executors_failed        # 所有 Executor 都失败
│      回退: ❌ 无更多回退选项
│      返回: success=false + 建议联系管理员
│
├── internal_error              # 未分类的内部错误
│      回退: ⚠️ 允许回退一次（可能是偶发问题）
│      两次都 internal_error → fail-fast
```

### 7.2 回退规则总结

| 规则 | 说明 |
|------|------|
| **安全错误不回退** | `sql_security_violation` 在任何 Executor 触发后，不尝试其他 Executor |
| **澄清错误不回退** | `clarification_required` → 直接返回用户，不尝试执行 |
| **授权错误触发告警 + 回退** | `mcp_auth_error` 自动回退到 Local，但需要后台告警 |
| **空数据不是错误** | `no_data` → `success=true`，不触发回退 |
| **同类型失败不回退** | MCP 因 `db_connection_failed` 失败 → Local 大概率也因同样原因失败 → 直接 fail-fast，不浪费时间 |
| **最多 2 级回退** | MCP → Local → QueryAgent（如果准入），不允许更深的链 |

---

## 8. Phase 1 ~ Phase 4 实施范围与验收标准

### Phase 1: Gateway 骨架 + 本地路径收敛

**目标**: 建立 DataQueryGateway 作为唯一入口，统一现有两条路径（QueryService + dispatch），替换 `use_langgraph` flag。**不接入 MCP。**

**修改模块**:

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/core/data_query_gateway.py` | **新增** | Gateway 骨架：Executor 接口、LocalExecutor、QueryAgentExecutor、`execute()` 方法、后处理 |
| `backend/app/services/query_service.py` | **修改** | `natural_query()` 退化为 `gateway.execute(question)` 的薄封装；删除 `_query_via_langgraph()` 和 `agent.query()` 直调 |
| `backend/app/orchestrator/dispatch.py` | **修改** | 删除 `dispatch_to_nl2sql`；Planner 的 nl2sql step 改为调用 Gateway |
| `backend/app/core/config.py` | **修改** | 删除 `use_langgraph` flag |
| `backend/app/agents/query_agent.py` | **修改** | 添加 `@deprecated` 标记；保持功能不变 |

**明确不做什么**:
- ❌ 不新建 `graph_mcp.py`
- ❌ 不新建 `core/mcp_client.py`
- ❌ 不实现 CircuitBreaker（MCP 还没接入）
- ❌ 不实现 Clarification Policy（Phase 3）
- ❌ 不修改 QueryAgent 内部逻辑（只加 deprecated 标记）

**验收标准**:
- [ ] `DataQueryGateway.execute(question)` 可被 QueryPage API 和 Orchestrator 调用
- [ ] QueryPage 和 OrchestratorPage 查询行为与修改前完全一致
- [ ] `use_langgraph` flag 已删除，Gateway 内部通过 Executor 优先级决定路径
- [ ] `dispatch_to_nl2sql` 已从 `dispatch.py` 移除
- [ ] 现有测试 `test_orchestrator_router.py` 通过
- [ ] 现有测试 `test_orchestrator_l2.py` 通过
- [ ] L2 测试能验证 LocalExecutor + QueryAgentExecutor 回退链（mock 失败场景）
- [ ] 返回结构符合 `UnifiedQueryResult` 规范

**风险点**:
- `dispatch_to_nl2sql` 移除影响 Planner 的 nl2sql step → 需确认 Planner 调用方式
- `_translate_columns()` 和 `_save_history()` 迁移到 Gateway 后需保持行为一致

---

### Phase 2: MCP MVP 接入

**目标**: MCP Executor 接入，成为主路径；实现 CircuitBreaker。

**修改模块**:

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/core/mcp_client.py` | **新增** | `WmsMcpClient` + `McpClientManager`（复用 MCP Guide 第 4 节） |
| `backend/app/agents/graph_mcp.py` | **新增** | McpExecutor 的 LangGraph 实现 |
| `backend/app/core/data_query_gateway.py` | **修改** | 注册 McpExecutor（优先级 0）、实现 CircuitBreaker、更新决策逻辑 |
| `backend/app/agents/prompts_sql.py` | **修改** | 新增 `MCP_TOOL_SELECT_PROMPT` |
| `backend/app/core/config.py` | **修改** | 新增 `mcp_enabled`, `mcp_base_url`, `mcp_api_key`, `mcp_timeout` |
| `.env.example` | **修改** | 新增 MCP 环境变量 |

**明确不做什么**:
- ❌ 不实现 Clarification Policy（Phase 3）
- ❌ 不实现 QueryAgent 准入控制（Phase 3，当前无条件回退）
- ❌ 不修改前端

**验收标准**:
- [ ] MCP Server 可用时，查询走 McpExecutor
- [ ] MCP Server 不可用时，自动回退到 LocalExecutor
- [ ] CircuitBreaker: 连续 3 次 MCP 失败 → OPEN，60s 后 → HALF_OPEN
- [ ] MCP Tool 选择准确率 ≥ 70%（基于 `mcp_queries.json` eval）
- [ ] McpExecutor 返回的 `RawQueryResult` 经 Gateway 后处理正确（字段翻译、source 标记）
- [ ] MCP 调用有 Trace span（`mcp.call_tool.{tool_name}`）
- [ ] 配置 `mcp_enabled=False` 时跳过 MCP，直接走 LocalExecutor

**风险点**:
- MCP Server 可能尚未部署 → 需本地 mock 或 staging 环境
- `MCP_TOOL_SELECT_PROMPT` 需要调优 → 预留 prompt 迭代窗口
- MCP Tool 返回的英文字段名翻译 → 依赖 SchemaManager 的 column_display_map

---

### Phase 3: Clarification + QueryAgent 准入 + 错误策略

**目标**: 实现完整的澄清判断、QueryAgent 受限准入、精细化错误处理。

**修改模块**:

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/core/data_query_gateway.py` | **修改** | 实现 `_check_clarification()`（L1 规则层）、`_can_use_queryagent()`、`_classify_error()`、更新 `_execute_with_fallback()` |
| `backend/app/agents/graph_nl2sql.py` | **修改** | 确保 `NEED_CLARIFICATION` 正确映射到 `RawQueryResult.clarification_needed` |
| `backend/app/agents/graph_mcp.py` | **修改** | LLM 未选出 Tool 时返回 `clarification_needed=true` |
| `backend/app/core/agent_state.py` | **修改** | `QueryAgentState` / `MCPAgentState` 增加 clarification 相关字段 |

**明确不做什么**:
- ❌ 不修改前端（直到 Phase 4）
- ❌ 不删除 QueryAgent

**验收标准**:
- [ ] 无实体的查询 → `clarification_needed=true`，不执行任何 Executor
- [ ] 无时间范围的"出库记录" → `clarification_needed=true`
- [ ] 明确查询 + MCP 失败 + Local 失败 + 满足准入条件 → 回退到 QueryAgent
- [ ] 明确查询 + MCP 失败 + Local 失败 + 不满足准入条件 → 返回错误（不回退 QueryAgent）
- [ ] `sql_security_violation` 在任何 Executor 触发 → 不回退，直接返回错误
- [ ] `no_data` → `success=true, total=0`，不触发回退
- [ ] 同一 session 内 QueryAgent 连续 2 次失败 → 该 session 禁用 QueryAgent
- [ ] 所有错误场景有对应的 `error_code`

**风险点**:
- L1 澄清判断的实体识别正则可能覆盖不全 → 初期保守（宁可多澄清，不要硬查）
- QueryAgent 准入条件可能过于严格 → 通过可观测数据迭代阈值

---

### Phase 4: 测试补强 + 可观测 + 前端适配 + 清理

**目标**: 完善测试覆盖、前端透明适配、清理废弃代码路径。

**修改模块**:

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/tests/test_gateway.py` | **新增** | Gateway 单元测试：Executor 选择、回退链、Clarification、错误分类 |
| `backend/tests/test_mcp_client.py` | **新增** | MCP Client 单元测试 |
| `backend/tests/test_gateway_l2.py` | **新增** | Gateway L2 集成测试（真实 MCP + MySQL） |
| `backend/eval/nl2sql/datasets/mcp_queries.json` | **新增** | MCP Tool 选择评估用例 |
| `backend/eval/nl2sql/datasets/clarification_cases.json` | **新增** | 澄清判断评估用例 |
| `backend/eval/nl2sql/runner.py` | **修改** | 支持 `--gateway` 模式 |
| `frontend/vue-app/src/views/OrchestratorPage.vue` | **修改** | `routed_to="mcp"` 渲染 + source 标记 |
| `frontend/vue-app/src/views/QueryPage.vue` | **修改** | source 标记展示 |
| `frontend/vue-app/src/stores/query.js` | **修改** | 解析 `source`、`clarification_needed` 字段 |
| `backend/app/agents/query_agent.py` | **删除?** | 根据 MCP 稳定性决定是否在此 Phase 删除 |

**验收标准**:
- [ ] Gateway 单元测试覆盖率 ≥ 80%
- [ ] L2 测试覆盖：MCP 主路径 / MCP→Local 回退 / Local→QueryAgent 回退 / 澄清判断 / CircuitBreaker
- [ ] Eval: MCP Tool 选择准确率 ≥ 85%、澄清判断准确率 ≥ 90%
- [ ] 前端 OrchestratorPage 和 QueryPage 展示 source 标记（mcp/local/queryagent）
- [ ] 前端正确处理 `clarification_needed=true` 的响应（展示追问文本）
- [ ] `data/traces/` 中可见完整 MCP 调用链 span
- [ ] 现有 eval 套件（`nl2sql/runner.py`）基线结果无退化
- [ ] （可选）QueryAgent 已删除

**风险点**:
- 前端适配依赖 Phase 3 的 Clarification 返回结构稳定
- QueryAgent 删除时机取决于 MCP 稳定性数据 → 可能推迟到下一 release

---

## 附录 A: 与收敛设计文档的差异跟踪

| 收敛设计文档 (v1.0) | Phase 0 补充设计 (本文档) | 变化说明 |
|---------------------|--------------------------|---------|
| 3 级回退链（MCP → Local → QueryAgent） | 受限回退链 + QueryAgent 准入条件 | QueryAgent 不再无条件兜底 |
| 无 Clarification Policy | 完整的 L1+L2 澄清策略 | 新增核心能力 |
| "都保留"的模糊态度 | 明确的准入/拒绝规则表 | 消除模糊性 |
| 无统一错误模型 | 18 种 error_code + 回退规则 | 新增 |
| 无执行策略决策表 | 10 种问题类型 x 5 种处理路径 | 新增 |
| Phase 1 包含 MCP | Phase 1 仅做 Gateway 骨架收敛 | 更安全的分步实施 |
| Generic Fallback Manager | Gateway 内部实现 | 消除独立模块 |

---

> **文档版本**: v1.0
> **设计完成时间**: 2026-06-24
> **关联文档**:
> - `docs/superpowers/plans/2026-06-24-mcp-migration-analysis.md`
> - `docs/superpowers/plans/2026-06-24-data-query-convergence-design.md`
> **下一步**: 审核冻结设计，确认后进入 Phase 1 实现
