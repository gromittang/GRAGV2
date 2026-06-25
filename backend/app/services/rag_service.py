"""
RAG 服务入口 — 文档管理
（问答功能已迁移到 app/agents/graph_rag.py）
"""
from typing import List, Dict
import os

from app.config import get_settings
from app.rag.index_builder import IndexBuilder
from app.core.vector_store import get_vector_store_manager

settings = get_settings()


class RAGService:
    """RAG 文档管理服务"""

    def __init__(self, knowledge_id: str = None, industry_type: str = None):
        self.knowledge_id = knowledge_id
        self.industry_type = industry_type or settings.industry_type

    def add_documents(self, documents: List[Dict]) -> Dict:
        """添加文档到知识库"""
        from llama_index.core import Document

        builder = IndexBuilder(self.knowledge_id, self.industry_type)
        llama_docs = []
        for doc in documents:
            llama_doc = Document(
                text=doc.get("content", ""),
                metadata=doc.get("metadata", {}),
                doc_id=doc.get("id", str(os.urandom(8).hex()))
            )
            llama_docs.append(llama_doc)

        builder.build_index_from_docs(llama_docs)
        return {"success": True, "message": f"添加 {len(llama_docs)} 个文档"}

    def delete_document(self, doc_id: str) -> Dict:
        """删除文档"""
        vector_manager = get_vector_store_manager()
        collection = vector_manager.get_collection(self.knowledge_id)

        try:
            results = collection.get(where={"document_id": doc_id})
            if results["ids"]:
                collection.delete(ids=results["ids"])
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_collection_info(self) -> Dict:
        """获取向量库信息"""
        vector_manager = get_vector_store_manager()
        collection = vector_manager.get_collection(self.knowledge_id)
        return {
            "name": collection.name,
            "count": collection.count(),
            "persist_dir": settings.resolved_chroma_persist_dir
        }

    def clear_all(self) -> Dict:
        """清空知识库"""
        vector_manager = get_vector_store_manager()
        try:
            vector_manager.delete_collection(self.knowledge_id)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}



# 服务缓存（按knowledge_id缓存）
_rag_services: Dict[str, RAGService] = {}


def get_rag_service(knowledge_id: str = None, industry_type: str = None) -> RAGService:
    """获取 RAG 服务（按knowledge_id缓存）"""
    cache_key = knowledge_id or "default"
    if cache_key not in _rag_services:
        _rag_services[cache_key] = RAGService(knowledge_id, industry_type)
    return _rag_services[cache_key]