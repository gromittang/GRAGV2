# ADR-005: 本地日志跟踪系统

**日期**: 2026-06-11
**状态**: 已实施

## 背景

系统当前存在以下诊断能力缺口：
1. 检索策略不透明 — 无法判断每次 RAG 实际使用了哪些检索器、BM25 和向量检索各召回多少
2. 性能瓶颈难定位 — 无法区分是检索慢、Reranker 慢还是 LLM 生成慢
3. Token 用量不可见 — 所有 LLM 调用点丢弃了 usage 数据
4. 全链路不可回溯 — 错误排查依赖 `print()` 输出，无法按请求 ID 串联

## 决策

构建**两层本地可观测性体系**，零外部依赖，保留 Langfuse 作为可选的云升级通道。

### 架构

```
Layer 2: core/tracing.py (Trace/Span 系统)
  - TraceContext (sync + async ctx manager)
  - TracingCallbackHandler (LangGraph 回调)
  - AsyncTraceWriter (asyncio.Queue + 批量写)

Layer 1: core/logging.py (Loguru 结构化日志)
  - 控制台: 可读彩色格式
  - 文件: JSON lines, 每日轮转
```

### 设计决策

1. **Loguru 替换所有 print()** — `data/logs/` 输出 JSON lines，支持按日轮转保留 30 天
2. **本地 Trace 系统 (core/tracing.py)** — `data/traces/` 输出 span JSON lines，异步批量写入避免热路径阻塞
3. **双通道 observability.py** — 本地 TracingCallbackHandler 始终启用，Langfuse 有凭证时附加
4. **TraceContext 同时支持 sync/async** — `graph_rag.py` 的 `asyncio.to_thread` 内部是同步代码，需要同步 `with TraceContext`
5. **使用 LangGraph Callback（非装饰器）** — 通过 `TracingCallbackHandler` 自动捕获 Graph 节点 span，避免与节点函数签名耦合

### Token 用量捕获

修复了 6 个 LLM 调用点使其返回/传递 token usage：

| 函数 | 文件 | 改动 |
|------|------|------|
| `stream_llm()` | `rag/context_utils.py` | 检查每个 chunk 的 `usage` 键，yield `{"type": "usage", ...}` |
| `llm_complete()` | `rag/context_utils.py` | 返回 `(answer, usage_dict)` 元组 |
| `QueryRewriter.rewrite()` | `rag/query_rewriter.py` | 返回 `(query, usage_dict)` 元组 |
| `_generate_llm_stream()` | `services/pm_solution_service.py` | 检查每个 chunk 的 `usage` 键 |
| `generate_structured_output()` | `services/pm_solution_service.py` | 附加 `_token_usage` 到返回值 |

通过 `stream_options: {"include_usage": True}` 参数让 DeepSeek API 在流式响应中包含 usage。

### Span 类型

| Span Name | 模块 | 关键字段 |
|-----------|------|---------|
| `http_request` | 全局 | method, path, status_code, duration_ms |
| `rag.query_rewrite` | RAG | original_query → rewritten_query, token_usage |
| `rag.vector_retrieve` | RAG | collection, top_k, results[{doc_id, score}] |
| `rag.bm25_retrieve` | RAG | collection, top_k, results[{doc_id, score}] |
| `rag.rrf_fusion` | RAG | vector_count, bm25_count, fused_count, results[{doc_id, rrf_score, vector_score, bm25_score}] |
| `rag.rerank` | RAG | candidate_count, final_count, results[{doc_id, rerank_score, rank_before, rank_after}] |
| `rag.llm_generate` | RAG | model, streaming, token_usage, answer_length |
| `nl2sql.sql_generate` | NL2SQL | schema_context_size, generated_sql, tables_used |
| `nl2sql.insight_generate` | NL2SQL | data_shape, insight_preview |

## 影响

### 新增文件
- `backend/app/core/logging.py`
- `backend/app/core/tracing.py`

### 修改文件
- `backend/app/core/observability.py` — 双通道
- `backend/app/main.py` — HTTP 中间件 + trace writer 生命周期
- `backend/app/agents/graph_rag.py` — TraceContext 仪表化
- `backend/app/agents/graph_nl2sql.py` — TraceContext 仪表化
- `backend/app/rag/context_utils.py` — token 捕获
- `backend/app/rag/query_rewriter.py` — token 捕获
- `backend/app/services/pm_solution_service.py` — token 捕获
- 全部 `print()` → logger 替换（16 个文件）
- `backend/requirements.txt` — 添加 `loguru`

### 输出文件
- `data/logs/app.{date}.jsonl` — 结构化日志
- `data/logs/error.{date}.jsonl` — 错误日志  
- `data/traces/trace.{date}.jsonl` — Span 追踪

## 回退

若需回退，删除 `core/logging.py` 和 `core/tracing.py`，将 `observability.py` 恢复为仅 Langfuse 的单通道版本，将 `print()` 改回即可。所有改动均为纯追加，不影响现有业务逻辑。
