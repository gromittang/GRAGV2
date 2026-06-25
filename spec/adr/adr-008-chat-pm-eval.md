# ADR-008: Chat 与 PM 模块评估体系建设

**日期**: 2026-06-15
**状态**: 已采纳
**相关**: ADR-001, ADR-003, ADR-006

---

## 背景

NL2SQL 模块已有完整的 CLI eval 体系（`backend/eval/nl2sql/`），包括多层确定性检查、LLM-as-Judge 语义评估、用户反馈收集。但 Chat（智能问答）和 PM（方案工作室）模块没有任何评估机制，无法量化质量和发现回归。

## 决策

为 Chat 和 PM 建立三级评估体系：

### Chat 模块
1. **用户反馈**：每条 AI 回答提供   /   按钮 + 来源准确性/完整性 toggle
2. **自动化评估**：CLI eval runner（`python -m eval.chat.runner`），检查检索命中 + 关键词覆盖
3. **深度评估**：LLM-as-Judge 5 维 RAG 质量评分（来源准确性/无幻觉/相关性/完整性/清晰度）

### PM 模块
1. **用户反馈**：每阶段 1-5 星评分 + 满意度 toggle + 修改次数自动计数

### 关键设计决策

**Chat eval 复用完整生产检索管线**：
`eval/chat/runner.py` 直接 import `graph_rag` 的 `retrieve_node` 和 `generate_answer_node`，而非仅调用 `retriever.py`。这确保了 eval 测试的是生产级别路径（query rewrite → vector → BM25 → RRF → reranker）。

**dry-run 模式通过临时禁用 query rewrite 实现零 LLM 成本**：
```python
settings.use_query_rewrite = False  # 临时覆盖
```

**LLM Judge 无条件对所有用例执行**（而非仅限检索失败 case）：
Chat 场景下"检索正确 ≠ 回答正确"，Judge 必须在 full 模式独立评估每个 case。

**反馈数据不自动消费**：
反馈存储在 SQLite（`chat_feedback.db` / `pm_feedback.db`），通过 stats API 暴露聚合数据，供人工定期复查后提炼为 eval 数据集。

### 复用 NL2SQL eval 的共享组件
- 抽取 `_get_llm()` 和 `_parse_judge_response()` 到 `backend/eval/judge_utils.py`
- 复用 runner 的并发控制（`asyncio.Semaphore`）、CLI 参数（`--dry-run`、`--category`、`--max-judge-calls`）
- 复用 reporter 的终端彩色摘要 + JSON 详情报告格式

## 影响

- 新增 `backend/app/models/chat_feedback.py` — SQLite 存储 Chat 用户反馈
- 新增 `backend/app/models/pm_feedback.py` — SQLite 存储 PM 阶段反馈
- 扩展 `backend/app/api/chat.py` — ChatResponse 增加 `best_relevance_score`，SSE done 事件增加 `message_index` 和 `best_relevance_score`
- 新增 `backend/eval/chat/` — Chat 自动化评估完整套件
- 新增 `backend/eval/judge_utils.py` — 共享 LLM Judge 工具
- 重构 `backend/eval/nl2sql/judges/sql_judge.py` — 改用共享 judge_utils
- 前端 `ChatMessage.vue` 扩展 props 支持反馈交互
- 前端 `PMStudioPage.vue` 集成 `StageFeedback.vue` 组件

## 未实施（后续考虑）

- PM 模块自动化评估（输出模板化使得评估可行，但 ROI 待验证）
- 反馈数据与 LangFuse trace 关联
- 反馈驱动的自动 prompt 调优
- eval 结果趋势面板（前端 dashboard）
