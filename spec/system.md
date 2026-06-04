# WMS RAG V2 系统概述

## 系统定位

企业级知识库问答系统，支持：
- RAG 检索增强生成
- NL2SQL 自然语言数据查询
- PM 方案工作室（多阶段方案设计）

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 + Pinia + TailwindCSS + Vite |
| 后端 | FastAPI + SQLAlchemy + LlamaIndex |
| LLM | DeepSeek/OpenAI/Claude (可配置) |
| Embedding | BAAI/bge-small-zh-v1.5 |
| 元数据库 | SQLite |
| 业务数据库 | MySQL |
| 向量库 | ChromaDB |

## 架构

```
Frontend (Vue3)
    ↓ HTTP/SSE
FastAPI Backend
    ├── RAG Service → ChromaDB + LLM
    ├── Query Agent → MySQL + LLM  
    └── PM Service → ChromaDB + LLM
    ↓
SQLite (元数据) + MySQL (业务)
```

## 前端路由

| 路径 | 页面 | 说明 |
|------|------|------|
| `/chat` | ChatPage | 对话问答 |
| `/knowledge` | KnowledgePage | 知识库管理 |
| `/query` | QueryPage | 数据查询 |
| `/settings` | SettingsPage | 系统设置 |
| `/pm-studio` | PMStudioPage | PM方案工作室 |

## 配置参数

| 参数 | 默认值 | 说明 |
|------|------|------|
| `data_dir` | ./data | 数据目录 |
| `sqlite_url` | sqlite:///./data/kb.db | SQLite连接 |
| `mysql_host` | - | MySQL主机 |
| `mysql_port` | 3306 | MySQL端口 |
| `llm_provider` | deepseek | LLM提供商 |
| `industry_type` | general | 行业类型 |
| `embedding_model` | BAAI/bge-small-zh-v1.5 | Embedding模型 |

## API统一规范

- 前缀：`/api/v1/{module}`
- 错误格式：`{"detail": "错误描述"}` 或 `{"success": false, "error": "描述"}`
- 时间格式：`%Y-%m-%d %H:%M:%S`
- 中文：所有用户可见文本

## 边界场景

| 场景 | 处理 |
|------|------|
| 知识库无文档 | LLM直接回答 |
| 文件类型不支持 | 400错误 |
| 文件超10MB | 400错误 |
| SQL安全校验失败 | 拒绝执行 |
| 向量索引损坏 | 启动自动修复 |
| Decimal序列化 | 自动转float |
| PM阶段回溯 | 删除后续数据 |

## 版本

- 当前版本：2.0.0
- 更新日期：2026-06-04

## NL2SQL 模块规范指引

NL2SQL 模块运行时遵循以下规范文件（优先级从高到低）：

1. `spec/nl2sql/semantic-layer.md` — 业务概念到数据库表的映射规则（运行时动态加载）
2. `spec/business-rules/sql-rules.md` — SQL 安全与格式约束（运行时动态加载）
3. `spec/workflows/nl2sql-workflow.md` — 完整工作流参考

开发 NL2SQL 模块时，必须以上述文件为权威参考。
修改 `semantic-layer.md` 后无需重启服务，效果即时生效。