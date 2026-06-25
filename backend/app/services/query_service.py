"""
查询编排服务
数据查询统一入口（委托给 DataQueryGateway）、Schema管理、历史管理

Phase 1: natural_query() 改为调用 DataQueryGateway。
_query_via_langgraph / _translate_columns / _save_history 已迁移到 Gateway。
"""
from typing import Dict, Any, List, Optional
import uuid

from app.agents.query_agent import get_query_agent
from app.core.schema_manager import get_schema_manager
from app.core.db_mysql import get_mysql_manager
from app.core.logging import get_logger
from app.core.observability import get_langgraph_config
from app.models.query_history import get_history_by_session, get_all_history_limit, clear_history as clear_history_db

_log = get_logger("service.query")


class QueryService:
    """查询编排服务（Phase 1: 退化为 Gateway 薄适配器 + Schema/History 管理）"""

    def __init__(self, session_id: str = None):
        self._session_id = session_id or self._generate_session_id()
        self._agent = None  # 延迟初始化（仍被 execute_sql / generate_insight 使用）

    def _generate_session_id(self) -> str:
        """生成会话ID"""
        return f"query_{uuid.uuid4().hex[:8]}"

    async def _get_agent(self):
        """获取 Agent（延迟初始化，按 session 隔离）

        仍被 execute_sql() 和 generate_insight() 使用。
        natural_query() 已改为走 Gateway，不再依赖此方法。
        """
        if self._agent is None:
            self._agent = await get_query_agent(self._session_id)
        return self._agent

    async def natural_query(self, question: str) -> Dict[str, Any]:
        """
        自然语言查询（委托给 DataQueryGateway）

        Args:
            question: 用户问题

        Returns:
            包含SQL、结果、Insight的完整响应（保持与改造前兼容的格式）
        """
        from app.core.data_query_gateway import get_gateway

        gateway = get_gateway()
        ctx = {
            "langgraph_config": get_langgraph_config(self._session_id),
            "user_context": {},
        }
        result = await gateway.execute(question, self._session_id, context=ctx)

        # 将 UnifiedQueryResult 映射为兼容旧 API 的 dict 格式
        insight_dict = {}
        if result.insight:
            insight_dict = {
                "summary": result.insight.summary,
                "insights": result.insight.insights,
                "follow_ups": result.insight.follow_ups,
            }

        # 将 list-of-lists 的 rows 转为 list-of-dicts（兼容旧 QueryAgent 返回格式）
        # 旧 QueryAgent 返回 [{"plu_code": "502620", ...}, ...]
        # graph_nl2sql 返回 [["502620", ...], ...]
        # 前端 store 通过 Object.keys(results[0]) 提取列名 → 必须转 dict
        dict_results = []
        if result.success and result.rows and result.columns:
            for row in result.rows:
                if isinstance(row, dict):
                    dict_results.append(row)
                elif isinstance(row, (list, tuple)):
                    row_dict = {}
                    for i, val in enumerate(row):
                        if i < len(result.columns):
                            row_dict[result.columns[i]] = val
                    dict_results.append(row_dict)

        return {
            "success": result.success,
            "sql": result.sql or "",
            "results": dict_results,
            "columns": result.columns,
            "total": result.total,
            "insight": insight_dict,
            "confidence": result.confidence,
            "explanation": "",
            "tables_used": [],  # Phase 1: Executor 不返回此信息，保留空列表
            "question": result.question,
            "session_id": self._session_id,
            "history_id": result.history_id,  # Gateway 内部保存并返回 ID
            "source": result.source,          # Phase 1 新增字段
            "error": result.error_message or "",
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

    async def get_history(self) -> List[Dict]:
        """获取当前会话历史"""
        return await get_history_by_session(self._session_id)

    async def get_all_history(self, limit: int = 20) -> List[Dict]:
        """获取所有历史（最近N条）"""
        return await get_all_history_limit(limit)

    async def clear_history(self) -> bool:
        """清空当前会话历史"""
        return await clear_history_db(self._session_id)

    async def search_schema(self, query: str, limit: int = 10) -> Dict:
        """
        搜索Schema（表名/注释/字段）

        Args:
            query: 搜索关键词
            limit: 返回数量限制

        Returns:
            匹配的表和字段列表
        """
        mysql_manager = await get_mysql_manager()

        # 搜索表
        tables = await mysql_manager.get_schema_tables()
        matched_tables = []
        for table in tables:
            name = table.get("table_name", "")
            display_name = table.get("display_name", "")
            desc = table.get("description", "")
            if query.lower() in name.lower() or query.lower() in display_name.lower() or query.lower() in desc.lower():
                matched_tables.append({
                    "name": name,
                    "display_name": display_name,
                    "description": desc,
                    "match_type": "table"
                })

        # 搜索字段（仅搜索前limit个表，避免性能问题）
        matched_columns = []
        for table in matched_tables[:limit]:
            columns = await mysql_manager.get_schema_columns(table["name"])
            for col in columns:
                col_name = col.get("column_name", "")
                col_display = col.get("display_name", "")
                col_desc = col.get("description", "")
                if query.lower() in col_name.lower() or query.lower() in col_display.lower() or query.lower() in col_desc.lower():
                    matched_columns.append({
                        "table_name": table["name"],
                        "column_name": col_name,
                        "display_name": col_display,
                        "data_type": col.get("data_type", ""),
                        "match_type": "column"
                    })

        return {
            "tables": matched_tables[:limit],
            "columns": matched_columns[:limit],
            "session_id": self._session_id
        }

    async def get_table_fields(self, table_name: str) -> Dict:
        """
        获取表的完整字段信息

        Args:
            table_name: 表名

        Returns:
            表信息和字段列表
        """
        mysql_manager = await get_mysql_manager()

        # 获取字段
        columns = await mysql_manager.get_schema_columns(table_name)

        # 获取表信息
        tables = await mysql_manager.get_schema_tables()
        table_info = next((t for t in tables if t["table_name"] == table_name), None)

        return {
            "table_name": table_name,
            "display_name": table_info.get("display_name", table_name) if table_info else table_name,
            "description": table_info.get("description", "") if table_info else "",
            "columns": columns,
            "session_id": self._session_id
        }


# 单例缓存（按session_id）
_query_services: Dict[str, QueryService] = {}


def get_query_service(session_id: str = None) -> QueryService:
    """获取查询服务"""
    if session_id and session_id in _query_services:
        return _query_services[session_id]

    service = QueryService(session_id)
    _query_services[service._session_id] = service
    return service