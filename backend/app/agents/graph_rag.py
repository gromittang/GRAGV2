"""
LangGraph RAG Agent
混合检索：向量 + BM25 → RRF 融合 → Reranker 精排
支持图片输出和流式生成，含越界拒绝机制

图结构:
  START → retrieve → (has_docs && score >= threshold) → generate_answer → END
                    → (no_docs || score < threshold)   → reject → END
"""
import asyncio
from typing import Any

from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import StreamWriter

import jieba
from rank_bm25 import BM25Okapi

from app.config import get_settings
from app.core.agent_state import RAGAgentState
from app.core.embedding import get_default_embedding
from app.core.vector_store import get_vector_store_manager
from app.core.logging import get_logger
from app.core.tracing import TraceContext
from app.rag.retriever import ChromaDirectRetriever
from app.rag.reranker import get_reranker
from app.rag.query_rewriter import get_query_rewriter
from app.rag.context_utils import (
    extract_images_from_text,
    preprocess_context,
    build_chat_messages,
    apply_img_safety_net,
    build_sources,
    stream_llm,
    get_kb_context_for_rejection,
)

_settings = get_settings()
_log = get_logger("rag.graph")


def _get_all_knowledge_ids_with_docs() -> list:
    vector_manager = get_vector_store_manager()
    collections = vector_manager.list_collections()
    return [
        coll.name.replace("kb_documents_", "")
        for coll in collections
        if coll.name.startswith("kb_documents_") and coll.count() > 0
    ]


def _bm25_search(collection, query: str, top_k: int) -> list:
    """从 ChromaDB collection 构建 BM25 并检索

    Returns:
        [(node_id, score), ...] 按分数降序
    """
    from llama_index.core.schema import TextNode

    docs = collection.get(include=["documents", "metadatas"])
    if not docs["ids"]:
        return []

    texts = docs["documents"]
    tokenized_corpus = [jieba.lcut(t) for t in texts]
    bm25 = BM25Okapi(tokenized_corpus)
    tokenized_query = jieba.lcut(query)
    scores = bm25.get_scores(tokenized_query)

    results = []
    for i, (doc_id, text, score) in enumerate(
        zip(docs["ids"], texts, scores)
    ):
        if score > 0:
            metadata = docs["metadatas"][i] if docs["metadatas"] else {}
            node = TextNode(text=text, id_=doc_id, metadata=metadata or {})
            node.metadata["bm25_score"] = float(score)
            results.append((score, node))

    results.sort(key=lambda x: x[0], reverse=True)
    return [node for _, node in results[:top_k]]


def _rrf_fusion(*node_lists, k: int = 60) -> list:
    """Reciprocal Rank Fusion：多路检索结果融合

    Args:
        *node_lists: 各路检索返回的节点列表
        k: RRF 常数，默认 60

    Returns:
        按 RRF 分数降序排列的节点列表
    """
    rrf_scores = {}
    all_nodes = {}

    for nodes in node_lists:
        for rank, node in enumerate(nodes):
            nid = node.node_id
            rrf_scores[nid] = rrf_scores.get(nid, 0) + 1.0 / (k + rank + 1)
            if nid not in all_nodes:
                all_nodes[nid] = node

    sorted_ids = sorted(rrf_scores, key=rrf_scores.get, reverse=True)
    for nid, node in all_nodes.items():
        node.metadata["rrf_score"] = rrf_scores.get(nid, 0)

    return [all_nodes[nid] for nid in sorted_ids]


async def retrieve_node(state: RAGAgentState) -> dict:
    """混合检索：Query 改写 → 向量+BM25 → RRF 融合 → Reranker 精排"""
    question = state["question"]
    user_ctx = state.get("user_context", {})
    knowledge_id = user_ctx.get("knowledge_id")

    # Step 0: 关键词提取增强（保留原查询 + 追加关键词）
    search_query = question
    if _settings.use_query_rewrite:
        async with TraceContext("rag.query_rewrite", original_query=question,
                                rewrite_enabled=True) as rw_span:
            try:
                rewriter = get_query_rewriter()
                search_query, rewrite_usage = await rewriter.rewrite(question)
                rw_span.set_output(rewritten_query=search_query,
                                   changed=(search_query != question))
                if rewrite_usage:
                    rw_span.set_output(token_usage=rewrite_usage)
                rw_span.set_metadata(model=_settings.deepseek_model)
            except Exception as e:
                rw_span.set_error(str(e))
                _log.warning("关键词提取失败，使用原查询: {}", e)

    top_k = _settings.retrieval_top_k
    candidate_multiplier = _settings.reranker_top_k_multiplier  # 候选数 = top_k × N
    retrieval_top_k = top_k * candidate_multiplier

    from llama_index.core import QueryBundle

    query_bundle = QueryBundle(search_query)

    def _sync_retrieve():
        """同步检索逻辑"""
        embed_model = get_default_embedding()
        vector_manager = get_vector_store_manager()
        all_vector_nodes = []
        all_bm25_nodes = []

        if knowledge_id:
            collections_to_search = [(knowledge_id, vector_manager.get_collection(knowledge_id))]
        else:
            kb_ids = _get_all_knowledge_ids_with_docs()
            collections_to_search = [
                (kb_id, vector_manager.get_collection(kb_id)) for kb_id in kb_ids
            ]

        for kb_id, collection in collections_to_search:
            try:
                if collection.count() == 0:
                    continue

                # 向量检索
                with TraceContext("rag.vector_retrieve", query=search_query,
                                  collection=collection.name, top_k=retrieval_top_k,
                                  embedding_model=_settings.embedding_model) as vec_span:
                    retriever = ChromaDirectRetriever(
                        collection, embed_model, similarity_top_k=retrieval_top_k
                    )
                    vec_nodes = retriever.retrieve(query_bundle)
                    all_vector_nodes.extend(vec_nodes)
                    vec_span.set_output(
                        num_results=len(vec_nodes),
                        results=[{"doc_id": n.node_id, "score": round(getattr(n, "score", 0), 4)}
                                 for n in vec_nodes[:10]]
                    )
                    vec_span.set_metadata(collection_size=collection.count())

                # BM25 检索
                if _settings.use_hybrid_retrieval:
                    try:
                        with TraceContext("rag.bm25_retrieve", query=search_query,
                                          collection=collection.name, top_k=retrieval_top_k,
                                          tokenizer="jieba") as bm25_span:
                            bm25_nodes = _bm25_search(collection, search_query, retrieval_top_k)
                            all_bm25_nodes.extend(bm25_nodes)
                            bm25_span.set_output(
                                num_results=len(bm25_nodes),
                                results=[{"doc_id": n.node_id, "score": round(n.metadata.get("bm25_score", 0), 2)}
                                         for n in bm25_nodes[:10]]
                            )
                            bm25_span.set_metadata(corpus_size=collection.count())
                    except Exception as e:
                        _log.warning("KB {} BM25 检索失败: {}", kb_id, e)

            except Exception as e:
                _log.error("KB {} 检索失败: {}", kb_id, e)

        return all_vector_nodes, all_bm25_nodes

    # ChromaDB + embedding 都是同步 I/O，用 to_thread 避免阻塞 event loop
    vector_nodes, bm25_nodes = await asyncio.to_thread(_sync_retrieve)

    # Step 1: RRF 融合
    if bm25_nodes:
        with TraceContext("rag.rrf_fusion", vector_count=len(vector_nodes),
                          bm25_count=len(bm25_nodes), k_constant=60) as rrf_span:
            fused_nodes = _rrf_fusion(vector_nodes, bm25_nodes)
            _log.info("RRF 融合: 向量 {} + BM25 {} → {}", len(vector_nodes), len(bm25_nodes), len(fused_nodes))
            rrf_span.set_output(
                fused_count=len(fused_nodes),
                results=[{"doc_id": n.node_id, "rrf_score": round(n.metadata.get("rrf_score", 0), 4),
                          "vector_score": round(getattr(n, "score", 0), 4),
                          "bm25_score": round(n.metadata.get("bm25_score", 0), 2)}
                         for n in fused_nodes[:10]]
            )
            rrf_span.set_metadata(fusion_algorithm="reciprocal_rank_fusion")
    else:
        fused_nodes = sorted(vector_nodes, key=lambda n: getattr(n, "score", 0), reverse=True)

    if not fused_nodes:
        return {"context": "", "sources": [], "has_documents": False,
                "best_relevance_score": 0.0, "score_source": "vector"}

    # Step 2: Reranker 精排
    top_nodes = fused_nodes[:retrieval_top_k]
    if _settings.use_reranker:
        try:
            reranker = get_reranker()
            if reranker:
                with TraceContext("rag.rerank", query=search_query,
                                  candidate_count=len(fused_nodes[:retrieval_top_k]),
                                  target_top_k=top_k) as rerank_span:
                    # 记录 rerank 前排位
                    pre_rank = {n.node_id: i for i, n in enumerate(top_nodes)}
                    top_nodes = reranker.rerank(search_query, top_nodes, top_k)
                    _log.info("Reranker: {} 候选 → top {}", len(fused_nodes[:retrieval_top_k]), len(top_nodes))
                    rerank_span.set_output(
                        final_count=len(top_nodes),
                        results=[{"doc_id": n.node_id,
                                  "rerank_score": round(n.metadata.get("rerank_score", 0), 4),
                                  "rank_before": pre_rank.get(n.node_id, -1),
                                  "rank_after": i}
                                 for i, n in enumerate(top_nodes)]
                    )
                    rerank_span.set_metadata(model=_settings.resolved_reranker_model_path,
                                             reranker_enabled=True)
        except Exception as e:
            _log.warning("Reranker 失败，降级为 RRF 排序: {}", e)
            top_nodes = fused_nodes[:top_k]
    else:
        top_nodes = fused_nodes[:top_k]

    # 计算最高相关性分（以节点实际数据为准，不依赖 use_reranker 开关）
    if top_nodes:
        if top_nodes[0].metadata.get("rerank_score") is not None:
            best_score = float(top_nodes[0].metadata["rerank_score"])
            score_source = "rerank"
        else:
            best_score = max(
                getattr(n, "score", 0) or n.metadata.get("bm25_score", 0) or n.metadata.get("rrf_score", 0)
                for n in top_nodes
            )
            score_source = "vector"
    else:
        best_score = 0.0
        score_source = "vector"

    context = "\n\n".join([n.text for n in top_nodes])
    sources = build_sources(top_nodes)

    return {
        "context": context,
        "sources": sources,
        "has_documents": True,
        "best_relevance_score": best_score,
        "score_source": score_source,
    }


async def reject_node(state: RAGAgentState, writer: StreamWriter) -> dict:
    """知识库无相关内容时生成自适应拒绝回复"""
    question = state["question"]

    writer({"type": "status", "content": "正在分析问题..."})

    # 获取知识库概览（to_thread 避免阻塞事件循环）
    kb_context = await asyncio.to_thread(get_kb_context_for_rejection)

    prompt = (
        "你是一个智能客服助手。用户提出了一个问题，但经检索判断，"
        "该问题与当前知识库的内容范围不匹配。\n\n"
        f"知识库概况：\n{kb_context}\n\n"
        f"用户问题：{question}\n\n"
        "请生成一段友好、礼貌的中文拒绝回复（80字以内），包含：\n"
        "1. 告知用户该问题超出了知识库的覆盖范围\n"
        "2. 简要说明知识库主要涵盖的内容领域（基于上述概况推断）\n"
        "3. 建议用户提出与知识库内容相关的具体问题"
    )

    full_answer = ""
    token_usage = None
    async with TraceContext("rag.llm_reject", model=_settings.deepseek_model,
                            streaming=True) as llm_span:
        try:
            async for token in stream_llm([{"role": "user", "content": prompt}]):
                if isinstance(token, dict) and token.get("type") == "usage":
                    token_usage = token
                elif token is not None:
                    full_answer += str(token)
                    writer({"type": "token", "content": token})
        except Exception as e:
            _log.warning("拒答 LLM 调用失败: {}", e)

        # 降级：如果 LLM 返回空或错误标记，使用硬编码 fallback
        if not full_answer.strip() or full_answer.startswith("\n[生成中断"):
            full_answer = (
                "抱歉，您的问题与当前知识库的内容范围不匹配，"
                "我无法回答该问题。请尝试提出与知识库内容相关的具体问题。"
            )
            writer({"type": "token", "content": full_answer})

        llm_span.set_output(
            answer_preview=full_answer[:200],
            answer_length_chars=len(full_answer),
        )
        if token_usage:
            llm_span.set_output(token_usage=token_usage)
        llm_span.set_metadata(temperature=0.7, max_tokens=200)

    best_score = state.get("best_relevance_score", 0)
    writer({"type": "done", "sources": [], "best_relevance_score": best_score})

    return {
        "answer": full_answer,
        "sources": [],
        "has_documents": False,
        "is_rejected": True,
        "token_usage": token_usage,
    }


async def generate_answer_node(state: RAGAgentState, writer: StreamWriter) -> dict:
    """基于检索结果生成回答（支持图片输出，支持流式和非流式）"""
    question = state["question"]
    context = state["context"]
    messages_history = state.get("messages", [])
    sources = state.get("sources", [])

    writer({"type": "status", "content": "正在生成回答..."})

    cleaned_context, img_refs = preprocess_context(context)
    llm_messages = build_chat_messages(question, cleaned_context, messages_history, img_refs)

    full_answer = ""
    token_usage = None
    async with TraceContext("rag.llm_generate", model=_settings.deepseek_model,
                            context_length_chars=len(context), streaming=True) as llm_span:
        if img_refs:
            tokens = []
            async for token in stream_llm(llm_messages):
                if isinstance(token, dict) and token.get("type") == "usage":
                    token_usage = token
                elif token is not None:
                    tokens.append(str(token))
            full_answer = apply_img_safety_net("".join(tokens), img_refs)
            writer({"type": "token", "content": full_answer})
        else:
            async for token in stream_llm(llm_messages):
                if isinstance(token, dict) and token.get("type") == "usage":
                    token_usage = token
                elif token is not None:
                    full_answer += str(token)
                    writer({"type": "token", "content": token})

        llm_span.set_output(
            answer_preview=full_answer[:200],
            answer_length_chars=len(full_answer),
        )
        if token_usage:
            llm_span.set_output(token_usage=token_usage)
        llm_span.set_metadata(temperature=0.7, max_tokens=1000)

    best_score = state.get("best_relevance_score", 0)
    writer({"type": "done", "sources": sources, "best_relevance_score": best_score})

    return {"answer": full_answer, "sources": sources, "token_usage": token_usage, "is_rejected": False}


# DEPRECATED: 由 reject_node 取代，不再接入图
async def direct_llm_node(state: RAGAgentState, writer: StreamWriter) -> dict:
    """[已废弃] 知识库无结果时 LLM 直接回答"""
    question = state["question"]
    messages_history = state.get("messages", [])

    writer({"type": "status", "content": "正在生成回答..."})

    history_text = ""
    if messages_history:
        parts = []
        for msg in messages_history[-6:]:
            role = "用户" if msg["role"] == "user" else "系统"
            content = msg["content"][:150]
            parts.append(f"{role}: {content}")
        history_text = "\n".join(parts)

    messages = [
        {"role": "system", "content": "你是WMS仓库操作助手。用户提问与知识库内容不匹配，请基于你的知识简洁回答。"},
        {"role": "user", "content": f"【对话历史】\n{history_text}\n\n【用户问题】\n{question}"},
    ]

    full_answer = ""
    token_usage = None
    async with TraceContext("rag.llm_generate", model=_settings.deepseek_model,
                            streaming=True, direct_mode=True) as llm_span:
        async for token in stream_llm(messages):
            if isinstance(token, dict) and token.get("type") == "usage":
                token_usage = token
            elif token is not None:
                full_answer += str(token)
                writer({"type": "token", "content": token})

        llm_span.set_output(
            answer_preview=full_answer[:200],
            answer_length_chars=len(full_answer),
        )
        if token_usage:
            llm_span.set_output(token_usage=token_usage)
        llm_span.set_metadata(temperature=0.7, max_tokens=1000)

    best_score = state.get("best_relevance_score", 0)
    writer({"type": "done", "sources": [], "best_relevance_score": best_score})

    return {"answer": full_answer, "has_documents": False, "sources": [], "token_usage": token_usage}


def _route_after_retrieve(state: RAGAgentState) -> str:
    if not state.get("has_documents"):
        return "reject"

    score = state.get("best_relevance_score", 0)
    source = state.get("score_source", "vector")

    if source == "rerank":
        threshold = _settings.retrieval_relevance_threshold_rerank
    else:
        threshold = _settings.retrieval_relevance_threshold_vector

    if score < threshold:
        _log.info("Relevance below threshold: score={:.4f} source={} threshold={:.4f}",
                  score, source, threshold)
        return "reject"
    return "generate_answer"


def _build_rag_graph() -> StateGraph:
    graph = StateGraph(RAGAgentState)

    graph.add_node("retrieve", retrieve_node)
    graph.add_node("generate_answer", generate_answer_node)
    graph.add_node("reject", reject_node)

    graph.add_edge(START, "retrieve")
    graph.add_conditional_edges("retrieve", _route_after_retrieve, {
        "generate_answer": "generate_answer",
        "reject": "reject",
    })
    graph.add_edge("generate_answer", END)
    graph.add_edge("reject", END)

    return graph


_compiled_rag_graph = None


def get_rag_graph():
    """获取编译后的 RAG StateGraph（单例）"""
    global _compiled_rag_graph
    if _compiled_rag_graph is None:
        _compiled_rag_graph = _build_rag_graph().compile(
            checkpointer=MemorySaver()
        )
    return _compiled_rag_graph
