# 知识库/智能问答规则

## RAG 检索规则

### 检索链路

完整检索链路（graph_rag.py:retrieve_node）：
1. Query 改写 → 2. 向量 + BM25 并行检索 → 3. RRF 融合 → 4. Reranker 精排 → 5. top_k 返回

### 通用规则

- 优先检索指定知识库
- 未指定时检索所有知识库
- 最终返回 top_k（默认 5）个相关片段
- 候选池 = top_k × reranker_top_k_multiplier（默认 3），扩大召回以利于精排
- 无文档时 LLM 直接回答
- 如果提问和知识库的行业十分不相关，避免参考该知识库

### Query 改写规则

- 启用: use_query_rewrite=True 时生效
- 实现: LLM 将口语化查询改写为精确检索关键词（≤30字）
- 降级: 改写失败（超时/API 错误）时使用原始 query，不阻塞检索
- 示例: "仓库盘点咋搞" → "仓库盘点操作流程"

### BM25 检索规则

- 启用: use_hybrid_retrieval=True 时生效
- 实现: 每次检索从 ChromaDB collection 构建 BM25Okapi 索引（jieba 分词）
- 候选数: 与向量检索相同（top_k × multiplier）
- 降级: BM25 构建/检索失败时仅使用向量结果，不阻塞主流程
- 不缓存索引: 仓库场景文档量（千级）构建耗时毫秒级，每次重建保证一致性

### RRF 融合规则

- 算法: Reciprocal Rank Fusion, k=60
- 公式: score = Σ 1/(k + rank + 1) 对所有检索路径
- 适用: 向量 + BM25 两路结果融合（单路时跳过直接用分数排序）
- 融合后保留全部候选节点进入 Reranker

### Reranker 重排序规则

- 启用: use_reranker=True 且模型可加载时生效
- 模型: bge-reranker-v2-m3 (cross-encoder, 2.2GB)
- 加载: 延迟加载单例，启动时不阻塞；Docker 通过 volume 挂载（只读）
- 每对截断: query + doc[:512]
- 打分: sigmoid(logits)，批处理一次 forward
- 降级: 模型加载失败或推理异常时使用 RRF 分数排序，不阻塞检索

## 文档规则

- 类型限制: .pdf/.docx/.txt/.md
- 大小限制: 10MB
- 知识库隔离: 独立向量集合 (kb_documents_{knowledge_id})

## 会话规则

- 最大历史: 10 轮对话
- 自动标题: 首条消息截取 30 字
- 持久化: data/sessions/
