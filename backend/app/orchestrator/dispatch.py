"""
Dispatch 函数 — 封装各模块 graph 的 ainvoke() 调用

Iteration 0: 内联在 api/orchestrator.py 中
Iteration 1 Phase 2: 提取到这里，供 API handler 和 Executor 共用
"""
from app.core.logging import get_logger

_log = get_logger("orchestrator.dispatch")


async def dispatch_to_rag(query: str) -> dict:
    """封装 graph_rag.ainvoke()。返回 {"answer": str, "sources": list}"""
    _log.info("dispatching to rag: query={:.80}", query)
    from app.agents.graph_rag import get_rag_graph
    graph = get_rag_graph()
    result = await graph.ainvoke({"question": query, "messages": []})
    return {"answer": result.get("answer", ""), "sources": result.get("sources", [])}


async def dispatch_to_nl2sql(query: str) -> dict:
    """封装 graph_nl2sql.ainvoke()。
    返回 {"sql": str, "data": dict, "insight": dict}
    失败时 raise RuntimeError。
    """
    _log.info("dispatching to nl2sql: query={:.80}", query)
    from app.agents.graph_nl2sql import get_query_graph
    graph = get_query_graph()
    result = await graph.ainvoke({"question": query})
    if result.get("error"):
        raise RuntimeError(result["error"])
    return {
        "sql": result.get("sql", ""),
        "data": result.get("query_result", {}),
        "insight": result.get("insight", {}),
    }


def dispatch_to_pm() -> dict:
    """返回 {"routed_to": "pm"}"""
    return {"routed_to": "pm"}


# Executor 通过 DI 注入 dispatch map，避免硬编码 if/elif
DISPATCH_MAP = {
    "rag": dispatch_to_rag,
    "nl2sql": dispatch_to_nl2sql,
}
