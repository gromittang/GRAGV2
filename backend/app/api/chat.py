"""
对话问答API - 支持多轮对话和流式输出
基于 LangGraph RAG Agent
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Dict
import asyncio
import uuid
import json
import os
from datetime import datetime
from collections import defaultdict

from app.agents.graph_rag import get_rag_graph
from app.core.observability import get_langgraph_config
from app.config import get_settings

router = APIRouter()
settings = get_settings()

# 会话存储
SESSIONS_DIR = os.path.join(settings.data_dir, "sessions")
os.makedirs(SESSIONS_DIR, exist_ok=True)

session_history: Dict[str, List[Dict]] = defaultdict(list)
_session_locks: Dict[str, asyncio.Lock] = {}
_locks_guard = asyncio.Lock()
MAX_HISTORY = 10


async def _get_session_lock(session_id: str) -> asyncio.Lock:
    if session_id not in _session_locks:
        async with _locks_guard:
            if session_id not in _session_locks:
                _session_locks[session_id] = asyncio.Lock()
    return _session_locks[session_id]


def _get_session_file(session_id: str) -> str:
    return os.path.join(SESSIONS_DIR, f"{session_id}.json")


async def _persist_session(session_id: str):
    lock = await _get_session_lock(session_id)
    async with lock:
        if session_id in session_history and session_history[session_id]:
            data = {
                "session_id": session_id,
                "history": list(session_history[session_id]),
                "title": _generate_session_title(session_history[session_id]),
                "updated_at": datetime.now().isoformat()
            }
            file_path = _get_session_file(session_id)
            tmp_path = file_path + '.tmp'
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, file_path)


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
    stream_failed: bool = False


class ChatResponse(BaseModel):
    answer: str
    sources: List[dict] = []
    related_questions: List[str] = []
    session_id: str
    has_documents: bool = True
    best_relevance_score: float = 0


class ChatFeedbackRequest(BaseModel):
    session_id: str
    message_index: int
    question: str
    answer: str
    sources: Optional[str] = None
    best_relevance_score: float = 0
    helpful: bool = True
    source_accurate: bool = True
    answer_complete: bool = True
    comment: Optional[str] = None


@router.post("/", response_model=ChatResponse)
async def chat_query(request: ChatRequest):
    """对话问答接口（非流式）"""
    if not request.question:
        raise HTTPException(400, "问题不能为空")

    session_id = request.session_id or str(uuid.uuid4())

    if session_id not in session_history:
        session_history[session_id] = _load_session_from_file(session_id)

    history = session_history[session_id]

    # SSE回退去重：若 SSE 实际已成功，直接返回已存储的回复
    if request.stream_failed and history:
        last_msg = history[-1]
        if last_msg.get("role") == "assistant" and last_msg.get("content"):
            return ChatResponse(
                answer=last_msg["content"],
                sources=last_msg.get("sources", []),
                related_questions=generate_related_questions(request.question),
                session_id=session_id,
                has_documents=True
            )

    graph = get_rag_graph()
    config = get_langgraph_config(session_id)

    final_state = await graph.ainvoke(
        {
            "question": request.question,
            "messages": [{"role": m["role"], "content": m["content"]} for m in history],
        },
        config=config,
    )

    answer = final_state.get("answer", "")
    sources = final_state.get("sources", [])
    has_docs = final_state.get("has_documents", True)
    best_relevance_score = final_state.get("best_relevance_score", 0)

    session_history[session_id].append({"role": "user", "content": request.question})
    session_history[session_id].append({"role": "assistant", "content": answer, "sources": sources, "best_relevance_score": best_relevance_score})

    if len(session_history[session_id]) > MAX_HISTORY * 2:
        session_history[session_id] = session_history[session_id][-MAX_HISTORY * 2:]

    await _persist_session(session_id)

    related_questions = generate_related_questions(request.question)

    return ChatResponse(
        answer=answer,
        sources=sources,
        related_questions=related_questions,
        session_id=session_id,
        has_documents=has_docs,
        best_relevance_score=best_relevance_score
    )


@router.post("/stream")
async def chat_query_stream(request: ChatRequest):
    """流式对话问答接口（SSE）"""
    if not request.question:
        raise HTTPException(400, "问题不能为空")

    session_id = request.session_id or str(uuid.uuid4())

    if session_id not in session_history:
        session_history[session_id] = _load_session_from_file(session_id)

    history = session_history[session_id]

    async def event_generator():
        graph = get_rag_graph()
        config = get_langgraph_config(session_id)

        full_answer = ""
        sources = []

        try:
            async for chunk in graph.astream(
                {
                    "question": request.question,
                    "messages": [{"role": m["role"], "content": m["content"]} for m in history],
                },
                config=config,
                stream_mode="custom",
            ):
                event_data = json.dumps(chunk, ensure_ascii=False)
                yield f"data: {event_data}\n\n"

                if chunk.get("type") == "token":
                    full_answer += chunk.get("content", "")
                elif chunk.get("type") == "done":
                    sources = chunk.get("sources", [])

            # 流结束后持久化会话
            if full_answer:
                session_history[session_id].append({"role": "user", "content": request.question})
                session_history[session_id].append({"role": "assistant", "content": full_answer, "sources": sources})
                if len(session_history[session_id]) > MAX_HISTORY * 2:
                    session_history[session_id] = session_history[session_id][-MAX_HISTORY * 2:]
                await _persist_session(session_id)

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


@router.post("/feedback")
async def submit_feedback(request: ChatFeedbackRequest):
    """提交 Chat 问答评价"""
    from app.models.chat_feedback import save_chat_feedback

    item = {
        "session_id": request.session_id,
        "message_index": request.message_index,
        "question": request.question,
        "answer": request.answer,
        "sources": request.sources or "[]",
        "best_relevance_score": request.best_relevance_score,
        "helpful": request.helpful,
        "source_accurate": request.source_accurate,
        "answer_complete": request.answer_complete,
        "comment": request.comment or "",
    }
    feedback_id = await save_chat_feedback(item)
    return {"success": True, "feedback_id": feedback_id}


@router.get("/feedback/stats")
async def feedback_stats():
    """获取 Chat 反馈统计"""
    from app.models.chat_feedback import get_chat_feedback_stats
    stats = await get_chat_feedback_stats()
    return stats


def generate_related_questions(question: str) -> List[str]:
    """生成相关问题"""
    related = []
    if "入库" in question:
        related.extend(["入库操作流程是什么？", "如何查看入库记录？"])
    if "出库" in question:
        related.extend(["出库操作流程是什么？", "如何查看出库记录？"])
    related.extend(["系统常见问题有哪些？", "操作手册目录"])
    return list(set(related))[:5]
