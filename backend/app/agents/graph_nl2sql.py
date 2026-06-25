"""
LangGraph NL2SQL Agent
将原 query_agent.py 的 5 步硬编码管线迁移到 LangGraph 图编排

图结构（含错误路由）:
  START → domain_classify → schema_search(filtered)
    → (error) → END
    → (ok) → sql_generate
      → (error) → END
      → (ok) → sql_validate
        → (valid) → sql_execute → insight_generate → END
        → (invalid) → END
"""
from typing import Any, Dict, Optional, List
import json
import re
import os

from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.memory import MemorySaver

from app.core.agent_state import QueryAgentState
from app.core.llm_manager import get_llm
from app.core.schema_manager import get_schema_manager
from app.core.db_mysql import get_mysql_manager
from app.core.tracing import TraceContext
from app.config import get_settings
from app.core.semantic_rules import (
    HARD_RULES,
    load_spec_context,
    match_semantic_rules,
    parse_insight,
)
from app.core.domain_classifier import get_domain_classifier
from app.core.sql_post_process import inject_plu_name
from app.agents.tools_sql import SQLValidateTool
from app.agents.prompts_sql import SQL_GENERATION_PROMPT, INSIGHT_GENERATION_PROMPT

_settings = get_settings()


# --- 图节点函数 ---

async def domain_classify_node(state: QueryAgentState) -> dict:
    """Node 0: Embedding 领域分类 + HARD_RULES fallback"""
    question = state["question"]
    classifier = get_domain_classifier()
    result = classifier.classify(question)

    domain = result["domain"]
    confidence = result["confidence"]
    domain_tables = result["domain_tables"]

    # HARD_RULES 始终执行 — 用于补充 forced_tables
    forced_tables = match_semantic_rules(question)

    # embedding 分类置信度 < 0.5 时，回退到 HARD_RULES 关键词匹配确定域
    if confidence < 0.5:
        if forced_tables:
            domain = "HARD_RULES"
        else:
            domain = ""

    # 合并 domain_tables 和 forced_tables（去重）
    all_hint_tables = list(dict.fromkeys(domain_tables + forced_tables))

    return {
        "domain": domain,
        "domain_confidence": confidence,
        "domain_tables": all_hint_tables,
        "forced_tables": forced_tables,
    }


async def schema_search_node(state: QueryAgentState) -> dict:
    """Node 1: Schema 搜索 + Spec 注入 + 域过滤"""
    question = state["question"]
    domain_tables = state.get("domain_tables", [])

    schema_manager = await get_schema_manager()

    # 如果有域过滤表列表，只在域内搜索；否则全量搜索
    if domain_tables:
        schema_result = await schema_manager.search_relevant_schema_filtered(
            question, table_filter=domain_tables
        )
    else:
        schema_result = await schema_manager.search_relevant_schema(question)

    if not schema_result.get("tables"):
        return {"error": "无法找到相关的数据库表，请确认问题是否与业务数据相关", "success": False}

    schema_text = schema_result.get("schema_text", "")

    spec_context = load_spec_context()
    if spec_context:
        schema_text = spec_context + "【可用表结构】\n" + schema_text

    forced_tables = state.get("forced_tables", [])
    if forced_tables:
        forced_schema = schema_manager.get_tables_schema_text(forced_tables)
        if forced_schema:
            schema_text = (
                "【优先表 - 硬件强制，必须优先使用】\n"
                + forced_schema + "\n" + schema_text
            )

    return {
        "schema_context": schema_text,
        "spec_context": spec_context,
    }


async def sql_generate_node(state: QueryAgentState) -> dict:
    """Node 2: LLM 生成 SQL"""
    llm = get_llm()
    prompt = SQL_GENERATION_PROMPT.format(
        schema_context=state["schema_context"],
        user_question=state["question"],
    )

    async with TraceContext("nl2sql.sql_generate", model=_settings.deepseek_model,
                            schema_context_size_chars=len(state["schema_context"])) as sql_span:
        import asyncio as _asyncio
        response = await _asyncio.to_thread(llm.invoke, prompt)
        content = response.content if hasattr(response, 'content') else str(response)

        json_match = re.search(r'\{[\s\S]*\}', content)
        if not json_match:
            sql_span.set_error("无法解析SQL生成结果")
            return {"error": "无法解析SQL生成结果", "success": False}

        sql_result = json.loads(json_match.group(0))

        if sql_result.get("error") or sql_result.get("sql") == "NEED_CLARIFICATION":
            sql_span.set_output(error=sql_result.get("error", "NEED_CLARIFICATION"))
            return {
                "error": sql_result.get("error", "无法生成有效的SQL，请提供更具体的问题"),
                "success": False,
                "tables_used": [],
            }

        generated_sql = inject_plu_name(sql_result.get("sql", ""))
        sql_span.set_output(
            generated_sql=generated_sql,
            tables_used=sql_result.get("tables_used", []),
            confidence=sql_result.get("confidence", 0),
        )

    return {
        "sql": generated_sql,
        "tables_used": sql_result.get("tables_used", []),
        "confidence": sql_result.get("confidence", 0),
        "explanation": sql_result.get("explanation", ""),
    }


async def sql_validate_node(state: QueryAgentState) -> dict:
    """Node 3: SQL 安全校验"""
    validate_tool = SQLValidateTool()
    result_str = await validate_tool._arun(state["sql"])
    validation = json.loads(result_str)

    return {"validation_result": validation}


async def sql_execute_node(state: QueryAgentState) -> dict:
    """Node 4: 执行 SQL"""
    final_sql = state["validation_result"].get("sql", state["sql"])
    mysql_manager = await get_mysql_manager()
    result = await mysql_manager.execute(final_sql)

    if not result.get("success"):
        return {
            "error": result.get("error", "SQL执行失败"),
            "success": False,
        }

    return {
        "query_result": result,
        "sql": final_sql,
    }


async def insight_generate_node(state: QueryAgentState) -> dict:
    """Node 5: 生成分析洞察"""
    query_result = state.get("query_result")
    if not query_result:
        return {
            "insight": {"summary": "查询执行失败", "insights": [], "follow_ups": []},
            "success": True,
            "total": 0,
            "columns": [],
        }
    rows = query_result.get("rows", [])

    if not rows:
        return {
            "insight": {"summary": "查询无结果", "insights": [], "follow_ups": []},
            "success": True,
            "total": 0,
            "columns": query_result.get("columns", []),
        }

    result_text = json.dumps(rows[:10], ensure_ascii=False, indent=2)

    llm = get_llm()
    prompt = INSIGHT_GENERATION_PROMPT.format(
        user_question=state["question"],
        query_result=result_text,
    )

    async with TraceContext("nl2sql.insight_generate", model=_settings.deepseek_model,
                            data_shape=[len(rows), len(query_result.get("columns", []))]) as is_span:
        import asyncio as _asyncio
        response = await _asyncio.to_thread(llm.invoke, prompt)
        content = response.content if hasattr(response, 'content') else str(response)

        insights = parse_insight(content)
        is_span.set_output(
            insight_preview=str(insights.get("summary", ""))[:200],
            num_insights=len(insights.get("insights", [])),
        )

    return {
        "insight": insights,
        "success": True,
        "total": len(rows),
        "columns": query_result.get("columns", []),
    }


# --- 图构建 ---

def _check_error(state: QueryAgentState) -> str:
    """条件边：检查是否有错误或失败标记"""
    if state.get("error") or state.get("success") is False:
        return END
    return "continue"


def _should_execute(state: QueryAgentState) -> str:
    """条件边：SQL 校验通过→执行，否则→结束"""
    if state.get("validation_result", {}).get("valid"):
        return "sql_execute"
    return END


def build_query_graph() -> StateGraph:
    """构建 NL2SQL LangGraph"""
    graph = StateGraph(QueryAgentState)

    graph.add_node("domain_classify", domain_classify_node)
    graph.add_node("schema_search", schema_search_node)
    graph.add_node("sql_generate", sql_generate_node)
    graph.add_node("sql_validate", sql_validate_node)
    graph.add_node("sql_execute", sql_execute_node)
    graph.add_node("insight_generate", insight_generate_node)

    graph.add_edge(START, "domain_classify")
    graph.add_edge("domain_classify", "schema_search")
    graph.add_conditional_edges("schema_search", _check_error, {
        "continue": "sql_generate",
        END: END,
    })
    graph.add_conditional_edges("sql_generate", _check_error, {
        "continue": "sql_validate",
        END: END,
    })
    graph.add_conditional_edges("sql_validate", _should_execute, {
        "sql_execute": "sql_execute",
        END: END,
    })
    graph.add_conditional_edges("sql_execute", _check_error, {
        "continue": "insight_generate",
        END: END,
    })
    graph.add_edge("insight_generate", END)

    return graph


# --- Checkpointer 单例 ---

_checkpointer: Optional[MemorySaver] = None


def get_checkpointer() -> MemorySaver:
    global _checkpointer
    if _checkpointer is None:
        _checkpointer = MemorySaver()
    return _checkpointer


# --- 编译后的 graph 缓存 ---

_compiled_graph = None


def get_query_graph():
    global _compiled_graph
    if _compiled_graph is None:
        # 不启用 checkpointer：JsonPlusSerializer 在 state 含 % 字符（如 SQL 的
        # DATE_FORMAT('%Y-%m')）时会抛 "not enough arguments for format string"。
        # 当前业务不需要 checkpoint 重放，去掉 checkpointer 不影响功能。
        _compiled_graph = build_query_graph().compile()
    return _compiled_graph
