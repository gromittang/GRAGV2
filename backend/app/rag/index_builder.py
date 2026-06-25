"""
索引构建
直接写入 ChromaDB，绕过 LlamaIndex VectorStoreIndex
（避免 langchain/pydantic v1-v2 版本冲突）
"""
from typing import List, Optional, Dict

from llama_index.core import Document

from app.core.embedding import get_default_embedding
from app.core.vector_store import get_vector_store_manager
from app.core.logging import get_logger
from app.rag.document_processor import DocumentProcessor
from app.core.settings import get_industry_settings
from app.config import get_settings

_settings = get_settings()
_log = get_logger("rag.indexer")


class IndexBuilder:
    """索引构建器"""

    def __init__(self, knowledge_id: str = None, industry_type: str = None):
        self.knowledge_id = knowledge_id
        self.industry_type = industry_type
        settings = get_settings()
        industry = get_industry_settings(industry_type or settings.industry_type)
        self.vector_store_manager = get_vector_store_manager()
        self.embed_model = get_default_embedding()
        self.processor = DocumentProcessor(industry_type)
        self.chunk_size = industry.chunk_size
        self.chunk_overlap = industry.chunk_overlap

    def build_index(self, nodes: List) -> list:
        """
        将节点写入 ChromaDB（绕过 VectorStoreIndex 避免 langchain/pydantic 冲突）

        Args:
            nodes: 分块后的节点列表

        Returns:
            写入的 node id 列表
        """
        collection = self.vector_store_manager.get_collection(self.knowledge_id)

        ids = []
        embeddings = []
        documents = []
        metadatas = []

        for node in nodes:
            node_id = node.node_id
            text = node.text
            embedding = self.embed_model.get_text_embedding(text)
            metadata = node.metadata or {}
            # ChromaDB 只接受简单类型
            clean_meta = {k: v for k, v in metadata.items() if isinstance(v, (str, int, float, bool))}

            ids.append(node_id)
            embeddings.append(embedding)
            documents.append(text)
            metadatas.append(clean_meta)

        if ids:
            collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas
            )

        _log.info("索引构建完成: {} 节点", len(ids))
        return ids

    def build_index_from_docs(self, documents: List[Document]) -> list:
        """
        从文档直接构建索引

        Args:
            documents: LlamaIndex Document 列表

        Returns:
            写入的 node id 列表
        """
        # 使用 DocumentProcessor 的 IMG 保护分割，避免图片标记被截断
        nodes = self.processor.split_documents(documents)

        return self.build_index(nodes)