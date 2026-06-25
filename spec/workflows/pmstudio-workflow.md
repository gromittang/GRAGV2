# PM方案工作流

## 多阶段流程

```
问题定义 → 方案分析 → 方案细化 → PRD生成
problem    analysis   detail     prd
  P0         P1         P2        P3
```

| 索引 | Key | 标签 | 说明 |
|------|-----|------|------|
| 0 | `problem` | 问题定义 | 明确问题背景、目标、约束、利益相关者 |
| 1 | `analysis` | 方案分析 | 对比多个可行方案，给出推荐 |
| 2 | `detail` | 方案细化 | 细化选定方案的功能设计、用户故事 |
| 3 | `prd` | PRD生成 | 整合前三个阶段成果，生成完整PRD文档 |

---

## 阶段状态机

每个阶段（Phase）独立维护状态，生命周期如下：

```
pending ──→ active ──→ generated ──→ confirmed
              ↑            │              │
              │            │              │
              └────────────┘              │
            (rollback恢复)                │
                                          │
              ┌───────────────────────────┘
              │  (重新生成内容后)
              ↓
          generated ←── update_stage_status()
```

| 状态 | 含义 | 前端视觉 |
|------|------|----------|
| `pending` | 尚未到达该阶段 | 灰色数字圆圈 |
| `active` | 当前正在操作的阶段 | 橙色光环圆圈，标签"进行中" |
| `generated` | AI已生成内容，用户尚未确认 | 蓝色文档图标，标签"已生成" |
| `confirmed` | 用户已确认，结构化输出已生成并锁定 | 绿色勾号，标签"已完成" |

---

## 阶段推进规则

### 规则1: 顺序推进，不可跳跃

用户只能通过「确认并进入下一阶段」按钮依次推进 P0 → P1 → P2 → P3。不存在跳过中间阶段直接到达后面阶段的路径。

**后端约束**: `POST /confirm` 始终将 `current_stage + 1` 作为下一阶段，不可指定跳跃目标。

### 规则2: 确认即推进，自动生成下一阶段内容

用户点击「确认并进入下一阶段」（最后阶段显示为「生成PRD」）:

1. 调用 `POST /confirm` → 后端生成当前阶段的结构化输出（JSON），标记阶段为 `confirmed`，推进 `current_stage += 1`
2. **API 成功返回后**，前端标记当前阶段为 `confirmed`（避免网络中断导致乐观更新后状态卡死）
3. 若为最后阶段（P3），直接调用 `POST /export` 导出 PRD Markdown 文件并下载
4. 若为非最后阶段:
   - 前端将 `currentPhase` 切换到下一阶段，状态设为 `active`
   - **清空下一阶段的 `chatHistory`**（覆盖旧内容）
   - **删除下一阶段旧的 `PMChat` 数据库记录**（后端 `confirm_stage` 中执行）
   - 自动发送初始提示词 `"请开始{阶段名}阶段的分析"` 触发 SSE 流式生成
   - AI 回复完成后，阶段状态更新为 `generated`

**关键**: 从前面阶段点「下一步」会**无条件覆盖**下一阶段的内容，不管下一阶段之前是否有内容。

### 规则3: 阶段内可自由对话

用户在当前阶段内可以多次通过「对话」按钮发送消息，与 AI 迭代讨论，不改变阶段状态。所有对话记录追加到当前阶段的 `chatHistory` 中，同时持久化到 `PMChat` 表。

### 规则4: 点击 Timeline 前面阶段 = 纯导航，内容保留

用户点击 Timeline 上任意已完成（`confirmed`）或已生成（`generated`）的阶段时:

- **有前端缓存时（路径A）**:
  - 纯前端切换 `currentPhase`，不调用后端 rollback API
  - 当前阶段（Phase X）的所有对话历史完整保留在 `chatHistory` 中
  - 调用 `PATCH /current-stage` 同步后端的 `current_stage`，但不影响阶段数据
  - 用户可随时点回 Phase X 继续查看和编辑

- **无前端缓存时（路径B，如刷新页面后）**:
  - 调用 `POST /rollback` API 从数据库恢复
  - 后端重置目标阶段为 `active`，目标阶段之后的阶段重置为 `pending`
  - 清除目标阶段之后阶段的 `output_data`、`output_summary` **和 `PMChat` 记录**
  - 若有历史对话则加载显示，无历史则自动生成

### 规则5: 从前面阶段点「下一步」才会覆盖

这是规则2和规则4的组合效果:

```
场景: 用户在 Phase 3，点击 Phase 1（规则4）→ Phase 1 内容恢复，Phase 3 内容保留
     用户在 Phase 1 点「下一步」（规则2）→ Phase 2 内容被清空并重新生成（覆盖）
```

如果用户仅点击导航查看前面阶段但不点「下一步」，则所有阶段内容保持完整。

---

## 阶段间上下文继承

后端 `chat_stream` 在生成内容时，会获取当前阶段及之前**所有阶段**的对话历史，构建跨阶段上下文:

- P0 (problem): 仅有 P0 的对话历史
- P1 (analysis): 包含 P0 + P1 的对话历史，前阶段 assistant 回复作为摘要注入
- P2 (detail): 包含 P0 + P1 + P2 的对话历史
- P3 (prd): 包含全部四个阶段的对话历史

各阶段 System Prompt 中明确要求继承前阶段讨论成果，不偏离主题。

---

## 知识库检索策略

- **P0 (problem)**: 始终执行向量检索
- **P1-P3**: 仅当用户输入包含新话题关键词（"新功能"、"另外"等）或长度超过100字符时才重新检索；否则复用已有上下文
- **检索范围**:
  - 指定 `knowledge_id`: 仅在指定知识库内检索
  - 空字符串 `""`: 检索全部知识库，跨库合并结果按相似度排序
  - 默认（null）: 使用"PM方案知识库"
- **相似度阈值**: 0.5，低于此值的结果不返回
- **结果排序**: 按相似度降序，取 top_k

---

## API 端点一览

| 方法 | 路径 | 用途 |
|------|------|------|
| `POST` | `/sessions` | 创建会话，初始阶段 P0 |
| `GET` | `/sessions` | 获取会话列表 |
| `GET` | `/sessions/{id}` | 获取会话详情（含各阶段状态） |
| `PATCH` | `/sessions/{id}/title` | 更新会话标题 |
| `PATCH` | `/sessions/{id}/current-stage` | 切换当前显示阶段（纯导航，不影响阶段数据） |
| `POST` | `/sessions/{id}/chat` | SSE 流式对话 |
| `GET` | `/sessions/{id}/chats` | 获取全部对话记录（按阶段分组） |
| `POST` | `/sessions/{id}/confirm` | 确认当前阶段，生成结构化输出并推进 |
| `POST` | `/sessions/{id}/rollback` | 回退到指定阶段，重置后续阶段 |
| `POST` | `/sessions/{id}/export` | 导出 PRD Markdown 文件 |
| `DELETE` | `/sessions/{id}` | 删除会话及其关联数据 |

---

## 数据库状态一致性约束

- `PMSession.current_stage` 记录后端视角的当前阶段
- 前端通过 `PATCH /current-stage` 同步纯导航切换，通过 `POST /rollback` 同步带回退语义的切换
- `confirm_stage` 推进时，若下一阶段已有 `PMStage` 记录，会先删除其旧的 `PMChat` 记录再复用
- `update_stage_status()` 在生成新内容后无条件更新阶段状态为 `generated`（包括从 `confirmed` 更新，因为新内容意味着旧确认已失效）

---

## LangGraph 架构（2026-06-12 迁移）

### 概述

PM 方案工作室已从 LangChain 过程式架构迁移到 LangGraph StateGraph。核心变化：

- 阶段编排由 `StateGraph` 管理，替代手动状态机
- `interrupt()` 实现人机协同（每阶段生成后暂停等待确认/继续）
- `MemorySaver` + SQLAlchemy 双写提供检查点持久化
- `StreamWriter` 统一流式输出（与 RAG 图一致）

### 图拓扑

```
START → retrieve → generate → [interrupt()]
  ↑                  │
  │    continue      │ confirm
  └──────────────────┤
                     ↓
              confirm → advance
                          │
                has next  │  completed
                     ↓    ↓
              retrieve   END
```

### State 定义

`PMSolutionState`（定义于 `backend/app/core/agent_state.py`）包含：

| 字段 | 类型 | 说明 |
|------|------|------|
| `session_id` | str | 会话 ID |
| `knowledge_id` | str\|None | 知识库 ID |
| `current_stage` | str | 当前阶段: "problem"\|"analysis"\|"detail"\|"prd" |
| `user_input` | str | 用户输入文本 |
| `user_action` | str | "continue"\|"confirm"（interrupt 恢复后设置） |
| `context` | str | 检索上下文 |
| `sources` | list | 检索来源 |
| `answer` | str | 流式生成的回答 |
| `structured_output` | dict | 确认时生成的结构化 JSON |
| `stage_outputs` | dict | 跨阶段累积输出 `{stage_type: {output_data, summary, confirmed_at}}` |
| `stage_chats` | dict | 跨阶段对话历史 `{stage_type: [{role, content, sources}, ...]}` |
| `session_topic` | str | Phase1 提取的核心主题 |
| `is_completed` | bool | 全部阶段完成标记 |

### 中断与恢复（interrupt / Command）

**interrupt 触发**: `generate_node` 完成流式生成后调用 `interrupt(snapshot)`，图暂停。snapshot 包含 `{"stage": ..., "answer_preview": ..., "sources": ...}`。

**Command 恢复**:
- 继续对话: `Command(resume={"action": "continue", "input": "用户输入"})` → route_after_interrupt → "continue" → retrieve（loop）
- 确认推进: `Command(resume={"action": "confirm"})` → route_after_interrupt → "confirm" → confirm_node → advance_node

**重要**: 确认操作必须使用 `astream`（而非 `ainvoke`），因为 confirm → advance → generate → interrupt() 会再次触发 interrupt，`ainvoke` 遇到 interrupt 会抛出 `GraphInterrupt` 异常。

### 检查点与持久化

| 存储层 | 职责 |
|--------|------|
| `MemorySaver` | 运行时检查点，支持 `aget_state_history()` 回退 |
| SQLAlchemy（MySQL） | 跨重启持久化，`sync_state_to_db()` / `load_state_from_db()` |

**双写时机**: 每次 `astream` 因 `interrupt()` 结束后，API 层从 `graph.get_state(config)` 提取最终 state，调用 `sync_state_to_db()` 将 `stage_outputs` → `PMStage`、`stage_chats` → `PMChat`。

**回退双路径**:
- 运行时: `aget_state_history(config)` → 找目标阶段检查点 → 用其 config 重新 `astream`
- 重启后: `load_state_from_db(session_id)` → 重建 state → 重置下游 PMStage → 新 `astream`

### API 端点实现

| 端点 | 实现方式 |
|------|---------|
| `POST /sessions/{id}/chat` | 检查 `graph.get_state(config)` 判断首次/恢复 → `graph.astream(initial_state \| Command(resume=...), config)` |
| `POST /sessions/{id}/confirm` | `graph.astream(Command(resume={"action": "confirm"}), config)` |
| `POST /sessions/{id}/rollback` | 先尝试 `aget_state_history`，失败则 `load_state_from_db` + 新执行 |
| CRUD 端点 | 直接查 DB（不经过图） |

### 代码文件

| 文件 | 说明 |
|------|------|
| `backend/app/agents/graph_pm.py` | 图定义、4 个节点、STAGE_PROMPTS、STAGE_TEMPLATES、检索函数 |
| `backend/app/core/agent_state.py` | `PMSolutionState` 类型定义 |
| `backend/app/services/pm_solution_service.py` | `sync_state_to_db()` / `load_state_from_db()` |
| `backend/app/api/pm_solution.py` | 核心端点 LangGraph 适配，SSE 流式输出 |
| `spec/adr/adr-007-pm-langgraph-migration.md` | 架构决策记录 |
