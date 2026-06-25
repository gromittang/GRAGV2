# ADR-007: PM方案工作室 LangGraph 迁移

**日期**: 2026-06-12
**状态**: 已实施

## 背景

PM方案工作室（PM Solution Studio）是 4 阶段方案分析管线（problem → analysis → detail → prd），此前使用 LangChain 时代的过程式代码实现：

1. **手动状态机**: `current_stage`（整数 0-3）+ `status`（pending/active/generated/confirmed）存在 MySQL 中，`PMSolutionService` 类手动管理
2. **手写回退逻辑**: `rollback_stage()` 70+ 行遍历所有阶段、清理 output_data、删除聊天记录
3. **跨阶段上下文手动拼接**: `_get_all_session_history()` 35 行每次从 DB 查询历史
4. **原始 httpx 流式**: `_generate_llm_stream()` 60 行直接调 DeepSeek API，不经过 LangGraph StreamWriter
5. **DB 与逻辑耦合**: `save_chat_record()`、`update_stage_status()` 散布在 API helper 函数中

项目的 RAG 和 NL2SQL 模块已迁移到 LangGraph（`graph_rag.py`、`graph_nl2sql.py`），PM 模块是最后一个未迁移的核心业务模块。

## 决策

将 PM 方案工作室从 LangChain 过程式架构迁移到 **LangGraph StateGraph**，核心利用 3 个能力：

### 1. `interrupt()` 人机协同

每个阶段生成内容后，图通过 `interrupt()` 暂停，等待用户决策：
- **继续对话**（continue）: 图回到 retrieve → generate loop，保持在同一阶段
- **确认推进**（confirm）: 图进入 confirm → advance 路径，生成结构化 JSON 并推进到下一阶段

### 2. StreamWriter 流式输出

`generate_node` 节点接收 `StreamWriter`，复用 `context_utils.stream_llm()` 进行流式生成。token 通过 `writer({"type": "token", "content": token})` 输出，API 层的 `_sse_stream()` 适配器将其转换为 SSE 事件。

### 3. 检查点持久化（MemorySaver + SQLAlchemy 双写）

`langgraph 0.2.54` 仅提供 `MemorySaver`（`SqliteSaver` 模块不存在），采用双写方案：

| 存储层 | 职责 |
|--------|------|
| MemorySaver | 运行时检查点，支持 `aget_state_history()` 回退 |
| SQLAlchemy（MySQL） | 跨重启持久化，`sync_state_to_db()` / `load_state_from_db()` |

每次 `astream` 因 `interrupt()` 结束后，API 层从最后一个 state snapshot 提取 `stage_outputs` 和 `stage_chats`，同步写入 `PMStage` / `PMChat` 表。

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

### 4 个节点

| 节点 | 职责 |
|------|------|
| `retrieve_node` | 条件检索知识库（P0 总是检索，P1-P3 按需）；通过 `asyncio.to_thread()` 包装同步 ChromaDB 调用 |
| `generate_node` | 构建上下文（session_topic + 前阶段摘要 + 知识库参考 + 近期对话），流式生成，`interrupt()` 暂停 |
| `confirm_node` | 非流式 LLM 调用（temperature=0.3），生成阶段结构化 JSON 输出 |
| `advance_node` | 将确认输出存入 `stage_outputs`，推进 `current_stage` 或标记 `is_completed=True` |

### 文件变更

| 文件 | 变更 | 说明 |
|------|------|------|
| `backend/app/core/agent_state.py` | 修改 | 新增 `PMSolutionState` TypedDict |
| `backend/app/agents/graph_pm.py` | **新建** (~400行) | 图定义、4 个节点、STAGE_PROMPTS、STAGE_TEMPLATES、检索/路由函数 |
| `backend/app/services/pm_solution_service.py` | 重度修改 (~675→150行) | 删除 `PMSolutionService` 类，保留 `sync_state_to_db()` / `load_state_from_db()` |
| `backend/app/api/pm_solution.py` | 中度修改 (~769→450行) | 核心端点改写为图调用，删除 `save_chat_record()` / `update_stage_status()` |
| `backend/app/rag/context_utils.py` | 修改 | `stream_llm()` / `llm_complete()` 增加 `max_tokens` / `temperature` 参数（向后兼容） |

### API 端点变更

| 端点 | 旧实现 | 新实现 |
|------|--------|--------|
| `POST /sessions/{id}/chat` | `service.chat_stream()` | `graph.astream(Command(resume=...), config)` |
| `POST /sessions/{id}/confirm` | 70 行手动逻辑 | `graph.astream(Command(resume={"action": "confirm"}), config)` |
| `POST /sessions/{id}/rollback` | 70 行手动清理 | 运行时: `aget_state_history` → 检查点回放；重启后: `load_state_from_db` → 新执行 |
| CRUD 端点 | 查 DB | **不变**（元数据查询仍走 DB） |

### 回退的双路径设计

- **运行时回退**: `aget_state_history(config)` 遍历检查点历史，找到目标阶段的检查点 config，用其重新 `astream`
- **重启后回退**: MemorySaver 无历史时，从 DB 重建目标阶段 state，重置下游 PMStage 为 pending，作为新 initial_state 启动 `astream`

## 备选方案

| 方案 | 评估 |
|------|------|
| 保持 LangChain 过程式代码 | 无需迁移成本，但状态管理、回退、跨阶段上下文继承全靠手写，扩展性差 |
| 使用子图（Subgraph） | 各阶段独立子图可复用，但 4 阶段共享 retrieve→generate→interrupt 模式，子图引入不必要的复杂度 |
| **单一 StateGraph + `current_stage` 参数化**（选中） | 通过 `current_stage` 字段参数化不同阶段的行为，保持图结构简洁 |

## 影响

### 正面

- 状态管理从手动 DB 操作变为显式的 `PMSolutionState` TypedDict，清晰可追溯
- `interrupt()` 天然支持人机协同，替代手写的 confirm/continue 状态切换
- 检查点机制自动支持回退，无需手动清理下游阶段数据
- StreamWriter 统一流式输出模式，与 RAG 图一致
- 代码量减少约 50%（service 675→150 行，API 769→450 行）

### 负面

- MemorySaver 跨重启丢失检查点历史，回退需降级到 DB 重建路径
- `JsonPlusSerializer`（MemorySaver 内置）对 `%` 等特殊字符敏感，需关注用户输入中的特殊字符
- LangGraph 概念（StateGraph、interrupt、Command、checkpointer）增加学习曲线

### 不改动的部分

| 模块 | 说明 |
|------|------|
| PMSession / PMStage / PMChat 表结构 | 不变，`sync_state_to_db()` 兼容现有 Schema |
| 前端 Vue 3（PMStudioPage.vue） | SSE 事件格式不变，前端无感知 |
| 知识库检索逻辑 | 提取为独立函数，检索行为不变 |
| STAGE_PROMPTS / STAGE_TEMPLATES | 内容不变，从 service 迁移到 graph_pm.py |
| CRUD 端点 | 始终走 DB 查询，不经过图 |

### 风险缓解

- **MemorySaver 跨重启丢失**: 双写机制确保 DB 中始终有可恢复的状态
- **`%` 字符序列化**: 与 NL2SQL 图相同的 `JsonPlusSerializer` 风险，在实际数据上验证
- **兼容性**: API 端点路径、SSE 事件格式、请求/响应模型不变，前端无需改动

## 相关文件

- `backend/app/agents/graph_pm.py` — 新建，图定义、节点、STAGE_PROMPTS、STAGE_TEMPLATES
- `backend/app/core/agent_state.py` — 新增 `PMSolutionState`
- `backend/app/services/pm_solution_service.py` — 重写，保留 `sync_state_to_db()` / `load_state_from_db()`
- `backend/app/api/pm_solution.py` — 重写核心端点，简化 helper
- `backend/app/rag/context_utils.py` — `stream_llm()` / `llm_complete()` 参数化
- `spec/workflows/pmstudio-workflow.md` — 新增 LangGraph 架构章节
