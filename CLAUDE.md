# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 常用命令

### 开发环境

```bash
# 一键启动/停止（Windows 双击 start.bat，或命令行）
start.bat           # 交互菜单：启动/停止/重启/状态
start.bat start     # 启动前后端
start.bat stop      # 停止
start.bat restart   # 重启

# 后端（手动启动，从 backend/ 目录）
pip install -r backend/requirements.txt
uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8912 --reload

# 前端（从 frontend/vue-app/ 启动）
npm run dev          # Vite 开发服务器，端口 5173，/api 自动代理到 :8912
npm run build        # 生产构建到 dist/
```

> **端口说明**: 开发环境使用 8912（非默认 8000/8812）。Windows Hyper-V 会保留 8807-8906 端口段，8912 在此范围外。`start.bat` 自动处理 Python Store 占位符和 PATH 问题。

### 测试

```bash
cd backend
pytest                          # 全部测试
pytest tests/ -k "test_name"    # 单个测试
```

### Docker 构建与推送（华为云 SWR）

```bash
# Windows 上构建 Linux 镜像并推送
docker buildx build --platform linux/amd64 --provenance=false --sbom=false \
  -t swr.cn-south-1.myhuaweicloud.com/ragai/ragv2:<版本号> --push .
```

`--provenance=false --sbom=false` 是必须的 — 华为云 SWR 不支持新 manifest 格式。

### Docker Compose 本地部署

```bash
docker-compose up -d
```

## 架构概览

```
Frontend (Vue3 + Vite, :5173)
    ↓ /api → proxy → :8912
FastAPI Backend (:8912)
    ├── DataQueryGateway (统一查询入口, executor链: MCP → Local → QueryAgent)
    │   ├── McpExecutor → MCP Server (:8922) — 15 个预构建 WMS Tool
    │   ├── LocalExecutor → graph_nl2sql (LangGraph NL2SQL)
    │   └── QueryAgentExecutor → query_agent (旧版兜底, @deprecated)
    ├── Orchestrator → Router → Planner → Executor (hybrid pipeline)
    ├── RAG Service → ChromaDB + LLM
    └── PM Service  → ChromaDB + LLM
    ↓
SQLite (元数据: kb.db, query_history.db) + MySQL (业务数据) + MCP Server (:8922)
```

> **Phase 2**: MCP Data Copilot 已接入。查询优先走 MCP 预构建 Tool（15个），失败自动回退 Local NL2SQL。
> **查询追踪**: `/logs` 页面 → "查询追踪" Tab，每次查询一条记录，展开显示三层详情（概览/运维/开发）。

后端入口 `backend/app/main.py` 使用 `lifespan` 管理启动/关闭：初始化数据目录、SQLite 表、向量索引健康检查、trace writer。路由前缀统一为 `/api/v1/{module}`。

### core/ 模块职责

| 模块 | 职责 |
|------|------|
| `config.py` | Pydantic Settings，自动检测前端 dist、reranker 模型路径 |
| `logging.py` | Loguru 结构化日志，控制台彩色 + JSON lines 文件按日轮转，通过 `ContextVar` 绑定 `trace_id` |
| `tracing.py` | 本地 trace 系统：TraceContext/Span，每个 HTTP 请求自动创建顶层 span，写入 `data/traces/` JSONL（可通过 `logs.py` API 查看） |
| `embedding.py` | BAAI/bge-small-zh-v1.5 本地加载，HF_ENDPOINT 镜像设置 |
| `vector_store.py` | ChromaDB 客户端管理，cosine 距离，collection 命名 `kb_documents_{kb_id}` |
| `llm_manager.py` | 多 LLM provider 支持（DeepSeek/OpenAI/Claude 可配置切换） |
| `db_mysql.py` | aiomysql 连接池管理（Data Copilot 用） |
| `schema_manager.py` | MySQL Schema Embedding 索引 — 从业务库提取表/字段元数据，生成 embedding 用于 NL2SQL schema 检索 |
| `semantic_rules.py` / `semantic_layer_loader.py` | 运行时动态加载 `spec/nl2sql/semantic-layer.md` |
| `domain_classifier.py` | NL2SQL 问题领域分类 |
| `sql_post_process.py` | SQL 生成后处理（格式修正等） |
| `agent_state.py` | LangGraph Agent 状态定义 |

### orchestrator/ 模块职责

| 模块 | 职责 |
|------|------|
| `router.py` | RuleEngine（关键词+DEFAULT_RULES+HYBRID_PATTERNS）→ MiniLLMRouter（LLM分类）→ HybridRouter（级联编排） |
| `planner.py` | PlanStep/ExecutionPlan schema + Planner class（LLM few-shot 生成执行计划 + 内联 validator + retry/fallback） |
| `executor.py` | `execute_plan()` 纯函数：按 plan 逐步 dispatch → 最后 synthesize。dispatch map DI 注入 |
| `dispatch.py` | `dispatch_to_rag/nl2sql/pm()` 封装各 graph 的 ainvoke() + `DISPATCH_MAP` |

**设计原则**: Contract-first（Planner 产出 ExecutionPlan → Executor 消费），DI 注入（`llm=None` / `dispatch=None`），纯函数优先（Executor 是 async for 循环）。

### 可观测性

- **日志**: Loguru，控制台彩色格式 + `data/logs/` JSONL（按日轮转，保留30天，error 保留90天）
- **Trace**: 本地 JSONL trace（`data/traces/`），每个 HTTP 请求自动创建 span，响应头带 `X-Trace-Id`
- **LangFuse**: 可选，通过 `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` 环境变量启用

### 关键 Feature Flag

- `use_langgraph: bool = False` — `config.py` 中控制。`false` 使用旧 Agent，`true` 使用 LangGraph 编排版本（Chat/PM/NL2SQL 均有 LangGraph 迁移 ADR）

## Spec 文件体系

`spec/` 目录按类型组织，开发前必须阅读对应 spec：

| 目录 | 内容 |
|------|------|
| `spec/adr/` | 架构决策记录（RAG 设计、NL2SQL 规则、混合检索、LangGraph 迁移、本地 Tracing 等） |
| `spec/workflows/` | 各模块完整工作流 |
| `spec/api/` | API 规范 |
| `spec/business-rules/` | SQL 安全规则、RAG 规则 |
| `spec/nl2sql/` | 语义层映射规则 |
| `spec/db/` | 数据库 schema（MySQL、SQLite、ChromaDB） |
| `spec/evals/` | 评估标准（NL2SQL、RAG、PM Studio） |
| `spec/system.md` | 全局系统概述 |

## 模块路由

| 模块 | 后端入口 | 前端入口 |
|------|---------|---------|
| **数据查询 (Gateway)** | `backend/app/core/data_query_gateway.py` | `frontend/vue-app/src/views/QueryPage.vue` |
| 智能编排 | `backend/app/api/orchestrator.py` → `orchestrator/` | `frontend/vue-app/src/views/OrchestratorPage.vue` |
| **MCP Data Copilot** | `backend/app/agents/graph_mcp.py` + `backend/app/core/mcp_client.py` | — (通过 QueryPage/Orchestrator 透明接入) |
| NL2SQL (Local) | `backend/app/agents/graph_nl2sql.py` | — (LocalExecutor 回退路径) |
| **查询追踪** | `backend/app/api/logs.py` (type=queries) + `backend/app/models/query_history.py` | `frontend/vue-app/src/views/LogsPage.vue` ("查询追踪" Tab) |
| 知识库 | `backend/app/api/documents.py` | `frontend/vue-app/src/views/KnowledgePage.vue` |
| 智能问答 | `backend/app/api/chat.py` | `frontend/vue-app/src/views/ChatPage.vue` |
| PM方案 | `backend/app/api/pm_solution.py` | `frontend/vue-app/src/views/PMStudioPage.vue` |
| 系统设置 | `/config` API | `frontend/vue-app/src/views/SettingsPage.vue` |
| 日志查看 | `backend/app/api/logs.py` | `frontend/vue-app/src/views/LogsPage.vue` |
| 向量库管理 | `backend/app/api/vector_admin.py` | — |

## MCP Data Copilot 配置 (Phase 2)

| 端口 | 服务 |
|------|------|
| **8912** | WMSRAGV2 后端 (FastAPI) |
| **8922** | MCP Data Copilot Server (独立 WMS MCP 服务) |
| **5173** | WMSRAGV2 前端 (Vite) |

**环境变量** (`.env`):
```bash
MCP_ENABLED=true                # 启用 MCP 主路径
MCP_BASE_URL=http://localhost:8922
MCP_API_KEY=gk-xxxx             # MCP Server API Key
MCP_TIMEOUT=60.0                # 请求超时 (秒)
```

**传输协议**: MCP 2024-11-05 Streamable HTTP (SSE + Session)。
**参考文档**: `docs/data-copilot-integration-guide.md`

## 关键约定

- 后端 API 前缀: `/api/v1/{module}`，错误格式 `{"detail": "..."}` 或 `{"success": false, "error": "..."}`
- 业务代码修改后，主动询问是否需要同步更新 `spec/` 下的对应规范文档
- NL2SQL 的语义层规则（`semantic-layer.md`）在运行时动态加载，修改后无需重启
- 前端 Vite dev server 通过 proxy 将 `/api` 和 `/images` 转发到 `http://localhost:8912`
- 前端 axios 默认 timeout 120s（首查询需冷启动 schema 索引和 LLM 连接）
- ChromaDB collection 命名: `kb_documents_{knowledge_id}`
- 日志获取: `get_logger("模块名")` — 自动绑定 `trace_id` 到每条日志
- 查询追踪: `query_history` 表 `trace_json` 列存储结构化追踪数据，`/logs` 页面可查看
- 所有用户可见文本使用中文
