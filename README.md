# WMS RAG V2 - 知识库智能问答系统

基于 LlamaIndex RAG + FastAPI + Vue 3 的企业知识库管理系统，支持多行业配置、知识库隔离、PM方案工作室、Data Copilot等功能。

## 功能特性

### 核心功能

- **知识库管理** - 多知识库创建、文档上传、索引构建
- **智能问答** - RAG检索增强生成，支持多轮对话
- **知识库隔离** - 严格按knowledge_id隔离检索，防止跨行业污染
- **SSE流式输出** - 实时显示AI生成内容

### Data Copilot（数据智能助手）

企业级 NL2SQL 数据查询模块，让仓库人员直接用自然语言查询业务数据：

```
自然语言问题 → Schema检索 → SQL生成 → 安全校验 → 执行 → AI分析
```

**核心特性：**
- **三层NL2SQL架构** - Schema Retriever → SQL Generator → SQL Validator
- **Schema Embedding索引** - 语义匹配相关表/字段，从7900+字段中精准定位
- **SQL安全校验** - 禁止DELETE/DROP/UPDATE，强制LIMIT，禁止SELECT *
- **AI Insight生成** - 自动分析查询结果，提供业务洞察和建议行动
- **查询历史记录** - SQLite存储查询历史，支持收藏和复用
- **追问建议** - 每次查询后推荐相关追问问题

### PM方案工作室

PM方案工作室是一个智能方案设计工作流，帮助PM基于知识库文档完成系统功能方案设计：

```
问题定义 → 方案分析 → 方案细化 → PRD生成
```

**核心特性：**
- **4阶段模板** - 预设问题定义、方案分析、方案细化、PRD生成
- **阶段内自由对话** - 每阶段可无限对话迭代，满意后再推进
- **知识库严格隔离** - 只检索选定知识库的内容
- **SSE流式对话** - 实时显示AI分析和建议
- **确认时自动生成结构化输出** - 基于对话历史生成JSON格式输出
- **对话历史持久化** - SQLite数据库存储，刷新不丢失
- **PRD一键导出** - Markdown格式完整PRD文档

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | FastAPI + LlamaIndex + LangChain + LangGraph + ChromaDB + SQLite + MySQL |
| 可观测性 | LangFuse |
| 前端 | Vue 3 + Pinia + Vite + TailwindCSS |
| LLM | DeepSeek API（支持OpenAI/Claude扩展） |
| Embedding | BAAI/bge-small-zh-v1.5（本地部署） |
| 数据查询 | aiomysql + Schema Embedding + NL2SQL |

## 项目结构

```
WMSRAGV2/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI入口
│   │   ├── config.py            # 配置管理
│   │   ├── api/
│   │   │   ├── pm_solution.py   # PM方案工作室API
│   │   │   ├── documents.py     # 文档管理API
│   │   │   ├── chat.py          # 对话问答API
│   │   │   └── query.py         # 数据查询API (NL2SQL)
│   │   ├── agents/
│   │   │   ├── query_agent.py   # Data Copilot Agent
│   │   │   ├── tools_sql.py     # SQL工具集
│   │   │   └── prompts_sql.py   # NL2SQL提示模板
│   │   ├── models/
│   │   │   ├── document.py      # 文档数据模型
│   │   │   ├── pm_solution.py   # PM方案数据模型
│   │   │   └── query_history.py # 查询历史模型
│   │   ├── services/
│   │   │   ├── rag_service.py   # RAG服务
│   │   │   ├── pm_solution_service.py  # PM方案服务
│   │   │   ├── query_service.py # 数据查询服务
│   │   │   ├── index_builder.py # 索引构建
│   │   │   ├── document_processor.py  # 文档处理
│   │   │   └── retriever.py     # 混合检索器
│   │   ├── core/
│   │   │   ├── vector_store.py  # ChromaDB配置
│   │   │   ├── embedding.py     # Embedding配置
│   │   │   ├── settings.py      # 行业配置
│   │   │   ├── db_mysql.py      # MySQL连接池管理
│   │   │   ├── schema_manager.py # Schema Embedding索引
│   │   │   └── llm_manager.py   # LLM管理
│   │   └ data/
│   │       ├── chroma/          # 向量存储
│   │       ├── kb.db            # SQLite数据库
│   │       ├── query_history.db # 查询历史数据库
│   │       └ uploads/          # 上传文件
│   ├── requirements.txt
│   └ requirements-docker.txt    # Docker精简版
│   └── .env                     # 环境配置
├── frontend/vue-app/
│   ├── src/
│   │   ├── views/
│   │   │   ├── PMStudioPage.vue  # PM方案工作室页面
│   │   │   ├── KnowledgeBase.vue # 知识库管理页面
│   │   │   └── QueryPage.vue     # 数据查询页面
│   │   ├── components/
│   │   │   ├── query/
│   │   │   │   ├── InsightCard.vue    # AI分析卡片
│   │   │   │   ├── QueryHistory.vue   # 查询历史侧边栏
│   │   │   │   └ QueryInput.vue       # 自然语言输入
│   │   │   │   └ ResultTable.vue      # 结果表格
│   │   │   │   └ SchemaBrowser.vue    # Schema浏览
│   │   ├── api/
│   │   │   ├── pmSolution.js    # PM方案API
│   │   │   ├── documentsV2.js   # 文档API
│   │   │   ├── query.js         # 数据查询API
│   │   ├── stores/
│   │   │   ├── knowledge.js     # 知识库状态
│   │   │   ├── query.js         # 数据查询状态
│   ├── package.json
│   └ vite.config.js
├── docs/                        # GitHub Pages文档
│   ├── index.html               # 项目主页
│   └── style.css                # 样式文件
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── 实施计划.md                   # 详细实施文档
```

## 快速开始

### 1. 环境配置

```bash
# 复制环境模板
cp .env.example .env

# 编辑.env，配置API密钥和数据库连接
DEEPSEEK_API_KEY=your_api_key_here
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=wms
```

### 2. 后端启动

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --port 8912 --reload
```

### 3. 前端启动

```bash
cd frontend/vue-app
npm install
npm run dev
```

访问 http://localhost:8912

### 4. Docker部署

```bash
docker-compose up -d
```

## API端点

### 数据查询 (Data Copilot)

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/api/v1/query/` | 自然语言查询（NL→SQL→结果→Insight） |
| POST | `/api/v1/query/execute` | 直接执行SQL（带安全校验） |
| GET | `/api/v1/query/schema` | 获取数据库Schema |
| GET | `/api/v1/query/test-connection` | 测试MySQL连接 |
| GET | `/api/v1/query/preview/{table}` | 预览表数据 |
| POST | `/api/v1/query/insight` | 为结果生成AI分析 |
| GET | `/api/v1/query/history/{session}` | 获取会话历史 |
| GET | `/api/v1/query/history/all` | 获取所有历史 |

### PM方案工作室

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/api/v1/pm-solution/sessions` | 创建方案会话 |
| GET | `/api/v1/pm-solution/sessions` | 获取会话列表 |
| GET | `/api/v1/pm-solution/sessions/{id}` | 获取会话详情 |
| POST | `/api/v1/pm-solution/sessions/{id}/chat` | SSE流式对话 |
| POST | `/api/v1/pm-solution/sessions/{id}/confirm` | 确认当前阶段 |
| POST | `/api/v1/pm-solution/sessions/{id}/rollback` | 回溯到指定阶段 |
| POST | `/api/v1/pm-solution/sessions/{id}/export` | 导出PRD文档 |
| DELETE | `/api/v1/pm-solution/sessions/{id}` | 删除会话 |

### 知识库管理

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/v1/documents/knowledge/list` | 获取知识库列表 |
| POST | `/api/v1/documents/upload` | 上传文档 |
| GET | `/api/v1/documents/list/{page}/{size}` | 获取文档列表 |
| DELETE | `/api/v1/documents/{id}` | 删除文档 |

### 对话问答

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/api/v1/chat/stream` | SSE流式对话 |
| POST | `/api/v1/chat/` | 标准对话 |

## 配置说明

### 行业配置

系统预置以下行业配置，可按需扩展：

| 行业 | 分块大小 | 检索数量 | BM25 |
|------|---------|---------|------|
| general | 500 | 5 | 是 |
| wms | 800 | 8 | 是 |
| medical | 300 | 10 | 是 |
| legal | 1000 | 5 | 否 |
| finance | 600 | 6 | 是 |

### LLM配置

```env
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=your_key
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat
```

### MySQL配置（数据查询）

```env
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=wms
```

## Data Copilot 使用示例

### 自然语言查询

```bash
# 查询示例
curl -X POST http://localhost:8912/api/v1/query/ \
  -H "Content-Type: application/json" \
  -d '{"question": "查询最近5条入库单数据"}'

# 返回结果包含：SQL、数据、AI分析、追问建议
```

### 前端界面

1. **Schema浏览器** - 查看数据库表结构和字段说明
2. **自然语言输入** - 直接输入问题，系统自动生成SQL
3. **结果表格** - 展示查询结果数据
4. **AI分析卡片** - 显示关键结论、异常点、建议行动
5. **追问按钮** - 点击推荐问题继续深入查询

## PM方案工作室使用流程

1. **选择知识库** - 选择要参考的行业文档库
2. **输入问题描述** - 描述要解决的问题场景
3. **阶段对话** - 在每个阶段与AI对话迭代
4. **确认推进** - 满意后点击"确认"进入下一阶段
5. **导出PRD** - 最终阶段自动生成并下载PRD文档

## 性能优化日志

系统内置详细性能日志，帮助分析生成速度：

**后端日志位置：** 控制台输出
```
[时间戳] [PM-API] 消息 (耗时: ms)
[时间戳] [PM-RETRIEVE] 检索完成 (耗时: ms)
[时间戳] [PM-LLM] 收到第一个token! (耗时: ms)
[时间戳] [SchemaManager] 索引构建完成: 7904 条
```

**前端日志位置：** 浏览器Console (F12)
```
[FRONTEND] 时间 开始sendChat
[FRONTEND] 时间 收到第一个token!
[FRONTEND] 时间 sendChat完成
```

## 版本历史

### v2.0.0
- 新增 Data Copilot 数据查询模块
- 三层NL2SQL架构（Schema检索 + SQL生成 + 安全校验）
- Schema Embedding语义索引
- AI Insight结果分析
- 查询历史记录存储
- 新增PM方案工作室功能
- SSE流式对话支持
- 知识库严格隔离检索
- 对话历史SQLite持久化
- 结构化输出生成
- PRD一键导出

## License

MIT