# WMS RAG V2 系统概述

## 系统定位

企业级知识库问答系统，支持：
- **RAG 检索增强生成** — 多知识库隔离 + 混合检索（向量 + BM25 + RRF 融合 + Reranker 精排）
- **NL2SQL 自然语言数据查询** — LangGraph 编排的 NL2SQL 管线 + MCP Data Copilot 预构建查询
- **PM 方案工作室** — 多阶段方案设计与迭代
- **智能编排** — Hybrid Router → Planner → Executor 跨模块管线
- **查询追踪** — 每次查询的三层展开详情（概览/运维/开发），含回退路径可视化

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 + Pinia + TailwindCSS + Vite |
| 后端 | FastAPI + SQLAlchemy + LlamaIndex + LangChain + LangGraph |
| 可观测性 | 本地 Trace (JSON Lines) + Loguru 结构化日志 + LangFuse (可选) |
| LLM | DeepSeek/OpenAI/Claude (可配置切换) |
| Embedding | BAAI/bge-small-zh-v1.5 (本地加载, 512维) |
| Reranker | bge-reranker-v2-m3 (cross-encoder 精排) |
| 元数据库 | SQLite (kb.db, query_history.db) |
| 业务数据库 | MySQL (aiomysql 连接池) |
| 向量库 | ChromaDB (PersistentClient, 按知识库隔离 Collection) |
| MCP 协议 | MCP 2024-11-05 Streamable HTTP (SSE + Session) |

## 架构

```
Frontend (Vue3 + Vite, :5173)
    ↓ HTTP/SSE (/api → proxy → :8912)
FastAPI Backend (:8912)
    │
    ├── Orchestrator → HybridRouter → Planner → Executor (hybrid pipeline)
    │
    ├── DataQueryGateway (executor链: MCP → Local → QueryAgent)
    │   ├── McpExecutor → MCP Server (:8922) — 15个预构建WMS Tool
    │   ├── LocalExecutor → graph_nl2sql — LangGraph NL2SQL
    │   └── QueryAgentExecutor — 旧版兜底 (@deprecated)
    │
    ├── RAG Service
    │   ├── graph_rag — LangGraph 检索编排
    │   │   ├── Query 改写 (LLM)
    │   │   ├── 并行检索: ChromaDB 向量 + BM25 (jieba 分词)
    │   │   ├── RRF 融合 (Reciprocal Rank Fusion, k=60)
    │   │   └── Reranker 精排 (bge-reranker-v2-m3 cross-encoder)
    │   ├── document_processor — 行业自适应分块 + IMG 保护
    │   └── index_builder — ChromaDB 向量索引构建
    │
    ├── Schema Manager — MySQL Schema Embedding 索引
    │   └── 语义搜索相关表/字段 → NL2SQL schema context
    │
    ├── MCP Client — WmsMcpClient + McpClientManager + CircuitBreaker
    │
    └── PM Service → ChromaDB + LLM
    ↓
SQLite (元数据: kb.db, query_history.db) + MySQL (业务数据) + MCP Server (:8922)
```

## 前端路由

| 路径 | 页面 | 说明 |
|------|------|------|
| `/orchestrator` | OrchestratorPage | 智能编排（跨模块混合管线） |
| `/chat` | ChatPage | 智能对话问答（RAG 检索增强） |
| `/knowledge` | KnowledgePage | 知识库管理（上传/预览/标签/统计） |
| `/query` | QueryPage | 数据查询（MCP/NL2SQL 统一入口） |
| `/pm-studio` | PMStudioPage | PM 方案工作室（多阶段设计） |
| `/settings` | SettingsPage | 系统设置 |
| `/logs` | LogsPage | 日志查看 + 查询追踪 |

## 核心技术特性

### 1. 数据查询网关（DataQueryGateway）

三级 Executor 回退链 + 熔断器保护。详见 [Data Query Gateway](components/data-query-gateway.md)。

**亮点**:
- MCP eligibility 纯规则判断（零 LLM 开销），含 Unicode 安全的正则实体识别
- CircuitBreaker 区分故障类型：仅服务级故障计入，业务错误不触发熔断
- 保守回退策略：未知错误默认允许回退，避免分类遗漏导致查询完全失败
- Trace JSON 三层视图（leader/ops/debug），一次查询满足管理/运维/开发三个角色

### 2. MCP Client 架构

完整的 MCP 2024-11-05 协议客户端实现。详见 [MCP Client Architecture](components/mcp-client-architecture.md)。

**亮点**:
- Phase 2 统一错误码体系，预留 Phase 3 扩展点
- SSE + JSON 双格式响应解析
- McpClientManager: Tool 缓存 (5min TTL) + 健康检查缓存 (30s TTL)
- Tool 领域自动推断 + LLM Tool 选择 prompt 生成
- 所有外部依赖通过 DI 注入，支持完整 mock 测试

### 3. 行业自适应分块策略

按知识库行业动态选择分块参数，保护 IMG 标记不被切断。详见 [ADR-011](adr/adr-011-chunk-strategy-optimization.md)。

**亮点**:
- 5 档行业预设（general/wms/medical/legal/finance），chunk_size 300~1000
- chunk_overlap 非线性缩放（≈ chunk_size × 15~20%）
- IMG token 占位符法：分块前替换 → 切分 → 分块后还原，保证图片标记完整性
- 检索参数联动：top_k 和 BM25 开关随行业调整

### 4. Schema Embedding 索引

将 MySQL 表/字段元数据向量化，支持自然语言语义搜索相关 Schema。详见 [Schema Manager](#schema-manager)。

**亮点**:
- 表级 + 字段级双层 embedding，余弦相似度搜索
- 字段白名单模式（通过 semantic-layer.md 控制），减少无关字段干扰
- 中文列名映射双路兜底：MySQL tfrmdataprop 表 → tfrmdataprop.json 文件
- 支持 table_filter 限定搜索范围，适配领域分类后的精准匹配

### 5. 混合 RAG 检索管线

多阶段检索 + 全链路降级。详见 [rag-workflow.md](workflows/rag-workflow.md)。

**亮点**:
- Query 改写 → 并行检索（向量 + BM25）→ RRF 融合 → Reranker 精排
- 每个阶段独立降级：改写失败用原 query，BM25 失败仅用向量，Reranker 不可用退到 RRF 分数
- bge-reranker-v2-m3 cross-encoder 批处理打分，sigmoid 分数排序

### 6. 本地可观测性体系

两层零外部依赖的可观测性。详见 [ADR-005](adr/adr-005-local-tracing.md)。

**亮点**:
- Layer 1: Loguru 结构化日志 — 控制台彩色 + JSON lines 文件按日轮转
- Layer 2: Trace/Span 系统 — 异步批量写入，支持 sync+async 双模式
- LangChain Callback 自动捕获 Graph 节点 span，零侵入
- 6 个 LLM 调用点全量捕获 token usage

### 7. 智能编排（Orchestrator）

Contract-first + DI 架构的跨模块混合管线。详见 [ADR-009](adr/adr-009-orchestrator-hybrid-pipeline.md)。

**亮点**:
- RuleEngine (HYBRID_PATTERNS 三重约束) → MiniLLMRouter → HybridRouter 级联路由
- Planner 内联 validator (5条规则)，PlanStep/ExecutionPlan Pydantic contract
- Executor 纯函数 async for 循环，DI 注入 dispatch map
- 零外部依赖，56 tests，7.7s

## 模块路由

| 模块 | 后端入口 | 前端入口 | 规范文档 |
|------|---------|---------|---------|
| **数据查询 (Gateway)** | `backend/app/core/data_query_gateway.py` | `QueryPage.vue` | [Gateway Spec](components/data-query-gateway.md) |
| **MCP Client** | `backend/app/core/mcp_client.py` | — (透明接入) | [MCP Client Spec](components/mcp-client-architecture.md) |
| **智能编排** | `backend/app/api/orchestrator.py` | `OrchestratorPage.vue` | [ADR-009](adr/adr-009-orchestrator-hybrid-pipeline.md) |
| **MCP Data Copilot** | `backend/app/agents/graph_mcp.py` | — (通过 QueryPage/Orchestrator 透明接入) | [ADR-010](adr/adr-010-mcp-data-copilot-integration.md) |
| NL2SQL (Local) | `backend/app/agents/graph_nl2sql.py` | — (LocalExecutor 回退路径) | [nl2sql-workflow.md](workflows/nl2sql-workflow.md) |
| 知识库 | `backend/app/api/documents.py` | `KnowledgePage.vue` | [rag-workflow.md](workflows/rag-workflow.md) |
| 智能问答 | `backend/app/api/chat.py` | `ChatPage.vue` | [chat-workflow.md](workflows/chat-workflow.md) |
| PM方案 | `backend/app/api/pm_solution.py` | `PMStudioPage.vue` | [pmstudio-workflow.md](workflows/pmstudio-workflow.md) |
| 查询追踪 | `backend/app/api/logs.py` | `LogsPage.vue` | — |
| 系统设置 | `/config` API | `SettingsPage.vue` | — |
| 日志查看 | `backend/app/api/logs.py` | `LogsPage.vue` | — |
| 向量库管理 | `backend/app/api/vector_admin.py` | — | — |

## Schema Manager

`backend/app/core/schema_manager.py` 负责从 MySQL 业务库提取表/字段元数据，生成 embedding 索引，为 NL2SQL 提供语义 schema 检索。

### 核心流程

```
MySQL 业务库
  ├── INFORMATION_SCHEMA.TABLES — 表信息
  ├── INFORMATION_SCHEMA.COLUMNS — 字段信息
  └── tfrmdataprop — 中文显示名映射
        │
        ▼
  SchemaManager.load_schema_from_db()
        │
        ▼
  _build_schema_texts()
  ├── "表: wms_inventory (库存表) - 存储实时库存数据"
  └── "字段: wms_inventory.sku_code (SKU编码) 类型:varchar - 商品唯一标识"
        │
        ▼
  build_embedding_index()
  └── bge-small-zh-v1.5 → 512维向量 → self._schema_embeddings
        │
        ▼
  search_relevant_schema(query, top_k=5)
  └── 余弦相似度 → 相关表+字段 → schema_context → Prompt 注入
```

### 字段白名单模式

`_format_schema_context()` 通过 `semantic-layer.md` 的 `get_essential_columns()` 实现字段白名单：
- 有白名单时：仅输出白名单字段 + JOIN 键
- 无白名单时：回退输出全部字段
- 效果：减少 prompt token 消耗，降低 LLM 选错字段的概率

---

## 配置参数

| 参数 | 默认值 | 说明 |
|------|------|------|
| `data_dir` | ./data | 数据目录 |
| `sqlite_url` | sqlite:///./data/kb.db | SQLite 连接 |
| `mysql_host` | - | MySQL 主机 |
| `mysql_port` | 3306 | MySQL 端口 |
| `llm_provider` | deepseek | LLM 提供商 |
| `industry_type` | general | 行业类型 (影响分块策略) |
| `embedding_model` | BAAI/bge-small-zh-v1.5 | Embedding 模型 |
| `mcp_enabled` | true | 是否启用 MCP 主路径 |
| `mcp_base_url` | http://localhost:8922 | MCP Server 地址 |
| `mcp_timeout` | 60.0 | MCP 请求超时 (秒) |
| `retrieval_top_k` | 5 | RAG 最终返回结果数 |
| `reranker_top_k_multiplier` | 3 | Reranker 候选池倍数 |
| `use_hybrid_retrieval` | true | 是否启用 BM25 混合检索 |
| `use_query_rewrite` | true | 是否启用 LLM Query 改写 |
| `use_reranker` | true | 是否启用 Reranker 重排序 |

## API 统一规范

- 前缀：`/api/v1/{module}`
- 错误格式：`{"detail": "错误描述"}` 或 `{"success": false, "error": "描述"}`
- 时间格式：`%Y-%m-%d %H:%M:%S`
- 用户可见文本：中文

## 边界场景

| 场景 | 处理 |
|------|------|
| 知识库无文档 | LLM 直接回答（不走 RAG） |
| 文件类型不支持 | 400 错误 (FILE_TYPE_INVALID) |
| 文件超 10MB | 400 错误 (FILE_TOO_LARGE) |
| SQL 安全校验失败 | 拒绝执行，不回退 |
| MCP Server 不可用 | CircuitBreaker 熔断 → 回退 LocalExecutor |
| 向量索引损坏 | 启动自动健康检查 + 手动 rebuild |
| Decimal 序列化 | 自动转 float |
| PM 阶段回溯 | 删除后续阶段数据 |
| Query 改写失败 | 降级使用原始 query |
| BM25 索引构建失败 | 降级仅使用向量检索 |
| Reranker 加载失败 | 降级使用 RRF 融合分数排序 |

## 规范文件索引

### ADR（架构决策记录）
| 文件 | 决策 |
|------|------|
| [ADR-001](adr/ADR-001-rag-design.md) | RAG 系统整体设计 |
| [ADR-002](adr/ADR-002-nl2sql-强制查询规则.md) | NL2SQL 强制查询规则 |
| [ADR-003](adr/adr-003-langgraph-migration.md) | LangGraph 迁移决策 |
| [ADR-003-hybrid](adr/ADR-003-hybrid-retrieval.md) | 混合检索策略 |
| [ADR-004](adr/adr-004-nl2sql-优化.md) | NL2SQL 优化 |
| [ADR-005](adr/adr-005-local-tracing.md) | 本地日志跟踪系统 |
| [ADR-006](adr/adr-006-chat-intent-rejection.md) | Chat 意图拒识 |
| [ADR-007](adr/adr-007-pm-langgraph-migration.md) | PM LangGraph 迁移 |
| [ADR-008](adr/adr-008-chat-pm-eval.md) | Chat/PM 评估标准 |
| [ADR-009](adr/adr-009-orchestrator-hybrid-pipeline.md) | 智能编排 Hybrid Pipeline |
| [ADR-010](adr/adr-010-mcp-data-copilot-integration.md) | MCP Data Copilot 接入 |
| [ADR-011](adr/adr-011-chunk-strategy-optimization.md) | 行业自适应分块策略 |

### 组件规范
| 文件 | 说明 |
|------|------|
| [MCP Client Architecture](components/mcp-client-architecture.md) | MCP Python 客户端架构 |
| [Data Query Gateway](components/data-query-gateway.md) | 数据查询网关架构 |

### 工作流规范
| 文件 | 说明 |
|------|------|
| [rag-workflow.md](workflows/rag-workflow.md) | 知识库管理完整工作流 |
| [chat-workflow.md](workflows/chat-workflow.md) | 智能问答工作流 |
| [nl2sql-workflow.md](workflows/nl2sql-workflow.md) | NL2SQL 工作流 |
| [pmstudio-workflow.md](workflows/pmstudio-workflow.md) | PM 方案工作室工作流 |

### 业务规则
| 文件 | 说明 |
|------|------|
| [sql-rules.md](business-rules/sql-rules.md) | SQL 安全与格式约束 |
| [rag-rules.md](business-rules/rag-rules.md) | RAG 检索规则 |
| [semantic-layer.md](nl2sql/semantic-layer.md) | 语义层映射规则（运行时动态加载） |

## NL2SQL 模块规范指引

NL2SQL 模块运行时遵循以下规范文件（优先级从高到低）：

1. `spec/nl2sql/semantic-layer.md` — 业务概念到数据库表的映射规则（运行时动态加载，修改无需重启）
2. `spec/business-rules/sql-rules.md` — SQL 安全与格式约束（运行时动态加载）
3. `spec/workflows/nl2sql-workflow.md` — 完整工作流参考
4. `spec/components/data-query-gateway.md` — Gateway 架构（Executor 链 + 回退策略）

开发 NL2SQL 模块时，必须以上述文件为权威参考。

---

## 版本

- **当前版本**: 2.2.0
- **更新日期**: 2026-07-07
- **主要更新**:
  - Phase 2: MCP Data Copilot 接入（15 个预构建 WMS Tool）
  - Phase 2: DataQueryGateway 三级 Executor 回退链 + CircuitBreaker
  - Phase 2: MCP Client 完整协议实现 + 错误码体系
  - 行业自适应分块策略（5 档行业配置 + IMG 标记保护）
  - 本地可观测性体系（两层零外部依赖）
  - Query 改写 → 混合检索 → RRF 融合 → Reranker 精排全链路
  - Schema Embedding 索引（语义搜索相关表/字段）
  - 查询追踪三层视图（概览/运维/开发）
