"""
RAG 服务测试
"""
import pytest
import os
import tempfile


def test_document_processor():
    """测试文档处理"""
    from app.rag.document_processor import DocumentProcessor

    processor = DocumentProcessor("general")

    # 创建测试文件
    test_content = "这是一个测试文档内容。用于验证文档处理功能。"
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write(test_content)
        test_file = f.name

    try:
        nodes = processor.process_file(test_file)
        assert len(nodes) > 0
        assert "测试" in nodes[0].text
    finally:
        os.unlink(test_file)


def test_vector_store_manager():
    """测试向量存储管理器"""
    from app.core.vector_store import VectorStoreManager

    manager = VectorStoreManager()
    # 简单验证类存在
    assert manager._collection_name == "kb_documents"