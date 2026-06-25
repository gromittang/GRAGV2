"""
Chat 问答反馈模型
SQLite 存储用户对 RAG 回答的评价
"""
from typing import Dict, List
from datetime import datetime
import aiosqlite
import os
import sqlite3

from app.config import get_settings

_settings = get_settings()

FEEDBACK_DB_PATH = os.path.join(_settings.data_dir, "chat_feedback.db")


async def init_chat_feedback_table():
    """初始化 Chat 反馈表"""
    os.makedirs(_settings.data_dir, exist_ok=True)

    async with aiosqlite.connect(FEEDBACK_DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                message_index INTEGER NOT NULL,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                sources TEXT,
                best_relevance_score REAL DEFAULT 0,
                helpful INTEGER DEFAULT 1,
                source_accurate INTEGER DEFAULT 1,
                answer_complete INTEGER DEFAULT 1,
                comment TEXT,
                created_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_feedback_session
            ON chat_feedback(session_id)
        """)
        await db.commit()


async def save_chat_feedback(item: Dict) -> int:
    """保存 Chat 反馈记录"""
    await init_chat_feedback_table()

    async with aiosqlite.connect(FEEDBACK_DB_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO chat_feedback
            (session_id, message_index, question, answer, sources,
             best_relevance_score, helpful, source_accurate, answer_complete,
             comment, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            item.get("session_id"),
            item.get("message_index", 0),
            item.get("question"),
            item.get("answer"),
            item.get("sources", "[]"),
            item.get("best_relevance_score", 0),
            1 if item.get("helpful", True) else 0,
            1 if item.get("source_accurate", True) else 0,
            1 if item.get("answer_complete", True) else 0,
            item.get("comment", ""),
            item.get("created_at", datetime.now().isoformat())
        ])
        await db.commit()
        return cursor.lastrowid


async def get_chat_feedback_stats() -> Dict:
    """获取 Chat 反馈统计"""
    await init_chat_feedback_table()

    async with aiosqlite.connect(FEEDBACK_DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute("SELECT COUNT(*) as total FROM chat_feedback")
        total = (await cursor.fetchone())["total"]

        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM chat_feedback WHERE helpful = 0"
        )
        unhelpful = (await cursor.fetchone())["cnt"]

        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM chat_feedback WHERE source_accurate = 0"
        )
        source_errors = (await cursor.fetchone())["cnt"]

        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM chat_feedback WHERE answer_complete = 0"
        )
        incomplete = (await cursor.fetchone())["cnt"]

        helpful_count = total - unhelpful

        return {
            "total": total,
            "helpful_count": helpful_count,
            "helpful_rate": round(helpful_count / total * 100, 1) if total > 0 else 0,
            "source_accuracy_rate": round((total - source_errors) / total * 100, 1) if total > 0 else 0,
            "completeness_rate": round((total - incomplete) / total * 100, 1) if total > 0 else 0,
            "source_errors": source_errors,
            "incomplete": incomplete,
        }


async def get_chat_feedback_by_session(session_id: str) -> List[Dict]:
    """按会话 ID 获取反馈"""
    await init_chat_feedback_table()

    async with aiosqlite.connect(FEEDBACK_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT * FROM chat_feedback
            WHERE session_id = ?
            ORDER BY created_at DESC
        """, [session_id])
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


def init_chat_feedback():
    """初始化 Chat 反馈表（同步入口，用于 lifespan）"""
    os.makedirs(_settings.data_dir, exist_ok=True)

    conn = sqlite3.connect(FEEDBACK_DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            message_index INTEGER NOT NULL,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            sources TEXT,
            best_relevance_score REAL DEFAULT 0,
            helpful INTEGER DEFAULT 1,
            source_accurate INTEGER DEFAULT 1,
            answer_complete INTEGER DEFAULT 1,
            comment TEXT,
            created_at TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_chat_feedback_session
        ON chat_feedback(session_id)
    """)
    conn.commit()
    conn.close()
