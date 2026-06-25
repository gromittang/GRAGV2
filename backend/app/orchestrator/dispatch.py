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
    from app.core.observability import get_langgraph_config
    graph = get_rag_graph()
    result = await graph.ainvoke(
        {"question": query, "messages": []},
        config=get_langgraph_config(session_id="orchestrator_rag"),
    )
    return {"answer": result.get("answer", ""), "sources": result.get("sources", [])}


async def dispatch_to_nl2sql(query: str) -> dict:
    """Phase 1: Gateway 适配器 — 委托给 DataQueryGateway。
    返回 {"sql": str, "data": dict, "insight": dict}
    失败时 raise RuntimeError。

    旧实现（直接调用 graph_nl2sql.ainvoke）已迁移到 Gateway 的 LocalExecutor。
    """
    _log.info("dispatching to nl2sql (via Gateway): query={:.80}", query)
    from app.core.data_query_gateway import get_gateway

    gateway = get_gateway()
    result = await gateway.execute(query)
    if not result.success:
        raise RuntimeError(result.error_message or "NL2SQL 查询失败")
    return {
        "sql": result.sql or "",
        "data": {"columns": result.columns, "rows": result.rows, "total": result.total},
        "insight": {
            "summary": result.insight.summary if result.insight else "",
            "insights": result.insight.insights if result.insight else [],
            "follow_ups": result.insight.follow_ups if result.insight else [],
        },
    }


def dispatch_to_pm() -> dict:
    """返回 {"routed_to": "pm"}"""
    return {"routed_to": "pm"}


# Executor 通过 DI 注入 dispatch map，避免硬编码 if/elif
DISPATCH_MAP = {
    "rag": dispatch_to_rag,
    "nl2sql": dispatch_to_nl2sql,
}
