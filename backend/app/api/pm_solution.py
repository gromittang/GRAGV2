"""
PM方案工作室API（LangGraph 重构）
核心对话/确认/回退端点使用 LangGraph 图编排
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import json
import uuid
import time

from langgraph.types import Command

from app.core.logging import get_logger
from app.models.document import get_session
from app.models.pm_solution import PMSession, PMStage, PMChat
from app.agents.graph_pm import (
    get_pm_graph, STAGE_TEMPLATES, STAGE_ORDER,
)
from app.services.pm_solution_service import (
    log_timing,
    sync_state_to_db,
    load_state_from_db,
)

_log = get_logger("api.pm")

router = APIRouter()


# ============================================================
# Request/Response Models
# ============================================================

class SessionCreateRequest(BaseModel):
    problem: str = Field(..., min_length=1, description="问题描述")
    title: Optional[str] = Field(None, max_length=256, description="会话标题")
    knowledge_id: Optional[str] = Field(None, description="知识库ID，传空字符串表示不限定知识库（检索全部）")


class SessionUpdateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=256)


class ChatRequest(BaseModel):
    user_input: str = Field(..., min_length=1, description="用户输入")
    current_phase: Optional[int] = Field(None, ge=0, le=3, description="用户当前所在的阶段(0-3)")


class ConfirmRequest(BaseModel):
    user_input: Optional[str] = Field(None, description="确认前用户在输入框的未发送内容")


class RollbackRequest(BaseModel):
    target_phase: int = Field(..., ge=0, le=3, description="目标阶段(0-3)")


class StageSwitchRequest(BaseModel):
    current_stage: int = Field(..., ge=0, le=3, description="切换到的阶段(0-3)")


class PMFeedbackRequest(BaseModel):
    session_id: str
    stage: str = Field(..., description="problem|analysis|detail|prd")
    rating: int = Field(ge=1, le=5, description="1-5 星评分")
    satisfied: bool = True
    modify_count: int = 1
    stage_output_summary: Optional[str] = None
    comment: Optional[str] = None


class SessionResponse(BaseModel):
    id: str
    title: str
    problem: str
    knowledge_id: Optional[str]
    document_id: Optional[str]
    current_stage: int
    stage_status: str
    stages: List[Dict]
    created_at: str
    updated_at: str


class SessionListResponse(BaseModel):
    total: int
    sessions: List[Dict]


class StageOutputResponse(BaseModel):
    stage_type: str
    stage_name: str
    status: str
    output_data: Dict
    output_summary: str


# ============================================================
# Session CRUD (largely unchanged)
# ============================================================

@router.post("/sessions", response_model=SessionResponse)
async def create_session(request: SessionCreateRequest):
    """创建新方案会话"""
    session = get_session()
    try:
        if request.knowledge_id == "":
            knowledge_id = None
        elif request.knowledge_id:
            knowledge_id = request.knowledge_id
        else:
            from app.models.document import get_or_create_knowledge
            kb = get_or_create_knowledge(session, "PM方案知识库")
            knowledge_id = kb.id

        pm_session = PMSession(
            title=request.title or f"方案分析-{datetime.now().strftime('%Y%m%d')}",
            knowledge_id=knowledge_id,
            problem=request.problem,
            current_stage=0,
            stage_status="active"
        )
        session.add(pm_session)
        session.flush()

        initial_stage = PMStage(
            session_id=pm_session.id,
            stage_type="problem",
            status="active"
        )
        session.add(initial_stage)
        session.commit()

        result = _build_session_response(pm_session, session)
        session.close()
        return result

    except Exception as e:
        session.rollback()
        session.close()
        raise HTTPException(500, f"创建会话失败: {str(e)}")


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    knowledge_id: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100)
):
    """获取会话列表"""
    session = get_session()
    try:
        query = session.query(PMSession)
        if knowledge_id:
            query = query.filter(PMSession.knowledge_id == knowledge_id)

        total = query.count()
        sessions = query.order_by(PMSession.updated_at.desc()).limit(limit).all()

        result_list = []
        for s in sessions:
            stages_info = session.query(PMStage).filter(
                PMStage.session_id == s.id
            ).all()
            result_list.append({
                "id": s.id,
                "title": s.title,
                "problem": s.problem[:100] + "..." if len(s.problem) > 100 else s.problem,
                "knowledge_id": s.knowledge_id,
                "current_stage": s.current_stage,
                "stage_status": s.stage_status,
                "stages": [{"type": st.stage_type, "status": st.status} for st in stages_info],
                "created_at": s.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "updated_at": s.updated_at.strftime("%Y-%m-%d %H:%M:%S")
            })

        session.close()
        return SessionListResponse(total=total, sessions=result_list)

    except Exception as e:
        session.close()
        raise HTTPException(500, f"获取会话列表失败: {str(e)}")


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session_detail(session_id: str):
    """获取会话详情"""
    session = get_session()
    try:
        pm_session = session.query(PMSession).filter(PMSession.id == session_id).first()
        if not pm_session:
            raise HTTPException(404, "会话不存在")

        result = _build_session_response(pm_session, session)
        session.close()
        return result

    except HTTPException:
        raise
    except Exception as e:
        session.close()
        raise HTTPException(500, f"获取会话详情失败: {str(e)}")


@router.get("/sessions/{session_id}/chats")
async def get_session_chats(session_id: str):
    """获取会话的对话记录（包含sources和stage信息）"""
    session = get_session()
    try:
        pm_session = session.query(PMSession).filter(PMSession.id == session_id).first()
        if not pm_session:
            raise HTTPException(404, "会话不存在")

        chats = session.query(PMChat).filter(
            PMChat.session_id == session_id
        ).order_by(PMChat.created_at).all()

        result_list = []
        for chat in chats:
            stage_type = None
            if chat.stage_id:
                stage = session.query(PMStage).filter(PMStage.id == chat.stage_id).first()
                if stage:
                    stage_type = stage.stage_type

            result_list.append({
                "id": chat.id,
                "role": chat.role,
                "content": chat.content,
                "sources": chat.sources or [],
                "stage_type": stage_type,
                "created_at": chat.created_at.strftime("%Y-%m-%d %H:%M:%S")
            })

        session.close()
        return {"success": True, "chats": result_list}

    except HTTPException:
        raise
    except Exception as e:
        session.close()
        raise HTTPException(500, f"获取对话记录失败: {str(e)}")


@router.patch("/sessions/{session_id}/title")
async def update_session_title(session_id: str, request: SessionUpdateRequest):
    """更新会话标题"""
    session = get_session()
    try:
        pm_session = session.query(PMSession).filter(PMSession.id == session_id).first()
        if not pm_session:
            raise HTTPException(404, "会话不存在")

        pm_session.title = request.title
        session.commit()
        session.close()

        return {"success": True, "title": request.title}

    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        session.close()
        raise HTTPException(500, f"更新标题失败: {str(e)}")


# ============================================================
# Core Interaction Endpoints (LangGraph powered)
# ============================================================

def _make_config(session_id: str) -> dict:
    return {"configurable": {"thread_id": session_id}}


def _build_initial_state(session_id: str, knowledge_id: str, title: str,
                         user_input: str, problem: str) -> dict:
    """构建首次调用的 initial_state"""
    return {
        "session_id": session_id,
        "knowledge_id": knowledge_id,
        "session_title": title,
        "current_stage": "problem",
        "stage_order": STAGE_ORDER,
        "user_input": user_input,
        "user_action": "continue",
        "stage_outputs": {},
        "stage_chats": {},
        "session_topic": problem or user_input,
        "is_completed": False,
    }


async def _sse_stream(graph, input_data, config: dict):
    """将 graph.astream(stream_mode="custom") 转换为 SSE 事件"""
    t0 = time.time()
    chunk_count = 0
    try:
        async for chunk in graph.astream(input_data, config, stream_mode="custom"):
            chunk_count += 1
            if isinstance(chunk, dict):
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
    except Exception as e:
        log_timing("SSE", f"stream error after {chunk_count} chunks: {e}")
        yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"
    log_timing("SSE", f"stream done, chunks={chunk_count}, elapsed={int((time.time()-t0)*1000)}ms")


@router.post("/sessions/{session_id}/chat")
async def chat_in_stage(session_id: str, request: ChatRequest):
    """阶段内对话（SSE流式输出，LangGraph 驱动）"""
    api_start = time.time()
    log_timing("API", f"chat session={session_id}, input_len={len(request.user_input)}")

    session = get_session()
    try:
        pm_session = session.query(PMSession).filter(PMSession.id == session_id).first()
        if not pm_session:
            raise HTTPException(404, "会话不存在")

        knowledge_id = pm_session.knowledge_id
        title = pm_session.title
        problem = pm_session.problem
        session.close()
    except HTTPException:
        raise
    except Exception as e:
        session.close()
        raise HTTPException(500, f"查询会话失败: {str(e)}")

    graph = get_pm_graph()
    config = _make_config(session_id)

    # 检查是首次调用还是恢复
    state_snapshot = graph.get_state(config)
    is_first_call = (state_snapshot is None or state_snapshot.values is None or
                     not state_snapshot.values)

    if is_first_call:
        log_timing("API", "first call — graph.astream with initial_state")
        initial_state = _build_initial_state(session_id, knowledge_id, title,
                                             request.user_input, problem)
        input_data = initial_state
    else:
        log_timing("API", "resuming — Command(continue)")
        input_data = Command(resume={"action": "continue", "input": request.user_input})

    stream_gen = _sse_stream(graph, input_data, config)

    async def stream_generator():
        async for event in stream_gen:
            yield event
        # 流结束后同步 state 到 DB
        try:
            final_state = graph.get_state(config)
            if final_state and final_state.values:
                sync_state_to_db(session_id, final_state.values)
        except Exception as e:
            log_timing("SYNC", f"post-chat sync error: {e}")
        log_timing("API", f"chat done, total={int((time.time()-api_start)*1000)}ms")

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )


@router.post("/sessions/{session_id}/confirm")
async def confirm_stage(session_id: str, request: ConfirmRequest):
    """确认当前阶段，推进到下一阶段（LangGraph 驱动）"""
    api_start = time.time()
    session = get_session()
    try:
        pm_session = session.query(PMSession).filter(PMSession.id == session_id).first()
        if not pm_session:
            raise HTTPException(404, "会话不存在")

        current_stage_idx = pm_session.current_stage
        stage_type = _get_stage_type(current_stage_idx)
        session.close()
    except HTTPException:
        raise
    except Exception as e:
        session.close()
        raise HTTPException(500, f"查询会话失败: {str(e)}")

    graph = get_pm_graph()
    config = _make_config(session_id)

    log_timing("CONFIRM", f"confirming stage={stage_type}")

    # 检查是否存在检查点（服务重启后 MemorySaver 为空）
    state_snapshot = graph.get_state(config)
    has_checkpoint = state_snapshot is not None and state_snapshot.values

    # 构建 resume 数据：包含 action 和可选的用户输入
    resume_data = {"action": "confirm"}
    if request.user_input:
        resume_data["input"] = request.user_input

    if not has_checkpoint:
        # 服务重启后无检查点：从 DB 重建状态，先跑通图到 interrupt 建立检查点
        log_timing("CONFIRM", "no checkpoint, rebuilding from DB to establish interrupt")
        state = load_state_from_db(session_id)
        if not state:
            raise HTTPException(404, "无法恢复会话状态")

        async def stream_generator():
            nonlocal config
            try:
                yield f"data: {json.dumps({'type': 'status', 'content': '正在确认当前阶段...'}, ensure_ascii=False)}\n\n"

                # First run: establish checkpoint (generate current stage, output discarded)
                try:
                    await graph.ainvoke(state, config)
                except Exception:
                    pass  # GraphInterrupt expected — checkpoint now exists

                yield f"data: {json.dumps({'type': 'status', 'content': '正在推进到下一阶段...'}, ensure_ascii=False)}\n\n"

                # Now resume with confirm action
                async for event in _sse_stream(
                    graph,
                    Command(resume=resume_data),
                    config
                ):
                    yield event
            except Exception as e:
                log_timing("SSE", f"confirm+rebuild error: {e}")
                yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"

            # Sync state to DB
            try:
                final_state = graph.get_state(config)
                if final_state and final_state.values:
                    sync_state_to_db(session_id, final_state.values)
            except Exception as e:
                log_timing("SYNC", f"post-confirm sync error: {e}")
            log_timing("CONFIRM", f"confirm done, total={int((time.time()-api_start)*1000)}ms")

        return StreamingResponse(
            stream_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
        )

    # 正常路径：检查点存在，直接恢复确认
    async def stream_generator():
        yield f"data: {json.dumps({'type': 'status', 'content': '正在确认阶段，推进到下一阶段...'}, ensure_ascii=False)}\n\n"
        async for event in _sse_stream(
            graph,
            Command(resume=resume_data),
            config
        ):
            yield event
        # 流结束后同步到 DB
        try:
            final_state = graph.get_state(config)
            if final_state and final_state.values:
                sync_state_to_db(session_id, final_state.values)
        except Exception as e:
            log_timing("SYNC", f"post-confirm sync error: {e}")
        log_timing("CONFIRM", f"confirm done, total={int((time.time()-api_start)*1000)}ms")

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )


@router.post("/sessions/{session_id}/rollback")
async def rollback_stage(session_id: str, request: RollbackRequest):
    """回溯到指定阶段（LangGraph 检查点 + DB 双路径）"""
    target_idx = request.target_phase
    target_stage = _get_stage_type(target_idx)
    log_timing("ROLLBACK", f"session={session_id}, target={target_stage}")

    graph = get_pm_graph()
    config = _make_config(session_id)

    # 先尝试从 MemorySaver 检查点历史回退
    try:
        states = [s async for s in graph.aget_state_history(config)]
        target_state = None
        for s in states:
            if s.values and s.values.get("current_stage") == target_stage:
                target_state = s
                break

        if target_state is not None and len(target_state.config.get("configurable", {}).get("checkpoint_id", "")) > 0:
            log_timing("ROLLBACK", "checkpoint found in MemorySaver, replaying")
            stream_gen = _sse_stream(
                graph,
                Command(resume={"action": "continue", "input": "请重新分析"}),
                target_state.config
            )

            async def stream_generator():
                async for event in stream_gen:
                    yield event
                try:
                    final_state = graph.get_state(target_state.config)
                    if final_state and final_state.values:
                        sync_state_to_db(session_id, final_state.values)
                except Exception as e:
                    log_timing("SYNC", f"post-rollback sync error: {e}")

            return StreamingResponse(
                stream_generator(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
            )
    except Exception as e:
        log_timing("ROLLBACK", f"aget_state_history failed: {e}")

    # 降级路径：从 DB 重建状态
    log_timing("ROLLBACK", "no checkpoint history — rebuilding from DB")
    state = load_state_from_db(session_id)
    if not state:
        raise HTTPException(404, "无法恢复会话状态")

    # 清除目标阶段之后的阶段输出和聊天
    target_index = STAGE_ORDER.index(target_stage)
    staged_outputs = state.get("stage_outputs", {})
    stage_chats = state.get("stage_chats", {})

    for st in STAGE_ORDER:
        st_idx = STAGE_ORDER.index(st)
        if st_idx > target_index:
            staged_outputs.pop(st, None)
            stage_chats.pop(st, None)

    state["current_stage"] = target_stage
    state["user_action"] = "continue"
    state["user_input"] = "请重新分析"
    state["stage_outputs"] = staged_outputs
    state["stage_chats"] = stage_chats
    state["is_completed"] = False

    # 清理 DB 中的下游阶段
    db = get_session()
    try:
        pm_session = db.query(PMSession).filter(PMSession.id == session_id).first()
        if pm_session:
            pm_session.current_stage = target_idx
            pm_session.stage_status = "active"
            for st in STAGE_ORDER:
                st_idx = STAGE_ORDER.index(st)
                if st_idx > target_idx:
                    stage_rec = db.query(PMStage).filter(
                        PMStage.session_id == session_id,
                        PMStage.stage_type == st
                    ).first()
                    if stage_rec:
                        stage_rec.status = "pending"
                        stage_rec.output_data = {}
                        stage_rec.output_summary = ""
                        stage_rec.confirmed_at = None
                        db.query(PMChat).filter(PMChat.stage_id == stage_rec.id).delete()
                    # 目标阶段设为 active
                    elif st_idx == target_idx:
                        target_rec = db.query(PMStage).filter(
                            PMStage.session_id == session_id,
                            PMStage.stage_type == st
                        ).first()
                        if target_rec:
                            target_rec.status = "active"
            db.commit()
    except Exception as e:
        db.rollback()
        log_timing("ROLLBACK", f"DB cleanup error: {e}")
    finally:
        db.close()

    stream_gen = _sse_stream(
        graph,
        state,  # initial state for new execution
        config
    )

    async def stream_generator():
        async for event in stream_gen:
            yield event
        try:
            final_state = graph.get_state(config)
            if final_state and final_state.values:
                sync_state_to_db(session_id, final_state.values)
        except Exception as e:
            log_timing("SYNC", f"post-rollback sync error: {e}")

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )


@router.patch("/sessions/{session_id}/current-stage")
async def switch_current_stage(session_id: str, request: StageSwitchRequest):
    """切换当前显示阶段（纯导航，不影响阶段数据）"""
    session = get_session()
    try:
        pm_session = session.query(PMSession).filter(PMSession.id == session_id).first()
        if not pm_session:
            raise HTTPException(404, "会话不存在")

        pm_session.current_stage = request.current_stage
        session.commit()
        session.close()

        return {"success": True, "current_stage": request.current_stage}

    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        session.close()
        raise HTTPException(500, f"切换阶段失败: {str(e)}")


@router.post("/sessions/{session_id}/export")
async def export_prd(session_id: str):
    """导出PRD文档"""
    session = get_session()
    try:
        pm_session = session.query(PMSession).filter(PMSession.id == session_id).first()
        if not pm_session:
            raise HTTPException(404, "会话不存在")

        stages = session.query(PMStage).filter(
            PMStage.session_id == session_id
        ).order_by(PMStage.created_at).all()

        prd_content = f"# PRD文档 - {pm_session.title}\n\n"
        prd_content += f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        prd_content += f"## 问题描述\n{pm_session.problem}\n\n"

        for stage in stages:
            if stage.status == "confirmed":
                template = STAGE_TEMPLATES[stage.stage_type]
                prd_content += f"## {template['name']}\n\n"

                output = stage.output_data
                if isinstance(output, dict):
                    for key, value in output.items():
                        prd_content += f"### {key}\n"
                        if isinstance(value, list):
                            for item in value:
                                if isinstance(item, dict):
                                    prd_content += f"- {json.dumps(item, ensure_ascii=False)}\n"
                                else:
                                    prd_content += f"- {item}\n"
                        else:
                            prd_content += f"{value}\n\n"
                        prd_content += "\n"

        session.close()

        return {
            "success": True,
            "prd_content": prd_content,
            "filename": f"{pm_session.title}_PRD.md"
        }

    except HTTPException:
        raise
    except Exception as e:
        session.close()
        raise HTTPException(500, f"导出失败: {str(e)}")


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """删除会话"""
    session = get_session()
    try:
        pm_session = session.query(PMSession).filter(PMSession.id == session_id).first()
        if not pm_session:
            raise HTTPException(404, "会话不存在")

        session.delete(pm_session)
        session.commit()
        session.close()

        return {"success": True, "message": f"会话 {session_id} 已删除"}

    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        session.close()
        raise HTTPException(500, f"删除失败: {str(e)}")


# ============================================================
# Feedback Endpoints
# ============================================================

@router.post("/feedback")
async def submit_feedback(request: PMFeedbackRequest):
    """提交 PM 阶段评价"""
    from app.models.pm_feedback import save_pm_feedback

    item = {
        "session_id": request.session_id,
        "stage": request.stage,
        "rating": request.rating,
        "satisfied": request.satisfied,
        "modify_count": request.modify_count,
        "stage_output_summary": request.stage_output_summary or "",
        "comment": request.comment or "",
    }
    feedback_id = await save_pm_feedback(item)
    return {"success": True, "feedback_id": feedback_id}


@router.get("/feedback/stats")
async def feedback_stats():
    """获取 PM 反馈统计（按阶段分组）"""
    from app.models.pm_feedback import get_pm_feedback_stats
    stats = await get_pm_feedback_stats()
    return stats


# ============================================================
# Helper Functions
# ============================================================

def _build_session_response(pm_session: PMSession, db_session) -> SessionResponse:
    """构建会话响应"""
    stages = db_session.query(PMStage).filter(
        PMStage.session_id == pm_session.id
    ).order_by(PMStage.created_at).all()

    stages_info = []
    for st in stages:
        stages_info.append({
            "type": st.stage_type,
            "name": STAGE_TEMPLATES[st.stage_type]["name"],
            "status": st.status,
            "output_summary": st.output_summary[:100] if st.output_summary else ""
        })

    return SessionResponse(
        id=pm_session.id,
        title=pm_session.title,
        problem=pm_session.problem,
        knowledge_id=pm_session.knowledge_id,
        document_id=pm_session.document_id,
        current_stage=pm_session.current_stage,
        stage_status=pm_session.stage_status,
        stages=stages_info,
        created_at=pm_session.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        updated_at=pm_session.updated_at.strftime("%Y-%m-%d %H:%M:%S")
    )


def _get_stage_type(stage_order: int) -> str:
    """获取阶段类型"""
    stage_types = ["problem", "analysis", "detail", "prd"]
    return stage_types[stage_order] if 0 <= stage_order < 4 else "problem"
