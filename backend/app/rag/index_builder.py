"""
索引构建
LlamaIndex VectorStoreIndex
"""
from llama_index.core import VectorStoreIndex, StorageContext, Document
from llama_index.core.node_parser import SentenceSplitter
from typing import List, Optional, Dict

from app.core.embedding import get_default_embedding
from app.core.vector_store import get_vector_store_manager
from app.rag.document_processor import DocumentProcessor
from app.core.settings import get_industry_settings
from app.config import get_settings


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

    def build_index(self, nodes: List) -> VectorStoreIndex:
        """
        从节点构建索引

        Args:
            nodes: 分块后的节点列表

        Returns:
            VectorStoreIndex
        """
        vector_store = self.vector_store_manager.get_vector_store(self.knowledge_id)

        storage_context = StorageContext.from_defaults(
            vector_store=vector_store
        )

        index = VectorStoreIndex(
            nodes,
            storage_context=storage_context,
            embed_model=self.embed_model
        )

        print(f"[IndexBuilder] 索引构建完成: {len(nodes)} 节点")
        return index

    def build_index_from_docs(self, documents: List[Document]) -> VectorStoreIndex:
        """
        从文档直接构建索引

        Args:
            documents: LlamaIndex Document 列表

        Returns:
            VectorStoreIndex
        """
        # 分块
        splitter = SentenceSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap
        )
        nodes = splitter.get_nodes_from_documents(documents)

        return self.build_index(nodes)

    def add_documents(self, index: VectorStoreIndex, file_paths: List[str], metadata: Dict = None):
        """
        向现有索引添加文档

        Args:
            index: 现有索引
            file_paths: 文件路径列表
            metadata: 元数据
        """
        all_nodes = []
        for fp in file_paths:
            nodes = self.processor.process_file(fp, metadata)
            all_nodes.extend(nodes)

        index.insert_nodes(all_nodes)
        print(f"[IndexBuilder] 添加 {len(all_nodes)} 节点到索引")

    def get_index(self) -> Optional[VectorStoreIndex]:
        """
        获取现有索引

        Returns:
            VectorStoreIndex 或 None
        """
        vector_store = self.vector_store_manager.get_vector_store(self.knowledge_id)

        # 检查集合是否有数据
        collection = self.vector_store_manager.get_collection(self.knowledge_id)
        if collection.count() == 0:
            return None

        storage_context = StorageContext.from_defaults(
            vector_store=vector_store
        )

        index = VectorStoreIndex.from_vector_store(
            vector_store,
            storage_context=storage_context,
            embed_model=self.embed_model
        )

        return index