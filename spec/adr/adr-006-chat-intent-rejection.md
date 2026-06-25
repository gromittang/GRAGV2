# ADR-006: 智能问答越界拒绝机制

**日期**: 2026-06-12
**状态**: 已实施

## 背景

智能问答（RAG Chat）对不相关知识库的问题会直接调用 LLM 通用知识回答（`direct_llm_node`），存在以下问题：

1. 用户问"怎么做红烧肉"等完全无关问题时，系统会用 LLM 通用知识回答，而非告知无法回答
2. System prompt 硬编码为"WMS仓库操作助手"，无法适配其他行业的知识库
3. 缺少检索结果质量判断——即使检索到的文档与问题无关，系统也会基于低质量上下文生成回答

## 决策

采用**双重防线**机制，以 RAG 相关性阈值为主、提示词约束为辅：

### 防线 1: RAG 相关性阈值（主防线）

在检索后检查最高分是否低于可配置阈值：
- Reranker 可用时：使用 `retrieval_relevance_threshold_rerank=0.3`（sigmoid 分）
- Reranker 不可用时：使用 `retrieval_relevance_threshold_vector=0.65`（余弦相似度分）

路由逻辑：`best_score < threshold → reject_node`，而非原 `direct_llm_node`。

### 防线 2: 提示词约束（辅防线）

System prompt 从 `"你是WMS仓库操作助手。根据知识库回答问题。"` 改为 `"你是知识库问答助手。请根据提供的知识库内容回答问题。如果知识库内容不足以回答，请告知用户你无法回答该问题。"`

### 拒绝消息自适应

`reject_node` 通过 `get_kb_context_for_rejection()` 查询 SQLite 中的知识库名称和文档标题样本，交由 LLM 推断知识库覆盖领域，生成行业适配的拒绝回复，而非硬编码行业名称。

### 双阈值设计理由

向量余弦相似度（集中在 0.5-0.9）和 reranker sigmoid 分（0-1 均匀分布）的尺度完全不同，单一阈值无法同时适配。系统以 `top_nodes[0].metadata` 上是否实际存在 `rerank_score` 为依据自动选择阈值（不依赖 `use_reranker` 配置开关，因为 reranker 可能启用但加载失败）。

## 备选方案

| 方案 | 评估 |
|------|------|
| 仅提示词约束 | LLM 倾向于过度自信，对看似合理的问题仍会尝试回答，不可靠 |
| 语义路由/意图分类 | 需预定义领域类别（如 NL2SQL 路径的 10 个 WMS 领域），不适用于通用行业适配 |
| **RAG 阈值 + 提示词**（选中） | 基于知识库实际内容判断相关性，自动适配任意行业，实现复杂度低 |

## 影响

### 图结构变更

```
旧: START → retrieve → (has_docs?) → generate_answer → END
                      → (no_docs) → direct_llm → END

新: START → retrieve → (has_docs && score >= threshold) → generate_answer → END
                      → (no_docs || score < threshold)    → reject → END
```

### 废弃组件

`direct_llm_node` 脱离图，函数保留并标记 `# DEPRECATED`。

### 配置新增

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `retrieval_relevance_threshold_rerank` | 0.3 | Reranker 分阈值 |
| `retrieval_relevance_threshold_vector` | 0.65 | 向量分阈值 |

### 前端兼容性

拒绝消息使用与正常回答相同的 SSE event type（`token` / `done`），前端无需改动。

## 后果

- **正面**：无关问题不再产生幻觉回答；系统自适应任意行业知识库；用户体验改善
- **负面**：拒绝回复需要额外一次 LLM 调用（增加延迟和 token 消耗）；LLM 不可达时降级为硬编码消息
- **风险**：阈值设置不当可能误拒合法问题（已提供校准指引，默认值偏保守）

## 相关文件

- `backend/app/agents/graph_rag.py` — 新增 `reject_node`，修改 `retrieve_node`/路由/图结构
- `backend/app/rag/context_utils.py` — 新增 `get_kb_context_for_rejection`，更新 system prompt
- `backend/app/config.py` — 新增双阈值配置
- `backend/app/core/agent_state.py` — 新增 `best_relevance_score`/`score_source`/`is_rejected`
- `spec/workflows/chat-workflow.md` — 更新架构文档
