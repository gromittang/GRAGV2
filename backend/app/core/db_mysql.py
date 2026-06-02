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

    async def execute(self, sql: str, params: Optional[List[Any]] = None) -> Dict:
        """执行SQL并返回结果

        Args:
            sql: SQL语句
            params: 参数列表

        Returns:
            包含success、rows/count或error的字典
        """
        try:
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
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
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
            DataObjCode as table_name,
            DataObjName as display_name,
            ObjDesc as description
        FROM tfrmdataobj
        WHERE DataObjType = '0'
        ORDER BY DataObjCode
        """
        result = await self.execute(sql)
        return result.get("rows", [])

    async def get_schema_columns(self, table_name: str = None) -> List[Dict]:
        """从tfrmdataprop读取字段信息"""
        if table_name:
            sql = """
            SELECT
                FieldName as column_name,
                FieldDesc as display_name,
                DataType as data_type,
                DataWidth as data_length,
                DataDec as description,
                DataObjCode as table_name
            FROM tfrmdataprop
            WHERE DataObjCode = %s
            ORDER BY FieldIndex
            """
            result = await self.execute(sql, [table_name])
        else:
            sql = """
            SELECT
                FieldName as column_name,
                FieldDesc as display_name,
                DataType as data_type,
                DataWidth as data_length,
                DataDec as description,
                DataObjCode as table_name
            FROM tfrmdataprop
            ORDER BY DataObjCode, FieldIndex
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


# 单例和锁
_mysql_manager: Optional[MySQLManager] = None
_init_lock = asyncio.Lock()


async def get_mysql_manager() -> MySQLManager:
    """获取MySQL管理器（单例）"""
    global _mysql_manager
    if _mysql_manager is None:
        async with _init_lock:
            if _mysql_manager is None:  # 双重检查
                _mysql_manager = MySQLManager()
                await _mysql_manager.init_pool()
    return _mysql_manager