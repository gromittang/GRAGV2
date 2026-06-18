# Iteration 2: Hybrid 管线验证 + 修复 + Polish

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复浏览器中发现的问题，确保 hybrid 管线在真实环境中可用。

**Architecture:** 不新增模块。在 Iteration 1 架构基础上做 bug fix + prompt tuning + UX polish。

**Tech Stack:** 同 Iteration 1 — FastAPI + LangGraph + DeepSeek LLM + Vue3 + Vite

---

## 0. Context

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
| 目标 | 修复 Task 1 中记录的每一个 bug |
| 涉及文件 | 根据问题定位决定，可能涉及：`executor.py` / `planner.py` / `api/orchestrator.py` / `dispatch.py` / `OrchestratorPage.vue` |
| 内容 | ① 按 bug 严重度排序修复；② 每修一个跑相关测试确认无回归；③ 修复后浏览器重新验证 |
| DoD | Bug 清单中所有项目状态为 fixed/verified；56 tests 继续通过 |
| 风险 | 中。问题可能涉及多个模块 |
| Rollback | 每个 bug 独立 commit，出问题可单独 revert |

---

### Task 3: Synthesis prompt 调优（20 min）

| 项 | 内容 |
|----|------|
| 目标 | 基于真实 RAG + NL2SQL 输出，优化 `SYNTHESIS_PROMPT` |
| 涉及文件 | `backend/app/orchestrator/executor.py` |
| 内容 | ① 用 curl 发 2 条 hybrid 请求，保存 synthesis 原始输出；② 评估：是否引用 data/docs？是否有幻觉？是否有空洞的开场？③ 调整 prompt 指令（如：加"必须引用步骤编号和具体数据"）；④ 重新测试确认改进 |
| DoD | synthesis 输出包含对具体步骤结果的引用；不以"根据您的要求"等空洞开场 |
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
| 目标 | 修复两个低 effort 遗留问题 |
| 涉及文件 | `backend/app/orchestrator/planner.py` / `CLAUDE.md` |
| 内容 | ① `VALID_INTENTS = ("nl2sql", "rag", "synthesize")` 常量提取，`Literal` 和 `_validate()` 引用同一来源；② CLAUDE.md 补充说明：`.env` 去重策略（根目录给 Docker，backend/ 给 uvicorn CWD） |
| DoD | `from app.orchestrator.planner import VALID_INTENTS` 可 import；CLAUDE.md 已更新；56 tests pass |
| 风险 | 极低 |
| Rollback | revert planner.py 即可 |

---

## 4. Task Dependency Graph

```
Task 1 (复现记录)
  ↓
Task 2 (修复 bug) ── 依赖 Task 1 的 bug 清单
  ↓
Task 3 (synthesis prompt) ── 依赖 Task 2（修复后才能拿到真实 synthesis 输出）
  ↓
Task 4 (前端 polish) ── 依赖 Task 2（修复后验证前端状态）
  ↓
Task 5 (tech debt) ── 独立，可任意时点执行
```

**全部顺序执行。** 每个 Task 独立 commit。

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

## 7. Notes

- Iteration 2 的本质是 **"让 Iteration 1 的价值真正对用户可见"**
- 不做新功能，只做验证 + 修 bug + 轻量 polish
- 如果 Task 2 发现的问题需要大改 Iteration 1 架构，应记录为 Iteration 3 而非当前 scope 膨胀
