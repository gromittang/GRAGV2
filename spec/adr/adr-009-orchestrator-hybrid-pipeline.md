# ADR-009: Orchestrator Hybrid Pipeline — Contract-first + DI Architecture

**Date:** 2026-06-18  
**Status:** Accepted  
**Iteration:** 1-2

## Context

用户输入跨模块问题（如 "结合SOP分析最近库存异常的原因"）需要同时查询数据库和检索文档。Iteration 0 的 HybridRouter 只能识别 `hybrid` intent 但返回 placeholder。需要一套机制将 hybrid intent 转化为真实的多步执行。

## Decision

采用 **Contract-first + DI (Dependency Injection)** 架构：

```
User Input
  → HybridRouter.route() — RuleEngine (HYBRID_PATTERNS) → MiniLLMRouter (LLM)
  → intent="hybrid"
  → Planner.plan() — LLM few-shot → ExecutionPlan (validated)
  → execute_plan(plan, question) — step loop + dispatch map + synthesize
  → OrchestratorResponse(steps[], synthesis)
```

**核心设计决策：**

1. **Contract-first**: `PlanStep` + `ExecutionPlan` Pydantic schemas 在 Planner 和 Executor 实现之前定义。Planner 是 producer，Executor 是 consumer，通过 schema 解耦。

2. **DI 注入，零 patch**: 所有模块暴露 `param=None` 接口——`Router(llm=None)`, `Planner(llm=None)`, `execute_plan(llm=None, dispatch=None)`。测试直接注入 mock，不需要 monkey-patch。

3. **纯函数优先**: Executor 是一个 async for 循环，不引入类、Workflow 引擎、Registry 抽象。

4. **内联 validator**: `_validate()` 在 Planner 内部，不独立为 Validator 模块。5 条规则（max 5 steps / 连续编号 / valid intent / >=1 non-synth / last=synthesize）。

5. **HYBRID_PATTERNS 三重约束**: 同时满足 verb + data_signal + doc_signal 才判 hybrid。Zero false positives (baseline precision 1.000 on 49 cases)。

## Modules

| Module | File | Role |
|--------|------|------|
| Router | `orchestrator/router.py` | RuleEngine (keywords + HYBRID_PATTERNS) → MiniLLMRouter (LLM) → HybridRouter (cascade) |
| Dispatch | `orchestrator/dispatch.py` | `dispatch_to_rag/nl2sql/pm()` + `DISPATCH_MAP` |
| Planner | `orchestrator/planner.py` | `PlanStep`/`ExecutionPlan` schemas + `Planner` class (LLM prompt + validate + retry/fallback) |
| Executor | `orchestrator/executor.py` | `execute_plan()` + `_run_synthesis()` |
| API | `api/orchestrator.py` | Handler: route → dispatch/hybrid → OrchestratorResponse |

## Consequences

**Positive:**
- 4 个新文件，0 个外部依赖，0 个新框架
- 每个模块可独立测试（mock LLM / mock dispatch map）
- 56 tests, 7.7s
- Baseline eval: effective accuracy 100%, hybrid recall 66.7% (rule only, remainder → LLM)

**Negative:**
- Fallback 永远走 RAG（不适合纯数据查询的降级场景）— 见 Iteration 2 backlog
- Linear steps only（并行执行推迟到后续 iteration）

## Alternatives Considered

- **LangGraph subgraph**: 当前只有线性步骤，LangGraph 过度设计。等需要并行/条件分支时再评估。
- **Workflow Registry pattern**: 模板数 < 10，不需要抽象层。`DISPATCH_MAP` 是更简单的替代。
- **Independent Validator module**: 5 条规则，不值得独立文件。内联在 Planner 中足够。

## References

- Iteration 1 Plan: `docs/superpowers/plans/2026-06-17-orchestrator-iter1-planner.md`
- Iteration 2 Plan: `docs/superpowers/plans/2026-06-18-orchestrator-iter2-plan.md`
- Baseline Eval: `backend/tests/router_baseline_eval.py`
