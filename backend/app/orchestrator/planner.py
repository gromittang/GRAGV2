"""
Planner — LLM 生成 ExecutionPlan + 内联 validator

Iteration 1 Phase 1: PlanStep + ExecutionPlan schema 定义
Iteration 1 Phase 3: Planner class + LLM prompt + _validate()
"""
import json

from pydantic import BaseModel, ValidationError
from typing import List, Literal

from app.core.llm_manager import get_llm
from app.core.logging import get_logger

_log = get_logger("orchestrator.planner")


# === Schema (Phase 1) ===

class PlanStep(BaseModel):
    step: int       # 1-based step number
    intent: Literal["nl2sql", "rag", "synthesize"]
    goal: str       # human-readable description
    query: str      # actual query / synthesis instruction


class ExecutionPlan(BaseModel):
    steps: List[PlanStep]


# === Planner (Phase 3) ===

class Planner:
    """LLM few-shot 生成 ExecutionPlan + 内联 validator。

    plan() 内部: LLM → parse JSON → _validate() → retry(1) → fallback clarify。
    """

    MAX_RETRIES = 1
    MAX_STEPS = 5

    PROMPT = (
        "你是一个执行计划生成器。根据用户问题，生成一个线性步骤计划。\n"
        "\n"
        "可用的步骤类型（intent）：\n"
        '- "nl2sql" — 查询数据库（库存、出入库、订单等业务数据）\n'
        '- "rag" — 检索文档（SOP、规范、操作手册等知识文档）\n'
        '- "synthesize" — 综合前几步结果，生成最终分析结论\n'
        "\n"
        "规则：\n"
        "1. 步骤编号 step 从 1 开始，连续递增\n"
        "2. 步骤数 ≤ 5\n"
        "3. 至少有一个 nl2sql 或 rag 步骤\n"
        "4. 最后一个步骤必须是 synthesize\n"
        "5. query 字段写具体的查询或综合指令，不是占位符\n"
        "\n"
        "示例 1 — 纯数据查询：\n"
        '用户: "查最近7天出库异常的记录"\n'
        '{"steps":[{"step":1,"intent":"nl2sql","goal":"最近7天出库异常","query":"查询最近7天出库数量超过平均值2倍标准差的所有记录"},'
        '{"step":2,"intent":"synthesize","goal":"总结结论","query":"根据步骤1的异常记录，总结出库异常的模式和分布"}]}\n'
        "\n"
        "示例 2 — 纯文档检索：\n"
        '用户: "仓库安全操作规范是什么"\n'
        '{"steps":[{"step":1,"intent":"rag","goal":"仓库安全操作规范","query":"仓库安全操作规范 SOP 管理制度"},'
        '{"step":2,"intent":"synthesize","goal":"总结规范要点","query":"根据步骤1的文档内容，总结仓库安全操作的关键规范要点"}]}\n'
        "\n"
        "示例 3 — 跨模块分析：\n"
        '用户: "结合SOP分析最近库存异常的原因"\n'
        '{"steps":[{"step":1,"intent":"nl2sql","goal":"库存异常数据","query":"查询最近30天库存异常变动的商品和数量"},'
        '{"step":2,"intent":"rag","goal":"库存管理规范","query":"库存管理规范 异常处理 SOP"},'
        '{"step":3,"intent":"synthesize","goal":"综合分析","query":"根据步骤1的数据和步骤2的规范，分析库存异常的可能原因和改进建议"}]}\n'
        "\n"
        "只输出 JSON，不要任何其他文本。\n"
        "用户输入：{question}"
    )

    def __init__(self, llm=None):
        self._llm = llm

    async def plan(self, question: str) -> ExecutionPlan:
        """LLM 生成 JSON → parse → _validate()。
        验证失败时 retry 一次 → 仍失败 fallback 到单模块 clarify。
        """
        llm = self._llm if self._llm is not None else get_llm()
        prompt = self.PROMPT.replace("{question}", question)

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                raw = await llm.ainvoke(prompt)
                data = json.loads(raw.strip())
                plan = ExecutionPlan(**data)
                self._validate(plan)
                _log.info("plan generated: {} steps, attempt={}", len(plan.steps), attempt + 1)
                return plan
            except (json.JSONDecodeError, ValidationError, ValueError) as e:
                _log.warning("plan attempt {} failed: {}", attempt + 1, str(e)[:100])
                if attempt >= self.MAX_RETRIES:
                    break
                # retry — 在 prompt 中附加错误提示
                prompt = self.PROMPT.replace("{question}", question) + (
                    f"\n\n上一次输出格式错误：{str(e)[:200]}。请严格按照 JSON 格式重新输出。"
                )

        # fallback: 单模块 clarify — 返回一个最小合法的 plan
        _log.warning("plan exhausted retries, falling back to clarify for: {:.80}", question)
        return ExecutionPlan(steps=[
            PlanStep(step=1, intent="rag", goal="降级检索",
                     query=question),
            PlanStep(step=2, intent="synthesize", goal="降级综合",
                     query=f"根据检索结果回答用户问题：{question}"),
        ])

    def _validate(self, plan: ExecutionPlan) -> None:
        """内联 validator。不通过 → raise ValueError。"""
        steps = plan.steps

        if len(steps) == 0:
            raise ValueError("Empty plan")

        if len(steps) > self.MAX_STEPS:
            raise ValueError(f"Too many steps: {len(steps)} (max {self.MAX_STEPS})")

        ids = {s.step for s in steps}
        if ids != set(range(1, len(steps) + 1)):
            raise ValueError(f"Step numbers must be 1..N consecutive, got: {sorted(ids)}")

        for s in steps:
            if s.intent not in ("nl2sql", "rag", "synthesize"):
                raise ValueError(f"Unknown intent: {s.intent}")

        non_synth = [s for s in steps if s.intent != "synthesize"]
        if not non_synth:
            raise ValueError("Plan must have at least one non-synthesize step")

        if steps[-1].intent != "synthesize":
            raise ValueError("Last step must be synthesize")
