"""
知识库管理API
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict

from app.models.document import get_session, Knowledge, Document
from app.core.settings import get_all_industries

router = APIRouter()


class KnowledgeInfo(BaseModel):
    id: str
    name: str
    description: str
    document_count: int
    industry_type: str = "general"


@router.get("/industries")
async def list_industries():
    """获取所有行业配置"""
    return {"industries": get_all_industries()}


@router.get("/stats")
async def get_knowledge_stats():
    """获取知识库统计"""
    session = get_session()
    try:
        total_kb = session.query(Knowledge).count()
        total_docs = session.query(Document).count()
        session.close()

        return {
            "total_knowledge_bases": total_kb,
            "total_documents": total_docs
        }
    except Exception as e:
        session.close()
        raise HTTPException(500, f"统计失败: {str(e)}")