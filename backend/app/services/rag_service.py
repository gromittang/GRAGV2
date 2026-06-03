"""
RAG 服务入口
整合 LlamaIndex RAG 流程
"""
from typing import List, Dict, Optional
import os
import httpx

from app.config import get_settings
from app.rag.index_builder import IndexBuilder
from app.rag.retriever import create_retriever
from app.core.vector_store import get_vector_store_manager

settings = get_settings()


def _get_document_info(document_id: str) -> Dict:
    """从数据库获取文档信息"""
    if not document_id:
        return {"name": "", "id": ""}

    try:
        from app.models.document import get_session, Document
        session = get_session()
        doc = session.query(Document).filter(Document.id == document_id).first()
        if doc:
            result = {"name": doc.name, "id": doc.id}
        else:
            result = {"name": "未知文档", "id": document_id}
        session.close()
        return result
    except Exception:
        return {"name": "未知文档", "id": document_id}


class RAGService:
    """RAG 问答服务"""

    def __init__(self, knowledge_id: str = None, industry_type: str = None):
        self.knowledge_id = knowledge_id
        self.industry_type = industry_type or settings.industry_type
        self._index = None
        self._retriever = None

    def _ensure_initialized(self):
        """确保索引已初始化"""
        if self._index is None:
            builder = IndexBuilder(self.knowledge_id, self.industry_type)
            self._index = builder.get_index()
            if self._index:
                self._retriever = create_retriever(self._index, self.knowledge_id, self.industry_type)

    def _build_sources(self, nodes: List) -> List[Dict]:
        """构建来源信息，包含文档名称"""
        sources = []
        seen_doc_ids = set()  # 避免重复

        for n in nodes:
            doc_id = n.metadata.get("document_id", "")

            # 获取文档信息
            doc_info = _get_document_info(doc_id)

            # 构建来源对象
            source = {
                "content": n.text[:200] + "..." if len(n.text) > 200 else n.text,
                "score": getattr(n, "score", 0),
                "metadata": {
                    **n.metadata,
                    "document_name": doc_info["name"],
                    "document_id": doc_info["id"],
                }
            }

            # 如果文档ID已出现过，只保留分数最高的
            if doc_id and doc_id in seen_doc_ids:
                continue
            if doc_id:
                seen_doc_ids.add(doc_id)

            sources.append(source)

        return sources[:5]  # 最多5个来源

    def add_documents(self, documents: List[Dict]) -> Dict:
        """添加文档到知识库"""
        self._ensure_initialized()

        builder = IndexBuilder(self.knowledge_id, self.industry_type)

        # 转换为 LlamaIndex Document
        from llama_index.core import Document
        llama_docs = []
        for doc in documents:
            llama_doc = Document(
                text=doc.get("content", ""),
                metadata=doc.get("metadata", {}),
                doc_id=doc.get("id", str(os.urandom(8).hex()))
            )
            llama_docs.append(llama_doc)

        if self._index:
            # 添加到现有索引
            from llama_index.core.node_parser import SentenceSplitter
            splitter = SentenceSplitter(chunk_size=500, chunk_overlap=100)
            nodes = splitter.get_nodes_from_documents(llama_docs)
            self._index.insert_nodes(nodes)
        else:
            # 创建新索引
            self._index = builder.build_index_from_docs(llama_docs)
            self._retriever = create_retriever(self._index, self.knowledge_id, self.industry_type)

        return {"success": True, "message": f"添加 {len(llama_docs)} 个文档"}

    def query(self, question: str, top_k: int = 5, history: List[Dict] = None) -> Dict:
        """执行 RAG 问答"""
        self._ensure_initialized()

        if self._index is None or self._retriever is None:
            return {
                "answer": "知识库暂无文档，请先上传操作手册。",
                "sources": [],
                "has_docs": False
            }

        # 检索相关文档
        from llama_index.core import QueryBundle
        query_bundle = QueryBundle(question)
        nodes = self._retriever.retrieve(query_bundle)

        # 构建上下文
        top_nodes = nodes[:top_k]
        context = "\n\n".join([n.text for n in top_nodes])

        # LLM 生成回答
        answer = self._generate_answer(question, context, history)

        # 构建来源信息（包含文档名称）
        sources = self._build_sources(top_nodes)

        return {
            "answer": answer,
            "sources": sources,
            "has_docs": True
        }

    def query_stream(self, question: str, top_k: int = 5, history: List[Dict] = None):
        """流式 RAG 问答"""
        self._ensure_initialized()

        if self._index is None:
            yield {"type": "error", "content": "知识库暂无文档"}
            return

        yield {"type": "status", "content": "正在搜索知识库..."}

        from llama_index.core import QueryBundle
        query_bundle = QueryBundle(question)
        nodes = self._retriever.retrieve(query_bundle)

        if not nodes:
            yield {"type": "error", "content": "未找到相关内容"}
            return

        top_nodes = nodes[:top_k]
        context = "\n\n".join([n.text for n in top_nodes])

        yield {"type": "status", "content": "正在生成回答..."}

        # 流式生成
        for token in self._generate_answer_stream(question, context, history):
            yield {"type": "token", "content": token}

        # 构建来源信息（包含文档名称）
        sources = self._build_sources(top_nodes)
        yield {"type": "done", "sources": sources}

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
            self._index = None
            self._retriever = None
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _build_messages(self, question: str, context: str, history: List[Dict] = None) -> List[Dict]:
        """构建 LLM 消息"""
        history_context = ""
        if history:
            parts = []
            for msg in history[-6:]:
                role = "用户" if msg["role"] == "user" else "系统"
                content = msg["content"][:150] if len(msg["content"]) > 150 else msg["content"]
                parts.append(f"{role}: {content}")
            history_context = "\n【对话历史】\n" + "\n".join(parts) + "\n"

        prompt = f"""你是WMS仓库操作助手。根据知识库回答问题。
{history_context}
【知识库内容】
{context}

【当前问题】
{question}

请根据知识库内容简洁准确回答，标注来源。"""

        messages = []
        if history:
            for msg in history:
                messages.append({"role": msg["role"], "content": msg["content"][:200]})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _generate_answer(self, question: str, context: str, history: List[Dict] = None) -> str:
        """调用 LLM 生成答案"""
        if not settings.deepseek_api_key:
            return f"检索结果:\n{context[:500]}\n\n[请配置DeepSeek API密钥]"

        messages = self._build_messages(question, context, history)

        try:
            response = httpx.post(
                f"{settings.deepseek_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.deepseek_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": settings.deepseek_model,
                    "messages": messages,
                    "max_tokens": 1000,
                    "temperature": 0.7
                },
                timeout=30.0
            )

            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
            return f"API失败: {response.status_code}"

        except Exception as e:
            return f"生成失败: {str(e)}"

    def _generate_answer_stream(self, question: str, context: str, history: List[Dict] = None):
        """流式生成答案"""
        if not settings.deepseek_api_key:
            yield "[请配置DeepSeek API密钥]"
            return

        messages = self._build_messages(question, context, history)

        try:
            with httpx.stream(
                "POST",
                f"{settings.deepseek_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.deepseek_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": settings.deepseek_model,
                    "messages": messages,
                    "max_tokens": 1000,
                    "temperature": 0.7,
                    "stream": True
                },
                timeout=60.0
            ) as response:
                for line in response.iter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            import json
                            chunk = json.loads(data)
                            delta = chunk["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except Exception:
                            continue

        except Exception as e:
            yield f"\n[生成中断: {str(e)}]"


# 服务缓存（按knowledge_id缓存）
_rag_services: Dict[str, RAGService] = {}


def get_rag_service(knowledge_id: str = None, industry_type: str = None) -> RAGService:
    """获取 RAG 服务（按knowledge_id缓存）"""
    cache_key = knowledge_id or "default"
    if cache_key not in _rag_services:
        _rag_services[cache_key] = RAGService(knowledge_id, industry_type)
    return _rag_services[cache_key]