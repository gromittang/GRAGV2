"""
L2 半集成测试 — 验证 execute_plan() 与真实 dispatch 函数的连通性

Mock LLM（避免 API 调用），使用真实 DISPATCH_MAP。
这些测试暴露 Iteration 1 的覆盖盲区：RAG checkpointer 配置缺失等。

运行:
  pytest tests/test_orchestrator_l2.py -v         # 全部 L2
  pytest tests/test_orchestrator_l2.py -v -m slow # 仅 slow（等价）
  pytest tests/ -q -m "not slow"                  # CI 快速模式（跳过 L2）
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.orchestrator.planner import ExecutionPlan, PlanStep
from app.orchestrator.executor import execute_plan


@pytest.mark.slow
@pytest.mark.asyncio
async def test_execute_plan_with_real_rag_dispatch():
    """L2: execute_plan + 真实 dispatch_to_rag。mock LLM。

    这个测试在 Iteration 1 不存在，导致 RAG checkpointer 配置缺失
    的 bug 在 mock 测试中完全不可见，直到浏览器测试才暴露。
    """
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value="综合结论")

    plan = ExecutionPlan(steps=[
        PlanStep(step=1, intent="rag", goal="查文档",
                 query="SOP规范 操作流程"),
        PlanStep(step=2, intent="synthesize", goal="总结",
                 query="根据步骤1总结要点"),
    ])
    result = await execute_plan(plan, "查询SOP规范",
                                llm=mock_llm)  # dispatch 不 mock

    # 验证步骤结构
    assert len(result["steps"]) == 2
    assert result["steps"][0]["intent"] == "rag"
    assert result["steps"][1]["intent"] == "synthesize"

    # 验证 RAG 真正跑通了
    rag_step = result["steps"][0]
    assert rag_step["error"] is None, (
        f"RAG dispatch 不应失败，实际 error={rag_step.get('error')}"
    )
    assert rag_step["result"]["answer"], "RAG 应返回非空 answer"
    assert isinstance(rag_step["result"].get("sources", None), list), (
        "RAG 应返回 sources 列表"
    )

    # 验证 synthesis 有输出
    assert result["synthesis"] == "综合结论"


@pytest.mark.slow
@pytest.mark.asyncio
async def test_execute_plan_with_real_nl2sql_dispatch():
    """L2: execute_plan + 真实 dispatch_to_nl2sql。mock LLM。

    如果 MySQL 不可用则自动 skip（pytest.skip），不视为测试失败。
    """
    # 检查 MySQL 环境
    try:
        from app.core.db_mysql import get_mysql_manager
        mgr = await get_mysql_manager()
        if mgr is None:
            pytest.skip("MySQL manager returned None")
    except (ConnectionRefusedError, OSError) as e:
        pytest.skip(f"MySQL not available: {e}")
    except Exception:
        # 非环境错误（如凭证错误）应该让测试 FAIL，不是 skip
        raise

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value="数据汇总分析结论")

    plan = ExecutionPlan(steps=[
        PlanStep(step=1, intent="nl2sql", goal="查数据",
                 query="查询最近7天的入库单"),
        PlanStep(step=2, intent="synthesize", goal="总结",
                 query="根据步骤1总结数据结论"),
    ])
    result = await execute_plan(plan, "查询入库单",
                                llm=mock_llm)

    assert len(result["steps"]) == 2
    nl2sql_step = result["steps"][0]
    assert nl2sql_step["error"] is None, (
        f"NL2SQL dispatch 不应失败，实际 error={nl2sql_step.get('error')}"
    )
    assert nl2sql_step["result"].get("sql"), "NL2SQL 应返回非空 SQL"
    assert result["synthesis"] == "数据汇总分析结论"


# NOTE: 测试命名自查规则 —— 审查时检查 名称 → 描述 → 断言 是否一致
# 反例: test_error_resilience → "验证异常恢复" → assert success == True（根本没测错误路径）
# L2 的 error resilience 已由 L1 unit test (test_execute_plan_step_error_continues) 覆盖，
# 不需要在 L2 重复。Pydantic Literal 约束使非法 intent 不可能进入正常 flow。
