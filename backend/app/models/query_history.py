"""
查询历史模型
SQLite存储查询历史记录
"""
from typing import Dict, List, Optional
import json
from datetime import datetime
import aiosqlite
import os
import asyncio

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
                trace_json TEXT,
                favorite INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)
        # 迁移：旧表无 trace_json 列则自动追加
        try:
            await db.execute("ALTER TABLE query_history ADD COLUMN trace_json TEXT")
        except Exception:
            pass  # 列已存在，忽略
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
            (session_id, question, sql, result_count, insight, tables_used,
             trace_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            item.get("session_id"),
            item.get("question"),
            item.get("sql"),
            item.get("result_count", 0),
            item.get("insight", ""),
            item.get("tables_used", "[]"),
            item.get("trace_json", "{}"),
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


def init_query_history():
    """初始化查询历史（同步入口，用于lifespan）"""
    import sqlite3
    os.makedirs(_settings.data_dir, exist_ok=True)

    conn = sqlite3.connect(HISTORY_DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS query_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            question TEXT NOT NULL,
            sql TEXT NOT NULL,
            result_count INTEGER DEFAULT 0,
            insight TEXT,
            tables_used TEXT,
            trace_json TEXT,
            favorite INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)
    try:
        cursor.execute("ALTER TABLE query_history ADD COLUMN trace_json TEXT")
    except Exception:
        pass
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_session_id ON query_history(session_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_created_at ON query_history(created_at)
    """)
    conn.commit()
    conn.close()