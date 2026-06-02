"""
对话问答API - 支持多轮对话和流式输出
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Dict
import uuid
import json
import os
from datetime import datetime
from collections import defaultdict

from app.services.rag_service import get_rag_service
from app.config import get_settings

router = APIRouter()
settings = get_settings()

# 会话存储
SESSIONS_DIR = os.path.join(settings.data_dir, "sessions")
os.makedirs(SESSIONS_DIR, exist_ok=True)

session_history: Dict[str, List[Dict]] = defaultdict(list)
MAX_HISTORY = 10


def _get_session_file(session_id: str) -> str:
    return os.path.join(SESSIONS_DIR, f"{session_id}.json")


def _persist_session(session_id: str):
    if session_id in session_history and session_history[session_id]:
        data = {
            "session_id": session_id,
            "history": session_history[session_id],
            "title": _generate_session_title(session_history[session_id]),
            "updated_at": datetime.now().isoformat()
        }
        with open(_get_session_file(session_id), 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def _generate_session_title(history: List[Dict]) -> str:
    for msg in history:
        if msg["role"] == "user":
            content = msg["content"]
            return content[:30] + "..." if len(content) > 30 else content
    return "新对话"


def _load_session_from_file(session_id: str) -> List[Dict]:
    filepath = _get_session_file(session_id)
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("history", [])
        except Exception:
            pass
    return []


def _load_all_sessions() -> List[Dict]:
    sessions = []
    for filename in os.listdir(SESSIONS_DIR):
        if filename.endswith(".json"):
            filepath = os.path.join(SESSIONS_DIR, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    sessions.append({
                        "session_id": data.get("session_id", ""),
                        "title": data.get("title", "未命名"),
                        "message_count": len(data.get("history", [])),
                        "updated_at": data.get("updated_at", "")
                    })
            except Exception:
                pass
    sessions.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return sessions


class ChatRequest(BaseModel):
    question: str
    session_id: Optional[str] = None
    context_type: Optional[str] = "all"


class ChatResponse(BaseModel):
    answer: str
    sources: List[dict] = []
    related_questions: List[str] = []
    session_id: str
    has_documents: bool = True


@router.post("/", response_model=ChatResponse)
async def chat_query(request: ChatRequest):
    """对话问答接口"""
    if not request.question:
        raise HTTPException(400, "问题不能为空")

    session_id = request.session_id or str(uuid.uuid4())

    if session_id not in session_history:
        session_history[session_id] = _load_session_from_file(session_id)

    history = session_history[session_id]

    rag_service = get_rag_service()
    result = rag_service.query(request.question, history=history)

    session_history[session_id].append({"role": "user", "content": request.question})
    session_history[session_id].append({"role": "assistant", "content": result["answer"], "sources": result.get("sources", [])})

    if len(session_history[session_id]) > MAX_HISTORY * 2:
        session_history[session_id] = session_history[session_id][-MAX_HISTORY * 2:]

    _persist_session(session_id)

    related_questions = generate_related_questions(request.question)

    return ChatResponse(
        answer=result["answer"],
        sources=result.get("sources", []),
        related_questions=related_questions,
        session_id=session_id,
        has_documents=result.get("has_docs", True)
    )


@router.post("/stream")
async def chat_query_stream(request: ChatRequest):
    """流式对话问答接口"""
    if not request.question:
        raise HTTPException(400, "问题不能为空")

    session_id = request.session_id or str(uuid.uuid4())

    if session_id not in session_history:
        session_history[session_id] = _load_session_from_file(session_id)

    history = session_history[session_id]

    async def event_generator():
        rag_service = get_rag_service()
        full_answer = ""

        try:
            for chunk in rag_service.query_stream(request.question, history=history):
                event_data = json.dumps(chunk, ensure_ascii=False)
                yield f"data: {event_data}\n\n"

                if chunk["type"] == "token":
                    full_answer += chunk["content"]
                elif chunk["type"] == "done":
                    session_history[session_id].append({"role": "user", "content": request.question})
                    session_history[session_id].append({"role": "assistant", "content": full_answer, "sources": chunk.get("sources", [])})
                    if len(session_history[session_id]) > 12:
                        session_history[session_id] = session_history[session_id][-12:]
                    _persist_session(session_id)

        except Exception as e:
            error_data = json.dumps({"type": "error", "content": "系统繁忙"}, ensure_ascii=False)
            yield f"data: {error_data}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/sessions")
async def list_sessions():
    """获取所有历史会话"""
    return {"sessions": _load_all_sessions()}


@router.get("/sessions/{session_id}")
async def get_session_detail(session_id: str):
    """获取指定会话详情"""
    if session_id in session_history:
        history = session_history[session_id]
    else:
        history = _load_session_from_file(session_id)
    return {"session_id": session_id, "history": history}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """删除指定会话"""
    if session_id in session_history:
        del session_history[session_id]
    filepath = _get_session_file(session_id)
    if os.path.exists(filepath):
        os.remove(filepath)
    return {"success": True}


def generate_related_questions(question: str) -> List[str]:
    """生成相关问题"""
    related = []
    if "入库" in question:
        related.extend(["入库操作流程是什么？", "如何查看入库记录？"])
    if "出库" in question:
        related.extend(["出库操作流程是什么？", "如何查看出库记录？"])
    related.extend(["系统常见问题有哪些？", "操作手册目录"])
    return list(set(related))[:5]