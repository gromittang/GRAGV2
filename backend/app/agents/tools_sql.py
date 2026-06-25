"""
SQL工具集
Schema搜索、SQL生成、SQL校验、SQL执行
"""
from langchain.tools import BaseTool
from typing import Dict, Any, Optional, Type, List
from pydantic import BaseModel, Field
import json
import re
import asyncio

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

    _schema_manager: Any = None

    def __init__(self, schema_manager=None):
        super().__init__()
        self._schema_manager = schema_manager

    def _run(self, query: str) -> str:
        """执行Schema搜索"""
        if not query or not isinstance(query, str):
            return json.dumps({"error": "查询不能为空"}, ensure_ascii=False)
        if self._schema_manager is None:
            return json.dumps({"error": "Schema管理器未初始化"}, ensure_ascii=False)

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果在异步环境中，创建新任务
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self._schema_manager.search_relevant_schema(query)
                    )
                    result = future.result()
            else:
                result = loop.run_until_complete(self._schema_manager.search_relevant_schema(query))
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    async def _arun(self, query: str) -> str:
        """异步执行Schema搜索"""
        if self._schema_manager is None:
            return json.dumps({"error": "Schema管理器未初始化"}, ensure_ascii=False)
        try:
            result = await self._schema_manager.search_relevant_schema(query)
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)


class SQLGenerateInput(BaseModel):
    """SQL生成输入"""
    question: str = Field(description="用户的自然语言问题")
    schema_context: str = Field(description="相关的Schema上下文")


class SQLGenerateTool(BaseTool):
    """SQL生成工具"""

    name: str = "sql_generate"
    description: str = "根据用户问题和Schema上下文生成安全的SQL查询语句。"
    args_schema: Type[BaseModel] = SQLGenerateInput

    _llm: Any = None

    def __init__(self, llm=None):
        super().__init__()
        self._llm = llm or get_llm()

    def _run(self, question: str, schema_context: str) -> str:
        """执行SQL生成"""
        if not question or not isinstance(question, str):
            return json.dumps({"error": "问题不能为空"}, ensure_ascii=False)
        if not schema_context:
            return json.dumps({"error": "Schema上下文不能为空"}, ensure_ascii=False)
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
            return json.dumps({"error": "无法解析LLM输出", "raw": content}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    async def _arun(self, question: str, schema_context: str) -> str:
        """异步执行SQL生成"""
        prompt = SQL_GENERATION_PROMPT.format(
            schema_context=schema_context,
            user_question=question
        )

        try:
            response = await self._llm.ainvoke(prompt)
            content = response.content if hasattr(response, 'content') else str(response)

            # 提取JSON
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                return json_match.group(0)
            return json.dumps({"error": "无法解析LLM输出", "raw": content}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)


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
        if not sql or not isinstance(sql, str):
            return json.dumps({"valid": False, "reason": "SQL语句不能为空"}, ensure_ascii=False)

        sql_lower = sql.lower().strip()

        # 使用正则匹配独立单词
        pattern = re.compile(r'\b(' + '|'.join(FORBIDDEN_KEYWORDS) + r')\b', re.IGNORECASE)
        match = pattern.search(sql)
        if match:
            return json.dumps({
                "valid": False,
                "reason": f"禁止使用 {match.group().upper()} 操作",
                "sql": sql
            }, ensure_ascii=False)

        # 必须是SELECT
        if not sql_lower.startswith("select"):
            return json.dumps({
                "valid": False,
                "reason": "只允许SELECT查询",
                "sql": sql
            }, ensure_ascii=False)

        # 禁止SELECT *
        if "select *" in sql_lower or "select  *" in sql_lower:
            return json.dumps({
                "valid": False,
                "reason": "禁止SELECT *，请指定具体字段",
                "sql": sql
            }, ensure_ascii=False)

        # 强制添加LIMIT（聚合查询用更大上限，普通查询100）
        has_aggregation = any(kw in sql_lower for kw in ["group by", "count(", "sum(", "avg(", "max(", "min("])
        if "limit" not in sql_lower:
            limit_value = "1000" if has_aggregation else "100"
            sql = sql.rstrip(";") + f" LIMIT {limit_value}"

        return json.dumps({
            "valid": True,
            "sql": sql,
            "reason": "校验通过"
        }, ensure_ascii=False)

    async def _arun(self, sql: str) -> str:
        """异步执行SQL校验"""
        return self._run(sql)


class SQLExecuteInput(BaseModel):
    """SQL执行输入"""
    sql: str = Field(description="待执行的SQL语句")


class SQLExecuteTool(BaseTool):
    """SQL执行工具"""

    name: str = "sql_execute"
    description: str = "执行校验通过的SQL语句，返回查询结果。"
    args_schema: Type[BaseModel] = SQLExecuteInput

    _mysql_manager: Any = None

    def __init__(self, mysql_manager=None):
        super().__init__()
        self._mysql_manager = mysql_manager

    def _run(self, sql: str) -> str:
        """执行SQL"""
        if not sql or not isinstance(sql, str):
            return json.dumps({"error": "SQL语句不能为空"}, ensure_ascii=False)
        if self._mysql_manager is None:
            return json.dumps({"error": "MySQL管理器未初始化"}, ensure_ascii=False)

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self._mysql_manager.execute(sql)
                    )
                    result = future.result()
            else:
                result = loop.run_until_complete(self._mysql_manager.execute(sql))
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    async def _arun(self, sql: str) -> str:
        """异步执行SQL"""
        if self._mysql_manager is None:
            return json.dumps({"error": "MySQL管理器未初始化"}, ensure_ascii=False)
        try:
            result = await self._mysql_manager.execute(sql)
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)


def get_sql_tools(schema_manager=None, mysql_manager=None, llm=None) -> List[BaseTool]:
    """获取SQL工具集"""
    return [
        SchemaSearchTool(schema_manager=schema_manager),
        SQLGenerateTool(llm=llm),
        SQLValidateTool(),
        SQLExecuteTool(mysql_manager=mysql_manager),
    ]