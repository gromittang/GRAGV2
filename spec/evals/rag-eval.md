# RAG质量指标

## 检索质量

| 指标 | 计算方式 | 目标 |
|------|------|------|
| 检索命中率 | 有结果返回 / 总查询 | ≥ 95% |
| 来源命中率 | expected_sources 命中 / 总数 | ≥ 70% |
| 关键词覆盖率 | 全部命中 / 总数 | ≥ 80% |
| 相似度 | cosine similarity | ≥ 0.3 |
| top_k召回 | 检索片段数 | 5 |

## 生成质量

| 指标 | 说明 | 目标 |
|------|------|------|
| 来源准确性 | LLM Judge 评分 (1-5) | ≥ 4.0 |
| 无幻觉 | LLM Judge 评分 (1-5) | ≥ 4.5 |
| 相关性 | 回答与问题匹配 | ≥ 3.5 |
| LLM Judge Overall | 加权综合分 (1-5) | ≥ 3.5 |

## 响应时间

| 场景 | 目标 |
|------|------|
| 检索 | < 1s |
| 生成 | < 3s |
| 流式首字 | < 500ms |

## 评估方法

- **自动化评估**: `python -m eval.chat.runner --dry-run` 检查检索命中 + 关键词覆盖
- **深度评估**: `python -m eval.chat.runner` LLM-as-Judge 5 维质量评分
- **用户反馈**: 每条 AI 回答的   /   按钮 + 来源准确性/完整性 toggle
- **反馈数据**: SQLite 存储（`chat_feedback.db`），GET /api/v1/chat/feedback/stats 查看统计
