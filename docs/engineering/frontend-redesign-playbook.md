# 前端改版工作流手册（frontend-redesign-playbook）

> 作用：定义本仓库“前端改版 / UI 重构 / 页面视觉升级”类任务的标准执行流程。
> 使用方式：当 Claude 执行前端改版相关任务时，除 `CLAUDE.md` 外，还必须读取本文件。

---

# 1. 当前激活的前端改版计划

## 当前计划文件

`docs/superpowers/plans/2026-06-25-frontend-redesign.md`

Claude 在执行任何前端改版 phase 前，必须先读取该计划文档。

---

# 2. 前端改版的执行模式

前端改版分为两种执行模式：

---

## 模式 A：Subagent-Driven（子 Agent 驱动）

适用于**低风险、边界清晰、主要是样式或结构改动**的阶段，例如：

* 设计 Token（颜色 / 字体 / 间距 / 阴影 / 圆角）
* 侧边栏 / 导航壳层
* 通用组件（空状态、状态 Badge、确认弹窗等）
* 不涉及复杂交互逻辑的样式重构

### 允许流程

1. 读取上下文
2. 实施当前 phase
3. 运行必要检查
4. 生成 receipt
5. 停下来等待 gate（除非用户明确允许继续）

---

## 模式 B：Manual Gate / Demo Gate（人工门禁）

适用于**中高风险、涉及核心页面或交互流程**的阶段，例如：

* Query / 数据查询 / NL2SQL 页面改版
* Chat / 智能问答页面改版
* Knowledge 页面改版
* PM Workspace 页面改版
* 涉及请求流、状态流、组件联动的页面改版

### 必须流程

1. 读取上下文
2. 先输出简短影响分析
3. 实施当前 scope
4. 运行必要检查
5. 参考页面回归清单说明已检查项 / 待人工验证项
6. 生成 receipt
7. 停下来等待用户确认

---

# 3. 标准 Phase 执行流程

所有前端改版 phase，统一按以下步骤执行。

---

## Step 1：读取上下文

必须按顺序读取：

1. `CLAUDE.md`
2. 当前激活的前端改版计划
3. `docs/engineering/page-regression-checklists.md`
4. 最近一次 phase receipt（如果存在）

---

## Step 2：复述本 Phase 的范围

在真正修改代码前，先明确输出：

1. 当前 Phase 编号 / 名称
2. 本 Phase 的目标
3. 预计会改到的文件 / 组件 / 页面
4. 可能影响到的页面流程
5. 风险等级：Low / Medium / High

如果本 Phase 涉及核心页面或交互逻辑，必须额外输出**影响分析**：

* 可能受影响的组件
* 可能受影响的页面主流程
* 后续需要重点回归的 checklist 项

---

## Step 3：只实施本 Phase 的范围

要求：

1. 不要私自扩大 scope。
2. 不要把“顺手重构”混进本 phase，除非能明确证明收益且风险可控。
3. 不要在“UI 改版”名义下偷偷改 API 行为或核心业务逻辑，除非任务明确要求。

---

## Step 4：实施后做验证

至少做与本 phase 相关的最小验证。根据改动内容，选择：

* lint
* 测试
* build
* 手工逻辑验证说明（如果暂无自动化测试）

如果没有跑自动化测试，必须在输出和 receipt 中明确说明：

* 为什么这次没有跑
* 当前已做了什么验证
* 哪些点仍需人工验证

---

## Step 5：页面回归检查

如果本 phase 改动了核心页面（如 Query / Chat / Knowledge / PM），必须参考：

`docs/engineering/page-regression-checklists.md`

并在输出中明确说明：

1. 已检查了哪些项
2. 哪些项因为环境/时间原因仍需人工验证

---

## Step 6：生成 Phase Receipt

每个 phase 完成后，必须在以下目录生成一份 receipt：

`docs/engineering/receipts/`

推荐命名格式：

`YYYY-MM-DD-frontend-phase-X-简短名称.md`

例如：

* `2026-06-25-frontend-phase-1-design-tokens.md`
* `2026-06-25-frontend-phase-2-sidebar.md`

---

## Step 7：停在 Gate

生成 receipt 后，默认**停止继续执行**，等待用户确认。
只有用户明确要求“继续下一个 phase”时，才可以继续。

---

# 4. 风险等级与 Gate 建议

下面是推荐的风险分层，你可以按实际计划调整。

| Phase | 示例内容                             |   风险等级 | 推荐 Gate            |
| ----- | -------------------------------- | -----: | ------------------ |
| 0     | Git 存档 / tag / 分支                |    Low | 快速人工确认             |
| 1     | 设计 Token / 全局样式基础                |    Low | Subagent + receipt |
| 2     | 侧边栏 / 导航外壳                       |    Low | Subagent + receipt |
| 3     | 通用组件（Empty / Badge / Dialog）     | Medium | 人工 Gate            |
| 4     | Query / Orchestrator / Chat      |   High | 人工 Demo Gate       |
| 5     | PM / Knowledge / Logs / Settings |   High | 人工 Demo Gate       |
| 6     | 收尾验证 / 扫描 / 清理                   |   High | 人工 Gate            |

---

# 5. Receipt 是 Phase 完成的必要条件

没有 receipt，就不算 phase 完成。

receipt 至少要包含：

1. 本 phase 的范围
2. 实际改动文件
3. 已完成项
4. 未完成 / 延后项
5. 跑过的测试 / 验证
6. 仍需人工验证的点
7. 风险点 / 后续事项
8. 对下一步的建议

---

# 6. Review 规则

每个 phase 完成后都应该 review，但力度可以分层：

## 低风险 phase

允许轻量 review。

## 中高风险 phase

必须单独跑一次 review，建议使用：

`.claude/commands/review-phase.md`

---

# 7. 修复规则（Findings Resolution）

如果 review 发现问题，建议统一通过：

`.claude/commands/resolve-findings.md`

并在修复时明确选择一种策略：

### Option A：最小修复

* 只修 blocking issues / 关键回归问题
* 不做额外重构

### Option B：修复 + 局部清理

* 修问题的同时，顺手整理附近结构
* 但 scope 必须局限在当前 phase 相关区域

### Option C：回滚并重做

* 当前实现已经明显偏离计划 / 风险过高时使用
* 先回滚问题区域，再重新按本 phase scope 实施

---

# 8. 人工 Gate 触发条件

满足任一条件时，必须停下来等用户确认：

1. 改到了核心页面
2. 改到了请求流 / 状态流 / composable / store 等交互逻辑
3. review 发现 blocking issues 尚未修复
4. 视觉层级 / 页面结构发生明显变化，需要用户看效果
5. 当前 phase 的 receipt 中存在高风险未验证项

---

# 9. 推荐输出格式

Claude 在执行前端改版 phase 时，建议输出以下结构：

## 1）Phase 范围复述

* 当前 phase
* 目标
* 风险等级
* 预计影响范围

## 2）实施摘要

* 实际改了哪些文件
* 做了哪些 UI / 结构 / 组件调整

## 3）验证情况

* 跑了什么
* 没跑什么
* 为什么

## 4）页面回归 / 人工验证点

* 已检查项
* 待人工验证项

## 5）Receipt 路径

* 生成到了哪个文件

## 6）下一步建议

* 可继续下一 phase
* 先做 review
* 先修 blocking issues
