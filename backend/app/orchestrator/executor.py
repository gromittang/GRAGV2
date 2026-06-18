"""
Executor — 按 ExecutionPlan 逐步执行 dispatch，最后 synthesize

Iteration 1 Phase 3: execute_plan() + _run_synthesis()
"""
import json

from app.core.llm_manager import get_llm
from app.core.logging import get_logger
from app.orchestrator.dispatch import DISPATCH_MAP

_log = get_logger("orchestrator.executor")

SYNTHESIS_PROMPT = (
    "你是数据分析助手。只能依据下方提供的数据和文档进行分析。"
    "如果信息不足必须说明不确定。不得编造。\n"
    "\n"
    "输出要求：\n"
    '1. 禁止任何开场白。第一句话必须是分析结论或步骤状态。\n'
    '2. 引用具体步骤编号和结果\n'
    '（如「步骤1返回了23条记录」「根据步骤2的SOP文档」）。\n'
    "3. 如果某步骤无数据或失败，明确说明该步骤的具体状态，"
    "并给出可操作的下一步建议"
    "（如「建议检查数据库是否有该时段的数据」），"
    '而不是仅说「信息不足」。\n'
    "\n"
    "步骤结果：{steps_json}\n"
    "用户问题：{question}"
)


async def _run_synthesis(llm, step_results: list, question: str) -> str:
    """调用 LLM 综合前几步结果，生成最终分析结论。"""
    steps_json = json.dumps(step_results, ensure_ascii=False, default=str)
    prompt = SYNTHESIS_PROMPT.format(steps_json=steps_json, question=question)
    _log.info("running synthesis: {} prior steps, question={:.60}", len(step_results), question)
    raw = await llm.ainvoke(prompt)
    return raw.strip()


async def execute_plan(
    plan,
    question: str,
    llm=None,
    dispatch: dict = None,
) -> dict:
    """逐步执行 ExecutionPlan，最后一步 synthesize。

    每步 try/except：失败步骤记录 error 字段后继续执行，
    确保后续步骤和 synthesis 仍能拿到部分结果。

    返回: {
        "steps": [{"step": 1, "intent": "nl2sql", "goal": "...",
                    "result": {...}, "error": None}],
        "synthesis": "..."
    }

    dispatch 参数用于测试注入 mock 函数，默认使用 DISPATCH_MAP。
    llm 参数用于测试注入 mock LLM。
    """
    llm = llm if llm is not None else get_llm()
    dispatch = dispatch if dispatch is not None else DISPATCH_MAP
    step_results = []

    for s in plan.steps:
        if s.intent == "synthesize":
            try:
                synthesis = await _run_synthesis(llm, step_results, question)
                step_results.append({
                    "step": s.step, "intent": s.intent,
                    "goal": s.goal,
                    "result": {"synthesis": synthesis},
                    "error": None,
                })
            except Exception as e:
                _log.warning("synthesis failed: {}", str(e)[:100])
                step_results.append({
                    "step": s.step, "intent": s.intent,
                    "goal": s.goal, "result": {},
                    "error": f"synthesis 失败: {str(e)[:200]}",
                })
        else:
            try:
                fn = dispatch[s.intent]
                result = await fn(s.query)
                step_results.append({
                    "step": s.step, "intent": s.intent,
                    "goal": s.goal, "result": result, "error": None,
                })
            except Exception as e:
                _log.warning("dispatch failed: intent={} step={} error={:.100}",
                             s.intent, s.step, str(e))
                step_results.append({
                    "step": s.step, "intent": s.intent,
                    "goal": s.goal, "result": {},
                    "error": f"dispatch 失败: {str(e)[:200]}",
                })

    return {
        "steps": step_results,
        "synthesis": step_results[-1]["result"].get("synthesis", ""),
    }
