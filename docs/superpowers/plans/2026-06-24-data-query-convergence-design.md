# Data Query 架构收敛设计

> **角色**: 企业级 Data Query / Data Copilot 架构负责人
> **目标**: 对当前数据查询架构做收敛式重构设计，消除多入口、多执行器、职责重叠问题
> **基线文档**: `docs/superpowers/plans/2026-06-24-mcp-migration-analysis.md`
> **约束**: 仅设计，不生成代码

---

## 1. 现状问题清单

### 问题 1: 多入口分裂

```
OrchestratorPage ──► dispatch_to_nl2sql() ──► graph_nl2sql
QueryPage        ──► QueryService.natural_query() ──► QueryAgent (旧)
                                 └── use_langgraph flag 控制
```

**根因**: QueryPage 和 OrchestratorPage 走完全不同的调用链，却做同一件事（数据查询）。`use_langgraph` feature flag 只在 QueryService 生效，dispatch 层不受控 — 导致两个入口的行为不可预测。

**影响**: 任何对数据查询的改动（如接入 MCP）需要在两个入口分别实现 + 分别测试。

### 问题 2: dispatch.py 职责膨胀

```
dispatch.py 当前职责:
  ✓ 为 Orchestrator Planner/Executor 提供 dispatch 函数 (原始设计)
  ✗ 直接被 API 层调用做 NL2SQL (越权使用)
  ✗ 计划新增 dispatch_to_mcp (继续膨胀)
  ✗ 计划新增 dispatch_to_query_agent (继续膨胀)
```

**根因**: `dispatch.py` 最初是为 Planner 的多步执行计划设计的 DI 容器（ADR-009）。但后来被直接用作 NL2SQL 的入口，混淆了"多步计划中的一步"和"独立的数据查询请求"。

### 问题 3: Fallback Manager 过度抽象

当前方案计划新建 `core/fallback.py` 作为独立模块，包含 CircuitBreaker + 三级链逻辑。问题是：

- CircuitBreaker 只被数据查询使用，不需要通用化
- 三级回退链是业务决策，不是基础设施
- 独立模块增加了一个调用层，不增加复用价值

### 问题 4: QueryService 职责过载

```
QueryService 当前承担:
  - 查询编排 (选择 QueryAgent vs GraphNL2SQL)
  - SQL 执行 (execute_sql)
  - Schema 管理 (get_schema, preview_table, get_table_fields)
  - 历史管理 (save/get/clear history)
  - 字段翻译 (_translate_columns)
  - 洞察生成 (generate_insight)
```

这是一个典型的"上帝对象" — 6 种不同职责混在一起。

### 问题 5: 三层执行器缺乏治理

```
MCP (计划新增) ──► 主路径，但触发条件是"可用"
GraphNL2SQL     ──► 本地回退，但什么时候触发？
QueryAgent      ──► 最深回退，但什么场景会落到这里？

问题: 三个执行器没有明确的"适用/不适用"边界。
     实际上，如果 MCP 可用且 GraphNL2SQL 维护良好，
     QueryAgent 几乎永远不会被触发 → 死代码。
```

### 问题 6: DISPATCH_MAP 模式被滥用

```python
DISPATCH_MAP = {
    "rag": dispatch_to_rag,       # Planner 的 step dispatch — 正确用法
    "nl2sql": dispatch_to_nl2sql, # Planner 的 step dispatch — 正确用法
    "mcp": dispatch_to_mcp,       # 计划新增 — 这是主路径入口，不应该在 DISPATCH_MAP 里
}
```

`DISPATCH_MAP` 是为 Planner/Executor 的多步执行设计的。MCP 作为主查询路径不应该挂在 DISPATCH_MAP 里。

---

## 2. 收敛原则

| # | 原则 | 说明 |
|---|------|------|
| P1 | **单一入口** | 所有数据查询请求经过同一个入口，无论来自哪个页面 |
| P2 | **策略模式** | 执行器是可替换的策略，Gateway 选择策略，策略不感知 Gateway |
| P3 | **纵深防御** | 回退是"替代方案"不是"同等选项"。每层有明确的存在理由 |
| P4 | **删除优先** | 能删除的模块优先删除，能合并的模块优先合并，只在必要时新增 |
| P5 | **内聚优先** | 相关逻辑放在一起（CircuitBreaker 在 Gateway 内），不为了"通用"而拆散 |
| P6 | **向下屏蔽** | 上层（API、前端）只看到 Gateway，不感知执行器细节 |

---

## 3. 收敛后架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FRONTEND                                     │
│                                                                      │
│   OrchestratorPage          QueryPage                               │
│   (智能助手)                (数据查询)                               │
│        │                        │                                    │
│        │  POST /orchestrator    │  POST /query                       │
│        │  /chat                 │                                    │
└────────┼────────────────────────┼────────────────────────────────────┘
         │                        │
┌────────┼────────────────────────┼────────────────────────────────────┐
│        ▼                        ▼                                    │
│  ┌──────────────────────────────────────────┐                       │
│  │          API Layer                        │                       │
│  │  orchestrator.py    query.py              │                       │
│  │  (意图路由)          (数据查询端点)        │                       │
│  └──────────┬───────────────┬────────────────┘                       │
│             │               │                                        │
│             │ intent=       │ 所有数据查询                           │
│             │ data_query    │ 都走这里                               │
│             │               │                                        │
│             ▼               ▼                                        │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                                                               │   │
│  │            DATA QUERY GATEWAY  (唯一入口)                     │   │
│  │            新增: core/data_query_gateway.py                   │   │
│  │                                                               │   │
│  │  ┌─────────────────────────────────────────────────────────┐ │   │
│  │  │  public API:                                            │ │   │
│  │  │    execute(question, session_id) → UnifiedQueryResult   │ │   │
│  │  │    execute_sql(sql)             → ExecutionResult       │ │   │
│  │  │    get_schema()                 → SchemaInfo            │ │   │
│  │  │                                                         │ │   │
│  │  │  internal:                                              │ │   │
│  │  │    _select_executor()  → Executor                       │ │   │
│  │  │    _circuit_breaker    → StateMachine                    │ │   │
│  │  │    _post_process()     → translate + history + insight  │ │   │
│  │  └─────────────────────────────────────────────────────────┘ │   │
│  │                              │                                │   │
│  │              ┌───────────────┼───────────────┐               │   │
│  │              ▼               ▼               ▼               │   │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐     │   │
│  │  │ MCP Executor │ │Local Executor│ │QueryAgent Exec   │     │   │
│  │  │ (priority 0) │ │(priority 1)  │ │(priority 2)      │     │   │
│  │  │              │ │              │ │⚠️ deprecated     │     │   │
│  │  │ graph_mcp    │ │graph_nl2sql  │ │query_agent       │     │   │
│  │  │ + WmsMcpClnt │ │+ SchemaMgr   │ │(保留不动)        │     │   │
│  │  └──────┬───────┘ └──────┬───────┘ └────────┬─────────┘     │   │
│  │         │                │                   │               │   │
│  │         ▼                ▼                   ▼               │   │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐     │   │
│  │  │MCP Server    │ │MySQL (直连)  │ │MySQL (直连)      │     │   │
│  │  │(:8922)       │ │(aiomysql)    │ │(aiomysql)        │     │   │
│  │  └──────────────┘ └──────────────┘ └──────────────────┘     │   │
│  │                                                               │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │              共享后处理 (Gateway 内部)                        │   │
│  │  • _translate_columns()  • _save_history()                   │   │
│  │  • _generate_insight()   • Tracing/Metrics                   │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │              保留的支撑模块                                   │   │
│  │  DomainClassifier  SchemaManager  SemanticLayerLoader        │   │
│  │  LLMManager        McpClientManager  Tracing                 │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │              Orchestrator (仅负责意图路由 + 混合编排)         │   │
│  │  Router → Planner → Executor                                 │   │
│  │  DISPATCH_MAP = {rag: dispatch_to_rag, pm: dispatch_to_pm}   │   │
│  │  (nl2sql 已从 DISPATCH_MAP 移除)                             │   │
│  └──────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

**关键变化:**
1. `DataQueryGateway` 是唯一的垂直入口，同时被 Orchestrator 和 QueryPage 调用
2. 三个 Executor 是 Gateway 的内部策略，对外不可见
3. `dispatch_to_nl2sql` 从 DISPATCH_MAP 移除 — Orchestrator 通过 Gateway 做数据查询
4. `Fallback Manager` 不再作为独立模块 — 逻辑内聚在 Gateway
5. `QueryService` 不再作为编排层 — 退化为 API 层的薄适配器

---

## 4. 模块职责矩阵

### 4.1 新增模块

| 模块 | 文件 | 单一职责 | 公开接口 |
|------|------|---------|---------|
| **DataQueryGateway** | `core/data_query_gateway.py` | 数据查询唯一入口：执行器选择、回退编排、结果统一、CircuitBreaker、后处理 | `execute(question, session_id)` → `UnifiedQueryResult` |

### 4.2 保留但重构的模块

| 模块 | 当前文件 | 收敛后职责 | 变化 |
|------|---------|-----------|------|
| **QueryService** | `services/query_service.py` | 退化为 API 层的薄适配器：解析请求 → 调用 Gateway → 格式化响应 | 删除编排逻辑，删除 `use_langgraph` 分支，删除 `_query_via_langgraph` 和 `agent.query` 直调 |
| **Orchestrator dispatch** | `orchestrator/dispatch.py` | 仅保留 Planner 多步执行所需的 dispatch 函数 | 移除 `dispatch_to_nl2sql`，Planner 的 nl2sql step 改为调用 Gateway |
| **graph_mcp.py** | `agents/graph_mcp.py` | MCP Executor 的 LangGraph 实现 | 职责不变，但不再被 dispatch.py 直接调用，而是被 Gateway 通过 Executor 接口调用 |
| **graph_nl2sql.py** | `agents/graph_nl2sql.py` | Local Executor 的 LangGraph 实现 | 职责不变，被 Gateway 通过 Executor 接口调用 |

### 4.3 保留不动的模块

| 模块 | 保留原因 |
|------|---------|
| **QueryAgent** (`agents/query_agent.py`) | 最深回退，标记 `@deprecated`，不修改，不增强，下一个大版本删除 |
| **DomainClassifier** (`core/domain_classifier.py`) | 供 Local Executor 和 MCP Tool 选择使用 |
| **SchemaManager** (`core/schema_manager.py`) | 供 Local Executor 使用，MCP 不可用时的 Schema 来源 |
| **SemanticLayerLoader** (`core/semantic_layer_loader.py`) | 字段白名单 + JOIN 图，供 Local Executor 使用 |
| **SemanticRules** (`core/semantic_rules.py`) | HARD_RULES + spec 加载，供 Local Executor 使用 |
| **SQLPostProcess** (`core/sql_post_process.py`) | `inject_plu_name`，供 Local Executor 使用 |
| **LLMManager** (`core/llm_manager.py`) | 所有 Executor 共用 |
| **McpClientManager** (`core/mcp_client.py`) | MCP Executor 的底层连接管理 |
| **Tracing** (`core/tracing.py`) | 扩展 span 覆盖 MCP 调用 |
| **Prompts** (`agents/prompts_sql.py`) | SQL_GENERATION_PROMPT + INSIGHT_GENERATION_PROMPT + MCP_TOOL_SELECT_PROMPT |

### 4.4 删除/合并的模块

| 模块 | 动作 | 理由 |
|------|------|------|
| **Fallback Manager** (`core/fallback.py`) | **不新建** | CircuitBreaker + 回退链逻辑内聚在 DataQueryGateway 内部，不需要独立模块 |
| **dispatch_to_nl2sql** | **从 dispatch.py 删除** | 数据查询入口统一为 Gateway，Planner 的 nl2sql step 改为调用 Gateway |
| **dispatch_to_query_agent** | **不新建** | QueryAgent 作为 Gateway 内部 Executor，不需要暴露为 dispatch 函数 |
| **SQLGenerateTool** (`agents/tools_sql.py`) | **不修改，标记废弃** | 被 MCP 预构建 Tool 替代，仅在 Local Executor 回退时可能使用 |
| **QueryAgent** | **标记 @deprecated，计划删除** | 2 个 release 后删除。过渡期保留作为最深回退 |

### 4.5 职责矩阵总览

```
                    ┌─────────────┬──────────┬──────────┬──────────┐
                    │  路由/编排   │ 查询执行  │ 后处理   │ 基础设施  │
                    ├─────────────┼──────────┼──────────┼──────────┤
│ DataQueryGateway │     ✅      │    ✅    │    ✅    │    -     │
│ QueryService     │     -      │    -     │    ✅    │    -     │
│ Orchestrator     │     ✅      │    -     │    -     │    -     │
│ graph_mcp        │     -      │    ✅    │    -     │    -     │
│ graph_nl2sql     │     -      │    ✅    │    -     │    -     │
│ QueryAgent       │     -      │    ✅    │    -     │    -     │
│ McpClientManager │     -      │    -     │    -     │    ✅     │
│ SchemaManager    │     -      │    -     │    -     │    ✅     │
│ DomainClassifier │     -      │    -     │    -     │    ✅     │
│ LLMManager       │     -      │    -     │    -     │    ✅     │
│ Tracing          │     -      │    -     │    -     │    ✅     │
└─────────────────┴─────────────┴──────────┴──────────┴──────────┘

✅ = 有职责  - = 无关
```

> 核心思想：每列只有一个模块负责。编排/执行/后处理 → Gateway。路由 → Orchestrator。查询逻辑 → 各自 Executor。基础设施 → 各自 core 模块。

---

## 5. 执行路径决策表

### 5.1 三种执行器定位

| 维度 | MCP Executor | Local Executor (GraphNL2SQL) | QueryAgent Executor |
|------|-------------|------------------------------|---------------------|
| **定位** | 主路径 | 本地回退 | 灾难回退 |
| **优先级** | 0 (最高) | 1 | 2 (最低) |
| **触发条件** | MCP 健康检查通过 | MCP 不可用（CircuitBreaker OPEN） | MCP 不可用 + Local Executor 也失败 |
| **适用范围** | 预构建 Tool 能覆盖的 WMS 查询 + execute_sql_readonly 自定义查询 | 所有数据查询 | 所有数据查询 |
| **核心依赖** | MCP Server (:8922) + 网络 | MySQL 直连 + LLM | MySQL 直连 + LLM |
| **优势** | 无需 SQL 生成，预构建 Tool 准确率高 | 自主可控，不受外部服务影响 | 最简单，不依赖 LangGraph 基础设施 |
| **劣势** | 依赖外部服务可用性 | 需要 LLM 生成 SQL，可能出错 | 旧架构，已被 LangGraph 替代 |
| **退出条件** | 连续 3 次失败 → CircuitBreaker OPEN (60s 冷却) | Gateway 内部异常 → 尝试 QueryAgent | 失败 → 返回错误给用户 |
| **用户可见** | 否（透明，source="mcp"） | 否（透明，source="local"） | 否（透明，source="fallback"） |
| **生命周期** | 长期主路径 | 长期保留（离线/灾备） | **计划删除**（2 个 release 后） |

### 5.2 执行路径决策树

```
Gateway.execute(question)
  │
  ├── [1] CircuitBreaker 状态检查
  │     ├── OPEN → 跳过 MCP，直接到 [3]
  │     └── CLOSED / HALF_OPEN → 继续 [2]
  │
  ├── [2] MCP Executor.execute(question)
  │     ├── 成功 → CircuitBreaker.record_success()
  │     │         → 跳到后处理 [6]
  │     │
  │     └── 失败 → CircuitBreaker.record_failure()
  │               → 检查是否达到 threshold (3次)
  │               → 继续 [3] (不中断，直接回退)
  │
  ├── [3] Local Executor (graph_nl2sql).execute(question)
  │     ├── 成功 → 跳到后处理 [6]
  │     │
  │     └── 失败 → 继续 [4]
  │
  ├── [4] QueryAgent Executor.execute(question)  ⚠️ deprecated
  │     ├── 成功 → 跳到后处理 [6] + 记录 WARNING 日志
  │     │         (触发此路径说明 MCP 和 LangGraph 都失效)
  │     │
  │     └── 失败 → 返回错误 [5]
  │
  ├── [5] 返回 UnifiedQueryResult {success: false, error: "..."}
  │
  └── [6] 后处理
          • _translate_columns() 英→中
          • _save_history() 持久化
          • _generate_insight() (如果 Executor 未返回 insight)
          • 附加 source 字段 (mcp/local/fallback)
          → 返回 UnifiedQueryResult
```

### 5.3 关键决策：为什么不直接删除 QueryAgent

| 保留理由 | 删除理由 |
|---------|---------|
| LangGraph 基础设施故障时仍有一条可用路径 | LangGraph 已在生产运行（Orchestrator 路径），稳定性已验证 |
| 不依赖 `langgraph` 库，无 checkpoint 序列化问题 | graph_nl2sql 编译时已知的 `%` 序列化问题已绕过 |
| 代码量小，维护成本低 | 仍需要维护 5 步管线的 Prompt + 规则同步 |
| **过渡期安全网** | 死代码 |

**结论**: 保留一个 release 周期（约 2-4 周）作为安全网，MCP 稳定运行后删除。删除时只需：
1. 从 Gateway 中移除 QueryAgent Executor
2. 删除 `backend/app/agents/query_agent.py`
3. 回退链变为：MCP → Local → 错误

---

## 6. 与现有迁移方案的差异分析

### 6.1 当前方案的问题点

| 问题 | 当前方案 | 收敛方案 |
|------|---------|---------|
| **入口数量** | 3 个：QueryService + dispatch_to_nl2sql + dispatch_to_mcp | 1 个：DataQueryGateway |
| **Fallback 位置** | 独立模块 `core/fallback.py` | Gateway 内部方法 `_execute_with_fallback()` |
| **dispatch.py 职责** | NL2SQL 入口 + Planner dispatch | 仅 Planner dispatch（NL2SQL 移除） |
| **QueryService 职责** | 编排 + 执行 + Schema + 历史 + 翻译 | 薄适配器：请求解析 → Gateway → 响应格式化 |
| **CircuitBreaker** | 通用独立模块 | Gateway 内聚实现 |
| **use_langgraph flag** | 保留，控制 QueryService 分支 | **删除** — Gateway 的 executor 优先级替代了 flag |
| **DISPATCH_MAP** | 含 nl2sql, mcp, rag, pm | 仅含 rag, pm（nl2sql 走 Gateway） |
| **Executor 数量** | 3 + "都保留" | 3 但 QueryAgent 有明确删除计划 |

### 6.2 复杂度对比

```
当前方案调用链:
  API → QueryService → use_langgraph? → QueryAgent / graph_nl2sql
  API → dispatch_to_nl2sql → graph_nl2sql
  API → dispatch_to_mcp → graph_mcp
  API → Fallback Manager → ? → ? → ?
  共 4 条路径，5 个决策点

收敛方案调用链:
  API → DataQueryGateway.execute()
          └── 内部: [MCP, Local, QueryAgent] 优先级链
  共 1 条路径，1 个决策点（Gateway 内部）
```

---

## 7. 推荐实施顺序

基于收敛设计，重新调整迭代计划：

### Phase 1: Gateway 骨架 + 现有逻辑迁移（替代原 Iteration 0-2）

1. 新建 `DataQueryGateway`，实现 Executor 接口
2. 将 `QueryService.natural_query()` 的编排逻辑迁移到 Gateway 的 `_execute_with_fallback()`
3. 将 `_translate_columns()`, `_save_history()` 迁移到 Gateway 的 `_post_process()`
4. QueryService 退化为薄适配器：`natural_query(question)` → `gateway.execute(question)`
5. Orchestrator dispatch 移除 `dispatch_to_nl2sql`，改为调用 Gateway
6. 此时功能上与现有完全一致，**但入口已统一**

### Phase 2: MCP Executor 接入（替代原 Iteration 2）

1. 实现 `McpExecutor`（封装 `graph_mcp.py`）
2. 注册到 Gateway 的 executor 链（优先级 0）
3. 实现 MCP CircuitBreaker（Gateway 内部）
4. 此时 MCP 自动成为主路径，Local 自动降级为回退

### Phase 3: 清理 + 测试（替代原 Iteration 3-6）

1. 删除 `use_langgraph` feature flag
2. 移除 `dispatch.py` 中的 `dispatch_to_nl2sql`
3. 删除 `DISPATCH_MAP["nl2sql"]`
4. QueryAgent 标记 `@deprecated`
5. 回归测试

### Phase 4: 最终清理（未来 release）

1. 删除 `QueryAgent`
2. `SQLGenerateTool` 标记废弃
3. 回退链简化为 MCP → Local → Error

---

## 8. 风险评估

### 8.1 收敛方案的额外风险

| 风险 | 严重程度 | 缓解 |
|------|---------|------|
| Gateway 成为单点故障 | 中 | Gateway 本身是薄层（~100 行），复杂度在 Executor 里；Gateway 不做重逻辑，不会成为瓶颈 |
| Executor 接口设计不当 | 中 | 三个 Executor 的输入输出已经相似（question → result），接口只需 2 个方法 |
| QueryService 重构风险 | 中 | Phase 1 先建 Gateway 骨架 + 保留旧路径双写，验证一致后切换 |

### 8.2 当前方案已缓解的旧风险

| 旧风险 | 收敛后状态 |
|-------|-----------|
| MCP Server 不可用 | 不变 — Gateway 自动回退到 Local Executor |
| 多入口导致行为不一致 | **已消除** — 唯一入口 |
| Fallback 逻辑分散 | **已消除** — 集中在 Gateway |
| 前端适配改动大 | **减轻** — 透明模式 + source 标记，Gateway 统一返回格式 |

---

## 9. 总结：收敛前后对比

```
收敛前:
  ┌──────────┐  ┌──────────┐
  │QueryPage │  │Orch.Page │  两个入口
  └────┬─────┘  └────┬─────┘
       │             │
       ▼             ▼
  ┌─────────┐  ┌───────────┐
  │QuerySvc │  │dispatch   │  两个编排层
  │(use_lgr)│  │(DISPATCH) │
  └────┬─────┘  └────┬──────┘
       │             │
    ┌──▼──┐      ┌───▼───┐
    │Agent│      │Graph  │    三个执行器
    │(旧) │      │NL2SQL │    无优先级
    └─────┘      └───────┘
    ┌─────┐      ┌─────┐
    │ MCP │      │Fall │    计划新增
    │Graph│      │back │    两个模块
    └─────┘      └─────┘

收敛后:
  ┌──────────┐  ┌──────────┐
  │QueryPage │  │Orch.Page │  入口层(不变)
  └────┬─────┘  └────┬─────┘
       │             │
       └──────┬──────┘
              ▼
  ┌───────────────────────┐
  │  DataQueryGateway     │  唯一编排层
  │  execute(question)    │  (新增, ~200行)
  │                       │
  │  ┌─────────────────┐  │
  │  │ Executor Chain  │  │
  │  │ [MCP → Local →  │  │
  │  │  QueryAgent]    │  │  执行器链(Gateway内部)
  │  │ + CircuitBreaker│  │
  │  │ + PostProcess   │  │
  │  └─────────────────┘  │
  └───────────────────────┘
```

**文件变更对比:**

| | 当前方案 | 收敛方案 |
|---|---------|---------|
| 新增文件 | 3 个 (mcp_client, graph_mcp, fallback) | 2 个 (mcp_client, data_query_gateway) |
| graph_mcp.py 位置 | 作为独立 graph，挂在 dispatch | 作为 Gateway 内部 Executor |
| 修改文件 | dispatch.py, query_service.py, config.py 等 | 同上，但改动更集中 |
| 计划删除 | 无明确计划 | QueryAgent (标记 deprecated，2 release 后删除) |

---

> **文档版本**: v1.0
> **设计完成时间**: 2026-06-24
> **关联文档**: `docs/superpowers/plans/2026-06-24-mcp-migration-analysis.md`
> **下一步**: 审核收敛设计，确认后进入 Phase 1 实现
