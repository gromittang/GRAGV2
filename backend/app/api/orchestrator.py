from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from app.orchestrator import get_router
from app.orchestrator.dispatch import dispatch_to_rag, dispatch_to_nl2sql, dispatch_to_pm
from app.core.logging import get_logger

router = APIRouter()
_log = get_logger("api.orchestrator")


class OrchestratorRequest(BaseModel):
    question: str


class OrchestratorResponse(BaseModel):
    intent: str
    confidence: float
    source: str
    routed_to: str
    clarification: Optional[str] = None
    answer: Optional[str] = None
    sources: Optional[list] = None
    sql: Optional[str] = None
    data: Optional[dict] = None
    insight: Optional[dict] = None
    error: Optional[str] = None


# === Handler ===

@router.post("/chat", response_model=OrchestratorResponse)
async def orchestrator_chat(request: OrchestratorRequest):
    router_instance = get_router()
    route_result = await router_instance.route(request.question)

    resp = OrchestratorResponse(
        intent=route_result.intent,
        confidence=route_result.confidence,
        source=route_result.source,
        routed_to="none",
        clarification=route_result.clarification,
        error=route_result.error,
    )

    if route_result.intent == "clarify":
        return resp

    if route_result.intent == "direct_answer":
        resp.routed_to = "direct"
        resp.answer = route_result.clarification or "请尝试更具体地描述您的问题"
        return resp

    if route_result.intent == "solution_design":
        pm = dispatch_to_pm()
        resp.routed_to = pm["routed_to"]
        resp.answer = "方案设计功能请访问 PM 方案工作室"
        return resp

    if route_result.intent == "hybrid":
        resp.routed_to = "hybrid_placeholder"
        resp.answer = (
            "跨模块综合分析功能即将在下一版本上线。当前支持：\n"
            "- 数据查询：直接输入业务问题\n"
            "- 文档检索：输入SOP/规范相关问题\n"
            "- 方案设计：访问PM方案工作室"
        )
        return resp

    try:
        if route_result.intent == "data_query":
            resp.routed_to = "nl2sql"
            nl2sql_result = await dispatch_to_nl2sql(request.question)
            resp.sql = nl2sql_result["sql"]
            resp.data = nl2sql_result["data"]
            resp.insight = nl2sql_result["insight"]

        elif route_result.intent == "knowledge_search":
            resp.routed_to = "rag"
            rag_result = await dispatch_to_rag(request.question)
            resp.answer = rag_result["answer"]
            resp.sources = rag_result["sources"]

        else:
            _log.warning("unknown intent: {} source={}", route_result.intent, route_result.source)
            resp.error = f"未知的意图类型：{route_result.intent}"

    except Exception as e:
        _log.warning("dispatch failed: intent={} error={:.100}", route_result.intent, str(e))
        resp.error = f"{'数据库查询' if route_result.intent == 'data_query' else '知识库检索'}失败：{str(e)[:100]}"

    return resp
