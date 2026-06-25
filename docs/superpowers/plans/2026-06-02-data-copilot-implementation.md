# Data Copilot 数据查询模块 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 实现企业级 Data Copilot 数据查询模块，包含三层NL2SQL引擎、查询历史存储、AI结果解释功能。

**架构：** Agent增强模式，复用现有Agent框架，新增QueryAgent和SQL工具集。Schema信息从tfrmdataobj/tfrmdataprop表读取，构建embedding索引实现语义检索。

**技术栈：** FastAPI + LangChain + MySQL(aiomysql) + Vue3 + Pinia

---

## 文件结构清单

### 后端新增文件

| 文件 | 职责 |
|------|------|
| `backend/app/core/db_mysql.py` | MySQL连接池管理、Schema元数据读取 |
| `backend/app/core/schema_manager.py` | Schema加载、Embedding索引、语义搜索 |
| `backend/app/agents/tools_sql.py` | SQL工具集（SchemaSearch/SQLGenerate/SQLExecute/SQLValidate） |
| `backend/app/agents/prompts_sql.py` | NL2SQL和Insight生成的Prompt模板 |
| `backend/app/agents/query_agent.py` | 数据查询Agent，整合工具链 |
| `backend/app/services/query_service.py` | 查询编排服务，协调Agent和Insight生成 |
| `backend/app/models/query_history.py` | 查询历史SQLite模型 |
| `backend/app/api/query.py` | 查询API路由（8个端点） |

### 后端修改文件

| 文件 | 改动 |
|------|------|
| `backend/app/config.py` | 新增MySQL配置项（host/port/user/password/database） |
| `backend/app/main.py` | 注册query路由，初始化SchemaManager |
| `backend/requirements.txt` | 新增aiomysql依赖 |

### 前端新增文件

| 文件 | 职责 |
|------|------|
| `frontend/vue-app/src/components/query/InsightCard.vue` | AI分析结论卡片组件 |
| `frontend/vue-app/src/components/query/QueryHistory.vue` | 查询历史侧边栏组件 |

### 前端修改文件

| 文件 | 改动 |
|------|------|
| `frontend/vue-app/src/stores/query.js` | 新增history/insight/followUps状态和方法 |
| `frontend/vue-app/src/api/query.js` | 新增getInsight/getHistory/saveHistory方法 |
| `frontend/vue-app/src/views/QueryPage.vue` | 集成InsightCard和QueryHistory组件 |

---

## Phase 1: 核心后端基础设施

### 任务 1：MySQL配置扩展

**文件：**
- 修改：`backend/app/config.py`
- 修改：`backend/.env`

- [ ] **步骤 1：在config.py添加MySQL配置项**

在 `Settings` 类中添加（约第44行后）：

```python
    # MySQL 配置（数据查询模块）
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = ""
    mysql_database: str = "wms"

    @property
    def mysql_connection_url(self) -> str:
        """MySQL 连接 URL"""
        return f"mysql+aiomysql://{self.mysql_user}:{self.mysql_password}@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
```

- [ ] **步骤 2：在.env添加MySQL配置**

在 `backend/.env` 添加：

```env
# MySQL 配置
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=wms
```

- [ ] **步骤 3：在requirements.txt添加aiomysql**

在 `backend/requirements.txt` 添加：

```text
# MySQL
aiomysql>=0.2.0
```

- [ ] **步骤 4：Commit**

```bash
git add backend/app/config.py backend/.env backend/requirements.txt
git commit -m "feat(config): add MySQL connection configuration"
```

---

### 任务 2：MySQL连接管理

**文件：**
- 创建：`backend/app/core/db_mysql.py`

- [ ] **步骤 1：创建db_mysql.py基础结构**

```python
"""
MySQL 连接管理
支持连接池和Schema元数据读取
"""
import asyncio
from typing import Dict, List, Optional, Any
import aiomysql
from contextlib import asynccontextmanager

from app.config import get_settings

_settings = get_settings()


class MySQLManager:
    """MySQL连接池管理器"""
    
    _pool: Optional[aiomysql.Pool] = None
    
    async def init_pool(self) -> None:
        """初始化连接池"""
        if self._pool is not None:
            return
        
        self._pool = await aiomysql.create_pool(
            host=_settings.mysql_host,
            port=_settings.mysql_port,
            user=_settings.mysql_user,
            password=_settings.mysql_password,
            db=_settings.mysql_database,
            minsize=1,
            maxsize=5,
            autocommit=True
        )
        print(f"[MySQL] 连接池初始化完成: {_settings.mysql_host}:{_settings.mysql_port}/{_settings.mysql_database}")
    
    async def close_pool(self) -> None:
        """关闭连接池"""
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()
            self._pool = None
    
    @asynccontextmanager
    async def get_connection(self):
        """获取连接（上下文管理器）"""
        if self._pool is None:
            await self.init_pool()
        
        async with self._pool.acquire() as conn:
            yield conn
    
    async def execute(self, sql: str, params: List = None) -> Dict:
        """执行SQL并返回结果"""
        async with self.get_connection() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(sql, params or [])
                
                if sql.strip().lower().startswith("select"):
                    rows = await cursor.fetchall()
                    return {
                        "success": True,
                        "rows": rows,
                        "count": len(rows),
                        "columns": [desc[0] for desc in cursor.description] if cursor.description else []
                    }
                else:
                    return {
                        "success": True,
                        "affected_rows": cursor.rowcount
                    }
    
    async def test_connection(self) -> bool:
        """测试连接"""
        try:
            async with self.get_connection() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("SELECT 1")
                    return True
        except Exception as e:
            print(f"[MySQL] 连接测试失败: {e}")
            return False
    
    async def get_schema_tables(self) -> List[Dict]:
        """从tfrmdataobj读取表信息"""
        sql = """
        SELECT 
            objcode as table_name,
            objname as display_name,
            objdesc as description
        FROM tfrmdataobj
        WHERE objtype = 'TABLE'
        ORDER BY objcode
        """
        result = await self.execute(sql)
        return result.get("rows", [])
    
    async def get_schema_columns(self, table_name: str = None) -> List[Dict]:
        """从tfrmdataprop读取字段信息"""
        if table_name:
            sql = """
            SELECT 
                propcode as column_name,
                propname as display_name,
                datatype as data_type,
                datalength as data_length,
                propdesc as description,
                objcode as table_name
            FROM tfrmdataprop
            WHERE objcode = %s
            ORDER BY propcode
            """
            result = await self.execute(sql, [table_name])
        else:
            sql = """
            SELECT 
                propcode as column_name,
                propname as display_name,
                datatype as data_type,
                datalength as data_length,
                propdesc as description,
                objcode as table_name
            FROM tfrmdataprop
            ORDER BY objcode, propcode
            """
            result = await self.execute(sql)
        return result.get("rows", [])
    
    async def get_full_schema(self) -> Dict:
        """获取完整Schema（表+字段）"""
        tables = await self.get_schema_tables()
        columns = await self.get_schema_columns()
        
        # 按表组织字段
        schema = {}
        for table in tables:
            table_name = table["table_name"]
            schema[table_name] = {
                "display_name": table.get("display_name", table_name),
                "description": table.get("description", ""),
                "columns": []
            }
        
        for col in columns:
            table_name = col.get("table_name")
            if table_name in schema:
                schema[table_name]["columns"].append({
                    "column_name": col["column_name"],
                    "display_name": col.get("display_name", col["column_name"]),
                    "data_type": col.get("data_type", "VARCHAR"),
                    "data_length": col.get("data_length", 0),
                    "description": col.get("description", "")
                })
        
        return schema


# 单例
_mysql_manager: Optional[MySQLManager] = None


async def get_mysql_manager() -> MySQLManager:
    """获取MySQL管理器（单例）"""
    global _mysql_manager
    if _mysql_manager is None:
        _mysql_manager = MySQLManager()
        await _mysql_manager.init_pool()
    return _mysql_manager
```

- [ ] **步骤 2：Commit**

```bash
git add backend/app/core/db_mysql.py
git commit -m "feat(core): add MySQL connection manager with schema metadata reading"
```

---

### 任务 3：Schema Manager（Embedding索引）

**文件：**
- 创建：`backend/app/core/schema_manager.py`

- [ ] **步骤 1：创建schema_manager.py**

```python
"""
Schema Manager
加载Schema元数据并构建Embedding索引，支持语义搜索
"""
from typing import Dict, List, Optional
import json

from app.core.db_mysql import get_mysql_manager
from app.core.embedding import get_default_embedding


class SchemaManager:
    """Schema加载与Embedding索引管理"""
    
    _schema_cache: Dict = {}
    _schema_texts: List[str] = []  # 用于embedding的文本列表
    _schema_embeddings: List = []  # embedding向量列表
    _initialized: bool = False
    
    async def load_schema_from_db(self) -> Dict:
        """从数据库加载Schema"""
        mysql = await get_mysql_manager()
        self._schema_cache = await mysql.get_full_schema()
        return self._schema_cache
    
    def _build_schema_texts(self) -> List[str]:
        """将Schema转为文本列表用于embedding"""
        texts = []
        for table_name, table_info in self._schema_cache.items():
            # 表级文本
            table_text = f"表: {table_name} ({table_info.get('display_name', '')}) - {table_info.get('description', '')}"
            texts.append(table_text)
            
            # 字段级文本
            for col in table_info.get("columns", []):
                col_text = f"字段: {table_name}.{col['column_name']} ({col.get('display_name', '')}) 类型:{col.get('data_type', '')} - {col.get('description', '')}"
                texts.append(col_text)
        
        return texts
    
    async def build_embedding_index(self) -> None:
        """构建Embedding索引"""
        if not self._schema_cache:
            await self.load_schema_from_db()
        
        self._schema_texts = self._build_schema_texts()
        
        # 使用现有embedding模型
        embedding_model = get_default_embedding()
        self._schema_embeddings = embedding_model.get_text_embedding_batch(self._schema_texts)
        
        self._initialized = True
        print(f"[SchemaManager] 索引构建完成: {len(self._schema_texts)} 条")
    
    async def search_relevant_schema(self, query: str, top_k: int = 5) -> List[Dict]:
        """语义搜索相关Schema"""
        if not self._initialized:
            await self.build_embedding_index()
        
        # 计算query embedding
        embedding_model = get_default_embedding()
        query_embedding = embedding_model.get_text_embedding(query)
        
        # 计算相似度（简单余弦相似度）
        import numpy as np
        similarities = []
        for i, emb in enumerate(self._schema_embeddings):
            sim = np.dot(query_embedding, emb) / (np.linalg.norm(query_embedding) * np.linalg.norm(emb))
            similarities.append((i, sim))
        
        # 排序取top_k
        similarities.sort(key=lambda x: x[1], reverse=True)
        top_indices = [x[0] for x in similarities[:top_k * 2]]  # 多取一些
        
        # 提取相关表和字段
        relevant_tables = set()
        relevant_columns = []
        
        for idx in top_indices:
            text = self._schema_texts[idx]
            if text.startswith("表:"):
                # 提取表名
                parts = text.split("(")[0].replace("表: ", "").strip()
                relevant_tables.add(parts)
            elif text.startswith("字段:"):
                # 提取表名和字段名
                parts = text.replace("字段: ", "").split(".")
                if len(parts) >= 2:
                    table = parts[0]
                    col = parts[1].split("(")[0].strip()
                    relevant_tables.add(table)
                    relevant_columns.append(f"{table}.{col}")
        
        # 构建schema_context
        schema_context = {}
        for table in relevant_tables:
            if table in self._schema_cache:
                schema_context[table] = self._schema_cache[table]
        
        return {
            "tables": list(relevant_tables),
            "columns": relevant_columns[:top_k],
            "schema_context": schema_context,
            "schema_text": self._format_schema_context(schema_context)
        }
    
    def _format_schema_context(self, schema: Dict) -> str:
        """格式化schema为Prompt用的文本"""
        lines = []
        for table_name, info in schema.items():
            lines.append(f"\n表 {table_name} ({info.get('display_name', '')}):")
            for col in info.get("columns", []):
                lines.append(f"  - {col['column_name']} ({col.get('display_name', '')}): {col.get('data_type', '')} - {col.get('description', '')}")
        return "\n".join(lines)
    
    async def refresh_index(self) -> None:
        """刷新索引"""
        self._initialized = False
        self._schema_cache = {}
        await self.build_embedding_index()
    
    def get_all_tables(self) -> List[Dict]:
        """获取所有表列表"""
        return [
            {
                "name": table_name,
                "display_name": info.get("display_name", table_name),
                "columns": info.get("columns", [])
            }
            for table_name, info in self._schema_cache.items()
        ]


# 单例
_schema_manager: Optional[SchemaManager] = None


async def get_schema_manager() -> SchemaManager:
    """获取Schema管理器（单例）"""
    global _schema_manager
    if _schema_manager is None:
        _schema_manager = SchemaManager()
        await _schema_manager.build_embedding_index()
    return _schema_manager
```

- [ ] **步骤 2：Commit**

```bash
git add backend/app/core/schema_manager.py
git commit -m "feat(core): add Schema Manager with embedding index for semantic search"
```

---

### 任务 4：SQL Prompt模板

**文件：**
- 创建：`backend/app/agents/prompts_sql.py`

- [ ] **步骤 1：创建prompts_sql.py**

```python
"""
SQL生成和Insight生成的Prompt模板
"""

SQL_GENERATION_PROMPT = """你是企业级SQL查询生成器（Data Copilot）。

## 可用的数据库表结构
{schema_context}

## 用户问题
{user_question}

## 强制规则（必须遵守）
1. 只能使用上面提供的表和字段，不得使用未列出的表或字段
2. 禁止使用以下操作：DROP、DELETE、UPDATE、INSERT、TRUNCATE、ALTER、CREATE
3. 必须添加 LIMIT 100（聚合统计查询除外）
4. 时间字段使用标准格式 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS
5. 禁止 SELECT *，必须指定具体字段
6. 如果无法确定使用哪个字段，返回 NEED_CLARIFICATION

## 输出格式（严格JSON，不要添加任何额外文字）
```json
{
  "sql": "SELECT field1, field2 FROM table WHERE condition LIMIT 100",
  "tables_used": ["table_name"],
  "confidence": 0.85,
  "explanation": "简要说明查询逻辑",
  "assumptions": ["如有假设列在这里"]
}
```

请根据用户问题和表结构，生成安全的SQL查询。"""

INSIGHT_GENERATION_PROMPT = """你是企业数据分析助手，擅长从数据中发现业务洞察。

## 用户原始问题
{user_question}

## SQL查询结果（前10条示例）
{query_result}

## 分析要求
请基于查询结果，提供业务层面的分析洞察：
1. 关键结论（最多3条，用业务语言，不要复述数据）
2. 异常点（如果发现异常数据，指出并说明可能原因）
3. 建议行动（给出可操作的建议）

## 输出格式
关键结论：
- [结论1]
- [结论2]

异常点：
- [如有异常]

建议：
- [行动建议1]

追问建议：
用户可能还想了解：[建议2-3个追问问题]"""

SQL_EXPLAIN_PROMPT = """请解释以下SQL查询的逻辑：

SQL:
{sql}

表结构上下文:
{schema_context}

请用简洁的中文解释：
1. 这个查询从哪些表获取数据
2. 使用了什么筛选条件
3. 返回哪些字段
4. 查询的业务含义是什么"""

- [ ] **步骤 2：Commit**

```bash
git add backend/app/agents/prompts_sql.py
git commit -m "feat(agents): add SQL generation and insight generation prompts"
```

---

### 任务 5：SQL工具集

**文件：**
- 创建：`backend/app/agents/tools_sql.py`

- [ ] **步骤 1：创建tools_sql.py**

```python
"""
SQL工具集
Schema搜索、SQL生成、SQL校验、SQL执行
"""
from langchain.tools import BaseTool
from typing import Dict, Any, Optional, Type, List
from pydantic import BaseModel, Field
import json
import re

from app.core.llm_manager import get_llm
from app.agents.prompts_sql import SQL_GENERATION_PROMPT


# SQL安全校验规则
FORBIDDEN_KEYWORDS = ["drop", "delete", "update", "insert", "truncate", "alter", "create"]


class SchemaSearchInput(BaseModel):
    """Schema搜索输入"""
    query: str = Field(description="用户问题或关键词")


class SchemaSearchTool(BaseTool):
    """Schema语义搜索工具"""
    
    name: str = "schema_search"
    description: str = "根据用户问题搜索相关的数据库表和字段。返回表名、字段名和中文描述。"
    args_schema: Type[BaseModel] = SchemaSearchInput
    
    def __init__(self, schema_manager=None):
        super().__init__()
        self._schema_manager = schema_manager
    
    def _run(self, query: str) -> str:
        """执行Schema搜索"""
        if self._schema_manager is None:
            return json.dumps({"error": "Schema管理器未初始化"})
        
        # 异步调用需要在服务层处理，这里返回同步包装
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            result = loop.run_until_complete(self._schema_manager.search_relevant_schema(query))
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)})


class SQLGenerateInput(BaseModel):
    """SQL生成输入"""
    question: str = Field(description="用户的自然语言问题")
    schema_context: str = Field(description="相关的Schema上下文")


class SQLGenerateTool(BaseTool):
    """SQL生成工具"""
    
    name: str = "sql_generate"
    description: str = "根据用户问题和Schema上下文生成安全的SQL查询语句。"
    args_schema: Type[BaseModel] = SQLGenerateInput
    
    def __init__(self, llm=None):
        super().__init__()
        self._llm = llm or get_llm()
    
    def _run(self, question: str, schema_context: str) -> str:
        """执行SQL生成"""
        prompt = SQL_GENERATION_PROMPT.format(
            schema_context=schema_context,
            user_question=question
        )
        
        try:
            response = self._llm.invoke(prompt)
            content = response.content if hasattr(response, 'content') else str(response)
            
            # 提取JSON
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                return json_match.group(0)
            return json.dumps({"error": "无法解析LLM输出", "raw": content})
        except Exception as e:
            return json.dumps({"error": str(e)})


class SQLValidateInput(BaseModel):
    """SQL校验输入"""
    sql: str = Field(description="待校验的SQL语句")


class SQLValidateTool(BaseTool):
    """SQL安全校验工具"""
    
    name: str = "sql_validate"
    description: str = "校验SQL语句的安全性，检查是否包含危险操作。"
    args_schema: Type[BaseModel] = SQLValidateInput
    
    def _run(self, sql: str) -> str:
        """执行SQL校验"""
        sql_lower = sql.lower().strip()
        
        # 检查禁止关键词
        for kw in FORBIDDEN_KEYWORDS:
            if kw in sql_lower:
                return json.dumps({
                    "valid": False,
                    "reason": f"禁止使用 {kw.upper()} 操作",
                    "sql": sql
                })
        
        # 必须是SELECT
        if not sql_lower.startswith("select"):
            return json.dumps({
                "valid": False,
                "reason": "只允许SELECT查询",
                "sql": sql
            })
        
        # 禁止SELECT *
        if "select *" in sql_lower or "select  *" in sql_lower:
            return json.dumps({
                "valid": False,
                "reason": "禁止SELECT *，请指定具体字段",
                "sql": sql
            })
        
        # 强制添加LIMIT（聚合查询除外）
        has_aggregation = any(kw in sql_lower for kw in ["group by", "count(", "sum(", "avg(", "max(", "min("])
        if not has_aggregation and "limit" not in sql_lower:
            sql = sql.rstrip(";") + " LIMIT 100"
        
        return json.dumps({
            "valid": True,
            "sql": sql,
            "reason": "校验通过"
        })


class SQLExecuteInput(BaseModel):
    """SQL执行输入"""
    sql: str = Field(description="待执行的SQL语句")


class SQLExecuteTool(BaseTool):
    """SQL执行工具"""
    
    name: str = "sql_execute"
    description: str = "执行校验通过的SQL语句，返回查询结果。"
    args_schema: Type[BaseModel] = SQLExecuteInput
    
    def __init__(self, mysql_manager=None):
        super().__init__()
        self._mysql_manager = mysql_manager
    
    def _run(self, sql: str) -> str:
        """执行SQL"""
        if self._mysql_manager is None:
            return json.dumps({"error": "MySQL管理器未初始化"})
        
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            result = loop.run_until_complete(self._mysql_manager.execute(sql))
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)})


def get_sql_tools(schema_manager=None, mysql_manager=None, llm=None) -> List[BaseTool]:
    """获取SQL工具集"""
    return [
        SchemaSearchTool(schema_manager=schema_manager),
        SQLGenerateTool(llm=llm),
        SQLValidateTool(),
        SQLExecuteTool(mysql_manager=mysql_manager),
    ]
```

- [ ] **步骤 2：Commit**

```bash
git add backend/app/agents/tools_sql.py
git commit -m "feat(agents): add SQL tools - SchemaSearch, SQLGenerate, SQLValidate, SQLExecute"
```

---

### 任务 6：Query Agent

**文件：**
- 创建：`backend/app/agents/query_agent.py`

- [ ] **步骤 1：创建query_agent.py**

```python
"""
数据查询Agent
整合Schema搜索、SQL生成、校验、执行工具链
"""
from typing import Dict, Any, List, Optional
import json

from app.core.llm_manager import get_llm
from app.core.schema_manager import get_schema_manager
from app.core.db_mysql import get_mysql_manager
from app.agents.tools_sql import get_sql_tools
from app.agents.prompts_sql import INSIGHT_GENERATION_PROMPT


class QueryAgent:
    """数据查询Agent"""
    
    def __init__(self, llm_provider: str = None):
        self._llm = get_llm(llm_provider)
        self._llm_provider = llm_provider
        self._memory: List[Dict] = []
    
    async def query(self, question: str) -> Dict[str, Any]:
        """
        执行自然语言查询
        
        流程：
        1. Schema搜索 → 找相关表/字段
        2. SQL生成 → LLM生成SQL
        3. SQL校验 → 安全检查
        4. SQL执行 → 获取结果
        5. Insight生成 → AI分析
        """
        self._memory.append({"role": "user", "content": question})
        
        try:
            # Step 1: Schema搜索
            schema_manager = await get_schema_manager()
            schema_result = await schema_manager.search_relevant_schema(question)
            
            if not schema_result.get("tables"):
                return {
                    "success": False,
                    "error": "无法找到相关的数据库表，请确认问题是否与业务数据相关",
                    "question": question
                }
            
            schema_text = schema_result.get("schema_text", "")
            
            # Step 2: SQL生成
            from app.agents.tools_sql import SQLGenerateTool
            sql_tool = SQLGenerateTool(llm=self._llm)
            sql_result_str = sql_tool._run(question, schema_text)
            sql_result = json.loads(sql_result_str)
            
            if sql_result.get("error") or sql_result.get("sql") == "NEED_CLARIFICATION":
                return {
                    "success": False,
                    "error": sql_result.get("error", "无法生成有效的SQL，请提供更具体的问题"),
                    "question": question,
                    "schema_matched": schema_result.get("tables", [])
                }
            
            generated_sql = sql_result.get("sql", "")
            
            # Step 3: SQL校验
            from app.agents.tools_sql import SQLValidateTool
            validate_tool = SQLValidateTool()
            validate_result_str = validate_tool._run(generated_sql)
            validate_result = json.loads(validate_result_str)
            
            if not validate_result.get("valid"):
                return {
                    "success": False,
                    "error": validate_result.get("reason"),
                    "sql": generated_sql,
                    "question": question
                }
            
            final_sql = validate_result.get("sql", generated_sql)
            
            # Step 4: SQL执行
            mysql_manager = await get_mysql_manager()
            execute_result = await mysql_manager.execute(final_sql)
            
            if not execute_result.get("success"):
                return {
                    "success": False,
                    "error": execute_result.get("error", "SQL执行失败"),
                    "sql": final_sql,
                    "question": question
                }
            
            rows = execute_result.get("rows", [])
            columns = execute_result.get("columns", [])
            
            # Step 5: Insight生成
            insight = await self._generate_insight(question, rows[:10])
            
            # 保存回答
            self._memory.append({
                "role": "assistant",
                "content": insight.get("summary", ""),
                "sql": final_sql
            })
            
            return {
                "success": True,
                "sql": final_sql,
                "results": rows,
                "columns": columns,
                "total": len(rows),
                "tables_used": sql_result.get("tables_used", []),
                "confidence": sql_result.get("confidence", 0),
                "explanation": sql_result.get("explanation", ""),
                "insight": insight,
                "question": question
            }
        
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "question": question
            }
    
    async def _generate_insight(self, question: str, results: List[Dict]) -> Dict:
        """生成AI分析洞察"""
        if not results:
            return {"summary": "查询无结果", "insights": [], "follow_ups": []}
        
        # 格式化结果用于Prompt
        result_text = json.dumps(results[:10], ensure_ascii=False, indent=2)
        
        prompt = INSIGHT_GENERATION_PROMPT.format(
            user_question=question,
            query_result=result_text
        )
        
        try:
            response = self._llm.invoke(prompt)
            content = response.content if hasattr(response, 'content') else str(response)
            
            # 解析Insight
            insights = self._parse_insight(content)
            return insights
        except Exception as e:
            return {
                "summary": f"分析生成失败: {e}",
                "insights": [],
                "follow_ups": []
            }
    
    def _parse_insight(self, content: str) -> Dict:
        """解析Insight内容"""
        lines = content.split("\n")
        insights = []
        follow_ups = []
        summary = ""
        
        for line in lines:
            line = line.strip()
            if line.startswith("- ") and "结论" in content[:100]:
                insights.append(line[2:])
            elif "追问" in line or "还想了解" in line:
                # 提取追问建议
                if ":" in line:
                    follow_part = line.split(":")[-1]
                    follow_ups = [q.strip() for q in follow_part.split(",") if q.strip()]
        
        summary = insights[0] if insights else "查询成功"
        
        return {
            "summary": summary,
            "insights": insights[:3],
            "follow_ups": follow_ups[:3],
            "raw": content
        }
    
    async def execute_sql(self, sql: str) -> Dict[str, Any]:
        """直接执行SQL（带校验）"""
        from app.agents.tools_sql import SQLValidateTool
        
        # 校验
        validate_tool = SQLValidateTool()
        validate_result = json.loads(validate_tool._run(sql))
        
        if not validate_result.get("valid"):
            return {
                "success": False,
                "error": validate_result.get("reason"),
                "sql": sql
            }
        
        final_sql = validate_result.get("sql", sql)
        
        # 执行
        mysql_manager = await get_mysql_manager()
        result = await mysql_manager.execute(final_sql)
        
        return {
            "success": result.get("success", False),
            "sql": final_sql,
            "results": result.get("rows", []),
            "columns": result.get("columns", []),
            "total": result.get("count", 0),
            "error": result.get("error")
        }
    
    def clear_memory(self):
        """清空记忆"""
        self._memory = []
    
    def get_memory_history(self) -> List[Dict]:
        """获取记忆历史"""
        return self._memory.copy()


# 单例
_query_agent: Optional[QueryAgent] = None


def get_query_agent(llm_provider: str = None) -> QueryAgent:
    """获取Query Agent（单例）"""
    global _query_agent
    if _query_agent is None:
        _query_agent = QueryAgent(llm_provider)
    return _query_agent
```

- [ ] **步骤 2：Commit**

```bash
git add backend/app/agents/query_agent.py
git commit -m "feat(agents): add QueryAgent with NL2SQL pipeline and insight generation"
```

---

### 任务 7：Query Service

**文件：**
- 创建：`backend/app/services/query_service.py`

- [ ] **步骤 1：创建query_service.py**

```python
"""
查询编排服务
协调QueryAgent、SchemaManager、History管理
"""
from typing import Dict, Any, List, Optional
import uuid
import json
from datetime import datetime

from app.agents.query_agent import get_query_agent
from app.core.schema_manager import get_schema_manager
from app.core.db_mysql import get_mysql_manager
from app.models.query_history import QueryHistory, save_history, get_history_by_session


class QueryService:
    """查询编排服务"""
    
    def __init__(self, session_id: str = None):
        self._session_id = session_id or self._generate_session_id()
        self._agent = get_query_agent()
    
    def _generate_session_id(self) -> str:
        """生成会话ID"""
        return f"query_{uuid.uuid4().hex[:8]}"
    
    async def natural_query(self, question: str) -> Dict[str, Any]:
        """
        自然语言查询
        
        Args:
            question: 用户问题
        
        Returns:
            包含SQL、结果、Insight的完整响应
        """
        result = await self._agent.query(question)
        
        # 保存历史
        if result.get("success"):
            await self._save_history(question, result)
        
        return {
            **result,
            "session_id": self._session_id
        }
    
    async def execute_sql(self, sql: str) -> Dict[str, Any]:
        """
        直接执行SQL
        
        Args:
            sql: SQL语句
        
        Returns:
            执行结果
        """
        result = await self._agent.execute_sql(sql)
        return {
            **result,
            "session_id": self._session_id
        }
    
    async def get_schema(self) -> Dict[str, Any]:
        """获取完整Schema"""
        schema_manager = await get_schema_manager()
        tables = schema_manager.get_all_tables()
        return {
            "tables": tables,
            "session_id": self._session_id
        }
    
    async def test_connection(self) -> Dict[str, Any]:
        """测试MySQL连接"""
        mysql_manager = await get_mysql_manager()
        ok = await mysql_manager.test_connection()
        return {
            "ok": ok,
            "session_id": self._session_id
        }
    
    async def preview_table(self, table_name: str, limit: int = 5) -> Dict[str, Any]:
        """预览表数据"""
        mysql_manager = await get_mysql_manager()
        sql = f"SELECT * FROM {table_name} LIMIT {limit}"
        result = await mysql_manager.execute(sql)
        return {
            "table_name": table_name,
            "rows": result.get("rows", []),
            "columns": result.get("columns", []),
            "session_id": self._session_id
        }
    
    async def generate_insight(self, question: str, sql: str, results: List[Dict]) -> Dict[str, Any]:
        """为已有结果生成Insight"""
        insight = await self._agent._generate_insight(question, results[:10])
        return {
            "insight": insight,
            "session_id": self._session_id
        }
    
    async def _save_history(self, question: str, result: Dict) -> None:
        """保存查询历史"""
        history_item = {
            "session_id": self._session_id,
            "question": question,
            "sql": result.get("sql", ""),
            "result_count": result.get("total", 0),
            "insight": result.get("insight", {}).get("summary", ""),
            "tables_used": json.dumps(result.get("tables_used", [])),
            "created_at": datetime.now().isoformat()
        }
        await save_history(history_item)
    
    async def get_history(self) -> List[Dict]:
        """获取当前会话历史"""
        return await get_history_by_session(self._session_id)
    
    async def get_all_history(self, limit: int = 20) -> List[Dict]:
        """获取所有历史（最近N条）"""
        from app.models.query_history import get_all_history_limit
        return await get_all_history_limit(limit)


# 单例缓存（按session_id）
_query_services: Dict[str, QueryService] = {}


def get_query_service(session_id: str = None) -> QueryService:
    """获取查询服务"""
    if session_id and session_id in _query_services:
        return _query_services[session_id]
    
    service = QueryService(session_id)
    _query_services[service._session_id] = service
    return service
```

- [ ] **步骤 2：Commit**

```bash
git add backend/app/services/query_service.py
git commit -m "feat(services): add QueryService for orchestrating query pipeline"
```

---

### 任务 8：查询历史模型

**文件：**
- 创建：`backend/app/models/query_history.py`

- [ ] **步骤 1：创建query_history.py**

```python
"""
查询历史模型
SQLite存储查询历史记录
"""
from typing import Dict, List, Optional
import json
from datetime import datetime
import aiosqlite
import os

from app.config import get_settings

_settings = get_settings()

# 历史数据库路径
HISTORY_DB_PATH = os.path.join(_settings.data_dir, "query_history.db")


async def init_history_db():
    """初始化历史数据库"""
    os.makedirs(_settings.data_dir, exist_ok=True)
    
    async with aiosqlite.connect(HISTORY_DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS query_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                question TEXT NOT NULL,
                sql TEXT NOT NULL,
                result_count INTEGER DEFAULT 0,
                insight TEXT,
                tables_used TEXT,
                favorite INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_session_id ON query_history(session_id)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_created_at ON query_history(created_at)
        """)
        await db.commit()


async def save_history(item: Dict) -> int:
    """保存历史记录"""
    await init_history_db()
    
    async with aiosqlite.connect(HISTORY_DB_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO query_history 
            (session_id, question, sql, result_count, insight, tables_used, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [
            item.get("session_id"),
            item.get("question"),
            item.get("sql"),
            item.get("result_count", 0),
            item.get("insight", ""),
            item.get("tables_used", "[]"),
            item.get("created_at", datetime.now().isoformat())
        ])
        await db.commit()
        return cursor.lastrowid


async def get_history_by_session(session_id: str) -> List[Dict]:
    """按会话ID获取历史"""
    await init_history_db()
    
    async with aiosqlite.connect(HISTORY_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT * FROM query_history 
            WHERE session_id = ? 
            ORDER BY created_at DESC
        """, [session_id])
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_all_history_limit(limit: int = 20) -> List[Dict]:
    """获取最近N条历史"""
    await init_history_db()
    
    async with aiosqlite.connect(HISTORY_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT * FROM query_history 
            ORDER BY created_at DESC 
            LIMIT ?
        """, [limit])
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def clear_history(session_id: str = None) -> bool:
    """清空历史"""
    await init_history_db()
    
    async with aiosqlite.connect(HISTORY_DB_PATH) as db:
        if session_id:
            await db.execute("DELETE FROM query_history WHERE session_id = ?", [session_id])
        else:
            await db.execute("DELETE FROM query_history")
        await db.commit()
        return True


async def set_favorite(history_id: int, favorite: bool = True) -> bool:
    """设置收藏"""
    await init_history_db()
    
    async with aiosqlite.connect(HISTORY_DB_PATH) as db:
        await db.execute("""
            UPDATE query_history SET favorite = ? WHERE id = ?
        """, [1 if favorite else 0, history_id])
        await db.commit()
        return True


# 初始化函数（在main.py调用）
def init_query_history():
    """初始化查询历史（同步入口）"""
    import asyncio
    asyncio.get_event_loop().run_until_complete(init_history_db())
```

- [ ] **步骤 2：Commit**

```bash
git add backend/app/models/query_history.py
git commit -m "feat(models): add query history model with SQLite storage"
```

---

## Phase 2: API路由与集成

### 任务 9：查询API路由

**文件：**
- 创建：`backend/app/api/query.py`

- [ ] **步骤 1：创建query.py API路由**

```python
"""
数据查询API路由
NL2SQL、Schema浏览、历史管理等端点
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Dict, Optional

from app.services.query_service import get_query_service

router = APIRouter()


class QueryRequest(BaseModel):
    """自然语言查询请求"""
    question: str
    session_id: Optional[str] = None


class ExecuteRequest(BaseModel):
    """SQL执行请求"""
    sql: str
    session_id: Optional[str] = None


class InsightRequest(BaseModel):
    """Insight生成请求"""
    question: str
    sql: str
    results: List[Dict]
    session_id: Optional[str] = None


class HistoryItem(BaseModel):
    """历史保存请求"""
    session_id: str
    question: str
    sql: str
    result_count: int = 0
    insight: Optional[str] = None


@router.post("/")
async def natural_query(request: QueryRequest):
    """
    自然语言查询
    
    流程：NL → Schema检索 → SQL生成 → 校验 → 执行 → Insight
    """
    service = get_query_service(request.session_id)
    result = await service.natural_query(request.question)
    
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "查询失败"))
    
    return result


@router.post("/execute")
async def execute_sql(request: ExecuteRequest):
    """
    直接执行SQL
    
    带安全校验，只允许SELECT
    """
    service = get_query_service(request.session_id)
    result = await service.execute_sql(request.sql)
    
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "执行失败"))
    
    return result


@router.get("/schema")
async def get_schema():
    """
    获取数据库Schema
    
    从tfrmdataobj/tfrmdataprop读取表和字段信息
    """
    service = get_query_service()
    result = await service.get_schema()
    return result


@router.get("/test-connection")
async def test_connection():
    """
    测试MySQL连接
    
    返回连接状态
    """
    service = get_query_service()
    result = await service.test_connection()
    return result


@router.get("/preview/{table_name}")
async def preview_table(
    table_name: str,
    limit: int = Query(default=5, ge=1, le=100)
):
    """
    预览表数据
    
    返回前N行数据
    """
    service = get_query_service()
    result = await service.preview_table(table_name, limit)
    return result


@router.post("/insight")
async def generate_insight(request: InsightRequest):
    """
    为查询结果生成AI分析
    
    返回关键结论、异常点、建议行动
    """
    service = get_query_service(request.session_id)
    result = await service.generate_insight(
        request.question,
        request.sql,
        request.results
    )
    return result


@router.get("/history/{session_id}")
async def get_history(session_id: str):
    """
    获取会话查询历史
    
    返回当前会话的所有查询记录
    """
    service = get_query_service(session_id)
    result = await service.get_history()
    return {"history": result, "session_id": session_id}


@router.post("/history/{session_id}")
async def save_history_item(session_id: str, item: HistoryItem):
    """
    保存查询历史
    
    手动保存查询记录
    """
    service = get_query_service(session_id)
    await service._save_history(item.question, {
        "sql": item.sql,
        "total": item.result_count,
        "insight": {"summary": item.insight or ""},
        "tables_used": []
    })
    return {"success": True, "session_id": session_id}


@router.delete("/history/{session_id}")
async def clear_history(session_id: str):
    """
    清空会话历史
    
    删除当前会话的所有查询记录
    """
    from app.models.query_history import clear_history
    await clear_history(session_id)
    return {"success": True, "session_id": session_id}


@router.get("/history/all")
async def get_all_history(limit: int = Query(default=20, ge=1, le=100)):
    """
    获取所有历史
    
    返回最近N条查询记录
    """
    service = get_query_service()
    result = await service.get_all_history(limit)
    return {"history": result, "limit": limit}
```

- [ ] **步骤 2：Commit**

```bash
git add backend/app/api/query.py
git commit -m "feat(api): add query API routes - NL2SQL, schema, history endpoints"
```

---

### 任务 10：main.py集成

**文件：**
- 修改：`backend/app/main.py`

- [ ] **步骤 1：导入query路由**

在 `main.py` 第16行添加导入：

```python
from app.api import chat, documents, knowledge, agent, pm_solution, query
```

- [ ] **步骤 2：注册query路由**

在 `main.py` 第67行后添加：

```python
app.include_router(query.router, prefix="/api/v1/query", tags=["数据查询"])
```

- [ ] **步骤 3：初始化SchemaManager**

在 `lifespan` 函数中（第39行后）添加：

```python
    # 初始化数据查询模块
    from app.models.query_history import init_query_history
    init_query_history()
    print("查询历史数据库初始化完成")
```

- [ ] **步骤 4：Commit**

```bash
git add backend/app/main.py
git commit -m "feat(main): integrate query API routes and initialize query history"
```

---

## Phase 3: 前端改动

### 任务 11：InsightCard组件

**文件：**
- 创建：`frontend/vue-app/src/components/query/InsightCard.vue`

- [ ] **步骤 1：创建InsightCard.vue**

```vue
<template>
  <div v-if="insight && (insight.insights?.length || insight.follow_ups?.length)" 
       class="border border-accent-orange/30 bg-accent-orange/5 p-4 mt-4">
    <div class="flex items-center gap-2 mb-3">
      <Icon icon="lucide:lightbulb" class="text-accent-orange" />
      <span class="font-mono text-[11px] font-bold text-accent-orange uppercase tracking-wider">AI 分析</span>
    </div>
    
    <!-- 关键结论 -->
    <ul v-if="insight.insights?.length" class="space-y-2 mb-3">
      <li v-for="(item, i) in insight.insights" :key="i" 
          class="text-[13px] text-primary/70 flex items-start gap-2">
        <span class="text-accent-orange mt-1">•</span>
        <span>{{ item }}</span>
      </li>
    </ul>
    
    <!-- 追问建议 -->
    <div v-if="insight.follow_ups?.length" class="pt-3 border-t border-grid">
      <span class="text-[11px] text-primary/40 mb-2 block">你可以继续问：</span>
      <div class="flex flex-wrap gap-2">
        <button v-for="(q, i) in insight.follow_ups" :key="i"
                @click="$emit('followUp', q)"
                class="px-3 py-1.5 text-[12px] text-accent-orange border border-accent-orange/30 
                       hover:bg-accent-orange/10 transition-colors">
          {{ q }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { Icon } from '@iconify/vue'

defineProps({
  insight: {
    type: Object,
    default: null
  }
})

defineEmits(['followUp'])
</script>
```

- [ ] **步骤 2：Commit**

```bash
git add frontend/vue-app/src/components/query/InsightCard.vue
git commit -m "feat(frontend): add InsightCard component for AI analysis display"
```

---

### 任务 12：QueryHistory组件

**文件：**
- 创建：`frontend/vue-app/src/components/query/QueryHistory.vue`

- [ ] **步骤 1：创建QueryHistory.vue**

```vue
<template>
  <div class="border-t border-grid">
    <div class="h-10 hairline-b flex items-center justify-between px-4">
      <span class="font-mono text-[10px] uppercase text-primary/40 tracking-wider">查询历史</span>
      <button @click="$emit('clear')" 
              class="text-[11px] text-primary/30 hover:text-red-500 transition-colors">
        清空
      </button>
    </div>
    
    <div v-if="history.length === 0" class="p-4 text-center text-[12px] text-primary/30">
      暂无历史记录
    </div>
    
    <div v-else class="max-h-[200px] overflow-y-auto">
      <div v-for="item in history" :key="item.id"
           @click="$emit('select', item)"
           class="p-3 border-b border-grid last:border-0 hover:bg-warm-gray cursor-pointer transition-colors">
        <p class="text-[12px] text-primary truncate mb-1">{{ item.question }}</p>
        <div class="flex items-center justify-between text-[10px] text-primary/30">
          <span class="font-mono truncate max-w-[150px]">{{ item.sql?.slice(0, 50) }}...</span>
          <span>{{ formatTime(item.created_at) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  history: {
    type: Array,
    default: () => []
  }
})

defineEmits(['select', 'clear'])

function formatTime(timeStr) {
  if (!timeStr) return ''
  const date = new Date(timeStr)
  const now = new Date()
  const diff = now - date
  
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`
  return date.toLocaleDateString()
}
</script>
```

- [ ] **步骤 2：Commit**

```bash
git add frontend/vue-app/src/components/query/QueryHistory.vue
git commit -m "feat(frontend): add QueryHistory component for history sidebar"
```

---

### 任务 13：Store和API扩展

**文件：**
- 修改：`frontend/vue-app/src/stores/query.js`
- 修改：`frontend/vue-app/src/api/query.js`

- [ ] **步骤 1：扩展api/query.js**

在现有方法后添加：

```javascript
// 新增方法
getInsight(question, sql, results) {
  return api.post('/query/insight', { question, sql, results })
}

getHistory(sessionId) {
  return api.get(`/query/history/${sessionId}`)
}

getAllHistory(limit = 20) {
  return api.get('/query/history/all', { params: { limit } })
}

saveHistory(sessionId, item) {
  return api.post(`/query/history/${sessionId}`, item)
}

clearHistory(sessionId) {
  return api.delete(`/query/history/${sessionId}`)
}
```

- [ ] **步骤 2：扩展stores/query.js**

在现有状态和方法后添加：

```javascript
// 新增状态
const sessionId = ref('')
const history = ref([])
const insight = ref(null)
const followUps = ref([])

// 新增方法
async function executeQueryWithInsight(q) {
  question.value = q
  loading.value = true
  error.value = ''
  
  try {
    const res = await queryApi.query(q)
    const data = res.data
    
    sessionId.value = data.session_id
    sql.value = data.sql || ''
    
    if (data.results && data.results.length > 0) {
      columns.value = Object.keys(data.results[0])
      results.value = data.results
      totalCount.value = data.total || data.results.length
    }
    
    // 设置Insight
    if (data.insight) {
      insight.value = data.insight
      followUps.value = data.insight.follow_ups || []
    }
    
    // 加载历史
    await loadHistory()
  } catch (e) {
    error.value = e.response?.data?.detail || e.message || '查询失败'
  } finally {
    loading.value = false
  }
}

async function loadHistory() {
  try {
    const res = await queryApi.getAllHistory(20)
    history.value = res.data.history || []
  } catch (e) {
    console.error('Failed to load history:', e)
  }
}

function handleFollowUp(q) {
  executeQueryWithInsight(q)
}

async function clearHistory() {
  if (!sessionId.value) return
  try {
    await queryApi.clearHistory(sessionId.value)
    history.value = []
  } catch (e) {
    console.error('Failed to clear history:', e)
  }
}

return {
  // 新增导出
  sessionId, history, insight, followUps,
  executeQueryWithInsight, loadHistory, handleFollowUp, clearHistory,
}
```

- [ ] **步骤 3：Commit**

```bash
git add frontend/vue-app/src/api/query.js frontend/vue-app/src/stores/query.js
git commit -m "feat(frontend): extend query store and API with history and insight"
```

---

### 任务 14：QueryPage集成

**文件：**
- 修改：`frontend/vue-app/src/views/QueryPage.vue`

- [ ] **步骤 1：导入新组件**

在 `<script setup>` 中添加：

```javascript
import InsightCard from '../components/query/InsightCard.vue'
import QueryHistory from '../components/query/QueryHistory.vue'
```

- [ ] **步骤 2：修改onMounted**

修改 `onMounted`：

```javascript
onMounted(() => {
  store.fetchSchema()
  store.testConnection()
  store.loadHistory()
})
```

- [ ] **步骤 3：添加InsightCard组件**

在 ResultTable 后添加：

```vue
<!-- AI分析卡片 -->
<InsightCard 
  :insight="store.insight" 
  @followUp="store.handleFollowUp($event)" 
/>
```

- [ ] **步骤 4：添加QueryHistory组件**

在 SchemaBrowser 的 preview 部分后添加：

```vue
<!-- 查询历史 -->
<QueryHistory 
  :history="store.history" 
  @select="store.executeQueryWithInsight($event.question)"
  @clear="store.clearHistory()" 
/>
```

- [ ] **步骤 5：修改QueryInput调用**

将 `@query="store.executeQuery($event)"` 改为：

```vue
<QueryInput :loading="store.loading" @query="store.executeQueryWithInsight($event)" />
```

- [ ] **步骤 6：Commit**

```bash
git add frontend/vue-app/src/views/QueryPage.vue
git commit -m "feat(frontend): integrate InsightCard and QueryHistory into QueryPage"
```

---

## 验证步骤

### 后端验证

- [ ] **验证1：启动后端服务**

```bash
cd backend
python -m uvicorn app.main:app --reload --port 8811
```

预期：服务启动，打印"查询历史数据库初始化完成"

- [ ] **验证2：测试MySQL连接**

```bash
curl http://localhost:8812/api/v1/query/test-connection
```

预期：返回 `{"ok": true, ...}`

- [ ] **验证3：获取Schema**

```bash
curl http://localhost:8812/api/v1/query/schema
```

预期：返回表列表，包含tfrmdataobj等表

- [ ] **验证4：执行自然语言查询**

```bash
curl -X POST http://localhost:8812/api/v1/query/ \
  -H "Content-Type: application/json" \
  -d '{"question": "查询库存最多的商品"}'
```

预期：返回SQL、结果、Insight

### 前端验证

- [ ] **验证5：启动前端**

```bash
cd frontend/vue-app
npm run dev
```

预期：前端启动，无报错

- [ ] **验证6：访问查询页面**

浏览器访问 `http://localhost:5173/query`

预期：
- SchemaBrowser显示表列表
- 连接状态显示"MySQL已连接"
- 输入自然语言后返回结果和AI分析
- InsightCard显示分析结论
- QueryHistory显示历史记录

---

## 自检清单

| 检查项 | 状态 | 说明 |
|--------|------|------|
| **规格覆盖度** | ✅ | 所有设计文档中的模块都有对应任务 |
| **占位符扫描** | ✅ | 无TODO/TBD，所有代码完整 |
| **类型一致性** | ✅ | 方法签名在各文件中一致（如search_relevant_schema、execute等） |
| **依赖顺序** | ✅ | 任务按依赖顺序排列：config→db→schema→tools→agent→service→api |

---

## 执行交接

计划已完成并保存到 `docs/superpowers/plans/2026-06-02-data-copilot-implementation.md`。

**两种执行方式：**

1. **子代理驱动（推荐）** - 使用 `superpowers:subagent-driven-development`，每个任务调度新的子代理，任务间审查

2. **内联执行** - 使用 `superpowers:executing-plans`，在当前会话批量执行，设有检查点

**选择哪种方式？**