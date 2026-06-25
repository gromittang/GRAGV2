"""
数据查询API路由
NL2SQL、Schema浏览、历史管理等端点
"""
from fastapi import APIRouter, HTTPException, Query as QueryParam
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Dict, Optional, Any

from app.services.query_service import get_query_service
from app.models.query_feedback import save_feedback, get_feedback_stats

router = APIRouter()


class QueryRequest(BaseModel):
    """自然语言查询请求"""
    question: str
    session_id: Optional[str] = None


class ExecuteRequest(BaseModel):
    """SQL执行请求"""
    sql: str
    session_id: Optional[str] = None


class InsightRequest(BaseModel):
    """Insight生成请求"""
    question: str
    sql: str
    results: List[Dict[str, Any]]
    session_id: Optional[str] = None


class HistoryItem(BaseModel):
    """历史保存请求"""
    session_id: str
    question: str
    sql: str
    result_count: int = 0
    insight: Optional[str] = None


@router.post("/")
async def natural_query(request: QueryRequest):
    """
    自然语言查询

    流程：NL → Schema检索 → SQL生成 → 校验 → 执行 → Insight
    """
    service = get_query_service(request.session_id)
    result = await service.natural_query(request.question)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "查询失败"))

    return JSONResponse(
        content=result,
        headers={"X-Query-Source": result.get("source", "unknown")},
    )


@router.post("/execute")
async def execute_sql(request: ExecuteRequest):
    """
    直接执行SQL

    带安全校验，只允许SELECT
    """
    service = get_query_service(request.session_id)
    result = await service.execute_sql(request.sql)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "执行失败"))

    return result


@router.get("/schema")
async def get_schema():
    """
    获取数据库Schema

    从tfrmdataobj/tfrmdataprop读取表和字段信息
    """
    service = get_query_service()
    result = await service.get_schema()
    return result


@router.get("/test-connection")
async def test_connection():
    """
    测试MySQL连接

    返回连接状态
    """
    service = get_query_service()
    result = await service.test_connection()
    return result


@router.get("/preview/{table_name}")
async def preview_table(
    table_name: str,
    limit: int = QueryParam(default=5, ge=1, le=100)
):
    """
    预览表数据

    返回前N行数据
    """
    service = get_query_service()
    result = await service.preview_table(table_name, limit)
    return result


@router.post("/insight")
async def generate_insight(request: InsightRequest):
    """
    为查询结果生成AI分析

    返回关键结论、异常点、建议行动
    """
    service = get_query_service(request.session_id)
    result = await service.generate_insight(
        request.question,
        request.sql,
        request.results
    )
    return result


@router.get("/history/{session_id}")
async def get_history(session_id: str):
    """
    获取会话查询历史

    返回当前会话的所有查询记录
    """
    service = get_query_service(session_id)
    result = await service.get_history()
    return {"history": result, "session_id": session_id}


@router.post("/history/{session_id}")
async def save_history_item(session_id: str, item: HistoryItem):
    """
    保存查询历史

    手动保存查询记录
    """
    service = get_query_service(session_id)
    await service._save_history(item.question, {
        "sql": item.sql,
        "total": item.result_count,
        "insight": {"summary": item.insight or ""},
        "tables_used": []
    })
    return {"success": True, "session_id": session_id}


@router.delete("/history/{session_id}")
async def clear_history(session_id: str):
    """
    清空会话历史

    删除当前会话的所有查询记录
    """
    service = get_query_service(session_id)
    result = await service.clear_history()
    return {"success": result, "session_id": session_id}


@router.get("/history/all")
async def get_all_history(limit: int = QueryParam(default=20, ge=1, le=100)):
    """
    获取所有历史

    返回最近N条查询记录
    """
    service = get_query_service()
    result = await service.get_all_history(limit)
    return {"history": result, "limit": limit}


class FeedbackRequest(BaseModel):
    """查询反馈请求"""
    history_id: int
    session_id: str
    question: str = ""
    sql: str = ""
    tables_used: Optional[str] = None
    table_correct: bool = True
    field_correct: bool = True
    result_correct: bool = True
    comment: Optional[str] = None


@router.post("/feedback")
async def submit_feedback(request: FeedbackRequest):
    """提交查询评价"""
    item = {
        "history_id": request.history_id,
        "session_id": request.session_id,
        "question": request.question,
        "sql": request.sql,
        "tables_used": request.tables_used or "[]",
        "table_correct": request.table_correct,
        "field_correct": request.field_correct,
        "result_correct": request.result_correct,
        "comment": request.comment or "",
    }
    feedback_id = await save_feedback(item)
    return {"success": True, "feedback_id": feedback_id}


@router.get("/feedback/stats")
async def feedback_stats():
    """获取反馈统计"""
    stats = await get_feedback_stats()
    return stats


@router.get("/schema/search")
async def search_schema(
    q: str = QueryParam(default="", min_length=1),
    limit: int = QueryParam(default=10, ge=1, le=50)
):
    """
    搜索Schema（表名/注释/字段）

    支持按表名、表注释、字段名、字段注释搜索
    """
    service = get_query_service()
    result = await service.search_schema(q, limit)
    return result


@router.get("/schema/table/{table_name}/fields")
async def get_table_fields(table_name: str):
    """
    获取表的完整字段信息

    返回字段名、类型、长度、注释
    """
    service = get_query_service()
    result = await service.get_table_fields(table_name)
    return result