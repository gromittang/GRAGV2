"""
向量存储配置
ChromaDB 初始化和管理
"""
import chromadb
from chromadb.config import Settings as ChromaSettings
from llama_index.vector_stores.chroma import ChromaVectorStore
from typing import Optional
import os

from app.config import get_settings
from app.core.logging import get_logger

_settings = get_settings()
_log = get_logger("core.vector_store")


class VectorStoreManager:
    """向量存储管理器"""

    def __init__(self):
        self._client: Optional[chromadb.Client] = None
        self._collection_name = "kb_documents"

    def get_client(self) -> chromadb.Client:
        """获取 ChromaDB 客户端"""
        if self._client is None:
            persist_dir = _settings.resolved_chroma_persist_dir
            os.makedirs(persist_dir, exist_ok=True)

            self._client = chromadb.PersistentClient(
                path=persist_dir,
                settings=ChromaSettings(anonymized_telemetry=False)
            )
            _log.info("ChromaDB 初始化: {}", persist_dir)

        return self._client

    def get_collection(self, knowledge_id: str = None) -> chromadb.Collection:
        """
        获取或创建集合

        Args:
            knowledge_id: 知识库ID，用于多知识库隔离
        """
        client = self.get_client()
        collection_name = f"{self._collection_name}_{knowledge_id}" if knowledge_id else self._collection_name

        try:
            collection = client.get_collection(name=collection_name)
            _log.info("使用已存在集合: {}", collection_name)
        except:
            collection = client.create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            _log.info("创建新集合: {}", collection_name)

        return collection

    def get_vector_store(self, knowledge_id: str = None) -> ChromaVectorStore:
        """获取 LlamaIndex VectorStore"""
        collection = self.get_collection(knowledge_id)
        return ChromaVectorStore(chroma_collection=collection)

    def delete_collection(self, knowledge_id: str):
        """删除知识库集合"""
        client = self.get_client()
        collection_name = f"{self._collection_name}_{knowledge_id}"
        try:
            client.delete_collection(name=collection_name)
            _log.info("删除集合: {}", collection_name)
        except:
            pass

    def list_collections(self) -> list:
        """列出所有集合"""
        client = self.get_client()
        return client.list_collections()


# 单例
_vector_store_manager: Optional[VectorStoreManager] = None


def get_vector_store_manager() -> VectorStoreManager:
    """获取向量存储管理器（单例）"""
    global _vector_store_manager
    if _vector_store_manager is None:
        _vector_store_manager = VectorStoreManager()
    return _vector_store_manager