# Data Copilot 数据查询模块设计文档

**日期**: 2026-06-02
**状态**: 待审查
**范围**: 数据查询模块完整实现 - 三层NL2SQL + 查询历史 + 结果智能解释

---

## 一、背景与目标

### 1.1 现状分析

**前端完成度**: 80%
- QueryInput、ResultTable、SqlDisplay、SchemaBrowser、ExportButton 均已实现
- 缺少：AI分析卡片、查询历史、追问能力

**后端完成度**: 0%
- 无 `/api/v1/query/` 路由
- 无 MySQL 连接配置
- 无 NL2SQL 引擎

### 1.2 目标

将"SQL工具UI"升级为**企业级 Data Copilot**：
- 自然语言 → 意图识别 → Schema检索 → SQL生成 → 安全校验 → 执行 → AI解释 → 可追问

### 1.3 Schema元数据来源

项目中Schema信息已结构化存储：
- `tfrmdataobj` - 表信息（含中文翻译）
- `tfrmdataprop` - 字段信息（含类型、长度、注释）

---

## 二、架构设计

### 2.1 整体架构（Agent增强模式）

```
backend/app/
├── agents/
│   ├── query_agent.py      # 【新增】数据查询Agent
│   ├── tools_sql.py        # 【新增】SQL工具集
│   └── prompts_sql.py      # 【新增】SQL生成Prompt模板
├── services/
│   └── query_service.py    # 【新增】查询编排服务
├── core/
│   ├── db_mysql.py         # 【新增】MySQL连接管理
│   └── schema_manager.py   # 【新增】Schema加载与Embedding索引
├── models/
│   └── query_history.py    # 【新增】查询历史存储
├── api/
│   └── query.py            # 【新增】查询API路由
└── config.py               # 【修改】添加MySQL配置

frontend/vue-app/src/
├── components/query/
│   ├── InsightCard.vue     # 【新增】AI分析结论卡片
│   └── QueryHistory.vue    # 【新增】查询历史侧边栏
│   └── SqlDisplay.vue      # 【小改】添加解释按钮
├── stores/query.js         # 【扩展】新增history/insight状态
└── api/query.js            # 【扩展】新增API方法
```

### 2.2 数据流

```
用户问题 → QueryService → QueryAgent
    ↓
SchemaManager (embedding检索相关表/字段)
    ↓
NL2SQL Prompt → LLM → SQL
    ↓
SQLValidator (安全校验)
    ↓
MySQL执行 → 结果
    ↓
InsightGenerator → AI解释 + 追问建议
    ↓
HistoryManager → 保存历史
```

---

## 三、后端模块详细设计

### 3.1 MySQL连接管理 (`core/db_mysql.py`)

**职责**: MySQL连接池管理、Schema元数据读取

**接口**:
```python
class MySQLManager:
    _pool: Optional[ConnectionPool] = None
    
    def get_connection() -> Connection
    def execute(sql: str, params: List = None) -> Dict
    def get_schema_tables() -> List[Dict]   # 从tfrmdataobj读取
    def get_schema_columns(table_name: str) -> List[Dict]  # 从tfrmdataprop读取
    def test_connection() -> bool
```

**配置新增**:
```env
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=xxx
MYSQL_DATABASE=wms
```

### 3.2 Schema Manager (`core/schema_manager.py`)

**职责**: Schema加载、Embedding索引构建、语义搜索

**接口**:
```python
class SchemaManager:
    _schema_index: Optional[VectorStoreIndex] = None
    _schema_cache: Dict = {}
    
    def load_schema_from_db() -> Dict
        # 从tfrmdataobj/tfrmdataprop加载全量Schema
    
    def build_embedding_index() -> None
        # 将表名+中文描述、字段名+类型+注释转为文本，embedding化
    
    def search_relevant_schema(query: str, top_k: int = 5) -> List[Dict]
        # 语义搜索返回相关表/字段
    
    def refresh_index() -> None
        # 刷新索引（Schema变更时）
```

**复用**: 使用现有 `embedding.py` 的 HuggingFaceEmbedding

### 3.3 SQL工具集 (`agents/tools_sql.py`)

**工具定义**:
```python
class SchemaSearchTool(BaseTool):
    name = "schema_search"
    description = "语义搜索相关数据库表和字段"
    def _run(query: str) -> str  # 返回相关schema JSON

class SQLGenerateTool(BaseTool):
    name = "sql_generate"
    description = "根据问题和schema生成安全SQL"
    def _run(question: str, schema_context: str) -> str  # 返回SQL JSON

class SQLExecuteTool(BaseTool):
    name = "sql_execute"
    description = "执行SQL并返回结果"
    def _run(sql: str) -> Dict  # 执行并返回结果

class SQLValidateTool(BaseTool):
    name = "sql_validate"
    description = "校验SQL安全性"
    def _run(sql: str) -> Dict  # 返回校验结果
```

### 3.4 Prompt模板 (`agents/prompts_sql.py`)

**SQL生成Prompt**:
```text
你是企业级SQL查询生成器（Data Copilot）。

## 可用的数据库表结构
{schema_context}

## 用户问题
{user_question}

## 强制规则
1. 只能使用提供的表和字段
2. 禁止使用：DROP、DELETE、UPDATE、INSERT、TRUNCATE
3. 必须添加 LIMIT 100（聚合统计除外）
4. 时间字段使用标准格式 YYYY-MM-DD
5. 禁止 SELECT *
6. 无法确定字段时返回 NEED_CLARIFICATION

## 输出格式（严格JSON）
{
  "sql": "SELECT ...",
  "tables_used": ["table_name"],
  "confidence": 0.85,
  "explanation": "查询逻辑说明",
  "assumptions": []
}
```

**Insight生成Prompt**:
```text
你是企业数据分析助手。

## 用户原始问题
{user_question}

## SQL查询结果
{query_result}

## 输出要求
1. 关键结论（3条以内，用业务语言）
2. 异常点（如果有）
3. 建议行动（如果有）

不要复述数据，要有管理视角。
```

### 3.5 SQL安全校验

**规则** (`query_service.py`内联):
```python
FORBIDDEN_KEYWORDS = ["drop", "delete", "update", "insert", "truncate", "alter", "create"]

def validate_sql(sql: str) -> Dict:
    sql_lower = sql.lower()
    
    # 禁止关键词
    for kw in FORBIDDEN_KEYWORDS:
        if kw in sql_lower:
            return {"valid": False, "reason": f"禁止使用 {kw} 操作"}
    
    # 必须是SELECT
    if not sql_lower.strip().startswith("select"):
        return {"valid": False, "reason": "只允许SELECT查询"}
    
    # 禁止SELECT *
    if "select *" in sql_lower:
        return {"valid": False, "reason": "禁止SELECT *"}
    
    # 强制LIMIT
    has_aggregation = any(kw in sql_lower for kw in ["group by", "count", "sum", "avg"])
    if not has_aggregation and "limit" not in sql_lower:
        sql = sql.rstrip(";") + " LIMIT 100"
    
    return {"valid": True, "sql": sql}
```

### 3.6 查询历史模型 (`models/query_history.py`)

```python
class QueryHistory(Base):
    __tablename__ = "query_history"
    
    id: int (PK)
    session_id: str          # 会话ID
    question: str            # 用户问题
    sql: str                 # 生成的SQL
    result_count: int        # 结果数量
    insight: str (nullable)  # AI分析
    tables_used: str         # JSON数组
    favorite: bool = False   # 收藏标记
    created_at: datetime
```

### 3.7 API路由 (`api/query.py`)

| 路由 | 方法 | 功能 |
|------|------|------|
| `/` | POST | 自然语言查询 → SQL → 结果 + AI分析 |
| `/execute` | POST | 直接执行SQL（带校验） |
| `/schema` | GET | 获取数据库Schema |
| `/test-connection` | GET | 测试MySQL连接 |
| `/preview/{table}` | GET | 预览表数据 |
| `/insight` | POST | 为结果生成AI分析 |
| `/history/{session_id}` | GET | 获取查询历史 |
| `/history/{session_id}` | POST | 保存查询记录 |

---

## 四、前端改动设计

### 4.1 新增组件

**InsightCard.vue** - AI分析结论卡片:
- 显示关键结论（3条以内）
- 显示追问建议按钮
- 点击追问触发新查询

**QueryHistory.vue** - 查询历史侧边栏:
- 显示最近20条查询
- 点击可复用历史查询
- 支持清空历史

### 4.2 Store扩展 (`stores/query.js`)

新增状态:
- `history` - 查询历史列表
- `insight` - AI分析结论
- `followUps` - 追问建议
- `sessionContext` - 多轮上下文

新增方法:
- `executeQueryWithInsight(q)` - 执行查询并获取分析
- `addToHistory(item)` - 添加历史记录
- `loadHistory(sessionId)` - 加载历史

### 4.3 API扩展 (`api/query.js`)

新增:
- `getInsight(question, sql, results)`
- `getHistory(sessionId)`
- `saveHistory(sessionId, item)`

---

## 五、实现优先级

### Phase 1: 核心后端（约3天）
1. `config.py` - MySQL配置
2. `core/db_mysql.py` - MySQL连接
3. `core/schema_manager.py` - Schema加载与索引
4. `agents/tools_sql.py` - SQL工具
5. `agents/prompts_sql.py` - Prompt模板

### Phase 2: API与服务（约2天）
1. `services/query_service.py` - 编排服务
2. `agents/query_agent.py` - Query Agent
3. `api/query.py` - API路由
4. `main.py` - 路由注册

### Phase 3: 前端改动（约1天）
1. `InsightCard.vue`
2. `QueryHistory.vue`
3. `stores/query.js` 扩展
4. `api/query.js` 扩展
5. `QueryPage.vue` 集成

### Phase 4: 历史存储（约1天）
1. `models/query_history.py`
2. 历史API完善
3. 前端历史功能

---

## 六、验收标准

1. **基础查询**: 自然语言输入 → 正确SQL → 结果展示
2. **Schema检索**: 用户问题能匹配到正确的表和字段
3. **安全校验**: 禁止危险SQL，强制LIMIT
4. **AI分析**: 查询结果有业务洞察和追问建议
5. **历史记录**: 查询可保存、查看、复用
6. **前端体验**: InsightCard、History组件正常工作

---

## 七、风险与依赖

| 风险 | 缓解措施 |
|------|----------|
| MySQL连接失败 | 配置验证 + 错误提示 |
| Schema索引构建慢 | 增量更新 + 缓存 |
| LLM生成SQL不准 | Prompt优化 + Schema上下文 |
| 大结果集性能 | 强制LIMIT + 分页 |