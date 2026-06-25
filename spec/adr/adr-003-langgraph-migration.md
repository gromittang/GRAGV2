# ADR-003: 采用 LangGraph 作为 Agent 编排框架

## 背景

当前项目的 Agent 编排存在以下问题：

1. **RAGAgent** 使用 LangChain AgentExecutor 单 Agent 模式，缺乏多步骤状态图编排能力
2. **QueryAgent** 使用硬编码管线，5 个步骤（Schema 检索 → SQL 生成 → 校验 → 执行 → Insight）通过顺序代码调用实现，无法灵活组合或分支
3. NL2SQL、RAG、Chat、PM 方案工作室等业务流程本质上是**有向图结构**（节点 + 条件边），但当前用顺序函数调用隐含表达，缺乏可视化、可中断、可恢复的能力
4. 缺乏以下企业级特性：
   - **会话持久化**：服务重启后对话状态丢失
   - **流式追踪**：无法追踪每一步的输入/输出和耗时
   - **人工审批节点**：无法在关键步骤（如 SQL 执行前）插入人工确认
   - **并行分支**：无法并行检索多个知识库后聚合结果
   - **错误恢复**：某步失败后无法自动重试或降级

## 决策

采用 **LangGraph** 作为统一的 Agent 编排框架，具体方案：

### 核心迁移

1. **图编排**：每个业务流程（NL2SQL、RAG、Chat、PM）定义为显式的 `StateGraph`，包含节点（Node）和条件边（Conditional Edge）
2. **保留现有生态**：
   - **LlamaIndex** 继续负责 RAG 检索引擎（向量检索 + BM25 混合检索）
   - **LangChain** 保留 `BaseTool`、`BaseLLM` 抽象，工具和 LLM 调用不重构
3. **新增依赖**：
   - `langgraph` — Agent 图编排引擎，提供状态图定义、条件路由、检查点持久化
   - `langfuse` — 可观测性平台，提供 LLM 调用追踪、Token 用量统计、延迟监控
   - `langgraph-checkpoint-sqlite` — 基于 SQLite 的检查点持久化，实现会话恢复

### 架构分层

```
应用层：FastAPI 路由（不变）
  ↓
编排层：LangGraph StateGraph ← 新增
  ├── 节点：LLM 调用、工具调用、SQL 校验、检索等
  ├── 条件边：根据状态决定下一节点
  └── Checkpointer：SQLite 会话持久化
  ↓
能力层：LlamaIndex（RAG）、LangChain Tools、aiomysql（不变）
  ↓
观测层：LangFuse ← 新增
```

### 并排部署策略

- 引入 `use_langgraph` feature flag（环境变量 `USE_LANGGRAPH=true`）
- 新旧版本通过同一 FastAPI 路由分发，根据 flag 选择 Agent 实现
- 默认关闭，验证稳定后切换默认值并逐步移除旧代码
- 前端和 API 契约不变，用户无感知

### 预埋扩展点

- `user_context` 字段预留，后续对接 RBAC（角色-权限模型）时直接使用
- 人工审批节点接口预定义，通过 `interrupt()` 挂起图执行，等待外部确认

## 理由

1. **图结构天然匹配** — NL2SQL 流程（检索→生成→校验→执行→分析）本质是有向图，LangGraph 的 `StateGraph` 可以精确表达条件分支（如校验失败→重新生成）、并行检索等
2. **生态兼容性** — LangGraph 与 LangChain 共享 BaseTool/BaseLLM 抽象，现有工具和 LLM 调用无需重写；LlamaIndex 作为独立检索引擎不受影响
3. **会话持久化** — 内置 `SqliteSaver` Checkpointer，服务重启后对话状态可恢复；用户多轮对话上下文完整保留
4. **可观测性** — LangFuse 集成提供每条链路的 Trace、每步 Latency、Token 消耗，便于性能分析和成本控制
5. **人工审批** — `interrupt()` 机制支持在任意节点挂起图执行，天然适合 SQL 执行前审批、PM 阶段确认等场景
6. **渐进式迁移** — feature flag 并排部署策略确保零风险回退，每个模块可独立迁移

## 影响

### 正面

- 状态管理从全局变量/函数参数变为显式的 `TypedDict` State，清晰可追溯
- 多步骤执行获得完整的 Tracing 链路，调试效率大幅提升
- 会话持久化后，服务重启不影响进行中的对话
- 人工审批能力可扩展到 SQL 执行确认、PM 方案评审等业务场景
- 图的可视化（`get_graph().draw_mermaid_png()`）便于团队理解和文档化

### 负面

- 团队需要学习 LangGraph 的状态图概念、Checkpointer 机制、条件边语法
- 新增依赖 `langgraph`、`langfuse`、`langgraph-checkpoint-sqlite`，维护负担增加
- 为简单 RAG 问答引入图编排可能过度设计

### 风险缓解

- Feature flag（`USE_LANGGRAPH`）确保可随时回退到旧版 Agent
- 新旧实现共享底层工具和 LLM，业务逻辑不重复
- 从 NL2SQL 模块（图结构最明显）开始迁移，积累经验后推广到其他模块

### 不改动的部分

| 模块 | 说明 |
|------|------|
| LlamaIndex RAG 检索引擎 | 向量检索 + BM25 混合检索逻辑不变 |
| FastAPI 路由层 | API 端点、SSE 格式、错误格式不变 |
| 前端 Vue 3 | 页面、组件、状态管理不变 |
| Spec 业务流程描述 | `spec/workflows/` 下文档不变 |
| Semantic Layer 规则 | `spec/nl2sql/semantic-layer.md` 不变 |
| LangChain BaseTool/BaseLLM | 工具和模型抽象层不变 |

## 替代方案

| 方案 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| 继续使用 LangChain AgentExecutor | 无迁移成本 | 无状态图编排、无 checkpointer、无人工审批 | 不满足长期需求 |
| LlamaIndex Workflow | LlamaIndex 原生支持，减少依赖 | 功能不如 LangGraph 成熟，checkpointer 和 interrupt 机制不完善 | 生态不如 LangGraph 丰富 |
| 自建编排器 | 完全自主可控 | 开发成本极高，需要自行实现检查点、追踪、人工审批等基础设施 | 不可行 |
| **LangGraph** | 状态图编排、Checkpointer、Interrupt、LangFuse 集成、LangChain 生态兼容 | 学习曲线、新增 3 个依赖 | **采纳** |

## 状态

已采纳。计划于 2026-06-08 开始实施，从 NL2SQL 模块先行迁移。
