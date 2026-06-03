"""
向量库管理API
支持重建索引、健康检测
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
import chromadb
import sqlite3
import os

from app.config import get_settings
from app.core.vector_store import get_vector_store_manager
from app.models.document import get_session, Knowledge, Document, Paragraph

router = APIRouter()
settings = get_settings()


class HealthCheckResponse(BaseModel):
    """健康检测结果"""
    knowledge_id: str
    knowledge_name: str
    status: str  # healthy, warning, critical
    issues: List[Dict]
    stats: Dict
    recommendations: List[str]


class HealthCheckListResponse(BaseModel):
    """所有知识库健康检测结果"""
    results: List[HealthCheckResponse]
    summary: Dict


class RebuildIndexResponse(BaseModel):
    """重建索引结果"""
    knowledge_id: str
    knowledge_name: str
    success: bool
    message: str
    stats: Dict


class VectorStoreStats(BaseModel):
    """向量库统计"""
    total_collections: int
    total_vectors: int
    collections: List[Dict]


def get_kb_name(knowledge_id: str) -> str:
    """获取知识库名称"""
    session = get_session()
    kb = session.query(Knowledge).filter(Knowledge.id == knowledge_id).first()
    name = kb.name if kb else "Unknown"
    session.close()
    return name


@router.get("/stats", response_model=VectorStoreStats)
async def get_vector_store_stats():
    """获取向量库整体统计"""
    vector_manager = get_vector_store_manager()
    collections = vector_manager.list_collections()

    coll_list = []
    total_vectors = 0

    for coll in collections:
        count = coll.count()
        total_vectors += count
        coll_list.append({
            "name": coll.name,
            "count": count
        })

    return VectorStoreStats(
        total_collections=len(collections),
        total_vectors=total_vectors,
        collections=coll_list
    )


@router.get("/health/{knowledge_id}", response_model=HealthCheckResponse)
async def check_knowledge_health(knowledge_id: str):
    """检测单个知识库向量健康状态"""
    kb_name = get_kb_name(knowledge_id)
    issues = []
    recommendations = []
    status = "healthy"

    # 1. 检查段落表数据
    session = get_session()
    para_count = session.query(Paragraph).filter(
        Paragraph.knowledge_id == knowledge_id
    ).count()
    doc_count = session.query(Document).filter(
        Document.knowledge_id == knowledge_id
    ).count()
    session.close()

    # 2. 检查向量库数据
    vector_manager = get_vector_store_manager()
    try:
        collection = vector_manager.get_collection(knowledge_id)
        vector_count = collection.count()
    except Exception as e:
        vector_count = 0
        issues.append({
            "type": "collection_missing",
            "severity": "critical",
            "message": f"向量库collection不存在或无法访问: {str(e)}"
        })
        recommendations.append("需要重建向量索引")

    # 3. 检查数据一致性
    if para_count > 0 and vector_count == 0:
        issues.append({
            "type": "vector_empty",
            "severity": "critical",
            "message": f"段落表有{para_count}条数据，但向量库为空"
        })
        recommendations.append("立即重建向量索引")
        status = "critical"

    elif para_count > 0 and vector_count < para_count * 0.5:
        issues.append({
            "type": "vector_insufficient",
            "severity": "warning",
            "message": f"向量库数据不足：段落{para_count}条，向量{vector_count}条"
        })
        recommendations.append("建议重建向量索引以确保完整性")
        status = "warning"

    elif vector_count > 0 and para_count == 0:
        issues.append({
            "type": "paragraph_missing",
            "severity": "warning",
            "message": f"向量库有{vector_count}条数据，但段落表为空"
        })
        recommendations.append("检查段落表是否被意外清空")
        status = "warning"

    # 4. 检查嵌入维度一致性
    if vector_count > 0:
        try:
            # 取一条数据检查metadata
            sample = collection.get(limit=1)
            if sample["metadatas"] and len(sample["metadatas"]) > 0:
                meta = sample["metadatas"][0]
                # 检查必要字段
                required_fields = ["document_id", "knowledge_id"]
                missing_fields = [f for f in required_fields if f not in meta]
                if missing_fields:
                    issues.append({
                        "type": "metadata_missing",
                        "severity": "warning",
                        "message": f"向量metadata缺少字段: {missing_fields}"
                    })
        except Exception as e:
            issues.append({
                "type": "metadata_check_failed",
                "severity": "warning",
                "message": f"无法检查向量metadata: {str(e)}"
            })

    # 5. 如果一切正常
    if len(issues) == 0:
        status = "healthy"
        if para_count == 0 and vector_count == 0:
            issues.append({
                "type": "empty_knowledge",
                "severity": "info",
                "message": "知识库暂无数据"
            })

    stats = {
        "paragraph_count": para_count,
        "document_count": doc_count,
        "vector_count": vector_count,
        "consistency_ratio": round(vector_count / max(para_count, 1), 2) if para_count > 0 else 0
    }

    return HealthCheckResponse(
        knowledge_id=knowledge_id,
        knowledge_name=kb_name,
        status=status,
        issues=issues,
        stats=stats,
        recommendations=recommendations
    )


@router.get("/health/all", response_model=HealthCheckListResponse)
async def check_all_health():
    """检测所有知识库健康状态"""
    session = get_session()
    knowledge_list = session.query(Knowledge).all()
    session.close()

    results = []
    critical_count = 0
    warning_count = 0
    healthy_count = 0

    for kb in knowledge_list:
        # 调用单个检测
        result = await check_knowledge_health(kb.id)
        results.append(result)

        if result.status == "critical":
            critical_count += 1
        elif result.status == "warning":
            warning_count += 1
        else:
            healthy_count += 1

    summary = {
        "total": len(results),
        "healthy": healthy_count,
        "warning": warning_count,
        "critical": critical_count
    }

    return HealthCheckListResponse(results=results, summary=summary)


@router.post("/rebuild/{knowledge_id}", response_model=RebuildIndexResponse)
async def rebuild_knowledge_index(knowledge_id: str):
    """重建单个知识库的向量索引"""
    kb_name = get_kb_name(knowledge_id)

    # 获取段落数据
    session = get_session()
    paragraphs = session.query(Paragraph).filter(
        Paragraph.knowledge_id == knowledge_id
    ).all()

    if len(paragraphs) == 0:
        session.close()
        return RebuildIndexResponse(
            knowledge_id=knowledge_id,
            knowledge_name=kb_name,
            success=False,
            message="知识库没有段落数据，无法重建索引",
            stats={"paragraph_count": 0, "vector_added": 0}
        )

    # 删除旧的向量库collection
    vector_manager = get_vector_store_manager()
    vector_manager.delete_collection(knowledge_id)

    # 创建新的collection
    collection = vector_manager.get_collection(knowledge_id)

    # 构建向量数据
    from llama_index.core import Document
    from llama_index.core.node_parser import SentenceSplitter
    from app.core.embedding import get_default_embedding

    embed_model = get_default_embedding()

    documents = []
    metadatas = []
    ids = []

    for p in paragraphs:
        # 获取文档信息
        doc = session.query(Document).filter(Document.id == p.document_id).first()
        doc_name = doc.name if doc else "未知文档"

        documents.append(p.content)
        metadatas.append({
            "document_id": p.document_id,
            "knowledge_id": knowledge_id,
            "document_name": doc_name,
            "paragraph_id": p.id
        })
        ids.append(p.id)

    session.close()

    # 生成嵌入向量并添加到collection
    try:
        # 批量处理，避免内存溢出
        batch_size = 50
        total_added = 0

        for i in range(0, len(documents), batch_size):
            batch_docs = documents[i:i+batch_size]
            batch_meta = metadatas[i:i+batch_size]
            batch_ids = ids[i:i+batch_size]

            # 生成嵌入向量
            embeddings = embed_model.get_text_embedding_batch(batch_docs)

            # 添加到向量库
            collection.add(
                documents=batch_docs,
                embeddings=embeddings,
                metadatas=batch_meta,
                ids=batch_ids
            )
            total_added += len(batch_docs)

        final_count = collection.count()

        return RebuildIndexResponse(
            knowledge_id=knowledge_id,
            knowledge_name=kb_name,
            success=True,
            message=f"向量索引重建成功，共添加{total_added}条向量",
            stats={
                "paragraph_count": len(paragraphs),
                "vector_added": total_added,
                "final_vector_count": final_count
            }
        )

    except Exception as e:
        return RebuildIndexResponse(
            knowledge_id=knowledge_id,
            knowledge_name=kb_name,
            success=False,
            message=f"重建索引失败: {str(e)}",
            stats={"paragraph_count": len(paragraphs), "vector_added": 0}
        )


@router.post("/rebuild/all")
async def rebuild_all_indexes():
    """重建所有需要重建的知识库索引"""
    # 先检测健康状态
    health_result = await check_all_health()

    rebuilt = []
    failed = []
    skipped = []

    for result in health_result.results:
        # 只重建critical状态的
        if result.status == "critical":
            rebuild_result = await rebuild_knowledge_index(result.knowledge_id)
            if rebuild_result.success:
                rebuilt.append({
                    "knowledge_id": result.knowledge_id,
                    "knowledge_name": result.knowledge_name,
                    "stats": rebuild_result.stats
                })
            else:
                failed.append({
                    "knowledge_id": result.knowledge_id,
                    "knowledge_name": result.knowledge_name,
                    "error": rebuild_result.message
                })
        else:
            skipped.append({
                "knowledge_id": result.knowledge_id,
                "knowledge_name": result.knowledge_name,
                "status": result.status
            })

    return {
        "success": True,
        "rebuilt": rebuilt,
        "failed": failed,
        "skipped": skipped,
        "summary": {
            "rebuilt_count": len(rebuilt),
            "failed_count": len(failed),
            "skipped_count": len(skipped)
        }
    }


@router.get("/test-retrieve/{knowledge_id}")
async def test_retrieve(knowledge_id: str, query: str = "拣货位调整"):
    """测试检索效果（用于调试）"""
    kb_name = get_kb_name(knowledge_id)

    vector_manager = get_vector_store_manager()
    try:
        collection = vector_manager.get_collection(knowledge_id)

        if collection.count() == 0:
            return {
                "success": False,
                "knowledge_id": knowledge_id,
                "knowledge_name": kb_name,
                "message": "向量库为空，无法检索",
                "results": []
            }

        # 使用embedding模型生成查询向量（避免维度不匹配问题）
        from app.core.embedding import get_default_embedding
        embed_model = get_default_embedding()
        query_embedding = embed_model.get_text_embedding(query)

        results = collection.query(
            query_embeddings=[query_embedding],
            where={"knowledge_id": knowledge_id},
            n_results=10
        )

        # 分析返回的文档分布
        session = get_session()
        doc_counts = {}
        retrieved_items = []

        for i, doc_id in enumerate(results["ids"][0]):
            text = results["documents"][0][i] if results["documents"] else ""
            meta = results["metadatas"][0][i] if results["metadatas"] else {}

            doc_name = meta.get("document_name", "Unknown")

            retrieved_items.append({
                "paragraph_id": doc_id[:8],
                "document_name": doc_name,
                "content_preview": text[:100] + "..." if len(text) > 100 else text,
                "distance": results["distances"][0][i] if results.get("distances") else None
            })

            doc_counts[doc_name] = doc_counts.get(doc_name, 0) + 1

        session.close()

        return {
            "success": True,
            "knowledge_id": knowledge_id,
            "knowledge_name": kb_name,
            "query": query,
            "total_results": len(results["ids"][0]),
            "document_distribution": doc_counts,
            "results": retrieved_items
        }

    except Exception as e:
        return {
            "success": False,
            "knowledge_id": knowledge_id,
            "knowledge_name": kb_name,
            "message": f"检索失败: {str(e)}",
            "results": []
        }