"""
检索器
支持向量检索 + BM25 混合检索
"""
from llama_index.core.retrievers import VectorIndexRetriever, BaseRetriever
from llama_index.core import QueryBundle
from typing import List, Optional
import jieba

from app.core.settings import get_industry_settings
from app.config import get_settings

_settings = get_settings()


class HybridRetriever(BaseRetriever):
    """
    混合检索器
    向量检索 + BM25 关键词检索
    使用简单的加权融合
    """

    def __init__(
        self,
        vector_retriever: VectorIndexRetriever,
        bm25_retriever: Optional[BaseRetriever] = None,
        alpha: float = 0.5,  # 向量权重
        top_k: int = 5
    ):
        self._vector_retriever = vector_retriever
        self._bm25_retriever = bm25_retriever
        self._alpha = alpha
        self._top_k = top_k

    def _retrieve(self, query_bundle: QueryBundle) -> List:
        """
        执行混合检索

        Args:
            query_bundle: 查询

        Returns:
            融合后的节点列表
        """
        # 向量检索
        vector_nodes = self._vector_retriever.retrieve(query_bundle)

        # BM25 检索
        bm25_nodes = []
        if self._bm25_retriever:
            bm25_nodes = self._bm25_retriever.retrieve(query_bundle)

        if not bm25_nodes:
            return vector_nodes[:self._top_k]

        # 简单融合：加权排序
        node_scores = {}

        for i, node in enumerate(vector_nodes):
            node_id = node.node_id
            score = (len(vector_nodes) - i) / len(vector_nodes) * self._alpha
            node_scores[node_id] = node_scores.get(node_id, 0) + score

        for i, node in enumerate(bm25_nodes):
            node_id = node.node_id
            score = (len(bm25_nodes) - i) / len(bm25_nodes) * (1 - self._alpha)
            node_scores[node_id] = node_scores.get(node_id, 0) + score

        # 按分数排序
        all_nodes = {}
        for node in vector_nodes + bm25_nodes:
            all_nodes[node.node_id] = node

        sorted_ids = sorted(node_scores.keys(), key=lambda x: node_scores[x], reverse=True)
        result_nodes = [all_nodes[nid] for nid in sorted_ids[:self._top_k]]

        return result_nodes


def create_retriever(index, knowledge_id: str = None, industry_type: str = None) -> BaseRetriever:
    """
    创建检索器

    Args:
        index: VectorStoreIndex
        knowledge_id: 知识库ID
        industry_type: 行业类型

    Returns:
        检索器实例
    """
    industry = get_industry_settings(industry_type or _settings.industry_type)
    top_k = industry.retrieval_top_k
    use_bm25 = industry.use_bm25

    # 向量检索器
    vector_retriever = VectorIndexRetriever(
        index=index,
        similarity_top_k=top_k * 2  # 取多一些用于融合
    )

    if not use_bm25:
        return vector_retriever

    # BM25 检索器
    try:
        from llama_index.retrievers.bm25 import BM25Retriever
        bm25_retriever = BM25Retriever.from_defaults(
            nodes=list(index.docstore.docs.values()),
            similarity_top_k=top_k * 2
        )

        return HybridRetriever(
            vector_retriever=vector_retriever,
            bm25_retriever=bm25_retriever,
            alpha=0.6,  # 向量权重稍高
            top_k=top_k
        )
    except Exception as e:
        print(f"[Retriever] BM25 创建失败，使用纯向量检索: {e}")
        return vector_retriever


def chinese_keyword_extract(text: str) -> List[str]:
    """
    中文关键词提取

    Args:
        text: 输入文本

    Returns:
        关键词列表
    """
    # 使用 jieba 分词
    words = jieba.cut(text)
    # 过滤短词
    keywords = [w for w in words if len(w) >= 2]
    return keywords