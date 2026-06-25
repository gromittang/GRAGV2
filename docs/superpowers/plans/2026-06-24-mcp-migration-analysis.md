# NL2SQL → MCP Data Copilot 迁移分析

> **角色**: Tech Lead 视角
> **原则**: 最大复用、最小改动、可回滚、可测试、可观测、增量迁移
> **约束**: 仅分析，不生成代码
> **端口**: MCP Server = 8922, WMSRAGV2 后端 = 8912 (独立部署, 端口错开)

---

## 决策记录

| # | 决策点 | 结论 | 确认时间 |
|---|--------|------|---------|
| D1 | MCP 主路径策略 | **MCP 优先**：MCP 可用时默认走 MCP，失败时自动回退本地 | 2026-06-24 |
| D2 | MySQL 直连定位 | **逐步废弃**：MCP 稳定运行后逐步移除本地 MySQL 直连，所有数据访问统一走 MCP | 2026-06-24 |
| D3 | Tool 选择模式 | **多Tool并行**：LLM 可选择 1-3 个 Tool 并行调用，适合复合查询场景 | 2026-06-24 |
| D4 | 前端改动范围 | **两个页面都改**：OrchestratorPage 和 QueryPage 都支持 MCP 模式，QueryPage 增加 source 标记展示路由来源 | 2026-06-24 |
| D5 | DomainClassifier 角色 | **Tool推荐辅助信号**：保留，输出作为 LLM Tool 选择的 hint，帮助缩小候选 Tool 范围 | 2026-06-24 |
| D6 | SchemaManager 索引 | **保持热维护**：继续随 schema 变化更新索引，作为 MCP 补充和回退依赖 | 2026-06-24 |
| D7 | LangGraph MCP 集成 | **自定义 Node**：在 LangGraph 节点中直接调用 WmsMcpClient，灵活控制 Tool 选择、参数填充、结果格式化 | 2026-06-24 |
| D8 | 前端 MCP 展示 | **透明模式**：后端自动选择路径，前端通过 source 标记展示路由来源（mcp/local），用户无需手动切换 | 2026-06-24 |
| D9 | QueryPage 升级策略 | **本次一并升级**：QueryService 增加 MCP 优先路径，QueryPage 和 OrchestratorPage 统一走 MCP → LangGraph → QueryAgent 三级回退链 | 2026-06-24 |

---

## NL2SQL 路径现状与统一方案

### 当前两条路径（分裂状态）

```
OrchestratorPage ──► dispatch_to_nl2sql() ──► graph_nl2sql (LangGraph) ✅
QueryPage ──► QueryService.natural_query() ──► QueryAgent (旧版) ❌
                       │
                       └── use_langgraph=False (默认, .env未设置)
```

### 统一后三条路径（本次实现）

```
任何入口 (OrchestratorPage / QueryPage)
  │
  ▼
QueryService / dispatch
  │
  ├─ [1] MCP Path (主路径)
  │      graph_mcp.py → WmsMcpClient → MCP Server (:8922)
  │      失败 → 回退到 [2]
  │
  ├─ [2] LangGraph NL2SQL (本地回退)
  │      graph_nl2sql.py → LLM生成SQL → MySQL直连
  │      失败 → 回退到 [3]
  │
  └─ [3] QueryAgent (最深回退, 保留不动)
         query_agent.py → 旧版5步管线
```

> **回退链**: MCP (graph_mcp) → LangGraph NL2SQL (graph_nl2sql) → QueryAgent
> **QueryAgent 保留不动**，仅作为最深回退存在。后续 MCP 稳定后自然不再触发。

---

## MCP Server 端口说明

| 服务 | 端口 | 说明 |
|------|------|------|
| MCP Data Copilot Server | **8922** | 独立 WMS MCP 服务，提供只读查询 Tool |
| WMSRAGV2 后端 | **8912** | 本项目 FastAPI 后端，通过 MCP Client 连接 :8922 |
| WMSRAGV2 前端 | **5173** | Vite 开发服务器 |

> 两个服务可能部署在同一台机器上，端口已错开避免冲突。

---

## Step 1: 现状审计 (Architecture Audit)

### 1.1 当前数据查询架构图

```
┌──────────────────────────────────────────────────────────────────────┐
│                          FRONTEND (Vue3 + Vite)                       │
│                                                                       │
│  ┌──────────────────┐  ┌──────────────┐  ┌────────────────────────┐  │
│  │  OrhestratorPage │  │  QueryPage   │  │  ChatPage (含Agent)    │  │
│  │  智能助手(主入口) │  │  数据查询    │  │  智能问答              │  │
│  └──────┬───────────┘  └──────┬───────┘  └───────────┬────────────┘  │
│         │                     │                       │               │
│         │  POST /orchestrator │  POST /query           │  POST /chat   │
│         │  /chat              │  /execute, /schema...  │  /stream      │
└─────────┼─────────────────────┼───────────────────────┼───────────────┘
          │                     │                       │
┌─────────┼─────────────────────┼───────────────────────┼───────────────┐
│         ▼                     ▼                       ▼               │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │                    API Layer (FastAPI)                           │ │
│  │  orchestrator.py   query.py   chat.py   pm_solution.py          │ │
│  └──────────────────────────────┬──────────────────────────────────┘ │
│                                 │                                    │
│  ┌──────────────────────────────▼──────────────────────────────────┐ │
│  │               ORCHESTRATOR (orchestrator/)                      │ │
│  │  HybridRouter ──► Planner ──► Executor ──► dispatch             │ │
│  │  (RuleEngine +    (LLM生成    (async for   (DISPATCH_MAP)       │ │
│  │   MiniLLMRouter)   执行计划)   dispatch)                         │ │
│  └───────┬──────────────┬──────────────────┬───────────────────────┘ │
│          │              │                  │                         │
│          ▼              ▼                  ▼                         │
│  ┌──────────────┐ ┌──────────┐ ┌──────────────────┐                 │
│  │ dispatch_to  │ │dispatch  │ │ dispatch_to_pm   │                 │
│  │ _nl2sql()    │ │_to_rag() │ │ (graph_pm)       │                 │
│  └──────┬───────┘ └──────────┘ └──────────────────┘                 │
│         │                                                            │
│  ┌──────▼──────────────────────────────────────────────────────┐    │
│  │              QUERY SERVICE (query_service.py)                │    │
│  │  natural_query() ──► use_langgraph? ──► 两条路径             │    │
│  └──────┬──────────────────────────────────────────────────────┘    │
│         │                                                            │
│    ┌────▼─────────────────┐                                         │
│    │  use_langgraph=False │  use_langgraph=True                      │
│    │  QueryAgent (旧版)   │  GraphNL2SQL (新版)                      │
│    │  5步硬编码管线       │  6节点StateGraph                        │
│    └──────┬───────────────┴──────┬──────────────────────┘           │
│           │                      │                                   │
│  ┌────────▼──────────────────────▼─────────────────────────────┐    │
│  │                   CORE LAYER (core/)                         │    │
│  │                                                              │    │
│  │  ┌─────────────────┐  ┌──────────────────┐                  │    │
│  │  │ DomainClassifier │  │  SchemaManager   │                  │    │
│  │  │ (embedding+cos)  │  │  (embedding索引) │                  │    │
│  │  └────────┬────────┘  └────────┬─────────┘                  │    │
│  │           │                    │                             │    │
│  │  ┌────────▼────────────────────▼─────────┐                  │    │
│  │  │       semantic_layer_loader.py        │                  │    │
│  │  │  DOMAINS, TABLE_KEY_COLUMNS,          │                  │    │
│  │  │  JOIN_GRAPH (字段白名单 + JOIN规则)    │                  │    │
│  │  └───────────────────────────────────────┘                  │    │
│  │                                                              │    │
│  │  ┌─────────────────┐  ┌──────────────────┐                  │    │
│  │  │ semantic_rules  │  │ sql_post_process │                  │    │
│  │  │ (HARD_RULES,    │  │ (inject_plu_name)│                  │    │
│  │  │  spec_context)  │  └──────────────────┘                  │    │
│  │  └─────────────────┘                                         │    │
│  │                                                              │    │
│  │  ┌─────────────────┐  ┌──────────────────┐                  │    │
│  │  │  LLM Manager    │  │  MySQL Manager   │                  │    │
│  │  │ (DeepSeek/OpenAI│  │ (aiomysql连接池) │                  │    │
│  │  │  /Claude可切换) │  │                  │                  │    │
│  │  └─────────────────┘  └──────────────────┘                  │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                                                                       │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │                   TOOLS & PROMPTS                             │    │
│  │  prompts_sql.py    tools_sql.py                              │    │
│  │  (SQL生成/洞察/   (Schema搜索/生成/验证/执行 4个Tool)        │    │
│  │   解释 3个Prompt)                                             │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                                                                       │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │              DATA STORES                                      │    │
│  │  MySQL (unwms)──业务库  SQLite──query_history/feedback       │    │
│  │  ChromaDB──知识库  SQLite──kb.db                             │    │
│  └──────────────────────────────────────────────────────────────┘    │
└───────────────────────────────────────────────────────────────────────┘
```

### 1.2 数据流分析

**完整请求链路 (以 orchestrator → NL2SQL 为例):**

```
用户输入自然语言
  │
  ▼
[1] HybridRouter.route(question)
    ├── RuleEngine: 关键词匹配 (正则: 出库单/库存/配送...)
    │   └── 命中 → intent="data_query", source="rule"
    └── MiniLLMRouter: LLM分类 (未命中规则时)
        └── JSON {intent, confidence} → confidence<0.6 → fallback="clarify"
  │
  ▼
[2] dispatch_to_nl2sql(question)
    │
    ├─ use_langgraph=True ──► GraphNL2SQL
    │   ├── domain_classify_node: DomainClassifier.classify() + HARD_RULES
    │   ├── schema_search_node: SchemaManager.search_relevant_schema_filtered()
    │   │   └── 注入 spec_context (semantic-layer.md + sql-rules.md)
    │   ├── sql_generate_node: LLM(SQL_GENERATION_PROMPT) → JSON → inject_plu_name()
    │   ├── sql_validate_node: SQLValidateTool (纯规则, 无LLM)
    │   ├── sql_execute_node: MySQLManager.execute(sql)
    │   └── insight_generate_node: LLM(INSIGHT_GENERATION_PROMPT) → parse_insight()
    │
    └─ use_langgraph=False ──► QueryAgent (同上5步, 但硬编码顺序)
  │
  ▼
[3] 后处理: _translate_columns() → _save_history()
  │
  ▼
[4] 返回 OrchestratorResponse {intent, sql, data, insight, ...}
```

**关键数据节点:**
| 阶段 | 输入 | 输出 | 延迟敏感度 |
|------|------|------|-----------|
| 路由 | question (str) | intent, confidence | 低 (~100ms) |
| 领域分类 | question (str) | domain, tables[] | 低 (embedding cos) |
| Schema搜索 | question + domain_tables | schema_context (str) | 低 (embedding cos) |
| SQL生成 | schema + question + rules | JSON {sql, tables, confidence} | **高** (LLM ~2s) |
| SQL验证 | sql (str) | {valid, sql} | 极低 (regex) |
| SQL执行 | validated_sql | {rows, columns, count} | 中 (MySQL ~1-3s) |
| 洞察生成 | question + results | {insights, follow_ups} | **高** (LLM ~2s) |

### 1.3 核心模块职责总结

| 模块 | 文件 | 职责 | 类型 |
|------|------|------|------|
| QueryService | `services/query_service.py` | 查询编排、history管理、中英文翻译 | **编排层** |
| QueryAgent | `agents/query_agent.py` | 旧版5步硬编码管线 | **编排层** |
| GraphNL2SQL | `agents/graph_nl2sql.py` | 新版LangGraph 6节点图 | **编排层** |
| HybridRouter | `orchestrator/router.py` | 意图分类 (规则+LLM级联) | **路由层** |
| Planner | `orchestrator/planner.py` | LLM生成多步执行计划 | **路由层** |
| Executor | `orchestrator/executor.py` | 按计划dispatch执行 | **路由层** |
| dispatch | `orchestrator/dispatch.py` | 封装各graph的ainvoke() | **粘合层** |
| DomainClassifier | `core/domain_classifier.py` | embedding领域分类 | **检索** |
| SchemaManager | `core/schema_manager.py` | schema嵌入索引+语义搜索 | **检索** |
| SemanticLayerLoader | `core/semantic_layer_loader.py` | 字段白名单+JOIN图+领域定义 | **规则** |
| SemanticRules | `core/semantic_rules.py` | HARD_RULES关键词+spec加载 | **规则** |
| SQLPostProcess | `core/sql_post_process.py` | inject_plu_name()后处理 | **规则** |
| LLMManager | `core/llm_manager.py` | 多provider LLM单例 | **基础设施** |
| MySQLManager | `core/db_mysql.py` | aiomysql连接池管理 | **基础设施** |
| SQLValidateTool | `agents/tools_sql.py` | 纯规则: 禁止DML/禁止*/强制LIMIT | **安全** |
| SQLExecuteTool | `agents/tools_sql.py` | MySQL执行封装 | **执行** |
| prompts_sql | `agents/prompts_sql.py` | SQL生成/洞察/解释 3个Prompt | **Prompt** |

### 1.4 MCP 接入影响范围

**直接影响 (需要变更的模块):**

| 模块 | 影响程度 | 说明 |
|------|---------|------|
| `orchestrator/dispatch.py` | **高** | 需新增 `dispatch_to_mcp()` 或修改 `dispatch_to_nl2sql()` |
| `services/query_service.py` | **高** | `natural_query()` 需增加 MCP 路径 |
| `agents/graph_nl2sql.py` | **高** | SQL生成节点可替换为MCP Tool调用 |
| `agents/query_agent.py` | **中** | 旧版路径可能需要同步适配 |
| `agents/prompts_sql.py` | **中** | SQL生成Prompt可能简化 |
| `core/schema_manager.py` | **中** | Schema发现可委托给MCP (保留本地索引作为回退) |
| `core/domain_classifier.py` | **低-中** | MCP的Tool选择可能替代领域分类的部分功能 |
| `core/db_mysql.py` | **低** | 执行层可保留，但MCP也提供 `execute_sql_readonly` |
| `core/config.py` | **高** | 需新增 MCP 相关配置项 |
| `api/query.py` | **中** | 可能需要新增MCP特定端点或参数 |
| `api/orchestrator.py` | **中** | 路由结果需增加 `mcp` 意图 |

**间接影响 (可能需要调整的模块):**

| 模块 | 影响程度 | 说明 |
|------|---------|------|
| `agents/tools_sql.py` | **低** | SQL验证逻辑与MCP的 `execute_sql_readonly` 安全层重叠 |
| `core/semantic_layer_loader.py` | **低** | MCP Tool描述可替代部分语义层规则 |
| `core/semantic_rules.py` | **低** | HARD_RULES在MCP Tool选择中仍有价值 |
| `core/sql_post_process.py` | **低** | `inject_plu_name()` MCP Tool已处理 |
| 前端 `OrchestratorPage.vue` | **中** | 需新增mcp意图的UI渲染 |
| 前端 `QueryPage.vue` | **低-中** | 可能需要新增MCP模式选择 |

### 1.5 可复用能力

| 能力 | 复用方式 | 价值 |
|------|---------|------|
| **Orchestrator 路由框架** | Router→Planner→Executor架构完整保留，新增MCP dispatch分支 | 高 — 入口统一 |
| **Domain Classifier** | 保留作为MCP Tool选择的辅助逻辑 | 中 — embedding分类快速且免费 |
| **SchemaManager 嵌入索引** | 保留作为MCP不可用时的本地回退 | 中 — 离线可用 |
| **Semantic Layer (spec文件)** | 规则知识可迁移到MCP Tool描述 | 中 — 业务知识资产 |
| **SQL 验证规则** | 与MCP安全层互补（纵深防御） | 中 — 安全冗余 |
| **Insight 生成** | MCP不提供洞察分析，完全保留 | 高 — 核心差异化能力 |
| **Query History / Feedback** | 完全保留，与MCP无关 | 高 — 数据资产 |
| **前端查询页面** | 保留UI框架，增加MCP结果渲染 | 高 — 用户体验连续 |
| **LLM Manager** | 完全保留，MCP Client内部也可能调用LLM | 高 — 基础设施 |
| **Tracing / Logging** | 扩展trace标记覆盖MCP调用 | 中 — 可观测性 |
| **NL2SQL Eval 体系** | 扩展测试用例覆盖MCP路径 | 中 — 质量保障 |

### 1.6 需要废弃的能力

| 能力 | 废弃理由 | 风险 |
|------|---------|------|
| **SQL_GENERATION_PROMPT (完整)** | MCP提供预构建Tool，LLM只需选择Tool+参数 | 中 — 复杂查询可能仍需自定义SQL |
| **SchemaManager 作为主路径** | MCP的Tool发现可替代Schema搜索作为主路径 | 低 — 保留作为回退 |
| **SQLGenerateTool** | 被MCP `execute_sql_readonly` 或预构建Tool替代 | 低 — 保留作为回退 |
| **QueryAgent 旧版路径** | LangGraph迁移完成后可逐步废弃 | 低 — Feature flag控制 |
| **部分 HARD_RULES** | MCP Tool描述替代关键词→表映射 | 低 — 保留作为MCP Tool选择的辅助 |

### 1.7 潜在风险

| 风险 | 严重程度 | 缓解措施 |
|------|---------|---------|
| **MCP Server 不可用** | 高 — 整个查询链路中断 | 本地回退路径 (保留现有NL2SQL管线) |
| **MCP Tool 返回格式不兼容** | 中 — 前端/洞察生成依赖特定格式 | Adapter层做格式转换 |
| **认证失败 (API Key)** | 中 — MCP调用失败 | 启动时health check + 运行时降级 |
| **语义层规则迁移遗漏** | 中 — MCP Tool描述不如spec详细 | 保持spec文件，MCP Tool描述引用spec |
| **LLM Tool选择错误** | 中 — LLM可能选错MCP Tool | 保留DomainClassifier做Tool推荐 |
| **execute_sql_readonly 安全边界差异** | 低 — 安全规则可能不同 | 保留本地SQLValidateTool做纵深防御 |
| **性能退化** | 中 — MCP网络开销 > 本地MySQL直连 | 本地直连作为热路径，MCP作为增强 |
| **测试覆盖不足** | 中 — 新增MCP路径需要新测试 | 扩展eval体系覆盖MCP路径 |

---

## Step 2: Gap Analysis

### 2.1 AS-IS Architecture (当前架构)

```
┌─────────────────────────────────────────────────────────────┐
│                    用户输入自然语言                            │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Orchestrator: 意图路由 (RuleEngine + MiniLLMRouter)         │
│  → data_query / knowledge_search / solution_design / hybrid  │
└──────────────────────────┬──────────────────────────────────┘
                           │ data_query
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  NL2SQL Pipeline (5-6步)                                     │
│                                                              │
│  [1] Domain Classify (embedding + HARD_RULES)                │
│       ↓                                                      │
│  [2] Schema Search (embedding语义搜索 + spec注入)             │
│       ↓                                                      │
│  [3] SQL Generate (LLM + SQL_GENERATION_PROMPT)              │
│       ↓                                                      │
│  [4] SQL Validate (纯规则: 禁止DML/禁止*/强制LIMIT)           │
│       ↓                                                      │
│  [5] SQL Execute (MySQL直连, aiomysql连接池)                  │
│       ↓                                                      │
│  [6] Insight Generate (LLM + INSIGHT_GENERATION_PROMPT)      │
│                                                              │
│  数据源: MySQL直连 (unwms)                                    │
│  Schema源: tfrmdataobj + tfrmdataprop 元数据表                │
│  规则源: spec/nl2sql/semantic-layer.md (运行时动态加载)       │
└─────────────────────────────────────────────────────────────┘
```

**核心特征:**
- Schema发现: 本地embedding索引 + spec文件
- SQL生成: LLM自由生成 (受prompt约束)
- SQL执行: 直接MySQL连接 (aiomysql)
- 安全检查: 应用层纯规则验证
- 洞察分析: LLM后处理
- 回退: 不存在MCP概念

### 2.2 TO-BE Architecture (目标架构)

```
┌─────────────────────────────────────────────────────────────┐
│                    用户输入自然语言                            │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Orchestrator: 意图路由 (RuleEngine + MiniLLMRouter)         │
│  → data_query / knowledge_search / solution_design / hybrid  │
│  → data_query 内部再分流: mcp / nl2sql (本地)                │
└──────────────────────────┬──────────────────────────────────┘
                           │ data_query
                           ▼
              ┌────────────┴────────────┐
              │ MCP Available?          │
              │ (health check缓存)      │
              └──────┬─────────┬────────┘
                     │ YES     │ NO (fallback)
                     ▼         ▼
┌──────────────────────────┐ ┌──────────────────────────────┐
│ MCP PATH (新)            │ │ LOCAL PATH (保留现有)         │
│                          │ │                               │
│ [1] LLM选择MCP Tool      │ │ [1] Domain Classify           │
│     (基于Tool描述+问题)   │ │ [2] Schema Search             │
│     ↓                    │ │ [3] SQL Generate (LLM)        │
│ [2] 调用MCP Tool         │ │ [4] SQL Validate              │
│     (预构建查询 或       │ │ [5] SQL Execute (直连)        │
│      execute_sql_readonly)│ │ [6] Insight Generate          │
│     ↓                    │ │                               │
│ [3] 结果格式化 (Adapter)  │ │                               │
│     ↓                    │ │                               │
│ [4] Insight Generate     │ │                               │
│     (保留本地LLM)        │ │                               │
│                          │ │                               │
│ ┌────────────────────┐   │ │                               │
│ │ WMS MCP Server     │   │ │                               │
│ │ (只读, 外部服务)    │   │ │                               │
│ │                    │   │ │                               │
│ │ • Schema Discovery │   │ │                               │
│ │   (Tool描述即schema)│   │ │                               │
│ │ • Query Planning   │   │ │                               │
│ │   (LLM选择Tool组合) │   │ │                               │
│ │ • SQL Generation   │   │ │                               │
│ │   (预构建Tool)     │   │ │                               │
│ │ • Validation       │   │ │                               │
│ │   (execute_sql_    │   │ │                               │
│ │    readonly内置)   │   │ │                               │
│ └────────────────────┘   │ │                               │
└──────────────────────────┘ └──────────────────────────────┘
              │                         │
              └──────────┬──────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  共享后处理层                                                │
│  • _translate_columns() 中英文字段名转换                      │
│  • _save_history() 查询历史持久化                             │
│  • Insight Generate LLM (如果前面没做)                        │
│  • 结果统一格式化返回前端                                     │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 Gap Analysis 详细对照

#### 2.3.1 MCP 能替代哪些模块

| MCP 能力 | 替代的现有模块 | 替代程度 | 说明 |
|----------|--------------|---------|------|
| **Schema Discovery** (Tool描述) | `SchemaManager.search_relevant_schema()` | **部分** | MCP Tool自带结构化参数描述 = schema自文档化。但通用/跨表查询仍需本地Schema索引 |
| **预构建查询Tool** (13+个) | `SQLGenerateTool` + `SQL_GENERATION_PROMPT` | **大部分** | MCP的 `query_inventory_by_sku` 等Tool覆盖了库存/商品/出入库/分析场景，LLM只需选择Tool+填参数，无需生成SQL |
| **execute_sql_readonly** | `SQLGenerateTool` + `SQLExecuteTool` | **部分** | 对于预构建Tool无法覆盖的复杂查询，MCP提供受控SQL执行 |
| **Query Planning** (LLM选择Tool) | `DomainClassifier` + Schema搜索 | **部分** | LLM根据Tool描述选择正确的Tool组合 = 隐式领域分类 + 查询规划 |
| **Validation** (MCP内置) | `SQLValidateTool` | **互补** | MCP的 `execute_sql_readonly` 内置安全检查 (禁止DML/DDL/多语句/危险函数/30s超时/自动LIMIT)。本地验证可作为纵深防御 |

#### 2.3.2 MCP 无法覆盖的能力 (必须保留)

| 能力 | 保留原因 | 保留位置 |
|------|---------|---------|
| **Insight 生成** (AI分析) | MCP不提供数据分析和业务洞察 | `INSIGHT_GENERATION_PROMPT` + LLM，完全保留 |
| **中文自然语言理解** | MCP Tool需要结构化参数，NL→参数映射仍需LLM | Orchestrator + LLM层 |
| **混合查询编排** (NL2SQL+RAG) | MCP只覆盖数据查询，不覆盖文档检索 | `orchestrator/planner.py` + `executor.py` |
| **PM方案工作室** | 与数据查询无关 | `graph_pm.py`，完全独立 |
| **知识库问答 (RAG)** | 与数据查询无关 | `graph_rag.py`，完全独立 |
| **查询历史/反馈系统** | 业务数据资产，与查询实现无关 | `models/query_history.py` + `query_feedback.py` |
| **语义层规则知识** | MCP Tool参数描述不包含所有业务约定 (如默认良品仓、UTC+8转换、_yyyymm表名规则) | `spec/nl2sql/semantic-layer.md` 保留 |
| **字段中文翻译** | MCP返回英文字段名 | `schema_manager.get_column_display_map()` 保留 |
| **可观测性 (Tracing/Logging)** | 需统一覆盖MCP调用 | `core/tracing.py` 扩展 |

#### 2.3.3 推荐的职责边界

```
┌─────────────────────────────────────────────────────────────┐
│                    本项目 (WMSRAGV2)                         │
│                                                              │
│  ✅ 保留:                                                    │
│  • 用户交互 (前端UI + 会话管理)                               │
│  • 意图路由 (Orchestrator: 规则+LLM)                         │
│  • NL理解 (NL→结构化参数, LLM)                                │
│  • 混合编排 (NL2SQL+RAG+PM多步计划)                           │
│  • 洞察生成 (AI分析 + 追问建议)                               │
│  • 字段中文化 (英→中映射)                                     │
│  • 查询历史/反馈 (SQLite持久化)                               │
│  • 知识库问答 (RAG, 独立)                                     │
│  • PM方案工作室 (独立)                                        │
│  • 本地SQL验证 (纵深防御第二层)                               │
│  • 可观测性 (Tracing + Logging)                               │
│  • NL2SQL Eval 体系                                           │
│  • Spec文件 (语义层规则, 业务知识库)                          │
│                                                              │
│  🔄 委托给MCP (新增):                                        │
│  • 数据查询执行 (预构建Tool + execute_sql_readonly)           │
│  • Schema结构提供 (Tool参数描述 = 字段定义)                   │
│  • 基础SQL安全检查 (MCP内置, 第一层)                          │
│  • 数据库连接管理 (MCP Server侧)                              │
│                                                              │
│  ❌ 可废弃/降级为回退:                                       │
│  • SchemaManager嵌入索引 (降级为MCP不可用时的回退)            │
│  • MySQL直连 (降级为回退路径)                                 │
│  • SQL_GENERATION_PROMPT完整版 (部分场景简化)                 │
│  • DomainClassifier主路径 (降级为MCP Tool推荐的辅助)         │
│                                                              │
├─────────────────────────────────────────────────────────────┤
│                    WMS MCP Server (外部)                      │
│                                                              │
│  提供:                                                       │
│  • 13+ 预构建只读查询Tool (库存/商品/入库/出库/分析)          │
│  • execute_sql_readonly (受控动态SQL)                         │
│  • 内置安全检查 (禁止DML/DDL, 自动LIMIT, 30s超时)            │
│  • 认证鉴权 (X-API-Key)                                      │
│  • 健康检查 (ping/health)                                    │
└─────────────────────────────────────────────────────────────┘
```

---

## Step 3: 迁移方案设计

### 3.1 MCP 接入架构

```
┌──────────────────────────────────────────────────────────────────┐
│  WMSRAGV2 (本项目)                                               │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  Config Layer (config.py)                                   │  │
│  │  + mcp_enabled: bool = True                                 │  │
│  │  + mcp_base_url: str = "http://localhost:8922/mcp"          │  │
│  │  + mcp_api_key: str = ""                                    │  │
│  │  + mcp_timeout: float = 60.0                                │  │
│  │  + mcp_fallback_to_local: bool = True                       │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  MCP Client Layer (新增: core/mcp_client.py)                │  │
│  │                                                              │  │
│  │  class WmsMcpClient:  (复用 MCP Guide 第4节代码)             │  │
│  │    • call_tool(name, arguments) → dict                      │  │
│  │    • list_tools() → list[dict]                              │  │
│  │    • ping() → bool                                          │  │
│  │    • health() → dict                                        │  │
│  │                                                              │  │
│  │  class McpClientManager:  (新增: 连接池+健康检查缓存)       │  │
│  │    • get_client() → WmsMcpClient (单例)                     │  │
│  │    • is_available() → bool (缓存30s)                        │  │
│  │    • refresh_tools_cache() → list[dict]                     │  │
│  │    • get_tool_descriptions() → str (供LLM选择)              │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  MCP Dispatch Layer (修改: orchestrator/dispatch.py)        │  │
│  │                                                              │  │
│  │  + dispatch_to_mcp(question) → dict                         │  │
│  │    • 检查 MCP availability                                   │  │
│  │    • LLM 选择 Tool (基于Tool描述)                            │  │
│  │    • 调用 MCP Tool                                           │  │
│  │    • 结果格式化为统一输出                                     │  │
│  │                                                              │  │
│  │  修改 DISPATCH_MAP:                                          │  │
│  │    "nl2sql" → dispatch_to_nl2sql (保留为回退)               │  │
│  │    "mcp"    → dispatch_to_mcp (新增)                         │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  MCP Agent (新增: agents/graph_mcp.py)                      │  │
│  │                                                              │  │
│  │  LangGraph 节点:                                             │  │
│  │    [1] tool_select_node:                                     │  │
│  │        LLM选择MCP Tool + 填参数                              │  │
│  │        (使用 McpClientManager.get_tool_descriptions())       │  │
│  │    [2] mcp_call_node:                                        │  │
│  │        调用 WmsMcpClient.call_tool()                         │  │
│  │    [3] result_format_node:                                   │  │
│  │        MCP返回 → 统一 {columns, rows, total} 格式            │  │
│  │    [4] insight_generate_node: (复用现有)                     │  │
│  │        LLM洞察生成                                            │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  Fallback Manager (新增: core/fallback.py)                  │  │
│  │                                                              │  │
│  │  async def query_with_fallback(question):                    │  │
│  │    try:                                                      │  │
│  │      return await dispatch_to_mcp(question)                  │  │
│  │    except McpUnavailableError:                               │  │
│  │      logger.warning("MCP不可用, 回退到本地NL2SQL")           │  │
│  │      return await dispatch_to_nl2sql(question)               │  │
│  │    except McpToolError as e:                                 │  │
│  │      if is_recoverable(e):                                   │  │
│  │        return await dispatch_to_nl2sql(question)             │  │
│  │      raise                                                   │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### 3.2 数据流 (MCP Path)

```
用户: "502620的库存情况，有没有临期的？"
  │
  ▼
[Orchestrator] HybridRouter.route()
  → intent="data_query", routed_to="mcp"
  │
  ▼
[dispatch_to_mcp]
  │
  ├─ [1] McpClientManager.is_available()
  │     → ping() → True (缓存30s)
  │
  ├─ [2] LLM Tool Selection (新增Prompt: MCP_TOOL_SELECT_PROMPT)
  │     输入: 用户问题 + MCP Tool列表(名称+描述+参数)
  │     输出: [
  │       {tool: "query_inventory_by_sku", args: {sku_code:"502620", limit:100}},
  │       {tool: "get_stock_warning", args: {warning_type:"near_expiry", near_expiry_days:30}}
  │     ]
  │
  ├─ [3] 并行调用 MCP Tools
  │     ├─ WmsMcpClient.call_tool("query_inventory_by_sku", {sku_code:"502620"})
  │     │   → {total: 3, items: [{location_code:"06080816", stork_count:1452, ...}, ...]}
  │     └─ WmsMcpClient.call_tool("get_stock_warning", {warning_type:"near_expiry", near_expiry_days:30})
  │         → {total: 0, items: []}
  │
  ├─ [4] Result Format (Adapter)
  │     MCP items → 统一 {columns: [...], rows: [[...], ...], total: N}
  │     (为兼容现有前端/Insight生成)
  │
  └─ [5] Insight Generate (复用现有)
        INSIGHT_GENERATION_PROMPT.format(question=..., query_result=...)
        LLM → parse_insight()
  │
  ▼
返回 OrchestratorResponse {sql: "(MCP预构建查询)", data: {...}, insight: {...}}
```

### 3.3 Tool 调用链设计

```
优先级策略:
  Level 1: 预构建Tool匹配 (query_inventory_by_sku, get_stock_warning, ...)
           → LLM选择Tool + 填参数
           → MCP执行
           → 最多2-3个Tool并行调用

  Level 2: 预构建Tool不匹配 → execute_sql_readonly
           → LLM生成SQL (复用SQL_GENERATION_PROMPT, 简化)
           → MCP执行 (带自动安全检查)

  Level 3 (回退): MCP不可用 → 本地NL2SQL管线
           → 现有5步流程完整保留
```

**Tool选择LLM Prompt设计要点:**
- 输入MCP Tool列表 (名称、描述、参数schema)
- 输入用户问题
- 输出JSON: `[{tool: str, args: dict}, ...]`
- 约束: 最多3个Tool, 优先用预构建Tool, `execute_sql_readonly`仅当预构建Tool不足时使用

### 3.4 错误处理机制

```
错误分类:
┌─────────────────┬──────────────────┬──────────────────────────┐
│ 错误类型         │ 处理策略          │ 用户体验                  │
├─────────────────┼──────────────────┼──────────────────────────┤
│ MCP连接失败      │ 立即回退到本地     │ 透明, 用户无感知          │
│ (ConnectError)  │ NL2SQL管线        │ (可能稍慢)               │
├─────────────────┼──────────────────┼──────────────────────────┤
│ MCP认证失败      │ 记录ERROR日志     │ 回退到本地NL2SQL          │
│ (401/403)       │ + 告警           │ + 后台通知管理员          │
├─────────────────┼──────────────────┼──────────────────────────┤
│ MCP超时          │ 重试1次           │ 超时前: loading状态       │
│ (ReadTimeout)   │ → 仍超时则回退    │ 回退后: 透明切换          │
├─────────────────┼──────────────────┼──────────────────────────┤
│ MCP Tool错误     │ 记录错误详情      │ 返回友好错误消息          │
│ (参数不对等)     │ → 尝试本地NL2SQL  │ + 可能的追问建议          │
├─────────────────┼──────────────────┼──────────────────────────┤
│ SQL安全拒绝      │ 不执行            │ 明确告知用户              │
│ (MCP返回         │ → 提示用户修改    │ SQL被拒绝的原因           │
│  VALIDATION_ERROR)│                  │                          │
├─────────────────┼──────────────────┼──────────────────────────┤
│ 本地回退也失败   │ 记录完整trace     │ 返回通用错误              │
│                 │ + 关联MCP+本地错误│ + 建议联系管理员          │
└─────────────────┴──────────────────┴──────────────────────────┘
```

### 3.5 回退机制 (Circuit Breaker 模式)

```
状态机:
  ┌──────────┐     连续失败N次     ┌──────────┐
  │  CLOSED  │ ─────────────────→ │  OPEN    │
  │ (用MCP)  │                    │ (跳过MCP) │
  └──────────┘                    └────┬─────┘
       ↑                               │
       │      冷却时间到               │
       └───────────────────────────────┘
                  ↓
          ┌──────────────┐
          │  HALF_OPEN   │
          │ (试探1次MCP) │
          └──┬────────┬──┘
             │        │
         成功│        │失败
             ↓        ↓
         CLOSED    OPEN (重置冷却)

配置:
  failure_threshold: 3      # 连续失败3次 → OPEN
  cooldown_seconds: 60      # 冷却60s → HALF_OPEN
  health_check_interval: 30 # 后台每30s ping一次

回退触发条件:
  1. MCP Client ping() 返回 False
  2. MCP call_tool() 连续失败达到阈值
  3. MCP 超时 (超过 mcp_timeout)
  4. 配置项 mcp_enabled = False (手动关闭)
```

### 3.6 监控方案

```
指标采集:
┌──────────────────┬──────────────────┬──────────────────────────┐
│ 指标              │ 来源              │ 用途                      │
├──────────────────┼──────────────────┼──────────────────────────┤
│ mcp_call_total   │ dispatch_to_mcp  │ MCP调用总量               │
│ mcp_call_success │ dispatch_to_mcp  │ 成功率                   │
│ mcp_call_latency │ dispatch_to_mcp  │ P50/P95/P99延迟          │
│ mcp_fallback_rate│ fallback.py      │ 回退频率(应<5%)          │
│ mcp_tool_usage   │ dispatch_to_mcp  │ 各Tool使用分布            │
│ circuit_state    │ fallback.py      │ 熔断器状态变化            │
│ mcp_auth_errors  │ WmsMcpClient     │ 认证失败次数              │
└──────────────────┴──────────────────┴──────────────────────────┘

Trace 扩展:
  Span: "mcp.tool_select" (LLM Tool选择)
  Span: "mcp.call_tool.{tool_name}" (每次MCP调用)
  Span: "mcp.result_format" (格式转换)
  Span: "nl2sql.fallback" (回退触发时)

日志:
  INFO: MCP调用成功 + 耗时 + Tool名称
  WARNING: MCP回退触发 + 原因
  ERROR: MCP连续失败 + 熔断器打开
  ERROR: MCP认证失败 (需人工处理)
```

---

## Step 4: 迭代规划

### Iteration 0: 基础设施准备 (MCP Client + 配置)

**目标:** 建立MCP连接能力，不影响现有业务

**修改文件:**
| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/core/config.py` | 修改 | 新增 `mcp_enabled`, `mcp_base_url`, `mcp_api_key`, `mcp_timeout`, `mcp_fallback_to_local` |
| `backend/app/core/mcp_client.py` | **新增** | `WmsMcpClient` + `McpClientManager` (复用MCP Guide第4节代码, 增加健康检查缓存) |
| `.env.example` | 修改 | 新增 MCP 相关环境变量 |
| `backend/requirements.txt` | 修改 | 确认 `httpx` 依赖 (已有) |

**测试策略:**
- 单元测试: `WmsMcpClient.call_tool()` mock MCP Server响应
- 单元测试: `McpClientManager.is_available()` 健康检查缓存逻辑
- 单元测试: `McpClientManager.get_tool_descriptions()` 格式化输出
- 集成测试: 真实MCP Server连接测试 (标记 `@pytest.mark.mcp`)

**风险:** 低 — 纯新增代码, 不影响现有路径

---

### Iteration 2: MCP Tool 选择 + 预构建Tool接入 + QueryService 统一

**目标:** LLM能根据用户问题选择正确的MCP Tool并调用；QueryService 和 Orchestrator dispatch 统一走 MCP 优先路径

**修改文件:**
| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/agents/prompts_sql.py` | 修改 | 新增 `MCP_TOOL_SELECT_PROMPT` |
| `backend/app/agents/graph_mcp.py` | **新增** | LangGraph图: tool_select → mcp_call → result_format |
| `backend/app/orchestrator/dispatch.py` | 修改 | 新增 `dispatch_to_mcp()`，修改 `DISPATCH_MAP` |
| `backend/app/core/agent_state.py` | 修改 | 新增 `MCPAgentState` |
| `backend/app/services/query_service.py` | 修改 | `natural_query()` 新增 MCP 优先路径，替换旧的 `use_langgraph` 分支逻辑 |

**测试策略:**
- 单元测试: `MCP_TOOL_SELECT_PROMPT` 格式化正确
- 单元测试: `graph_mcp` 各节点函数 (mock MCP Client)
- 单元测试: `dispatch_to_mcp()` 端到端 (mock MCP)
- 单元测试: `QueryService.natural_query()` MCP路径 (mock)
- 集成测试: 真实MCP Tool调用 (库存查询、预警查询等)
- Eval扩展: 新增 `datasets/mcp_queries.json` 覆盖MCP Tool选择准确性

**风险:** 中 — LLM Tool选择可能不准确, 需要prompt调优；QueryService 重构需保持响应格式兼容

---

### Iteration 3: 三级回退链 + Circuit Breaker

**目标:** 实现 MCP → LangGraph NL2SQL → QueryAgent 三级回退链，MCP不可用时自动降级

**回退链:**
```
[1] MCP Path (graph_mcp)       ← 主路径
      ↓ 失败
[2] LangGraph NL2SQL (graph_nl2sql) ← 本地回退
      ↓ 失败
[3] QueryAgent (query_agent)   ← 最深回退 (保留不动)
```

**修改文件:**
| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/core/fallback.py` | **新增** | `query_with_fallback()` + CircuitBreaker状态机 + 三级链 |
| `backend/app/orchestrator/dispatch.py` | 修改 | `dispatch_to_nl2sql`作为第二级回退，新增 `dispatch_to_query_agent` 作为第三级 |
| `backend/app/services/query_service.py` | 修改 | `natural_query()` 整合三级回退逻辑，移除旧 `use_langgraph` 分支 |

**测试策略:**
- 单元测试: CircuitBreaker OPEN/CLOSED/HALF_OPEN状态转换
- 单元测试: MCP失败→LangGraph回退触发
- 单元测试: LangGraph失败→QueryAgent回退触发
- 单元测试: MCP超时→回退触发
- 集成测试: 模拟MCP不可用场景 (关停MCP Server)
- L2测试: 真实场景端到端回退

**风险:** 中 — 三级回退链输出格式需统一适配器确保兼容；`use_langgraph` flag 废弃需确认无其他引用

---

### Iteration 4: 监控 + Trace + 日志

**目标:** MCP调用全链路可观测

**修改文件:**
| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/core/tracing.py` | 修改 | 扩展TracingCallbackHandler覆盖MCP span |
| `backend/app/core/mcp_client.py` | 修改 | 增加metrics埋点 |
| `backend/app/core/fallback.py` | 修改 | 增加circuit state变化日志 |
| `backend/app/api/logs.py` | 修改 | 可选: MCP状态查询端点 |

**测试策略:**
- 单元测试: Span创建/结束正确
- 集成测试: Trace JSONL输出包含MCP span
- 手动测试: 查询`data/traces/`确认MCP调用记录

**风险:** 低 — 扩展现有体系

---

### Iteration 5: 前端适配（两个页面）

**目标:** OrchestratorPage 和 QueryPage 都支持 MCP 查询结果展示（透明模式）

**修改文件:**
| 文件 | 操作 | 说明 |
|------|------|------|
| `frontend/vue-app/src/api/orchestrator.js` | 修改 | 确认MCP响应格式兼容 |
| `frontend/vue-app/src/views/OrchestratorPage.vue` | 修改 | 新增 `routed_to="mcp"` 渲染逻辑；source 标记展示路由来源 (mcp/local) |
| `frontend/vue-app/src/views/QueryPage.vue` | 修改 | 新增 source 标记展示（mcp/local/langgraph/queryagent），用户无感知自动切换 |
| `frontend/vue-app/src/stores/query.js` | 修改 | 响应中解析 source 字段，传递给 UI 展示 |
| `frontend/vue-app/src/api/query.js` | 修改 | 确认 MCP 响应格式兼容 |

**测试策略:**
- 手动测试: OrchestratorPage 输入库存查询 → 验证 MCP 结果 + source 标记
- 手动测试: QueryPage 输入查询 → 验证 source 标记展示 (mcp/local)
- 手动测试: 关闭 MCP → 验证回退到 LangGraph → source 标记变为 local
- 手动测试: 关闭 MCP + LangGraph → 验证回退到 QueryAgent → source 标记变为 queryagent

**风险:** 低 — 透明模式，UI 改动小；主要是 source 标记展示

---

### Iteration 6: 回归测试 + Eval 扩展

**目标:** 确保MCP路径不破坏现有功能

**修改文件:**
| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/eval/nl2sql/datasets/mcp_queries.json` | **新增** | MCP Tool选择评估用例 |
| `backend/eval/nl2sql/runner.py` | 修改 | 支持 `--mcp` 模式 |
| `backend/tests/test_mcp_client.py` | **新增** | MCP Client单元测试 |
| `backend/tests/test_mcp_fallback.py` | **新增** | 回退机制单元测试 |
| `backend/tests/test_orchestrator_l2.py` | 修改 | 扩展L2测试覆盖MCP路径 |

**测试策略:**
- 跑完整 `nl2sql eval` 套件 (本地路径基线)
- 跑 MCP 路径 eval 套件
- 对比 MCP vs 本地 准确率差异
- 跑 `test_orchestrator_router.py` + `test_orchestrator_l2.py` 确认未回归

**风险:** 中 — 需要MCP Server可用才能跑完整eval

---

### 迭代依赖关系

```
Iteration 0 (MCP Client)
    ↓
Iteration 2 (Tool选择+预构建Tool)
    ↓
Iteration 3 (回退机制)
    ↓
Iteration 4 (监控)
    ↓
Iteration 5 (前端)
    ↓
Iteration 6 (回归测试)
```

---

## 附录: 关键决策点

### A. MySQL直连保留 vs 完全委托MCP

**推荐:** 保留MySQL直连作为回退路径，逐步将主路径迁移到MCP。
- 回退确保高可用
- MCP不可用时不阻塞业务
- `config.py` 中 `mcp_fallback_to_local=True` 控制

### B. DomainClassifier保留 vs 废弃

**推荐:** 保留作为MCP Tool选择的辅助信号，但不作为主路径。
- embedding分类快速 (无LLM开销)
- 可作为LLM Tool选择的hint输入
- 在离线/MCP不可用场景完整保留

### C. SQL_GENERATION_PROMPT保留 vs 简化

**推荐:** 保留完整Prompt，但在MCP路径中只用于 `execute_sql_readonly` 场景。
- 预构建Tool覆盖80%查询 → 不需要SQL生成
- 复杂自定义查询 → 仍需SQL生成能力
- Prompt中的业务规则对LLM理解MCP Tool也有帮助

### D. Feature Flag 策略

**推荐:** 新增 `mcp_enabled` flag，与现有 `use_langgraph` 独立。
- `mcp_enabled=True` + MCP可用 → MCP路径
- `mcp_enabled=True` + MCP不可用 → 本地回退
- `mcp_enabled=False` → 完全本地 (现有行为)
- 可在运行时通过环境变量切换，无需重启

---

> **文档版本**: v1.0
> **分析完成时间**: 2026-06-24
> **下一步**: 等待用户审核确认后进入实现阶段
