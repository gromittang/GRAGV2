"""
查询反馈模型
SQLite存储测试人员对查询结果的评价
"""
from typing import Dict, List
from datetime import datetime
import aiosqlite
import os
import sqlite3

from app.config import get_settings

_settings = get_settings()

HISTORY_DB_PATH = os.path.join(_settings.data_dir, "query_history.db")


async def init_feedback_table():
    """初始化反馈表"""
    os.makedirs(_settings.data_dir, exist_ok=True)

    async with aiosqlite.connect(HISTORY_DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS query_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                history_id INTEGER NOT NULL,
                session_id TEXT NOT NULL,
                question TEXT NOT NULL,
                sql TEXT NOT NULL,
                tables_used TEXT,
                table_correct INTEGER DEFAULT 1,
                field_correct INTEGER DEFAULT 1,
                result_correct INTEGER DEFAULT 1,
                comment TEXT,
                created_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_feedback_session ON query_feedback(session_id)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_feedback_history ON query_feedback(history_id)
        """)
        await db.commit()


async def save_feedback(item: Dict) -> int:
    """保存反馈记录"""
    await init_feedback_table()

    async with aiosqlite.connect(HISTORY_DB_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO query_feedback
            (history_id, session_id, question, sql, tables_used,
             table_correct, field_correct, result_correct, comment, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            item.get("history_id"),
            item.get("session_id"),
            item.get("question"),
            item.get("sql"),
            item.get("tables_used", "[]"),
            1 if item.get("table_correct", True) else 0,
            1 if item.get("field_correct", True) else 0,
            1 if item.get("result_correct", True) else 0,
            item.get("comment", ""),
            item.get("created_at", datetime.now().isoformat())
        ])
        await db.commit()
        return cursor.lastrowid


async def get_feedback_stats() -> Dict:
    """获取反馈统计"""
    await init_feedback_table()

    async with aiosqlite.connect(HISTORY_DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute("SELECT COUNT(*) as total FROM query_feedback")
        total = (await cursor.fetchone())["total"]

        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM query_feedback WHERE result_correct = 0"
        )
        failures = (await cursor.fetchone())["cnt"]

        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM query_feedback WHERE table_correct = 0"
        )
        table_errors = (await cursor.fetchone())["cnt"]

        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM query_feedback WHERE field_correct = 0"
        )
        field_errors = (await cursor.fetchone())["cnt"]

        return {
            "total": total,
            "result_failures": failures,
            "table_errors": table_errors,
            "field_errors": field_errors,
            "accuracy": round((total - failures) / total * 100, 1) if total > 0 else 0,
        }


async def get_feedback_by_session(session_id: str) -> List[Dict]:
    """按会话ID获取反馈"""
    await init_feedback_table()

    async with aiosqlite.connect(HISTORY_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT * FROM query_feedback
            WHERE session_id = ?
            ORDER BY created_at DESC
        """, [session_id])
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_all_feedback(limit: int = 50) -> List[Dict]:
    """获取最近N条反馈"""
    await init_feedback_table()

    async with aiosqlite.connect(HISTORY_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT * FROM query_feedback
            ORDER BY created_at DESC
            LIMIT ?
        """, [limit])
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


def init_query_feedback():
    """初始化反馈表（同步入口，用于lifespan）"""
    os.makedirs(_settings.data_dir, exist_ok=True)

    conn = sqlite3.connect(HISTORY_DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS query_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            history_id INTEGER NOT NULL,
            session_id TEXT NOT NULL,
            question TEXT NOT NULL,
            sql TEXT NOT NULL,
            tables_used TEXT,
            table_correct INTEGER DEFAULT 1,
            field_correct INTEGER DEFAULT 1,
            result_correct INTEGER DEFAULT 1,
            comment TEXT,
            created_at TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_feedback_session ON query_feedback(session_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_feedback_history ON query_feedback(history_id)
    """)
    conn.commit()
    conn.close()
