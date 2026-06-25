"""
PM 方案工作室反馈模型
SQLite 存储用户对各阶段的评价
"""
from typing import Dict, List
from datetime import datetime
import aiosqlite
import os
import sqlite3

from app.config import get_settings

_settings = get_settings()

FEEDBACK_DB_PATH = os.path.join(_settings.data_dir, "pm_feedback.db")


async def init_pm_feedback_table():
    """初始化 PM 反馈表"""
    os.makedirs(_settings.data_dir, exist_ok=True)

    async with aiosqlite.connect(FEEDBACK_DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pm_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                rating INTEGER NOT NULL CHECK(rating >= 1 AND rating <= 5),
                satisfied INTEGER DEFAULT 1,
                modify_count INTEGER DEFAULT 1,
                stage_output_summary TEXT,
                comment TEXT,
                created_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_pm_feedback_session
            ON pm_feedback(session_id)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_pm_feedback_stage
            ON pm_feedback(stage)
        """)
        await db.commit()


async def save_pm_feedback(item: Dict) -> int:
    """保存 PM 阶段反馈记录"""
    await init_pm_feedback_table()

    async with aiosqlite.connect(FEEDBACK_DB_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO pm_feedback
            (session_id, stage, rating, satisfied, modify_count,
             stage_output_summary, comment, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            item.get("session_id"),
            item.get("stage"),
            item.get("rating", 3),
            1 if item.get("satisfied", True) else 0,
            item.get("modify_count", 1),
            item.get("stage_output_summary", ""),
            item.get("comment", ""),
            item.get("created_at", datetime.now().isoformat())
        ])
        await db.commit()
        return cursor.lastrowid


async def get_pm_feedback_stats() -> Dict:
    """获取 PM 反馈统计（按阶段分组）"""
    await init_pm_feedback_table()

    async with aiosqlite.connect(FEEDBACK_DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute("SELECT COUNT(*) as total FROM pm_feedback")
        total = (await cursor.fetchone())["total"]

        cursor = await db.execute(
            "SELECT AVG(rating) as avg_rating FROM pm_feedback"
        )
        avg_rating = (await cursor.fetchone())["avg_rating"] or 0

        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM pm_feedback WHERE satisfied = 0"
        )
        unsatisfied = (await cursor.fetchone())["cnt"]

        cursor = await db.execute(
            "SELECT AVG(modify_count) as avg_modify FROM pm_feedback"
        )
        avg_modify = (await cursor.fetchone())["avg_modify"] or 0

        # 按阶段分组统计
        cursor = await db.execute("""
            SELECT stage, COUNT(*) as cnt, AVG(rating) as avg_rating,
                   SUM(CASE WHEN satisfied = 0 THEN 1 ELSE 0 END) as unsatisfied
            FROM pm_feedback
            GROUP BY stage
            ORDER BY stage
        """)
        by_stage = []
        for row in await cursor.fetchall():
            r = dict(row)
            stage_total = r["cnt"]
            stage_satisfied = stage_total - r["unsatisfied"]
            by_stage.append({
                "stage": r["stage"],
                "total": stage_total,
                "avg_rating": round(r["avg_rating"], 1) if r["avg_rating"] else 0,
                "satisfaction_rate": round(stage_satisfied / stage_total * 100, 1) if stage_total > 0 else 0,
            })

        return {
            "total": total,
            "avg_rating": round(avg_rating, 1),
            "satisfaction_rate": round((total - unsatisfied) / total * 100, 1) if total > 0 else 0,
            "avg_modify_count": round(avg_modify, 1),
            "by_stage": by_stage,
        }


async def get_pm_feedback_by_session(session_id: str) -> List[Dict]:
    """按会话 ID 获取反馈"""
    await init_pm_feedback_table()

    async with aiosqlite.connect(FEEDBACK_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT * FROM pm_feedback
            WHERE session_id = ?
            ORDER BY created_at DESC
        """, [session_id])
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


def init_pm_feedback():
    """初始化 PM 反馈表（同步入口，用于 lifespan）"""
    os.makedirs(_settings.data_dir, exist_ok=True)

    conn = sqlite3.connect(FEEDBACK_DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pm_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            stage TEXT NOT NULL,
            rating INTEGER NOT NULL CHECK(rating >= 1 AND rating <= 5),
            satisfied INTEGER DEFAULT 1,
            modify_count INTEGER DEFAULT 1,
            stage_output_summary TEXT,
            comment TEXT,
            created_at TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_pm_feedback_session
        ON pm_feedback(session_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_pm_feedback_stage
        ON pm_feedback(stage)
    """)
    conn.commit()
    conn.close()
