"""
PM方案工作室API
支持多阶段方案设计，SSE流式对话
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import json
import uuid
import time

from app.models.document import get_session
from app.models.pm_solution import PMSession, PMStage, PMChat
from app.services.pm_solution_service import PMSolutionService, log_timing

router = APIRouter()


# 阶段模板配置
STAGE_TEMPLATES = {
    "problem": {
        "name": "问题定义",
        "description": "明确问题背景、目标、约束",
        "order": 0,
        "output_schema": {
            "summary": "问题摘要",
            "background": "背景信息",
            "goals": ["目标列表"],
            "constraints": ["约束列表"],
            "stakeholders": ["利益相关者"]
        }
    },
    "analysis": {
        "name": "方案分析",
        "description": "分析多个可行方案",
        "order": 1,
        "output_schema": {
            "options": [{"name": "", "approach": "", "pros": "", "cons": "", "score": 0}],
            "recommendation": "推荐方案"
        }
    },
    "detail": {
        "name": "方案细化",
        "description": "细化选定方案的功能设计",
        "order": 2,
        "output_schema": {
            "features": [{"name": "", "description": "", "priority": ""}],
            "user_stories": ["用户故事"],
            "technical_requirements": ["技术需求"]
        }
    },
    "prd": {
        "name": "PRD生成",
        "description": "生成完整产品需求文档",
        "order": 3,
        "output_schema": {
            "prd_content": "完整PRD文档"
        }
    }
}


# Request/Response Models
class SessionCreateRequest(BaseModel):
    problem: str = Field(..., min_length=1, description="问题描述")
    title: Optional[str] = Field(None, max_length=256, description="会话标题")
    knowledge_id: Optional[str] = Field(None, description="知识库ID")


class SessionUpdateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=256)


class ChatRequest(BaseModel):
    user_input: str = Field(..., min_length=1, description="用户输入")


class RollbackRequest(BaseModel):
    target_phase: int = Field(..., ge=0, le=3, description="目标阶段(0-3)")


class SessionResponse(BaseModel):
    id: str
    title: str
    problem: str
    knowledge_id: str
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


@router.post("/sessions", response_model=SessionResponse)
async def create_session(request: SessionCreateRequest):
    """创建新方案会话"""
    session = get_session()
    try:
        # 获取或创建默认知识库
        if not request.knowledge_id:
            from app.models.document import get_or_create_knowledge
            kb = get_or_create_knowledge(session, "PM方案知识库")
            knowledge_id = kb.id
        else:
            knowledge_id = request.knowledge_id

        # 创建会话
        pm_session = PMSession(
            title=request.title or f"方案分析-{datetime.now().strftime('%Y%m%d')}",
            knowledge_id=knowledge_id,
            problem=request.problem,
            current_stage=0,
            stage_status="active"
        )
        session.add(pm_session)
        session.flush()

        # 创建初始阶段
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
            # 获取stage_type
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


@router.post("/sessions/{session_id}/chat")
async def chat_in_stage(session_id: str, request: ChatRequest):
    """阶段内对话（SSE流式输出）"""
    api_start = time.time()
    log_timing("API", f"收到chat请求 session_id={session_id}, input_len={len(request.user_input)}")

    session = get_session()
    try:
        pm_session = session.query(PMSession).filter(PMSession.id == session_id).first()
        if not pm_session:
            raise HTTPException(404, "会话不存在")

        knowledge_id = pm_session.knowledge_id
        current_stage = pm_session.current_stage
        session.close()
        log_timing("API", f"查询session完成 knowledge_id={knowledge_id}, current_stage={current_stage}", api_start)

        # 调用服务层进行流式对话
        service = PMSolutionService(knowledge_id)

        async def stream_generator():
            stream_start = time.time()
            log_timing("STREAM", "开始流式生成...")
            full_response = ""
            sources = []
            chunk_count = 0

            for chunk in service.chat_stream(
                session_id=session_id,
                stage_type=_get_stage_type(current_stage),
                user_input=request.user_input
            ):
                chunk_count += 1
                if chunk["type"] == "token":
                    full_response += chunk["content"]
                    yield f"data: {json.dumps(chunk)}\n\n"
                elif chunk["type"] == "status":
                    yield f"data: {json.dumps(chunk)}\n\n"
                elif chunk["type"] == "done":
                    sources = chunk.get("sources", [])
                    yield f"data: {json.dumps(chunk)}\n\n"

            log_timing("STREAM", f"流式生成完成，共{chunk_count}个chunk，response_len={len(full_response)}", stream_start)

            # 保存对话记录
            save_start = time.time()
            save_chat_record(session_id, current_stage, request.user_input, full_response, sources)
            log_timing("SAVE", f"保存对话记录完成", save_start)

            log_timing("API", f"chat请求完全处理，总耗时={(time.time()-api_start)*1000:.0f}ms", api_start)

        return StreamingResponse(
            stream_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
        )

    except HTTPException:
        raise
    except Exception as e:
        session.close()
        log_timing("API", f"chat请求失败: {str(e)}")
        raise HTTPException(500, f"对话失败: {str(e)}")


@router.post("/sessions/{session_id}/confirm", response_model=StageOutputResponse)
async def confirm_stage(session_id: str):
    """确认当前阶段，生成结构化输出并推进"""
    session = get_session()
    try:
        pm_session = session.query(PMSession).filter(PMSession.id == session_id).first()
        if not pm_session:
            raise HTTPException(404, "会话不存在")

        current_stage = pm_session.current_stage
        stage_type = _get_stage_type(current_stage)

        # 获取当前阶段记录
        stage_record = session.query(PMStage).filter(
            PMStage.session_id == session_id,
            PMStage.stage_type == stage_type
        ).first()

        if not stage_record:
            raise HTTPException(400, "当前阶段不存在")

        # 获取本阶段所有对话历史
        chats = session.query(PMChat).filter(
            PMChat.session_id == session_id,
            PMChat.stage_id == stage_record.id
        ).order_by(PMChat.created_at).all()

        chat_history = [{"role": c.role, "content": c.content} for c in chats]

        # 调用LLM生成结构化输出
        service = PMSolutionService(pm_session.knowledge_id)
        structured_output = service.generate_structured_output(
            stage_type=stage_type,
            chat_history=chat_history,
            output_schema=STAGE_TEMPLATES[stage_type]["output_schema"]
        )

        # 更新阶段输出
        stage_record.status = "confirmed"
        stage_record.output_data = structured_output
        stage_record.output_summary = _extract_summary(structured_output)
        stage_record.confirmed_at = datetime.utcnow()

        # 推进到下一阶段
        if current_stage < 3:
            pm_session.current_stage = current_stage + 1
            pm_session.stage_status = "active"

            # 检查下一阶段记录是否已存在
            next_stage_type = _get_stage_type(current_stage + 1)
            next_stage = session.query(PMStage).filter(
                PMStage.session_id == session_id,
                PMStage.stage_type == next_stage_type
            ).first()

            if next_stage:
                # 已存在，更新状态
                next_stage.status = "active"
            else:
                # 不存在，创建新记录
                next_stage = PMStage(
                    session_id=session_id,
                    stage_type=next_stage_type,
                    status="active"
                )
                session.add(next_stage)
        else:
            pm_session.stage_status = "completed"

        session.commit()

        result = StageOutputResponse(
            stage_type=stage_type,
            stage_name=STAGE_TEMPLATES[stage_type]["name"],
            status="confirmed",
            output_data=structured_output,
            output_summary=stage_record.output_summary
        )
        session.close()
        return result

    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        session.close()
        raise HTTPException(500, f"确认阶段失败: {str(e)}")


@router.post("/sessions/{session_id}/rollback")
async def rollback_stage(session_id: str, request: RollbackRequest):
    """回溯到指定阶段"""
    session = get_session()
    try:
        pm_session = session.query(PMSession).filter(PMSession.id == session_id).first()
        if not pm_session:
            raise HTTPException(404, "会话不存在")

        target_stage = request.target_phase

        # 删除目标阶段之后所有重复的stage记录，只保留每个type一个
        for stage_order in range(4):
            stage_type = _get_stage_type(stage_order)
            all_stages = session.query(PMStage).filter(
                PMStage.session_id == session_id,
                PMStage.stage_type == stage_type
            ).order_by(PMStage.created_at).all()

            if len(all_stages) > 1:
                # 保留第一个，删除其他重复的
                keep_stage = all_stages[0]
                for dup_stage in all_stages[1:]:
                    session.delete(dup_stage)

                if stage_order > target_stage:
                    # 目标阶段之后的，重置为pending
                    keep_stage.status = "pending"
                    keep_stage.output_data = {}
                    keep_stage.output_summary = ""
                    keep_stage.confirmed_at = None
                elif stage_order == target_stage:
                    # 目标阶段，设为active
                    keep_stage.status = "active"
                elif stage_order < target_stage:
                    # 目标阶段之前的，保持confirmed
                    keep_stage.status = "confirmed"
            elif len(all_stages) == 1:
                if stage_order > target_stage:
                    all_stages[0].status = "pending"
                    all_stages[0].output_data = {}
                    all_stages[0].output_summary = ""
                    all_stages[0].confirmed_at = None
                elif stage_order == target_stage:
                    all_stages[0].status = "active"
            else:
                # 没有记录，创建一个
                new_stage = PMStage(
                    session_id=session_id,
                    stage_type=stage_type,
                    status="active" if stage_order == target_stage else ("confirmed" if stage_order < target_stage else "pending")
                )
                session.add(new_stage)

        # 重置当前阶段
        pm_session.current_stage = target_stage
        pm_session.stage_status = "active"

        session.commit()
        session.close()

        target_stage_type = _get_stage_type(target_stage)
        return {
            "success": True,
            "current_stage": target_stage,
            "message": f"已回溯到阶段 {target_stage}: {STAGE_TEMPLATES[target_stage_type]['name']}"
        }

    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        session.close()
        raise HTTPException(500, f"回溯失败: {str(e)}")


@router.post("/sessions/{session_id}/export")
async def export_prd(session_id: str):
    """导出PRD文档"""
    session = get_session()
    try:
        pm_session = session.query(PMSession).filter(PMSession.id == session_id).first()
        if not pm_session:
            raise HTTPException(404, "会话不存在")

        # 获取所有已确认阶段的输出
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


# Helper functions
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


def _extract_summary(output_data: dict) -> str:
    """提取输出摘要"""
    if "summary" in output_data:
        return output_data["summary"][:200]
    elif "recommendation" in output_data:
        return output_data["recommendation"][:200]
    elif "prd_content" in output_data:
        return output_data["prd_content"][:200]
    else:
        return json.dumps(output_data, ensure_ascii=False)[:200]


def save_chat_record(session_id: str, stage_order: int, user_input: str, response: str, sources: list):
    """保存对话记录"""
    session = get_session()
    try:
        stage_type = _get_stage_type(stage_order)
        stage_record = session.query(PMStage).filter(
            PMStage.session_id == session_id,
            PMStage.stage_type == stage_type
        ).first()

        # 保存用户消息
        user_chat = PMChat(
            session_id=session_id,
            stage_id=stage_record.id if stage_record else None,
            role="user",
            content=user_input,
            sources=[]
        )
        session.add(user_chat)

        # 保存助手回复
        assistant_chat = PMChat(
            session_id=session_id,
            stage_id=stage_record.id if stage_record else None,
            role="assistant",
            content=response,
            sources=sources
        )
        session.add(assistant_chat)

        session.commit()
        session.close()

    except Exception as e:
        print(f"[PM] 保存对话记录失败: {e}")
        session.close()