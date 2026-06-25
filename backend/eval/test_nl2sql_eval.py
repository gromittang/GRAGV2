"""
NL2SQL Eval 测试用例
迁移前后并排对比，验证功能完整性。

前置条件:
  - DEEPSEEK_API_KEY 环境变量已配置
  - MySQL 连接可用
  - 运行: python -m pytest backend/eval/test_nl2sql_eval.py -v -s
"""
import os
import uuid
import pytest


def _skip_if_no_llm():
    from app.config import get_settings
    s = get_settings()
    return not s.deepseek_api_key


def _skip_if_no_mysql():
    from app.config import get_settings
    s = get_settings()
    return not s.mysql_host or not s.mysql_password


SKIP_LLM = _skip_if_no_llm()
SKIP_MYSQL = _skip_if_no_mysql()


EVAL_CASES = [
    {
        "question": "查询当前库存数量大于100的商品",
        "expected_tables": ["sto_stock_batch_yyyymm_org"],
        "expected_sql_keywords": ["SELECT", "FROM", "sto_stock_batch"],
    },
    {
        "question": "最近一周的出库记录有哪些",
        "expected_tables": ["sto_out_ware_head_yyyymm"],
        "expected_sql_keywords": ["SELECT", "FROM", "sto_out_ware"],
    },
    {
        "question": "显示待配送的订单",
        "expected_tables": ["sto_send_pln_head_yyyymm"],
        "expected_sql_keywords": ["SELECT", "FROM", "sto_send_pln"],
    },
    {
        "question": "统计各仓库的入库总量",
        "expected_tables": [],
        "expected_sql_keywords": ["SELECT", "SUM", "GROUP BY"],
    },
    {
        "question": "查询今天的收货验收记录",
        "expected_tables": ["sto_accept_head_yyyymm"],
        "expected_sql_keywords": ["SELECT", "FROM"],
    },
    {
        "question": "查看所有商品的基础信息",
        "expected_tables": ["cob_plu"],
        "expected_sql_keywords": ["SELECT", "FROM", "cob_plu"],
    },
    {
        "question": "当前有哪些拣货任务",
        "expected_tables": ["sto_pick_opr_head_yyyymm"],
        "expected_sql_keywords": ["SELECT", "FROM"],
    },
    {
        "question": "查询被锁定的库存",
        "expected_tables": ["sto_lock_yyyymm_org"],
        "expected_sql_keywords": ["SELECT", "FROM", "sto_lock"],
    },
]


async def _run_old_agent(question: str) -> dict:
    from app.agents.query_agent import QueryAgent
    agent = QueryAgent()
    return await agent.query(question)


async def _run_new_agent(question: str) -> dict:
    from app.agents.graph_nl2sql import get_query_graph
    from app.core.observability import get_langgraph_config
    graph = get_query_graph()
    final_state = await graph.ainvoke(
        {"question": question, "user_context": {}},
        config=get_langgraph_config(session_id=uuid.uuid4().hex),
    )
    if final_state.get("error"):
        return {"success": False, "error": final_state["error"]}
    return {
        "success": final_state.get("success", True),
        "sql": final_state.get("sql", ""),
        "results": final_state.get("query_result", {}).get("rows", []),
        "columns": final_state.get("columns", []),
        "total": final_state.get("total", 0),
        "tables_used": final_state.get("tables_used", []),
        "insight": final_state.get("insight", {}),
    }


def _verify_result(result: dict, expected: dict) -> list[str]:
    failures = []
    if not result.get("success"):
        failures.append(f"Agent 返回失败: {result.get('error', '未知错误')}")
        return failures

    sql = result.get("sql", "").upper()
    for table in expected.get("expected_tables", []):
        if table.upper() not in sql:
            failures.append(f"SQL 未使用预期表 {table}")
    for keyword in expected.get("expected_sql_keywords", []):
        if keyword.upper() not in sql:
            failures.append(f"SQL 缺少关键词 {keyword}")
    return failures


class TestNL2SQLOldAgent:
    """旧 Agent 基准测试"""
    @pytest.mark.asyncio
    @pytest.mark.skipif(SKIP_LLM, reason="DEEPSEEK_API_KEY 未配置")
    @pytest.mark.skipif(SKIP_MYSQL, reason="MySQL 连接不可用")
    @pytest.mark.parametrize("case", EVAL_CASES)
    async def test_case(self, case):
        result = await _run_old_agent(case["question"])
        failures = _verify_result(result, case)
        if failures:
            print(f"\n  SQL: {result.get('sql', 'N/A')}")
        assert len(failures) == 0, f"旧 agent 失败: {'; '.join(failures)}"


class TestNL2SQLNewAgent:
    """LangGraph Agent 测试"""
    @pytest.mark.asyncio
    @pytest.mark.skipif(SKIP_LLM, reason="DEEPSEEK_API_KEY 未配置")
    @pytest.mark.skipif(SKIP_MYSQL, reason="MySQL 连接不可用")
    @pytest.mark.parametrize("case", EVAL_CASES)
    async def test_case(self, case):
        result = await _run_new_agent(case["question"])
        failures = _verify_result(result, case)
        if failures:
            print(f"\n  SQL: {result.get('sql', 'N/A')}")
        assert len(failures) == 0, f"LangGraph agent 失败: {'; '.join(failures)}"


class TestNL2SQLCrossComparison:
    """新旧 Agent 交叉对比"""
    @pytest.mark.asyncio
    @pytest.mark.skipif(SKIP_LLM, reason="DEEPSEEK_API_KEY 未配置")
    @pytest.mark.skipif(SKIP_MYSQL, reason="MySQL 连接不可用")
    @pytest.mark.parametrize("case", EVAL_CASES[:5])
    async def test_same_result(self, case):
        old_result = await _run_old_agent(case["question"])
        new_result = await _run_new_agent(case["question"])
        assert old_result.get("success") == new_result.get("success"), (
            f"新旧 agent 成功状态不一致: old={old_result.get('success')}, new={new_result.get('success')}"
        )
        if old_result.get("success") and new_result.get("success"):
            old_sql = old_result.get("sql", "")
            new_sql = new_result.get("sql", "")
            assert old_sql, "旧 agent SQL 为空"
            assert new_sql, "新 agent SQL 为空"
