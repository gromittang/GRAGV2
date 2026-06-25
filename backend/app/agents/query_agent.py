"""
数据查询Agent（旧版 5 步硬编码管线）

@deprecated: Phase 1 起由 DataQueryGateway 统一管理，QueryAgentExecutor 作为受限兜底。
计划 2 个 release 后删除。

整合Schema搜索、SQL生成、校验、执行工具链
"""
from typing import Dict, Any, List, Optional
import os
import json
import asyncio

from app.core.llm_manager import get_llm
from app.core.schema_manager import get_schema_manager
from app.core.db_mysql import get_mysql_manager
from app.agents.tools_sql import SQLValidateTool
from app.agents.prompts_sql import INSIGHT_GENERATION_PROMPT
from app.core.semantic_rules import (
    HARD_RULES as _HARD_RULES,
    load_spec_context as _load_spec_context,
    match_semantic_rules as _match_semantic_rules,
    parse_insight as _parse_insight,
)
from app.core.domain_classifier import get_domain_classifier
from app.core.sql_post_process import inject_plu_name


class QueryAgent:
    """数据查询Agent

    @deprecated: 自 Phase 1 起由 DataQueryGateway 管理。
    QueryAgentExecutor 仅作为受限兜底（满足准入条件时）。
    不要直接实例化此类 — 请使用 DataQueryGateway.execute()。
    """

    def __init__(self, llm_provider: str = None):
        self._llm = get_llm(llm_provider)
        self._llm_provider = llm_provider
        self._memory: List[Dict] = []

    async def query(self, question: str) -> Dict[str, Any]:
        """
        执行自然语言查询

        流程：
        1. Schema搜索 → 找相关表/字段
        2. SQL生成 → LLM生成SQL
        3. SQL校验 → 安全检查
        4. SQL执行 → 获取结果
        5. Insight生成 → AI分析
        """
        self._memory.append({"role": "user", "content": question})

        try:
            # Step 0: 领域分类（embedding + HARD_RULES fallback）
            classifier = get_domain_classifier()
            domain_result = classifier.classify(question)
            domain_tables = domain_result["domain_tables"]

            # HARD_RULES 强制表注入
            forced_tables = _match_semantic_rules(question)
            all_hint_tables = list(dict.fromkeys(domain_tables + forced_tables))

            # Step 1: Schema搜索（域过滤）
            schema_manager = await get_schema_manager()
            if all_hint_tables:
                schema_result = await schema_manager.search_relevant_schema_filtered(
                    question, table_filter=all_hint_tables
                )
            else:
                schema_result = await schema_manager.search_relevant_schema(question)

            if not schema_result.get("tables"):
                return {
                    "success": False,
                    "error": "无法找到相关的数据库表，请确认问题是否与业务数据相关",
                    "question": question
                }

            schema_text = schema_result.get("schema_text", "")

            # Step 1.5: 加载 spec 业务规则，注入到 schema 上下文前方
            spec_context = _load_spec_context()
            if spec_context:
                schema_text = spec_context + "【可用表结构】\n" + schema_text

            # Step 1.6: 强制注入优先表
            if forced_tables:
                forced_schema = schema_manager.get_tables_schema_text(forced_tables)
                if forced_schema:
                    schema_text = (
                        "【优先表 - 硬件强制，必须优先使用】\n"
                        + forced_schema
                        + "\n"
                        + schema_text
                    )

            # Step 2: SQL生成（使用LLM）
            from app.agents.prompts_sql import SQL_GENERATION_PROMPT

            prompt = SQL_GENERATION_PROMPT.format(
                schema_context=schema_text,
                user_question=question
            )

            response = self._llm.invoke(prompt)
            content = response.content if hasattr(response, 'content') else str(response)

            # 提取JSON
            import re
            json_match = re.search(r'\{[\s\S]*\}', content)
            if not json_match:
                return {
                    "success": False,
                    "error": "无法解析SQL生成结果",
                    "question": question,
                    "raw_output": content
                }

            sql_result = json.loads(json_match.group(0))

            if sql_result.get("error") or sql_result.get("sql") == "NEED_CLARIFICATION":
                return {
                    "success": False,
                    "error": sql_result.get("error", "无法生成有效的SQL，请提供更具体的问题"),
                    "question": question,
                    "schema_matched": schema_result.get("tables", [])
                }

            generated_sql = sql_result.get("sql", "")

            # Step 2.5: plu_name 自动注入 — 仓库用户需要同时看到商品名称
            generated_sql = inject_plu_name(generated_sql)

            # Step 3: SQL校验
            validate_tool = SQLValidateTool()
            validate_result_str = await validate_tool._arun(generated_sql)
            validate_result = json.loads(validate_result_str)

            if not validate_result.get("valid"):
                return {
                    "success": False,
                    "error": validate_result.get("reason"),
                    "sql": generated_sql,
                    "question": question
                }

            final_sql = validate_result.get("sql", generated_sql)

            # Step 4: SQL执行
            mysql_manager = await get_mysql_manager()
            execute_result = await mysql_manager.execute(final_sql)

            if not execute_result.get("success"):
                return {
                    "success": False,
                    "error": execute_result.get("error", "SQL执行失败"),
                    "sql": final_sql,
                    "question": question
                }

            rows = execute_result.get("rows", [])
            columns = execute_result.get("columns", [])

            # Step 5: Insight生成
            insight = await self._generate_insight(question, rows[:10])

            # 保存回答
            self._memory.append({
                "role": "assistant",
                "content": insight.get("summary", ""),
                "sql": final_sql
            })

            return {
                "success": True,
                "sql": final_sql,
                "results": rows,
                "columns": columns,
                "total": len(rows),
                "tables_used": sql_result.get("tables_used", []),
                "confidence": sql_result.get("confidence", 0),
                "explanation": sql_result.get("explanation", ""),
                "insight": insight,
                "question": question
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "question": question
            }

    async def _generate_insight(self, question: str, results: List[Dict]) -> Dict:
        """生成AI分析洞察"""
        if not results:
            return {"summary": "查询无结果", "insights": [], "follow_ups": []}

        # 格式化结果用于Prompt
        result_text = json.dumps(results[:10], ensure_ascii=False, indent=2)

        prompt = INSIGHT_GENERATION_PROMPT.format(
            user_question=question,
            query_result=result_text
        )

        try:
            response = self._llm.invoke(prompt)
            content = response.content if hasattr(response, 'content') else str(response)

            # 解析Insight
            insights = _parse_insight(content)
            return insights
        except Exception as e:
            return {
                "summary": f"分析生成失败: {e}",
                "insights": [],
                "follow_ups": []
            }


    async def execute_sql(self, sql: str) -> Dict[str, Any]:
        """直接执行SQL（带校验）"""
        validate_tool = SQLValidateTool()
        validate_result = json.loads(await validate_tool._arun(sql))

        if not validate_result.get("valid"):
            return {
                "success": False,
                "error": validate_result.get("reason"),
                "sql": sql
            }

        final_sql = validate_result.get("sql", sql)

        mysql_manager = await get_mysql_manager()
        result = await mysql_manager.execute(final_sql)

        return {
            "success": result.get("success", False),
            "sql": final_sql,
            "results": result.get("rows", []),
            "columns": result.get("columns", []),
            "total": result.get("count", 0),
            "error": result.get("error")
        }

    def clear_memory(self):
        """清空记忆"""
        self._memory = []

    def get_memory_history(self) -> List[Dict]:
        """获取记忆历史"""
        return self._memory.copy()


# 按 session_id 隔离 Agent 实例，避免跨会话记忆污染
_agent_instances: Dict[str, QueryAgent] = {}
_locks: Dict[str, asyncio.Lock] = {}


async def get_query_agent(session_id: str = "default", llm_provider: str = None) -> QueryAgent:
    """获取Query Agent（按 session_id 隔离）"""
    if session_id not in _agent_instances:
        if session_id not in _locks:
            _locks[session_id] = asyncio.Lock()

        async with _locks[session_id]:
            if session_id not in _agent_instances:
                _agent_instances[session_id] = QueryAgent(llm_provider)

    return _agent_instances[session_id]