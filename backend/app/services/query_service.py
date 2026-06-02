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
from app.models.query_history import save_history, get_history_by_session, get_all_history_limit, clear_history as clear_history_db


class QueryService:
    """查询编排服务"""

    def __init__(self, session_id: str = None):
        self._session_id = session_id or self._generate_session_id()
        self._agent = None  # 延迟初始化

    def _generate_session_id(self) -> str:
        """生成会话ID"""
        return f"query_{uuid.uuid4().hex[:8]}"

    async def _get_agent(self):
        """获取Agent（延迟初始化）"""
        if self._agent is None:
            self._agent = await get_query_agent()
        return self._agent

    async def natural_query(self, question: str) -> Dict[str, Any]:
        """
        自然语言查询

        Args:
            question: 用户问题

        Returns:
            包含SQL、结果、Insight的完整响应
        """
        agent = await self._get_agent()
        result = await agent.query(question)

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
        agent = await self._get_agent()
        result = await agent.execute_sql(sql)
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
        agent = await self._get_agent()
        insight = await agent._generate_insight(question, results[:10])
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
        return await get_all_history_limit(limit)

    async def clear_history(self) -> bool:
        """清空当前会话历史"""
        return await clear_history_db(self._session_id)


# 单例缓存（按session_id）
_query_services: Dict[str, QueryService] = {}


def get_query_service(session_id: str = None) -> QueryService:
    """获取查询服务"""
    if session_id and session_id in _query_services:
        return _query_services[session_id]

    service = QueryService(session_id)
    _query_services[service._session_id] = service
    return service