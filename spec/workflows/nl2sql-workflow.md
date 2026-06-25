# 数据查询工作流规范 (NL2SQL)

> **版本**: 2.0 (Phase 2 MCP 接入)
> **最后更新**: 2026-06-25
> **负责模块**: `backend/app/core/data_query_gateway.py` (统一入口) | `backend/app/agents/graph_mcp.py` (MCP) | `backend/app/agents/graph_nl2sql.py` (Local NL2SQL) | `frontend/src/views/QueryPage.vue`

---

## 1. 概述

数据查询模块提供**自然语言到数据的完整流水线**。Phase 2 引入 MCP Data Copilot 作为主路径：系统优先通过 15 个预构建 MCP Tool 执行查询，失败或不适配时自动回退到本地 NL2SQL。

核心链路 (Phase 2)：

```
Gateway._check_mcp_eligibility (Layer A)
  ├── eligible=true → McpExecutor
  │   ├── tool_filter_node (Layer B: domain → 候选Tool)
  │   ├── tool_select_node (Layer C: LLM 选Tool+参数)
  │   ├── mcp_call_node (WmsMcpClient → MCP Server :8922)
  │   └── result_format_node
  │   成功 → 返回
  │   失败 → 回退 LocalExecutor
  └── eligible=false → LocalExecutor
      └── graph_nl2sql (Domain Classify → Schema Search → SQL Generate → SQL Validate → Execute → Insight)
      失败 → QueryAgentExecutor (旧版兜底)
```

---

## 2. 系统架构

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Frontend (Vue 3 + Pinia)                    │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │
│  │ QueryPage.vue │  │ SchemaBrowser│  │QueryHistory  │               │
│  │  (主编排页)    │  │  (表浏览器)   │  │  (查询历史)  │               │
│  │              │  │              │  │              │               │
│  │ ┌QueryInput  │  │ 搜索/筛选 →  │  │ 列表+导出    │               │
│  │ │.vue       │  │ FloatingWindow│  │              │               │
│  │ ├SqlDisplay │  │ (悬浮窗详情)  │  └──────────────┘               │
│  │ │.vue       │  └──────────────┘                                  │
│  │ ├ResultTable│                                                     │
│  │ │.vue       │  stores/query.js (Pinia Store)                     │
│  │ ├InsightCard│  ┌─────────────────────────────────┐               │
│  │ │.vue       │  │ question, sql, results, columns, │               │
│  │ └ExportBtn  │  │ totalCount, insight, schema,     │               │
│  └──────────────┘  │ loading, error, sessionId,      │               │
│                     │ connectionOk, history           │               │
│                     └─────────────────────────────────┘               │
│                              │                                       │
│              API Layer      │                                       │
│  ┌──────────────────────────┼─────────────────────────────────┐      │
│  │  api/query.js            │  api/schema.js  api/reports.js   │      │
│  └──────────────────────────┼─────────────────────────────────┘      │
└──────────────────────────────┼────────────────────────────────────────┘
                               │  HTTP (localhost:8812/api/v1/query/)
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     Backend (FastAPI / Python)                        │
│                                                                       │
│  ┌─────────────────────┐   ┌──────────────────────┐                  │
│  │  app/api/query.py   │   │ app/core/            │                  │
│  │  REST API 路由       │──▶│ schema_manager.py    │                  │
│  │  (12 个端点)         │   │ (Embedding检索)      │                  │
│  └─────────┬───────────┘   └──────────┬───────────┘                  │
│            │                          │                               │
│            ▼                          ▼                               │
│  ┌─────────────────────┐   ┌──────────────────────┐                  │
│  │ app/agents/         │   │ app/core/            │                  │
│  │ query_agent.py      │   │ db_mysql.py          │                  │
│  │ (5步流水线)          │   │ (aiomysql 连接池)     │                  │
│  ├─────────────────────┤   └──────────┬───────────┘                  │
│  │ app/agents/         │              │                              │
│  │ prompts_sql.py      │              ▼                              │
│  │ (Prompt模板)         │   ┌──────────────────────┐                  │
│  ├─────────────────────┤   │ app/models/          │                  │
│  │ app/agents/         │   │ query_history.py     │                  │
│  │ tools_sql.py        │   │ (SQLite 查询历史)     │                  │
│  │ (4 个Tool)          │   └──────────────────────┘                  │
│  └─────────┬───────────┘                                             │
│            │ LLM 调用                                                │
│            ▼                                                         │
│  ┌─────────────────────────────────────────┐                         │
│  │  app/core/llm_manager.py                │                         │
│  │  多Provider: DeepSeek/OpenAI/Anthropic  │                         │
│  └─────────────────────────────────────────┘                         │
└──────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                        Data Sources                                   │
│                                                                       │
│  ┌──────────────────────┐        ┌──────────────────────┐            │
│  │  MySQL (业务数据库)    │        │  SQLite (查询历史)     │            │
│  │  - tfrmdataobj (表)   │        │  - query_history.db  │            │
│  │  - tfrmdataprop (列)  │        └──────────────────────┘            │
│  │  - 业务数据表          │                                           │
│  └──────────────────────┘                                            │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.2 调用链 (`query_agent.py:24` 五步流水线)

```
QueryAgent.query(question)
│
├─[Step 1] schema_manager.search_relevant_schema(question)
│          └─ 返回: 格式化后的相关表/字段文本
│
├─[Step 2] LLM.invoke(SQL_GENERATION_PROMPT)
│          └─ 返回: JSON {sql, tables_used, confidence, explanation, assumptions}
│
├─[Step 3] SQLValidateTool.validate(sql)
│          └─ 返回: 校验通过/失败 + 可能修正后的sql
│
├─[Step 4] MySQLManager.execute(sql)
│          └─ 返回: {success, rows, count, columns}
│
└─[Step 5] QueryAgent._generate_insight(question, rows[:10])
           └─ 返回: {key_conclusions, anomalies, suggested_actions, follow_up_questions}

注意: QueryAgent 按 session_id 隔离实例（`get_query_agent(session_id)` 工厂方法），
每个会话独立的 `_memory: List[Dict]` 防止跨用户上下文泄漏。
```

---

## 3. 五阶段流水线详细说明

### 3.1 Step 1: Schema检索

| 项目 | 描述 |
|------|------|
| **触发入口** | `QueryAgent.query()` 第1步 |
| **核心方法** | `SchemaManager.search_relevant_schema(question: str) -> str` |
| **嵌入模型** | `BAAI/bge-small-zh-v1.5` |
| **匹配算法** | 余弦相似度（cosine similarity） |

**Schema数据来源**：

| MySQL 表 | 用途 | 关键字段 |
|-----------|------|---------|
| `tfrmdataobj` | 表/视图定义 | `DataObjCode`（表名）, `DataObjName`（显示名）, `ObjDesc`（描述） |
| `tfrmdataprop` | 字段/列定义 | `FieldName`, `FieldDesc`（显示名）, `DataType`, `DataWidth`, `DataDec`, `FieldIndex`（排序） |

过滤条件：`tfrmdataobj.DataObjType='0'`（仅业务数据对象）。

**Schema文本语料构建**：

```
表:  {DataObjCode} ({DataObjName}) - {ObjDesc}
字段: {DataObjCode}.{FieldName} ({FieldDesc}) 类型:{DataType}({DataWidth},{DataDec}) - {字段描述}
```

**检索流程**：

1. 启动时批量加载所有表/字段文本，调用 `BAAI/bge-small-zh-v1.5` 生成嵌入向量
2. 用户问题向量化，与所有schema嵌入计算余弦相似度
3. 返回 Top-K 最相关表/字段，格式化为LLM可理解的文本

**缓存策略**：内存缓存 `_schema_cache`, `_schema_texts`, `_schema_embeddings`，应用启动时一次性加载。

**失败处理**：若无匹配到任何相关表，返回错误提示 `"无法找到相关的数据库表..."`。

---

### 3.2 Step 2: SQL生成

| 项目 | 描述 |
|------|------|
| **触发入口** | `QueryAgent.query()` 第2步 |
| **核心调用** | `LLM.invoke(SQL_GENERATION_PROMPT.format(schema_text=..., question=...))` |
| **Prompt 文件** | `backend/app/agents/prompts_sql.py` → `SQL_GENERATION_PROMPT` |

**输出格式（严格JSON）**：

```json
{
  "sql": "SELECT field1, field2 FROM table WHERE ...",
  "tables_used": ["table1", "table2"],
  "confidence": 0.85,
  "explanation": "查询逻辑说明...",
  "assumptions": "基于自然语言的假设..."
}
```

**Prompt 中嵌入的规则**：

| 规则 | 说明 |
|------|------|
| 仅使用提供的表/字段 | 不得编造不存在的表名或字段名 |
| 禁止危险操作 | 禁止 DROP / DELETE / UPDATE / INSERT |
| 强制 LIMIT | 聚合查询(GROUP BY/COUNT/SUM等)添加 `LIMIT 1000`，普通查询添加 `LIMIT 100` |
| 禁止 SELECT * | 必须显式指定具体字段列表 |
| 无法确定时 | 返回 `NEED_CLARIFICATION` 而非猜测 |

**失败处理**：

| 情况 | 处理 |
|------|------|
| LLM 返回 NEED_CLARIFICATION | 向用户展示需要澄清的信息 |
| JSON 解析失败 | `"无法解析SQL生成结果"` |

---

### 3.3 Step 3: SQL校验

| 项目 | 描述 |
|------|------|
| **核心工具** | `SQLValidateTool`（位于 `backend/app/agents/tools_sql.py`） |
| **触发时机** | SQL生成后、执行前，自动执行 |

**校验规则表**：

| 序号 | 校验项 | 规则 | 违规错误信息 |
|------|--------|------|-------------|
| 1 | 非空检查 | SQL 字符串不能为空 | — |
| 2 | 禁止关键词 | 禁止包含：`DROP`, `DELETE`, `UPDATE`, `INSERT`, `TRUNCATE`, `ALTER`, `CREATE` | `"禁止使用 {WORD} 操作"` |
| 3 | SELECT 起始 | SQL 必须以 `SELECT` 开头 | `"只允许SELECT查询"` |
| 4 | 禁止 SELECT * | 不允许 `SELECT *` | `"禁止SELECT *，请指定具体字段"` |
| 5 | 自动追加 LIMIT | 若无已有 LIMIT：聚合查询(GROUP BY/COUNT/SUM/AVG/MAX/MIN)追加 `LIMIT 1000`，普通查询追加 `LIMIT 100` | — |

**注意**：校验可能在 Step 2 返回的 SQL 基础上进行自动修正（如追加LIMIT），修正后的 SQL 传递给 Step 4。

---

### 3.4 Step 4: SQL执行

| 项目 | 描述 |
|------|------|
| **核心方法** | `MySQLManager.execute(sql: str)` |
| **连接库** | `aiomysql`（异步MySQL驱动） |
| **连接池** | `min=1, max=5`，自动管理 |
| **游标类型** | `DictCursor`（返回字典格式） |

**返回格式**：

```python
{
    "success": True / False,
    "rows": [...],       # 查询结果行列表，每行为dict
    "count": int,        # 返回行数
    "columns": [...]     # 列名列表
}
```

**数据类型转换**：

| Python 类型 | 转换方式 |
|-------------|---------|
| `Decimal` | → `float` |
| `bytes` | → `str` (UTF-8 decode) |

**失败处理**：`success=False` 时附带 MySQL 原始错误信息字符串。

---

### 3.5 Step 5: Insight生成

| 项目 | 描述 |
|------|------|
| **触发入口** | `QueryAgent._generate_insight(question, rows[:10])` |
| **核心调用** | `LLM.invoke(INSIGHT_GENERATION_PROMPT)` |
| **Prompt 文件** | `backend/app/agents/prompts_sql.py` → `INSIGHT_GENERATION_PROMPT` |
| **数据限制** | 仅发送前 **10 行** 给 LLM（避免token爆炸） |

**输出格式（JSON）**：

```json
{
  "key_conclusions": ["结论1", "结论2", ...],
  "anomalies": ["异常点1", ...],
  "suggested_actions": ["建议1", ...],
  "follow_up_questions": ["追问1", ...]
}
```

**失败处理**：`f"分析生成失败: {e}"`。

**独立调用**：Insight 也可通过 API 单独重新生成（`POST /api/v1/query/insight`），无需重新执行查询。

---

## 4. Schema 管理详解

### 4.1 初始化流程

```
应用启动
  └→ SchemaManager.__init__()
       └→ 连接 MySQL
            └→ 读取 tfrmdataobj（WHERE DataObjType='0'）
            └→ 读取 tfrmdataprop（按 FieldIndex 排序）
            └→ 构建文本语料库
            └→ BAAI/bge-small-zh-v1.5 批量嵌入
            └→ 缓存到内存: _schema_cache, _schema_texts, _schema_embeddings
```

### 4.2 两种检索机制

| 机制 | 用途 | 接口 | 算法 |
|------|------|------|------|
| **Embedding语义检索** | NL2SQL 流程 Step 1 | `SchemaManager.search_relevant_schema()` | 余弦相似度（BGE嵌入） |
| **关键词检索** | SchemaBrowser 搜索框 | `GET /schema/search?q=` | 大小写不敏感子串匹配 |

---

## 5. API 端点清单

所有端点基路径：`/api/v1/query/`

| 方法 | 路径 | 功能 | 说明 |
|------|------|------|------|
| `POST` | `/` | 完整 NL2SQL 流水线 | 接收 `{question}`, 返回完整5步结果 |
| `POST` | `/execute` | 直接执行SQL | 接收 `{sql}`, 经过校验后执行 |
| `GET` | `/schema` | 获取完整Schema | 返回所有表/字段定义 |
| `GET` | `/test-connection` | 测试MySQL连通性 | 用于SchemaBrowser连接状态指示 |
| `GET` | `/preview/{table}` | 预览表数据 | 返回表前N行（用于探索） |
| `POST` | `/insight` | 重新生成Insight | 不重查数据，仅重新分析已有结果 |
| `GET` | `/history/{session_id}` | 获取会话历史 | 返回该会话所有历史记录 |
| `POST` | `/history/{session_id}` | 保存历史记录 | 追加一条查询历史 |
| `DELETE` | `/history/{session_id}` | 清除会话历史 | 删除该会话所有历史 |
| `GET` | `/history/all` | 全局历史 | 返回最近 20 条全局记录 |
| `GET` | `/schema/search?q=` | 关键词搜索表/字段 | SchemaBrowser搜索框调用 |
| `GET` | `/schema/table/{name}/fields` | 表字段详情 | FloatingWindow 悬浮窗展示 |

---

## 6. 前端组件树与状态管理

### 6.1 核心组件层次

```
QueryPage.vue  (主编排页面)
│
├── SchemaBrowser.vue      (左侧边栏 - 数据库表浏览器)
│   ├── 连接状态指示器
│   ├── 搜索框（关键词过滤）
│   ├── 表列表（树形/列表）
│   └── FloatingWindow.vue  (悬浮窗，最多5个)
│       └── 表字段详情 (GET /schema/table/{name}/fields)
│
├── QueryInput.vue          (主输入区 - 自然语言问题)
│
├── SqlDisplay.vue          (SQL展示区 - 生成的SQL)
│
├── ResultTable.vue         (查询结果表格)
│
├── InsightCard.vue         (洞察分析卡片)
│
├── ExportButton.vue        (导出按钮 → xlsx)
│   └── POST /api/v1/reports/generate-from-query
│
└── QueryHistory.vue        (历史记录侧边栏)
```

### 6.2 Pinia Store (`stores/query.js`)

| 字段 | 类型 | 说明 |
|------|------|------|
| `question` | string | 用户输入的自然语言问题 |
| `sql` | string | 生成/输入的SQL |
| `results` | array | 查询返回的行数据 |
| `columns` | array | 列名列表 |
| `totalCount` | number | 返回总行数 |
| `insight` | object/null | 洞察分析结果对象 |
| `schema` | array | 全部Schema缓存 |
| `connectionOk` | boolean | MySQL 连接状态 |
| `loading` | boolean | 查询进行中标志 |
| `error` | string/null | 错误信息 |
| `sessionId` | string | 当前会话ID |
| `history` | array | 当前会话历史记录 |

### 6.3 FloatingWindow 机制

- **用途**：点击 SchemaBrowser 中的表名时，弹出悬浮窗展示字段详情
- **特性**：可拖拽、可调整大小
- **限制**：最多同时 5 个悬浮窗
- **管理**：由 `QueryPage.vue` 统一管理悬浮窗生命周期

---

## 7. 会话管理 (Session)

- **会话ID格式**：`query_{uuid4().hex[:8]}` —— 由 `uuid4()` 生成，取前8位十六进制字符
- **生命周期**：用户进入 QueryPage 时创建唯一 sessionId，页面内所有查询共享该 session
- **历史持久化**：SQLite (`app/models/query_history.py`)，每次查询结果通过 `POST /history/{session_id}` 保存
- **历史查询**：支持按 session 查询、全局最近20条、按 session 清除

---

## 8. 错误处理总表

| 阶段 | 失败点 | 检测方式 | 返回/处理 |
|------|--------|---------|----------|
| Step 1 | 无相关表匹配 | 相似度低于阈值或结果为空 | `"无法找到相关的数据库表..."` |
| Step 2 | LLM 不确定 | LLM 返回 NEED_CLARIFICATION | 展示澄清信息给用户 |
| Step 2 | JSON 解析失败 | `json.loads()` 异常 | `"无法解析SQL生成结果"` |
| Step 3 | 校验不通过 | SQLValidateTool 检查 | 返回具体违规原因（见3.3） |
| Step 3 | 禁止关键词 | 正则/子串匹配 | `"禁止使用 {WORD} 操作"` |
| Step 3 | 非SELECT | 字符串 startswith | `"只允许SELECT查询"` |
| Step 3 | SELECT * | 正则匹配 `SELECT *` | `"禁止SELECT *，请指定具体字段"` |
| Step 4 | MySQL 执行失败 | `aiomysql` 异常 | 返回 MySQL 原始错误 |
| Step 5 | Insight 生成失败 | LLM 调用异常 | `"分析生成失败: {exception}"` |

---

## 9. 数据模型

### 9.1 SQLite 查询历史 (`app/models/query_history.py`)

```sql
-- 逻辑结构（具体建表见对应 model 文件）
CREATE TABLE query_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,       -- 会话标识
    question    TEXT,                -- 用户自然语言问题
    sql         TEXT,                -- 执行的SQL
    result      TEXT,                -- 结果（JSON序列化）
    insight     TEXT,                -- 洞察结果（JSON）
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 9.2 MySQL Schema 元数据

```sql
-- tfrmdataobj: 业务数据对象（表/视图）定义
-- 关键列: DataObjCode, DataObjName, ObjDesc
-- 过滤: DataObjType = '0'

-- tfrmdataprop: 字段属性定义
-- 关键列: FieldName, FieldDesc, DataType, DataWidth, DataDec
-- 排序: ORDER BY FieldIndex
```

---

## 10. 关键文件索引

| 文件路径 | 职责 |
|----------|------|
| `backend/app/agents/query_agent.py` | **核心编排** — 5步流水线主逻辑 |
| `backend/app/agents/tools_sql.py` | **SQL工具集** — SchemaSearchTool, SQLGenerateTool, SQLValidateTool, SQLExecuteTool |
| `backend/app/agents/prompts_sql.py` | **Prompt模板** — SQL_GENERATION_PROMPT, INSIGHT_GENERATION_PROMPT |
| `backend/app/api/query.py` | **REST API** — 12个HTTP端点定义 |
| `backend/app/core/schema_manager.py` | **Schema检索** — Embedding语义匹配引擎 |
| `backend/app/core/db_mysql.py` | **数据库** — aiomysql连接池、Schema元数据读取 |
| `backend/app/core/llm_manager.py` | **LLM** — 多Provider管理（DeepSeek/OpenAI/Anthropic） |
| `backend/app/models/query_history.py` | **历史** — SQLite查询历史模型 |
| `frontend/src/views/QueryPage.vue` | **主页面** — 前端编排组件 |
| `frontend/src/components/QueryInput.vue` | 查询输入组件 |
| `frontend/src/components/SqlDisplay.vue` | SQL展示组件 |
| `frontend/src/components/ResultTable.vue` | 结果表格组件 |
| `frontend/src/components/InsightCard.vue` | 洞察分析卡片 |
| `frontend/src/components/SchemaBrowser.vue` | Schema浏览侧边栏 |
| `frontend/src/components/FloatingWindow.vue` | 悬浮窗（最多5个） |
| `frontend/src/components/QueryHistory.vue` | 查询历史侧边栏 |
| `frontend/src/components/ExportButton.vue` | 导出xlsx按钮 |
| `frontend/src/stores/query.js` | Pinia状态管理 |
| `frontend/src/api/query.js` | 前端API调用（query端点） |
| `frontend/src/api/schema.js` | 前端API调用（schema端点） |
| `frontend/src/api/reports.js` | 前端API调用（导出端点） |
