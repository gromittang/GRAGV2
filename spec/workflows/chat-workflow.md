# 智能问答工作流

## 架构概览

```
用户提问 → ChatInput.vue → ChatPage.vue → store.sendMessage()
                                              │
                    POST /api/v1/chat/stream (SSE)
                                              │
                    chat.py:chat_query_stream() → RAGService.query_stream()
                                              │
                    ┌──────────────────────────────┐
                    │  graph_rag.py                │
                    │  retrieve_node()             │
                    │                              │
                    │  1. Query 改写 (LLM)          │
                    │  2. 向量 + BM25 并行检索      │
                    │  3. RRF 融合 (k=60)          │
                    │  4. Reranker 精排             │
                    │         ↓                     │
                    │  score >= threshold?          │
                    │    → yes: generate_answer     │
                    │    → no:  reject_node (拒绝)   │
                    │                              │
                    │  ChromaDB + bge-reranker      │
                    └──────────────────────────────┘
                                              │
                    DeepSeek LLM 流式生成 (SSE)
                                              │
                    前端 SSE 解析 → ChatMessage 实时渲染
```

### 关键文件

| 层 | 文件 | 职责 |
|----|------|------|
| 前端页面 | `frontend/vue-app/src/views/ChatPage.vue` | 页面入口，header + new-chat 按钮 |
| 前端组件 | `frontend/vue-app/src/components/chat/ChatView.vue` | 消息列表容器，流式占位，滚动管理 |
| 前端组件 | `frontend/vue-app/src/components/chat/ChatMessage.vue` | 单条消息：头像、Markdown渲染、来源引用、图片提取 |
| 前端组件 | `frontend/vue-app/src/components/chat/ChatInput.vue` | 自适应文本框，Enter 发送，loading 禁用 |
| 前端状态 | `frontend/vue-app/src/stores/chat.js` | Pinia store：messages、sessions、loading/streaming 状态 |
| 前端 API | `frontend/vue-app/src/api/chat.js` | SSE 流式 fetch + axios 非流式回退 |
| 后端路由 | `backend/app/api/chat.py` | FastAPI router，挂载于 `/api/v1/chat` |
| 后端服务 | `backend/app/services/rag_service.py` | RAG 服务：调用 LangGraph agent，SSE 流式输出 |
| 检索器 | `backend/app/rag/retriever.py` | ChromaDirectRetriever：向量相似度检索 |
| BM25 | `backend/app/agents/graph_rag.py` | `_bm25_search()`: 从 ChromaDB 构建 BM25Okapi + jieba 分词 |
| 重排序 | `backend/app/rag/reranker.py` | bge-reranker-v2-m3 cross-encoder 精排 |
| 改写 | `backend/app/rag/query_rewriter.py` | LLM 关键词提取增强 (原查询保留 + 领域关键词追加) |
| 编排 | `backend/app/agents/graph_rag.py` | LangGraph 检索编排 (RRF 融合 + 降级) |
| 向量库 | `backend/app/core/vector_store.py` | ChromaDB 单例，集合命名 `kb_documents_{knowledge_id}` |
| 上下文 | `backend/app/rag/context_utils.py` | 图片提取、上下文预处理、消息构建、流式LLM、Safety Net |
| 嵌入 | `backend/app/core/embedding.py` | BAAI/bge-small-zh-v1.5，CPU，HF镜像 |
| 行业配置 | `backend/app/core/settings.py` | 按行业定制 chunk_size、top_k、BM25开关、system prompt |

---

## 完整请求流程

### 1. 用户发起提问

`ChatInput.vue` → emit `send` → `ChatPage.vue` → `store.sendMessage()`

```
store:
  1. messages.push({ role: 'user', content: question })
  2. loading = true, streaming = true, streamingContent = ''
  3. chatApi.sendStream(question, currentSessionId)
```

### 2. 后端接收 (chat.py:chat_query_stream, line 133)

```
1. 若 session_id 为空，生成 UUID 作为新会话ID
2. 加载会话历史：先查内存 dict，再查磁盘 JSON
3. 调用 rag_service.query_stream(question, history)
4. 返回 StreamingResponse (text/event-stream)
```

### 3. RAG 检索 (graph_rag.py:retrieve_node)

**检索链路** (LangGraph StateGraph 编排):

```
1. 关键词提取增强 (query_rewriter.py):
   - LLM 从口语化查询中提取关键实体和操作类型（≤40字关键词）
   - 保留原查询完整性，关键词追加在后方：`原查询 + 提取关键词`
   - Prompt 含 WMS 领域上下文：保留数字编码、专有名词、操作类型
   - 降级: 失败时使用原始 query

2. 并行检索 (向量 + BM25):
   - ChromaDirectRetriever: 向量相似度搜索 (top_k × multiplier 候选)
   - _bm25_search: 从 ChromaDB collection 构建 BM25Okapi (jieba 分词)
   - 降级: BM25 失败时仅用向量结果

3. RRF 融合 (Reciprocal Rank Fusion, k=60):
   - 合并两路结果，按 1/(k + rank + 1) 加权

4. Reranker 精排 (reranker.py):
   - bge-reranker-v2-m3 cross-encoder 批处理打分
   - 取 top_k 最终结果
   - 降级: 模型不可用时使用 RRF 分数排序
```

**单知识库模式** (指定 knowledge_id):
- 仅在 `kb_documents_{knowledge_id}` 集合中检索

**多知识库模式** (knowledge_id 为空):
- 扫描全部 `kb_documents_*` 集合
- 每个集合执行完整检索链路（向量+BM25→融合→精排）
- 跨知识库合并，全局按分数降序取 top_k

**行业配置影响** (`config.py`):

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| retrieval_top_k | 5 | 最终返回结果数 |
| reranker_top_k_multiplier | 3 | 候选池倍数 |
| use_hybrid_retrieval | True | 是否启用 BM25 |
| use_query_rewrite | True | 是否启用 Query 改写 |
| use_reranker | True | 是否启用 Reranker |
| retrieval_relevance_threshold_rerank | 0.3 | Reranker 分阈值（sigmoid 0~1），低于此值拒绝 |
| retrieval_relevance_threshold_vector | 0.65 | 向量分阈值（余弦相似度），reranker 不可用时使用 |

### 3b. 越界拒绝 (graph_rag.py:reject_node)

**双重防线机制**：

1. **RAG 相关性阈值**（主防线）：检索后检查最高分是否低于阈值，触发则路由到 `reject_node`
2. **提示词约束**（辅防线）：system prompt 要求 LLM 仅基于知识库内容回答，不足时主动告知

**双阈值设计**：

评分尺度因来源而异——reranker 分（sigmoid, ~0-1 均匀）和向量分（余弦相似度, 集中在 0.5-0.9）无法用单一阈值比较。系统根据 `top_nodes` 上是否实际存在 `rerank_score` 自动选择对应阈值。

**拒绝消息生成**：

```
1. get_kb_context_for_rejection() 获取知识库文档概览（SQLite 查询，to_thread 异步）
2. 构建 prompt（含知识库概况 + 用户问题）
3. LLM 生成自适应拒绝回复（≤80字，推断知识库覆盖领域）
4. 降级：LLM 失败时输出硬编码 fallback 消息
```

拒绝消息使用与正常流式相同的 SSE event type（token/done），前端无需改动。拒绝回复的 `has_documents=False`、`sources=[]`。

**Graph 结构**：
```
START → retrieve → (has_docs && score >= threshold) → generate_answer → END
                  → (no_docs || score < threshold)    → reject → END
```

### 4. 上下文构建 (context_utils.py + graph_rag.py:generate_answer_node)

```
上下文预处理 (context_utils.preprocess_context):
  1. 用 _extract_images_from_text() 提取 [IMG]url|label[/IMG] 标记
  2. 按 URL 去重，构建 img_refs: {idx: {url, label}}
  3. 将原始 [IMG] 标记替换为可读占位符: 【图片N: label】

System Prompt（单独 role=system）:
  "你是知识库问答助手。请根据提供的知识库内容回答问题。
   如果知识库内容不足以回答，请告知用户你无法回答该问题。"

组装内容:
  - 【对话历史】: 最近 6 条历史消息，每条截断至 150 字符
  - 【知识库内容】: 检索返回的 top_k 个文本块（[IMG] 已替换为【图片N】）
  - 【可用图片引用】: 有图片时动态追加，提供 !()[url] Markdown 模板
  - 【当前问题】: 用户原始提问

最终 messages 数组:
  - [system]: 助手角色描述 + 图片引用指令
  - 历史消息（每条截断至 200 字符）
  - [user]: 最终用户消息（含知识库上下文 + 图片引用表）

Safety Net (context_utils.apply_img_safety_net):
  LLM 回复后处理：若回答中仍含【图片N】占位符（未转为 Markdown），
  自动替换为 ![label](url) 语法。

图片输出端到端流程:
  1. 文档上传: [IMG]/images/xxx.png|图片N[/IMG] 嵌入文本 → 分块保护 → 向量入库
  2. 检索召回: chunk 文本仍含原始 [IMG] 标记
  3. 上下文预处理: [IMG] 替换为【图片N】，提取 {url, label} → img_refs
  4. Prompt: 拼接"可用图片引用"Markdown 表 + 图片引用指令
  5. LLM 生成: 产生 ![label](url) Markdown 图片（或残留【图片N】）
  6. Safety Net: 后处理替换残留【图片N】为 Markdown
  7. 前端渲染: marked.parse() 将 Markdown 转为 <img> 标签，CSS 限定 max-width
  8. 补充展示: source.images 缩略图作为"相关图片"独立展示
``` (graph_rag.py:generate_answer_node → context_utils.stream_llm)

```
核心流式调用使用 context_utils.stream_llm()，支持 async generator。

流式策略:
  - 无图片引用: 直接逐 token 流式输出（保留打字机效果）
  - 有图片引用: 缓冲全部 token → 应用 safety net → 一次性输出
    （确保图片引用的完整性，避免【图片N】跨 token 被截断）

httpx.stream POST → {deepseek_base_url}/chat/completions
  model: deepseek-chat
  max_tokens: 1000
  temperature: 0.7
  stream: true

每个 token → SSE event: {"type": "token", "content": token}
最终 event: {"type": "done", "sources": [...]}
```

### 6. 来源构建 (context_utils.build_sources)

```
每个检索节点构建:
  {
    content: 文本前200字符,
    score: 相似度分数,
    images: [从文本提取的图片URL],
    metadata: { document_name, document_id, ... }
  }

按 document_id 去重，上限 5 个来源
```

### 7. 前端 SSE 解析 (chat.js:sendMessage, line 90-160)

```
ReadableStream reader 逐块读取:
  data: {"type":"status",...}    → 仅日志，不展示
  data: {"type":"token",...}     → 追加到 streamingContent，实时渲染
  data: {"type":"done",...}      → messages.push({role:'assistant',content,sources})
  data: {"type":"error",...}     → 错误处理

异常回退链路:
  SSE 流失败 → 回退到非流式 chatApi.send(content, sessionId, stream_failed=true) (POST /api/v1/chat/)
  后端检测 stream_failed=true → 检查会话历史是否已有assistant回复（SSE可能实际已成功）
  若有 → 直接返回已有回复（去重）
  若无 → 正常生成并返回
  非流式也失败 → 显示 "抱歉，请求失败，请稍后重试。"
```

### 8. 会话持久化

```
并发安全机制:
  asyncio.Lock 按 session_id 保护 _persist_session() 调用
  原子写入: 先写 {session_id}.json.tmp → os.replace() 重命名

非流式路径:
  session_history[id].append(user_msg, assistant_msg)
  截断至 MAX_HISTORY * 2 = 20 条 (10 轮)
  await _persist_session(id) → data/sessions/{id}.json

流式路径:
  截断至 12 条 (6 轮)
  await _persist_session(id)
```

---

## SSE 事件类型

| type | 方向 | 含义 | 触发时机 |
|------|------|------|----------|
| `status` | 后端→前端 | 进度更新 | "正在搜索知识库..." / "正在生成回答..." |
| `token` | 后端→前端 | LLM 生成的一个文本 token | 流式生成期间持续推送 |
| `done` | 后端→前端 | 流式生成完成 | 包含 `sources` 数组 |
| `error` | 后端→前端 | 异常发生 | `content` 含错误描述 |

---

## 会话管理

### 存储架构

| 层级 | 存储 | 格式 |
|------|------|------|
| 内存 | `chat.py` 模块级 `session_history: Dict[str, List[Dict]]` | 进程生命周期 |
| 磁盘 | `{data_dir}/sessions/{session_id}.json` | 持久化 |

```json
{
  "session_id": "uuid",
  "history": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "...", "sources": [...]}
  ],
  "title": "首条消息前30字符",
  "updated_at": "2026-06-04T..."
}
```

### 生命周期

1. **创建**: 请求中 `session_id` 为空时，`str(uuid.uuid4())` 生成新ID
2. **加载**: 先查内存 dict → 未命中则 `_load_session_from_file()` 读磁盘 JSON → 回写内存
3. **持久化**: 每次成功查询后调用 `_persist_session()`
4. **标题**: 首条用户消息截取 30 字符，无消息时为"新对话"
5. **限制**: 非流式 20 条/10 轮，流式 12 条/6 轮，LLM 语境使用最近 6 条
6. **删除**: `DELETE /sessions/{id}` 清理内存 + 删除磁盘文件
7. **列表**: `GET /sessions` 扫描 sessions 目录，按 `updated_at` 降序

---

## 错误处理

| 场景 | 后端处理 | 前端处理 |
|------|----------|----------|
| 空问题 | 400 "问题不能为空" | 发送按钮 disabled (空文本) |
| 知识库无文档 | 返回 "知识库暂无文档，请先上传操作手册。" | 正常消息展示 |
| 检索无结果 | SSE error: "未找到相关内容" | 消息展示 |
| LLM API Key 缺失 | 返回 "检索结果:... [请配置DeepSeek API密钥]" | 消息展示 |
| LLM API 错误 | 返回 "API失败: {status_code}" | 消息展示 |
| LLM 生成异常 | `"\n[生成中断: {str(e)}]"` | 消息展示 |
| 相关性低于阈值 | 路由至 reject_node，LLM 生成自适应拒绝回复 | 流式展示拒绝消息，无来源 |
| 拒答 LLM 失败 | 降级为硬编码 fallback 拒绝消息 | 消息展示 |
| SSE 流网络失败 | `{"type":"error","content":"系统繁忙"}` | 回退到非流式 POST |
| 非流式也失败 | — | "抱歉，请求失败，请稍后重试。" |
| 会话 JSON 损坏 | try/catch 返回空列表 | 空历史加载 |

### 前端加载状态

| 状态 | 视觉 |
|------|------|
| 等待响应（无流） | ChatView 显示脉冲圆点 + "Agent 思考中..." |
| 流式输出中 | ChatMessage 实时更新 streamingContent |
| 流式完成 | 内容固化到 messages[]，流式占位消失 |
| 加载中 | ChatInput 禁用，按钮显示动画点 + "处理中" |

---

## API 端点

所有端点挂载于 `/api/v1/chat` (`backend/app/api/chat.py`)

| 方法 | 路径 | 函数 | 行号 | 用途 |
|------|------|------|------|------|
| POST | `/` | `chat_query()` | 98 | 非流式问答 |
| POST | `/stream` | `chat_query_stream()` | 133 | SSE 流式问答 |
| GET | `/sessions` | `list_sessions()` | 171 | 会话列表 |
| GET | `/sessions/{id}` | `get_session_detail()` | 177 | 会话详情+完整历史 |
| DELETE | `/sessions/{id}` | `delete_session()` | 187 | 删除会话 |

### 请求/响应模型

```python
class ChatRequest(BaseModel):
    question: str
    session_id: Optional[str] = None
    context_type: Optional[str] = "all"
    stream_failed: bool = False  # SSE回退去重标记

class ChatResponse(BaseModel):
    answer: str
    sources: List[dict] = []
    related_questions: List[str] = []
    session_id: str
    has_documents: bool = True  # 拒绝回复时为 False
```

---

## 前端状态管理 (chat.js Pinia Store)

```javascript
{
  messages: [{role, content, sources}],   // 当前会话消息列表
  sessions: [{session_id, title, ...}],   // 会话列表
  currentSessionId: "uuid" | null,        // 当前会话ID
  loading: Boolean,                       // 是否加载中
  streaming: Boolean,                     // 是否流式输出中
  streamingContent: String,               // 实时流式文本
  tools: []                               // Agent工具列表
}
```

关键 actions:
- `sendMessage(question)` — 发送消息 + SSE 解析 + 回退逻辑
- `loadSession(sessionId)` — 加载历史会话
- `newChat()` — 重置为空白对话
- `deleteSession(sessionId)` — 删除会话
- `fetchSessions()` — 获取会话列表

---

## 嵌入模型

- 模型: `BAAI/bge-small-zh-v1.5`
- 加载: HuggingFace，优先本地 `backend/models/bge-small-zh-v1.5/`，回退至 `hf-mirror.com`
- 设备: CPU
- 单例: `get_default_embedding()` 全局缓存
