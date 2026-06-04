# CLAUDE.md

## Spec 文件优先级

本项目的所有开发必须遵循 `spec/` 目录下的规范文件。在修改任何模块前，先阅读对应的 spec：

| 模块 | Spec 文件 |
|------|----------|
| NL2SQL（数据查询） | `spec/nl2sql/semantic-layer.md`, `spec/business-rules/sql-rules.md`, `spec/workflows/nl2sql-workflow.md` |
| RAG（知识库） | `spec/workflows/rag-workflow.md` |
| Chat（智能问答） | `spec/workflows/chat-workflow.md` |
| PM（方案工作室） | `spec/workflows/pmstudio-workflow.md` |
| 全局 | `spec/system.md` |

## 模块路由

| 模块 | 后端入口 | 前端入口 |
|------|---------|---------|
| NL2SQL | `backend/app/agents/query_agent.py` | `frontend/vue-app/src/views/QueryPage.vue` |
| 知识库 | `backend/app/api/documents.py` | `frontend/vue-app/src/views/KnowledgePage.vue` |
| 智能问答 | `backend/app/api/chat.py` | `frontend/vue-app/src/views/ChatPage.vue` |
| PM方案 | `backend/app/api/pm_solution.py` | `frontend/vue-app/src/views/PMStudioPage.vue` |

## 关键约定

- 后端 API 前缀: `/api/v1/{module}`
- 业务代码修改后，主动询问是否需要同步更新 `spec/` 下的对应规范文档
- NL2SQL 的语义层规则（`semantic-layer.md`）在运行时动态加载，修改后无需重启
