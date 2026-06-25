# Iteration 1: Planner + Executor + Hybrid Orchestration (Refined)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Hybrid 意图从 placeholder 变为真实执行。

**Architecture:** Contract-first。Planner（LLM few-shot → Plan），Executor（函数 + dispatch map DI 按步骤执行），synthesize 内联为最后一步。不引入新类层次、新框架、新抽象。

**Tech Stack:** FastAPI + existing LangGraph graphs + DeepSeek LLM + Pydantic schemas

## Refinement Summary

### 相比原版改了什么

| # | 原版 | 修正版 | 原因 |
|---|------|--------|------|
| 1 | `Executor` class + `__init__` + `execute()` | `async def execute_plan()` 函数 | 单方法类没有状态，函数更简单；测试中直接 `await execute_plan(plan, question, dispatch=mock_map)` |
| 2 | Executor 内部 `if step.intent == "nl2sql": dispatch_to_nl2sql()` 硬编码 | `DISPATCH_MAP` dict + `dispatch[s.intent]` + DI 注入 | 新增 dispatch target 不改 Executor；测试零 patch |
| 3 | `PlanStep.depends_on` 字段 | 删除 | Executor 不消费，纯 speculative。等并行执行时加回来 |
| 4 | `HYBRID_PATTERNS` = 5 条 `(verb, "分析")` 二元组 | 5 条 `(verb, [data_signals], [doc_signals])` 三元组 | `"结合实际情况分析库存"` 只含 data_signal 无 doc_signal → 不误判 hybrid |
| 5 | Task 3（提取 dispatch）无门禁 | Task 3 必须跑 37 个现有测试 | 单模块 5 条路径依赖 dispatch 函数签名不变 |

### 为什么这样更合理

1. **函数 > 类**：`execute_plan` 和 `dispatch_to_rag` 一样都是纯函数——Iteration 0 的函数风格在 Iteration 1 保持一致。需要状态时（如 CancellationToken）再升级为类，成本为零。

2. **DI > 硬编码**：`MiniLLMRouter.__init__(llm=None)` / `HybridRouter.__init__(llm_router=None)` / `execute_plan(dispatch=None)` — 三个模块用同一种测试注入模式。新人看一个就能理解三个。

3. **诚实 > 前瞻**：`depends_on` 不在当前 scope 内就不定义。JSON schema 只承诺当前能交付的能力。

4. **精准 > 覆盖**：hybrid 规则从"两个词"升级为"三个语义角色"，误报率从"50% 左右"降到"极低"。

### 为什么适合当前阶段

- **3 个新文件，0 个新依赖，0 个新框架**。所有新增模块都是纯 Python + 现有 LLM
- **dispatch.py 提取是唯一的重构**，且有机房门禁（37 tests）
- **Planner 的复杂度限制在 prompt engineering**，不是架构复杂度
- **Executor 本质是一个 async for 循环**，不隐藏控制流
- **API 向后兼容**：新增 2 个 Optional 字段，旧客户端不受影响

---

## 0. Contract First: ExecutionPlan Schema

Planner 的输出是 Executor 的输入。这是 Iteration 1 的核心契约。

```python
from pydantic import BaseModel
from typing import List

class PlanStep(BaseModel):
    step: int     # 1-based step number
    intent: str   # "nl2sql" | "rag" | "synthesize"
    goal: str     # 此步骤的目的（human-readable，展示用）
    query: str    # 实际执行的查询/synthesis 指令


class ExecutionPlan(BaseModel):
    steps: List[PlanStep]
```

**示例 — "分析最近库存波动原因，并查最近7天出库异常"**：
```json
{
  "steps": [
    {
      "step": 1,
      "intent": "nl2sql",
      "goal": "最近7天库存波动数据",
      "query": "查询最近7天每日库存变动量和变动率"
    },
    {
      "step": 2,
      "intent": "nl2sql",
      "goal": "最近7天出库异常记录",
      "query": "查询最近7天出库数量超过平均值2倍标准差的所有记录"
    },
    {
      "step": 3,
      "intent": "rag",
      "goal": "库存管理规范和异常处理标准",
      "query": "库存管理规范 异常处理标准 SOP"
    },
    {
      "step": 4,
      "intent": "synthesize",
      "goal": "综合分析结论",
      "query": "根据步骤1-3的数据和规范，分析库存波动原因和出库异常可能的关联"
    }
  ]
}
```

**Schema 设计原则**：
- 当前只支持**线性步骤**（按顺序执行）。`depends_on` 暂不引入（Executor 不消费），等需要并行执行时再加
- 最后一个步骤必须是 `synthesize`，由 Executor 内部处理

**Validator 规则（内联在 Planner 中，不独立模块化）**：
- `max_steps <= 5`
- `step` 编号连续且从 1 开始
- `intent` 只能为 `nl2sql`、`rag`、`synthesize`
- 至少有一个 non-synthesize 步骤
- 最后一个步骤必须是 `synthesize`

---

## 1. Iteration Goal

Hybrid 意图从 "placeholder" 变为真实执行。用户输入跨模块问题 → Planner 生成执行计划 → Executor 逐步调用 RAG/NL2SQL → Synthesize 综合 → 返回结果。

## 2. Scope

**包含：**
- `Contract`: `PlanStep` + `ExecutionPlan` Pydantic schemas
- `RuleEngine`: 新增 5 条 hybrid 专属信号规则（方案 C）
- `dispatch.py`: 从 `api/orchestrator.py` 提取 `_dispatch_to_*()`，单独模块
- `Planner`: LLM few-shot 生成 `ExecutionPlan` + 内联 validator
- `Executor`: 按 plan 逐步执行 `dispatch_to_*()`，synthesize 作为最后一步
- `API`: `OrchestratorResponse` 新增 `steps` + `synthesis` 字段（向后兼容）
- `Frontend`: 最小 plan visualization（步骤列表 + 状态 + 结果摘要）
- `Tests`: 集成测试 mock dispatch 函数（解决 53s 问题）
- `Baseline`: Router 准确率一次测量（自动化 LLM 生成 50 条问题集，见 Task 5.3）

**不包含：**
- Workflow Registry（模板数量 < 10，不需要抽象）
- PlanValidator 独立模块（内联在 Planner 中）
- Synthesize 独立模块（作为 Executor 最后一步）
- LangGraph subgraph（当前只有线性步骤）
- ExecutionPlanPanel 完整版（仅做步骤列表）
- CancellationToken（步骤全串行，无长时间阻塞）
- Evidence-first prompt（已在 Iteration 0 的 Synthesize 设计中定义，Executor 复用）

## 3. Architecture Changes

```
Iteration 0:
  api/orchestrator.py
    ├── _dispatch_to_rag()        # 内联在 API 文件中
    ├── _dispatch_to_nl2sql()
    └── _dispatch_to_pm()

Iteration 1:
  orchestrator/dispatch.py        # NEW: 提取到这里
    ├── dispatch_to_rag()
    ├── dispatch_to_nl2sql()
    └── dispatch_to_pm()

  orchestrator/planner.py         # NEW
    ├── PlanStep (schema)
    ├── ExecutionPlan (schema)
    └── Planner (LLM → plan + validate)

  orchestrator/executor.py        # NEW
    └── execute_plan() + _run_synthesis() (step loop + synthesize)

  orchestrator/router.py          # MOD: RuleEngine +HYBRID_PATTERNS
  api/orchestrator.py             # MOD: hybrid → Planner → Executor
```

**数据流**：
```
User Input
  → HybridRouter.route()
    → intent="hybrid" (Rule HYBRID_PATTERNS 或 LLM 判断)
  → Planner.plan(question)
    → ExecutionPlan (validated)
  → execute_plan(plan, question)
    → for step in plan.steps:
        step.intent == "nl2sql" → dispatch_to_nl2sql(step.query)
        step.intent == "rag"    → dispatch_to_rag(step.query)
        step.intent == "synthesize" → LLM(steps_results + question)
    → { steps: [...], synthesis: "..." }
```

## 4. File-level Change Plan

### 新增文件

| 文件 | 职责 |
|------|------|
| `backend/app/orchestrator/dispatch.py` | 三个 `dispatch_to_*()` 函数，从 `api/orchestrator.py` 提取 |
| `backend/app/orchestrator/planner.py` | `PlanStep` + `ExecutionPlan` schemas + `Planner` class + 内联 validator |
| `backend/app/orchestrator/executor.py` | `execute_plan()` 函数 + dispatch map DI（逐步执行 + 最后一步 synthesize） |

### 修改文件

| 文件 | 修改 |
|------|------|
| `backend/app/orchestrator/router.py` | RuleEngine 新增 `HYBRID_PATTERNS` + 匹配逻辑 |
| `backend/app/api/orchestrator.py` | hybrid 分支 → Planner → Executor；`OrchestratorResponse` 加 `steps`+`synthesis`；移除内联 dispatch 函数（改 import orchestrator.dispatch） |
| `backend/tests/test_orchestrator_router.py` | RuleEngine hybrid pattern 测试；mock dispatch 函数（修 53s） |
| `frontend/vue-app/src/views/OrchestratorPage.vue` | hybrid 结果展示：步骤列表 + synthesis |

## 5. Class / Function Design

### 5.1 dispatch.py（从 api/orchestrator.py 提取）

```python
async def dispatch_to_rag(query: str) -> dict:
    """封装 graph_rag.ainvoke()。返回 {"answer": str, "sources": list}"""

async def dispatch_to_nl2sql(query: str) -> dict:
    """封装 graph_nl2sql.ainvoke()。返回 {"sql": str, "data": dict, "insight": dict}"""

def dispatch_to_pm() -> dict:
    """返回 {"routed_to": "pm"}"""

# Dispatch map — Executor 通过 DI 注入，避免硬编码 if/elif
DISPATCH_MAP = {
    "rag": dispatch_to_rag,
    "nl2sql": dispatch_to_nl2sql,
}
```

### 5.2 planner.py — Schema + Planner

```python
from pydantic import BaseModel, ValidationError
from typing import List

class PlanStep(BaseModel):
    step: int     # 1-based
    intent: str   # "nl2sql" | "rag" | "synthesize"
    goal: str     # human-readable
    query: str    # dispatch query / synthesis instruction

class ExecutionPlan(BaseModel):
    steps: List[PlanStep]

class Planner:
    """LLM few-shot 生成 ExecutionPlan + 内联 validator"""

    PROMPT = (
        "你是一个执行计划生成器..."
        # few-shot examples
    )

    def __init__(self, llm=None):
        self._llm = llm

    MAX_RETRIES = 1  # 验证失败时重试一次

    async def plan(self, question: str) -> ExecutionPlan:
        """1. LLM 生成 JSON → 2. parse → 3. validate → 4. return
        验证失败 → retry(1) → 仍失败 fallback 到单模块 clarify。
        retry/fallback 逻辑内联在 plan() 中，不暴露给 API handler。"""

    def _validate(self, plan: ExecutionPlan) -> None:
        """内联 validator。不通过 → raise ValueError"""
```

**Validator 逻辑（内联）**：
```python
def _validate(self, plan: ExecutionPlan) -> None:
    steps = plan.steps
    if len(steps) > 5:
        raise ValueError(f"Too many steps: {len(steps)}")
    if len(steps) == 0:
        raise ValueError("Empty plan")

    ids = {s.step for s in steps}
    if ids != set(range(1, len(steps) + 1)):
        raise ValueError("Step numbers must be 1..N consecutive")

    for s in steps:
        if s.intent not in ("nl2sql", "rag", "synthesize"):
            raise ValueError(f"Unknown intent: {s.intent}")

    non_synth = [s for s in steps if s.intent != "synthesize"]
    if not non_synth:
        raise ValueError("Plan must have at least one non-synthesize step")

    if steps[-1].intent != "synthesize":
        raise ValueError("Last step must be synthesize")
```

### 5.3 executor.py

```python
from app.core.llm_manager import get_llm
from orchestrator.dispatch import DISPATCH_MAP

SYNTHESIZE_PROMPT = (
    "你是数据分析助手。只能依据下方提供的数据和文档进行分析。"
    "如果信息不足必须说明不确定。不得编造。\n"
    "步骤结果：{steps_json}\n"
    "用户问题：{question}"
)


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
    llm = llm or get_llm()
    dispatch = dispatch or DISPATCH_MAP
    step_results = []

    for s in plan.steps:
        if s.intent == "synthesize":
            # 聚合前几步结果（含失败的 error 字段） → LLM 综合
            try:
                synthesis = await _run_synthesis(llm, step_results, question)
                step_results.append({"step": s.step, "intent": s.intent,
                                     "goal": s.goal, "result": {"synthesis": synthesis},
                                     "error": None})
            except Exception as e:
                step_results.append({"step": s.step, "intent": s.intent,
                                     "goal": s.goal, "result": {},
                                     "error": f"synthesis 失败: {str(e)[:200]}"})
        else:
            try:
                fn = dispatch[s.intent]
                result = await fn(s.query)
                step_results.append({"step": s.step, "intent": s.intent,
                                     "goal": s.goal, "result": result, "error": None})
            except Exception as e:
                step_results.append({"step": s.step, "intent": s.intent,
                                     "goal": s.goal, "result": {},
                                     "error": f"dispatch 失败: {str(e)[:200]}"})

    return {
        "steps": step_results,
        "synthesis": step_results[-1]["result"].get("synthesis", ""),
    }
```

**P0-2 修复验证**：测试注入 mock dispatch map，零 patch：
```python
result = await execute_plan(plan, question,
    dispatch={"rag": mock_rag, "nl2sql": mock_nl2sql})
```

### 5.4 router.py — RuleEngine 新增 HYBRID_PATTERNS

```python
class RuleEngine:
    # (cross_module_verb, data_signals, doc_signals)
    # 三个条件同时满足才判 hybrid：
    # 1. cross_module_verb 出现
    # 2. 至少一个 data_signal 出现
    # 3. 至少一个 doc_signal 出现
    HYBRID_PATTERNS = [
        ("结合", ["数据", "统计", "查询", "记录", "明细", "指标"],
                 ["SOP", "规范", "制度", "手册", "流程", "文档"]),
        ("对比", ["数据", "统计", "查询", "记录", "明细", "指标"],
                 ["SOP", "规范", "制度", "手册", "流程", "文档"]),
        ("根据", ["数据", "统计", "查询", "记录", "明细", "指标"],
                 ["SOP", "规范", "制度", "手册", "流程", "文档"]),
        ("参考", ["数据", "统计", "查询", "记录", "明细", "指标"],
                 ["SOP", "规范", "制度", "手册", "流程", "文档"]),
        ("按照", ["数据", "统计", "查询", "记录", "明细", "指标"],
                 ["SOP", "规范", "制度", "手册", "流程", "文档"]),
    ]

    def classify(self, question: str, rules: dict = None) -> Optional[RouteResult]:
        # 1. 先检查 HYBRID_PATTERNS
        #    → verb + data_signal + doc_signal 同时命中
        #    → RouteResult(intent="hybrid", source="rule", confidence=0.95)
        # 2. 再走现有 DEFAULT_RULES 逻辑
```
**为什么三重约束**：`"结合实际情况分析库存"` 只有 `"结合"+"统计"` 无 doc_signal → 不判 hybrid。需要 verb + data 词 + doc 词三者同时出现。

**对现有 smoke cases 的影响**：`router_smoke_cases.json` 中的 4 条 hybrid 类 case（"出库单的SOP标准核对流程" / "入库单的管理制度规定" / "拣货单的操作手册说明" / "盘点单的规范文件要求"）包含 data_signal + doc_signal 但**不含 cross_module_verb**（结合/对比/根据/参考/按照），因此 HYBRID_PATTERNS 不会触发，RuleEngine 仍返回 None → LLM 判定，行为不变。实现时在 `classify()` 中加一行注释说明此约束即可。

### 5.5 API response — 向后兼容

```python
class OrchestratorResponse(BaseModel):
    # === Iteration 0 字段（不变） ===
    intent: str
    confidence: float
    source: str
    routed_to: str
    clarification: Optional[str] = None
    answer: Optional[str] = None
    sources: Optional[list] = None
    sql: Optional[str] = None
    data: Optional[dict] = None
    insight: Optional[dict] = None
    error: Optional[str] = None

    # === Iteration 1 新增（仅 hybrid 使用） ===
    steps: Optional[list] = None          # 每步结果
    synthesis: Optional[str] = None       # 综合结论
```

## 6. Frontend: Minimal Plan Visualization

在 `OrchestratorPage.vue` 中新增 hybrid 结果展示（`v-if="result.steps"`）：

```
┌──────────────────────────────────────┐
│  ◎ 执行计划                          │
│                                      │
│  · Step1: 查询最近7天库存波动数据    │
│    [NL2SQL] · 23 rows · 1.2s        │
│                                      │
│  · Step2: 查询最近7天出库异常记录    │
│    [NL2SQL] · 5 rows · 0.8s         │
│                                      │
│  · Step3: 查找库存管理规范           │
│    [RAG] · 4 docs · 0.7s            │
│                                      │
│  · Step4: 综合分析中...              │
│                                      │
│  📊 综合分析结论                      │
│  （synthesis 文本）                   │
└──────────────────────────────────────┘
```

## 7. Test Plan

### 现有技术债修复
- Mock `dispatch_to_rag` / `dispatch_to_nl2sql` 在 setup 中 → 集成测试从 53s 降到 < 1s

### 新增测试

| 层 | 测试 | 类型 |
|----|------|------|
| RuleEngine | `test_hybrid_pattern_hit` — "结合SOP分析库存异常" → intent="hybrid", source="rule" | 单元 |
| RuleEngine | `test_hybrid_pattern_no_false_positive` — "结合实际情况"（无跨模块意图） → miss | 单元 |
| Planner | `test_plan_generation` — mock LLM → valid ExecutionPlan | 单元 |
| Planner | `test_plan_too_many_steps` — LLM 返回 6 步 → ValueError | 单元 |
| Planner | `test_plan_bad_intent` — LLM 返回 intent="invalid" → ValueError | 单元 |
| Executor | `test_execute_plan_linear` — mock dispatch map → 按步骤收集结果 | 单元 |
| Executor | `test_execute_plan_synthesis` — 前几步有结果 → LLM synthesis | 单元 |
| API | `test_hybrid_returns_steps_and_synthesis` — mock Planner + Executor | 集成 |
| Eval | `router_baseline_eval.py` — 50 条 LLM 生成问题集，per-intent accuracy | 评估 |

## 8. Task Breakdown (AI-Assisted, 20-60 min each)

**排序原则**：先基础设施，后业务逻辑；先低风险，后高依赖；每步可独立验证。

---

### Phase 0 — 前置准备（可并行，~1h）

#### Task 0.1: 修复 53s 集成测试（20 min）

| 项 | 内容 |
|----|------|
| 目标 | 集成测试从真实 graph 调用改为 mock dispatch，耗时 < 5s |
| 文件 | `backend/tests/test_orchestrator_router.py` |
| 内容 | 在 `TestOrchestratorAPI.client` fixture 中 mock `_dispatch_to_rag` / `_dispatch_to_nl2sql`；Mock 返回预设 dict（`{"answer": "mock", "sources": []}` / `{"sql": "mock", "data": {}, "insight": {}}`） |
| 测试 | `cd backend && python -m pytest tests/test_orchestrator_router.py -q` 耗时 < 5s |
| DoD | 37 tests pass，总耗时 < 5s |
| 风险 | 极低。只改测试文件 |
| Rollback | `git checkout tests/test_orchestrator_router.py` |

---

### Phase 1 — 基础设施（顺序，~2h）

#### Task 1.1: Contract-first Schema（15 min）

| 项 | 内容 |
|----|------|
| 目标 | 定义 `PlanStep` + `ExecutionPlan`，纯 schema，无逻辑 |
| 文件 | 新增 `backend/app/orchestrator/planner.py`（仅 schema 部分） |
| 内容 | 按 §0 写两个 Pydantic 类，`intent` 用 `Literal["nl2sql", "rag", "synthesize"]` |
| 测试 | `python -c "from app.orchestrator.planner import PlanStep, ExecutionPlan; s=PlanStep(step=1, intent='nl2sql', goal='test', query='test'); print(s)"` |
| DoD | import 无错，`ExecutionPlan(steps=[...])` 构造成功 |
| 风险 | 极低。无外部依赖 |
| Rollback | 删除 `planner.py` |

#### Task 1.2: RuleEngine HYBRID_PATTERNS（30 min）

| 项 | 内容 |
|----|------|
| 目标 | RuleEngine 能直接输出 `intent="hybrid"` |
| 文件 | 修改 `backend/app/orchestrator/router.py`，修改 `backend/tests/test_orchestrator_router.py` |
| 内容 | 在 `classify()` 开头加 hybrid 检测逻辑（三元组模式），在 `DEFAULT_RULES` 之前执行 |
| 测试 | 加 3 条单元测试：命中 hybrid、纯 data 不误判、纯 rag 不误判 |
| DoD | `test_hybrid_pattern_hit` / `test_hybrid_no_false_positive_data` / `test_hybrid_no_false_positive_rag` PASS |
| 风险 | 低。新增 feature，不影响现有规则 |
| Rollback | 删除 `HYBRID_PATTERNS` 块，revert tests |

---

### Phase 2 — 重构（顺序，~1h）

#### Task 2.1: 提取 dispatch 到独立模块（20 min）

| 项 | 内容 |
|----|------|
| 目标 | `dispatch_to_*()` 从 `api/orchestrator.py` 移到 `orchestrator/dispatch.py` |
| 文件 | 新增 `backend/app/orchestrator/dispatch.py`，修改 `backend/app/api/orchestrator.py` |
| 内容 | 复制三个函数到新文件；加 `DISPATCH_MAP` dict；`api/orchestrator.py` 改为 `from orchestrator.dispatch import dispatch_to_rag, dispatch_to_nl2sql, dispatch_to_pm` |
| 测试 | 跑全部 37 个测试 |
| DoD | `dispatch.py` 可 import；37 tests PASS |
| 风险 | 中。影响 Iteration 0 所有单模块路由 |
| Rollback | 还原 `api/orchestrator.py` 中的内联函数，删除 `dispatch.py` |

**⚠️ 硬门禁**：Task 2.1 完成后必须 37 tests 全绿才能继续。

---

### Phase 3 — 核心业务（顺序，~2h）

#### Task 3.1: Planner + LLM 集成（30 min）

| 项 | 内容 |
|----|------|
| 目标 | Planner 能调用 LLM 生成 ExecutionPlan |
| 文件 | 修改 `backend/app/orchestrator/planner.py` |
| 内容 | 写 `Planner.PROMPT`（含 few-shot examples）、`__init__(llm=None)`、`async plan(question) → ExecutionPlan`；LLM 返回 JSON → `ExecutionPlan(**parsed)` 构造 |
| 测试 | mock LLM → `plan()` 返回 2-4 步的 ExecutionPlan |
| DoD | `test_plan_generation` PASS；mock LLM 返回合法 JSON 能被正确解析 |
| 风险 | 中。LLM prompt 可能需要调优 |
| Rollback | 删除 `plan()` 方法即可（schema 保留） |

#### Task 3.2: Planner inline validator（20 min）

| 项 | 内容 |
|----|------|
| 目标 | 拒绝不合法的 ExecutionPlan |
| 文件 | 修改 `backend/app/orchestrator/planner.py` |
| 内容 | 实现 `_validate()`（6 条规则），在 `plan()` 中 JSON 解析后调用；验证失败 log warning + raise ValueError |
| 测试 | 4 条：steps=6 拒绝 / empty plan 拒绝 / bad intent 拒绝 / 无 synthesize 拒绝 |
| DoD | 4 条 validator 测试 PASS |
| 风险 | 低。纯逻辑，无外部依赖 |
| Rollback | 注释掉 `_validate()` 调用即可 |

#### Task 3.3: execute_plan() 执行函数（30 min）

| 项 | 内容 |
|----|------|
| 目标 | 按 plan 逐步执行 dispatch，最后 synthesize |
| 文件 | 新增 `backend/app/orchestrator/executor.py` |
| 内容 | `execute_plan(plan, question, llm=None, dispatch=None) -> dict`；dispatch map DI；synthesize 最后一步调 LLM；返回 `{steps, synthesis}` |
| 测试 | mock dispatch map + mock LLM → 3 步 plan 正确收集结果；synthesis prompt 包含步骤结果 |
| DoD | `test_execute_plan_linear` / `test_execute_plan_synthesis` PASS |
| 风险 | 中。依赖 dispatch map 和 LLM |
| Rollback | 删除 `executor.py` 即可 |

---

### Phase 4 — 集成（顺序，~1.5h）

#### Task 4.1: OrchestratorResponse 扩展（10 min）

| 项 | 内容 |
|----|------|
| 目标 | API response 支持 hybrid 结果字段 |
| 文件 | 修改 `backend/app/api/orchestrator.py` |
| 内容 | `OrchestratorResponse` 加 `steps: Optional[list] = None` + `synthesis: Optional[str] = None` |
| 测试 | 现有 37 tests PASS（旧字段不变，新字段 None） |
| DoD | `response.steps is None` for non-hybrid queries |
| 风险 | 极低。Optional 字段，完全向后兼容 |
| Rollback | 删除两行即可 |

#### Task 4.2: API handler hybrid 分支（30 min）

| 项 | 内容 |
|----|------|
| 目标 | hybrid intent → Planner → Executor → 返回 steps + synthesis |
| 文件 | 修改 `backend/app/api/orchestrator.py` |
| 内容 | 在 handler 的 hybrid 分支中：`plan = await planner.plan(question)` → `result = await execute_plan(plan, question)` → `resp.steps = result["steps"]; resp.synthesis = result["synthesis"]` |
| 测试 | mock Planner + mock execute_plan → 验证 response.steps/synthesis 填充正确 |
| DoD | `test_hybrid_returns_steps_and_synthesis` PASS；非 hybrid 路径不受影响（37 tests） |
| 风险 | 中。依赖 Task 3.1-3.3 全部完成 |
| Rollback | 还原 hybrid 分支为 placeholder |

---

### Phase 5 — 前端 + E2E（可并行，~1h）

#### Task 5.1: 前端 plan visualization（30 min）

| 项 | 内容 |
|----|------|
| 目标 | hybrid 结果展示步骤列表 + 综合结论 |
| 文件 | 修改 `frontend/vue-app/src/views/OrchestratorPage.vue` |
| 内容 | 在 `v-if="result.steps"` 块中：`v-for` 遍历 steps 显示 step/goal/intent/result；底部展示 synthesis 文本 |
| 测试 | `npm run build` 零错误 |
| DoD | hybrid 响应在前端正确渲染步骤列表 |
| 风险 | 低。纯前端，不影响后端 |
| Rollback | 删除 `v-if="result.steps"` 块 |

#### Task 5.2: E2E 浏览器验证（20 min）

| 项 | 内容 |
|----|------|
| 目标 | 浏览器中验证完整 hybrid 流程 |
| 文件 | Playwright 脚本（不 commit，验证后丢弃） |
| 内容 | 输入跨模块问题 → 等待 steps 渲染 → 截图确认步骤列表 + synthesis |
| DoD | 浏览器中可见步骤逐一执行，synthesis 文本展示 |
| 风险 | 低 |
| Rollback | N/A |

#### Task 5.3: Router Accuracy Baseline（30 min）

| 项 | 内容 |
|----|------|
| 目标 | 测量 Router 在 50 条问题上的准确率，建立迭代基线 |
| 文件 | 新增 `backend/tests/router_baseline_eval.py` + LLM 自动生成的问题集 |
| 内容 | ① 写脚本调用 LLM 按 6 个 intent 类别自动生成 50 条问题（每类 8-9 条）→ 保存为 `router_baseline_cases.json`；② 对每条问题跑 `HybridRouter.route()` 比较 `result.intent` vs `expected_intent`；③ 输出准确率矩阵（per-intent precision/recall + overall accuracy） |
| 测试 | `python -m pytest tests/router_baseline_eval.py -v -s` 输出准确率报告 |
| DoD | 准确率矩阵输出到 stdout，与 iteration 基线对比（hybrid 类预期较高，单模块类预期 ≥ 90%） |
| 风险 | 低。纯评估脚本，不改任何业务代码 |
| Rollback | 删除 `router_baseline_eval.py` + `router_baseline_cases.json` |

---

## Task Dependency Graph

```
Phase 0 (可并行):
  Task 0.1 (mock dispatch) ── 独立

Phase 1 (顺序):
  Task 1.1 (schema) ──→ Task 1.2 (hybrid rules)
                           │
Phase 2 (顺序):            │
  Task 2.1 (extract) ──────┤
                           │
Phase 3 (顺序):            │
  Task 1.1 ──→ Task 3.1 (planner) ──→ Task 3.2 (validator)
                                           │
  Task 2.1 ──→ Task 3.3 (executor) ────────┤
                                           │
Phase 4 (顺序):                            │
  Task 4.1 ──→ Task 4.2 (API handler) ─────┘ (depends on 1.2 + 3.1-3.3)

Phase 5 (顺序):
  Task 4.2 ──→ Task 5.1 (frontend) ──→ Task 5.2 (E2E)

Phase 5 独立:
  Task 5.3 (accuracy baseline) ── 可随时执行（不依赖任何任务，仅需 router.py + dispatch.py）
```

**关键路径**（最慢）：1.1 → 3.1 → 3.2 → 3.3 → 4.2 → 5.1 → 5.2
**可并行**：0.1、5.3、1.2（与 dispatch 提取并行）

## 9. Success Criteria (Definition of Done)

- [ ] 集成测试耗时 < 5s（mock dispatch）
- [ ] RuleEngine HYBRID_PATTERNS 对 5 条测试 case 归因正确
- [ ] `POST /api/v1/orchestrator/chat` 对 hybrid 问题返回 `steps` + `synthesis`
- [ ] `ExecutionPlan` schema 校验拒绝非法 plan（过多步骤/非法 intent/缺少 synthesize/空计划）
- [ ] Iteration 0 的 5 种单模块 intent 行为不变（向后兼容）
- [ ] 前端 hybrid 结果展示：步骤列表 + synthesis 文本
- [ ] 37 条现有测试 + 新增测试全部通过
- [ ] E2E: 输入跨模块问题 → 步骤逐一执行 → 综合结论展示
- [ ] Task 5.3: Router accuracy baseline 准确率矩阵输出（单模块 ≥ 90%，hybrid 记录基准值）

## 10. Risks

| 风险 | 缓解 |
|------|------|
| Planner LLM 生成的 JSON 格式不稳定 | 内联 validator 拒绝非法格式 → retry 一次 → 仍失败则 fallback 到单模块 Clarify |
| Executor 逐步执行的延迟随步骤数线性增长（每步 ~3s） | max_steps=5 硬限制；后续可并行执行独立步骤 |
| dispatch 提取可能影响 Iteration 0 单模块路径 | dispatch.py 保持函数签名不变；API handler 两种路径都测 |
| Hybrid 前端展示复杂度可能膨胀 | 只做步骤列表 + synthesis 文本，不做交互式卡片 |
