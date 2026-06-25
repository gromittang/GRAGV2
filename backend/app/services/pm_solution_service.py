"""
PM方案工作室服务层（LangGraph 重构后）
LLM 编排逻辑已迁移至 graph_pm.py；本模块保留持久化辅助函数
"""
import json
import time
from typing import List, Dict, Any, Optional
from datetime import datetime

from app.core.logging import get_logger

_log = get_logger("service.pm")


def log_timing(stage: str, message: str, start_time: float = None):
    """记录带耗时的时间日志"""
    elapsed = (time.time() - start_time) * 1000 if start_time else 0
    if start_time:
        _log.info("[PM-{}] {} (耗时: {:.0f}ms)", stage, message, elapsed)
    else:
        _log.info("[PM-{}] {}", stage, message)


# 向后兼容：graph_pm.py 拥有权威副本，此处保留重导出
from app.agents.graph_pm import STAGE_PROMPTS, STAGE_TEMPLATES, STAGE_ORDER  # noqa


def sync_state_to_db(session_id: str, state: dict):
    """将 LangGraph state 中的 stage_outputs / stage_chats 同步到 SQLAlchemy"""
    from app.models.document import get_session
    from app.models.pm_solution import PMSession, PMStage, PMChat

    db = get_session()
    try:
        pm_session = db.query(PMSession).filter(PMSession.id == session_id).first()
        if not pm_session:
            db.close()
            return

        current_stage = state.get("current_stage", "problem")
        stage_idx = STAGE_ORDER.index(current_stage) if current_stage in STAGE_ORDER else 0
        is_completed = state.get("is_completed", False)

        pm_session.current_stage = stage_idx
        pm_session.stage_status = "completed" if is_completed else "active"

        # 同步 stage_outputs → PMStage
        staged_outputs = state.get("stage_outputs", {})
        for st_type, st_data in staged_outputs.items():
            stage_rec = db.query(PMStage).filter(
                PMStage.session_id == session_id,
                PMStage.stage_type == st_type
            ).first()
            if not stage_rec:
                stage_rec = PMStage(session_id=session_id, stage_type=st_type)
                db.add(stage_rec)
                db.flush()
            stage_rec.status = "confirmed"
            stage_rec.output_data = st_data.get("output_data", {})
            stage_rec.output_summary = st_data.get("summary", "")
            if st_data.get("confirmed_at"):
                stage_rec.confirmed_at = datetime.fromtimestamp(st_data["confirmed_at"])

        # 当前活跃阶段
        active_stage = db.query(PMStage).filter(
            PMStage.session_id == session_id,
            PMStage.stage_type == current_stage
        ).first()
        if not active_stage:
            active_stage = PMStage(session_id=session_id, stage_type=current_stage)
            db.add(active_stage)
        active_stage.status = "generated"

        # 同步 stage_chats → PMChat
        stage_chats = state.get("stage_chats", {})
        for st_type, chats in stage_chats.items():
            stage_rec = db.query(PMStage).filter(
                PMStage.session_id == session_id,
                PMStage.stage_type == st_type
            ).first()
            if not stage_rec:
                stage_rec = PMStage(session_id=session_id, stage_type=st_type)
                db.add(stage_rec)
                db.flush()

            # 删除旧聊天记录（replace mode）
            db.query(PMChat).filter(PMChat.stage_id == stage_rec.id).delete()

            for msg in chats:
                chat = PMChat(
                    session_id=session_id,
                    stage_id=stage_rec.id,
                    role=msg.get("role", "user"),
                    content=msg.get("content", ""),
                    sources=msg.get("sources", [])
                )
                db.add(chat)

        db.commit()
        _log.info("[PM-sync] state synced to DB, session={}, stage={}", session_id, current_stage)
    except Exception as e:
        db.rollback()
        _log.error("[PM-sync] failed: {}", e)
    finally:
        db.close()


def load_state_from_db(session_id: str) -> Optional[dict]:
    """从 SQLAlchemy 重建 LangGraph state（用于服务重启后恢复）"""
    from app.models.document import get_session
    from app.models.pm_solution import PMSession, PMStage, PMChat

    db = get_session()
    try:
        pm_session = db.query(PMSession).filter(PMSession.id == session_id).first()
        if not pm_session:
            db.close()
            return None

        current_stage_idx = pm_session.current_stage
        current_stage = STAGE_ORDER[current_stage_idx] if 0 <= current_stage_idx < 4 else "problem"

        # 重建 stage_outputs
        staged_outputs = {}
        stages = db.query(PMStage).filter(PMStage.session_id == session_id).all()
        for st in stages:
            if st.status == "confirmed" and st.output_data:
                staged_outputs[st.stage_type] = {
                    "output_data": st.output_data,
                    "summary": st.output_summary or "",
                    "confirmed_at": st.confirmed_at.timestamp() if st.confirmed_at else None,
                }

        # 重建 stage_chats
        stage_chats = {}
        for st in stages:
            chats = db.query(PMChat).filter(PMChat.stage_id == st.id).order_by(PMChat.created_at).all()
            if chats:
                stage_chats[st.stage_type] = [
                    {"role": c.role, "content": c.content, "sources": c.sources or []}
                    for c in chats
                ]

        # 提取 session_topic
        session_topic = pm_session.problem or ""
        if "problem" in stage_chats:
            for msg in stage_chats["problem"]:
                if msg["role"] == "user":
                    session_topic = msg["content"]
                    break

        state = {
            "session_id": session_id,
            "knowledge_id": pm_session.knowledge_id,
            "session_title": pm_session.title,
            "current_stage": current_stage,
            "stage_order": STAGE_ORDER,
            "user_action": "continue",
            "stage_outputs": staged_outputs,
            "stage_chats": stage_chats,
            "session_topic": session_topic,
            "is_completed": pm_session.stage_status == "completed",
        }

        _log.info("[PM-load] state rebuilt from DB, session={}, stage={}", session_id, current_stage)
        return state

    except Exception as e:
        _log.error("[PM-load] failed: {}", e)
        return None
    finally:
        db.close()
