# Iteration 2: Hybrid 管线验证 + 修复 + Polish

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复浏览器中发现的问题，确保 hybrid 管线在真实环境中可用。

**Architecture:** 不新增模块。在 Iteration 1 架构基础上做 bug fix + prompt tuning + UX polish。

**Tech Stack:** 同 Iteration 1 — FastAPI + LangGraph + DeepSeek LLM + Vue3 + Vite

---

## 0. Context

> **Since plan creation (2026-06-18):** Task 5 的 CLAUDE.md 更新已在 commit `d99c2a2` 完成。Task 2 已修复 RAG checkpointer bug (`8b39f23`) 和 axios timeout (`39f4129`)。NL2SQL ambiguous column 错误确认属于 `query_agent.py` 范围，记录为 backlog。Task 5 范围缩减为仅 `VALID_INTENTS` 常量提取。

Iteration 1 已完成的骨架：
```
User Input → HybridRouter.route() → intent="hybrid"
  → Planner.plan() → ExecutionPlan
  → execute_plan() → steps[] + synthesis
  → OrchestratorResponse(steps, synthesis)
  → 前端 OrchestratorPage.vue 渲染步骤列表 + 综合结论
```

**已验证:**
- Planner prompt: 真实 DeepSeek LLM 4/4 case 一次通过 ✅
- data_query dispatch: 远程 MySQL 连通，NL2SQL 返回正常 SQL ✅
- Backend 启动: ChromaDB 健康检查通过，4 个知识库 healthy ✅
- 前端 build: `npm run build` 零错误 ✅

**未验证/已知问题:**
- 浏览器中 hybrid 全链路有 bug（用户已发现，待本 iteration 修复）
- RAG dispatch 真实效果未知
- Executor synthesis 质量未知
- Frontend stepSummary 字段匹配未在真实数据上验证

---

## 1. Iteration Goal

修复所有已知问题，让 hybrid 管线在浏览器中完整跑通，synthesis 输出质量达到"可用"级别。

## 2. Scope

**包含：**
- 复现并记录已知 hybrid 问题
- 修复所有发现的问题（不限范围，crash / 空白 / 错误提示 / 字段不匹配 等）
- Synthesis prompt 调优（基于真实 RAG + NL2SQL 输出）
- 前端 hybrid 体验 polish（loading / error / 正常三种状态）
- Tech debt 轻量清理（VALID_INTENTS 常量提取）

**不包含：**
- 自动化 E2E 测试（Playwright）
- 新增 intent 类型
- 并行步骤执行（`depends_on` 字段）
- Docker 部署验证
- 任何前端交互式卡片 / 展开 / 动画
- Planner prompt 大改（当前已验证有效）
- 任何新的 abstraction 层

---

## 3. Task Breakdown

### Task 1: 复现并记录已知问题（20 min）

| 项 | 内容 |
|----|------|
| 目标 | 在浏览器中复现用户已发现的 hybrid 问题，逐一记录到 iteration log |
| 涉及文件 | 无代码修改，仅记录 |
| 内容 | ① 在智能助手输入至少 3 条 hybrid 问题；② 观察每一步的结果（NL2SQL 数据是否正确、RAG 文档是否相关、synthesis 是否有内容）；③ 截图保存到 `docs/superpowers/screenshots/` 目录；④ 在 `docs/superpowers/plans/2026-06-18-iter2-bugs.md` 中记录每个问题的复现步骤和现象 |
| DoD | 所有已知问题均有截图 + 复现说明；bug 清单完整 |
| 风险 | 极低 |
| Rollback | N/A |

---

### Task 2: 修复所有发现的问题（30 min）

| 项 | 内容 |
|----|------|
| 目标 | 修复 Task 1 中记录的每一个 bug（限 orchestrator 范围） |
| 涉及文件 | 根据问题定位决定，可能涉及：`executor.py` / `planner.py` / `api/orchestrator.py` / `dispatch.py` / `OrchestratorPage.vue` |
| 内容 | ① 按 bug 严重度排序修复；② 每修一个跑相关测试确认无回归；③ 修复后浏览器重新验证 |
| DoD | ① Bug 清单中所有项目状态为 fixed/verified；② 每个 bug fix 附带一条新增测试，该测试在不含 fix 的代码上失败（证明测试有效），含 fix 后通过；③ 新增 ≥1 条 `@pytest.mark.slow` 半集成测试：mock Planner(LLM) 但不 mock dispatch 函数，验证 `execute_plan()` + 真实 `dispatch_to_rag/nl2sql` 连通性（此类测试会暴露如 RAG checkpointer 这类 mock 无法发现的 bug）；④ 56+ tests 继续通过（含 slow marker） |
| 风险 | 中。问题可能涉及多个模块 |
| Rollback | 每个 bug 独立 commit，出问题可单独 revert |
| **Scope 边界** | 以下不属于 Iteration 2 范围，发现后记录到 backlog：NL2SQL agent SQL 生成逻辑 (`query_agent.py` / `graph_nl2sql.py`)；ChromaDB / MySQL 基础设施问题；Reranker 模型问题；需要大改 Iteration 1 架构的问题 |

---

### Task 3: Synthesis prompt 调优（20 min）

| 项 | 内容 |
|----|------|
| 目标 | 基于真实 RAG + NL2SQL 输出，优化 `SYNTHESIS_PROMPT` |
| 涉及文件 | `backend/app/orchestrator/executor.py` |
| 内容 | ① 用 curl 发 2 条 hybrid 请求，保存 synthesis 原始输出；② 评估：是否引用 data/docs？是否有幻觉？是否有空洞的开场？③ 调整 prompt 指令（如：加"必须引用步骤编号和具体数据"）；④ 重新测试确认改进 |
| DoD | ① synthesis 中至少包含一次对具体步骤数据的直接引用（如 "步骤1返回了23条记录" 或 "根据步骤2的SOP文档"）；② 当所有前置步骤均失败时 synthesis 不编造数据（明确回复 "信息不足" 或逐步骤说明失败原因，如我们在真实测试中看到的 "无法完成您的请求...1. 库存查询失败...2. 出库操作规范查询失败..."）；③ 不以 "根据您的要求..." / "综合分析如下..." 等毫无信息量的填词开场 |
| 风险 | 低。仅改 prompt 字符串 |
| Rollback | revert prompt 字符串即可 |

---

### Task 4: 前端 hybrid 体验 polish（20 min）

| 项 | 内容 |
|----|------|
| 目标 | 确保前端 hybrid 结果在 loading / error / 正常三种状态下均有合理展示 |
| 涉及文件 | `frontend/vue-app/src/views/OrchestratorPage.vue` |
| 内容 | ① 确认 `stepSummary()` 提取逻辑与真实 dispatch 返回字段匹配（如 `result.data.rows.length`）；② 确保 loading 期间有视觉反馈（现有 spinner 已覆盖）；③ 步骤失败时错误文本可读（红色背景已实现）；④ 确认 synthesis 区域与周边视觉区分明显 |
| DoD | 三种状态均可用；`npm run build` 零错误 |
| 风险 | 低 |
| Rollback | revert Vue 文件即可 |

---

### Task 5: Tech debt 轻量清理（15 min）

| 项 | 内容 |
|----|------|
| 目标 | 提取 VALID_INTENTS 常量（CLAUDE.md 已在 commit `d99c2a2` 更新，本 Task 不再重复） |
| 涉及文件 | `backend/app/orchestrator/planner.py` |
| 内容 | `VALID_INTENTS = ("nl2sql", "rag", "synthesize")` 常量提取，`PlanStep.intent` 的 `Literal` 和 `_validate()` 引用同一来源。注意：Python 3.11 的 `Literal` 不支持直接解包 tuple，需用 `Literal["nl2sql", "rag", "synthesize"]` 显式声明 |
| DoD | `_validate()` 中 hardcoded tuple 替换为 `VALID_INTENTS` 引用；56 tests pass |
| 风险 | 极低 |
| Rollback | revert planner.py 即可 |

---

## 4. Task Dependency Graph

```
Task 1 (复现记录)
  ↓
Task 2 (修复 bug + 半集成测试) ── 依赖 Task 1 的 bug 清单
  ├→ Task 3 (synthesis prompt) ── 依赖 Task 2
  ├→ Task 4 (前端 polish)       ── 依赖 Task 2（改不同文件，可与 Task 3 并行）
  ↓
Task 5 (tech debt) ── 独立，可任意时点执行
```

**Task 3 和 4 可并行**（改 `executor.py` vs `OrchestratorPage.vue`，无冲突）。每个 Task 独立 commit。

---

## 5. Success Criteria (Definition of Done)

- [ ] 至少 3 条 hybrid 问题在浏览器中完整走通（路由 → plan → dispatch → synthesis → 前端渲染）
- [ ] Bug 清单中所有项目 fixed + verified
- [ ] Synthesis 输出引用具体步骤数据，无幻觉
- [ ] 前端三种 hybrid 状态（loading / error / normal）均可用
- [ ] `VALID_INTENTS` 常量提取完成
- [ ] CLAUDE.md 已更新
- [ ] 56 tests pass + 前端 `npm run build` 零错误

---

## 6. Risks

| 风险 | 缓解 |
|------|------|
| RAG 知识库无相关文档 → dispatch 返回空 sources | synthesis prompt 处理空结果；记录为已知限制 |
| 远程 MySQL 查询慢 | 前端 loading 状态已覆盖 |
| 浏览器发现的 bug 需要改多个模块 | 每个 bug 独立 commit，可 revert |
| synthesis LLM 编造内容 | Task 3 prompt 加"不得编造" + "必须引用"约束 |

---

## 7. Test Regime（Iteration 2 建立的测试制度）

### 为什么需要这个

Iteration 1 完成后：**56 tests pass，浏览器一跑就崩。**

根因：100% 的测试 mock 了 dispatch 层。`dispatch_to_rag()` 的真实 `ainvoke()` 从未在测试中执行过，所以 RAG graph 的 checkpointer 配置缺失、axios 超时配置不足这些问题全部漏过。

```
Iteration 1 测试覆盖：
  Mock Router ──→ Mock Planner ──→ Mock dispatch ──→ Mock LLM
  （全 mock，逻辑正确性 ✅，连通性 ❌）

真实浏览器路径：
  Real Router ──→ Real Planner ──→ Real dispatch ──→ Real LLM
  （mock 覆盖不到的地方全是 bug）
```

### 四层测试制度

| 层 | 名称 | 覆盖 | Mock 策略 | 速度 | 运行时机 |
|----|------|------|-----------|------|---------|
| L1 | **Unit tests** | 逻辑正确性：validator、rule matching、plan parse/validate | Mock LLM + Mock dispatch + Mock graph | ~7s (56 tests) | 每次 commit |
| L2 | **Semi-integration** | dispatch ↔ graph 连通性：`execute_plan()` 调真实 `dispatch_to_rag/nl2sql` | Mock Planner(LLM) + **Real dispatch** | ~5s per test | 每次 commit（`@pytest.mark.slow`） |
| L3 | **API integration** | HTTP 层：route → handler → response schema | Mock Router + Mock Planner + Mock dispatch | ~7s（已有） | 每次 commit |
| L4 | **Manual E2E** | 全链路：浏览器输入 → 后端 → 前端渲染 | 无 mock（真实环境） | ~2 min | 每次 merge |

### 各层守卫的 bug 类别

| Bug | L1 能发现？ | L2 能发现？ | L3 能发现？ | L4 能发现？ |
|-----|-----------|-----------|-----------|-----------|
| Planner 返回非法 JSON（validator 拒绝） | ✅ | — | — | — |
| RAG graph checkpointer 配置缺失 | ❌ | ✅ | — | ✅ |
| dispatch 返回 shape 与 Executor 不匹配 | ❌ | ✅ | — | ✅ |
| axios 超时配置过短 | ❌ | ❌ | ❌ | ✅ |
| NL2SQL 生成 ambiguous column SQL | ❌ | ❌ | — | ✅ |
| 前端 stepSummary 字段不匹配 | ❌ | ❌ | ❌ | ✅ |
| Router 误判 intent | ✅（smoke） | — | — | ✅ |

### L2 半集成测试规范

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.orchestrator.executor import execute_plan
from app.orchestrator.planner import ExecutionPlan, PlanStep

@pytest.mark.slow
@pytest.mark.asyncio
async def test_execute_plan_with_real_rag_dispatch():
    """L2: execute_plan + 真实 dispatch_to_rag。mock LLM 避免 API 调用。"""
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value="综合结论")
    plan = ExecutionPlan(steps=[
        PlanStep(step=1, intent="rag", goal="查文档", query="SOP规范"),
        PlanStep(step=2, intent="synthesize", goal="总结", query="综合"),
    ])
    result = await execute_plan(plan, "测试问题", llm=mock_llm)  # dispatch 不 mock
    assert result["steps"][0]["error"] is None, f"RAG dispatch failed: {result['steps'][0].get('error')}"
    assert result["steps"][0]["result"]["answer"] != ""  # 真实 RAG 有输出
    assert len(result["steps"]) == 2
```

**L2 测试条件**: 需要后端环境（ChromaDB 有数据、MySQL 连通）。如果环境不可用，L2 测试自动 skip：

```python
@pytest.mark.slow
@pytest.mark.asyncio
async def test_execute_plan_with_real_nl2sql_dispatch():
    """L2: execute_plan + 真实 dispatch_to_nl2sql"""
    try:
        from app.core.db_mysql import get_mysql_pool
        await get_mysql_pool()
    except Exception:
        pytest.skip("MySQL not available")
    # ... test body
```

### 运行命令

```bash
# 快速测试（每次 commit）
pytest tests/test_orchestrator_router.py -q -m "not slow"

# 完整测试（merge 前）
pytest tests/test_orchestrator_router.py -q

# 仅半集成测试
pytest tests/test_orchestrator_router.py -q -m slow
```

### 制度要求

- **每个 bug fix** → 新增 ≥1 条 L1 或 L2 测试
- **每个 dispatch 路径变更** → 运行 L2 测试
- **每次 merge 前** → 手动 L4 E2E 验证（至少 1 条 hybrid case）
- **L2 测试允许因环境缺失败跳过**，但不允许因代码错误跳过

---

## 7. Notes

- Iteration 2 的本质是 **"让 Iteration 1 的价值真正对用户可见"**
- 不做新功能，只做验证 + 修 bug + 轻量 polish
- 如果 Task 2 发现的问题需要大改 Iteration 1 架构，应记录为 Iteration 3 而非当前 scope 膨胀
