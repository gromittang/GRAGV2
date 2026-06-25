# ADR-003: 混合检索架构升级

## 背景

原智能问答检索链路仅使用纯向量检索（ChromaDB 余弦相似度），缺少关键词匹配和精排环节。用户口语化查询（如"仓库盘点咋搞"）与文档中的正式术语（如"库存盘点操作指南"）之间存在语义鸿沟，向量检索召回质量不稳定。

需要在不大幅增加基础设施成本的前提下优化检索质量。

## 核心决策

### 1. BM25 关键词检索选用 `rank-bm25` 而非 `llama-index-retrievers-bm25`

**决策**: 使用 `rank-bm25`（纯 Python, ~10KB）而非 llama-index 生态的 `llama-index-retrievers-bm25`。

**理由**:
- `rank-bm25` 零额外依赖，pip install 即用
- `llama-index-retrievers-bm25` 依赖 llama-index 生态，版本冲突风险高（已知 pydantic v1/v2 冲突）
- 实际代码已绕过 llama-index 直接用 ChromaDB（`ChromaDirectRetriever`），BM25 同理
- jieba 分词满足中文检索需求

### 2. Reranker 模型选用 `bge-reranker-v2-m3` (2.2GB)

**决策**: 选用 BAAI/bge-reranker-v2-m3 cross-encoder，而非 bge-reranker-base（1.1GB 但性能不足）或 bge-reranker-v2-m3 的大型变体。

**理由**:
- v2-m3 是多语言版本，中文效果优于 base
- 2.2GB 在 CPU 推理延迟可接受（10 个候选对 < 1s）
- 单一 `model.safetensors` 文件，加载简单
- 比 v2.5-Gemma 等更大模型节省内存

### 3. 使用原生 transformers API 而非 FlagEmbedding

**决策**: 使用 `transformers.AutoModelForSequenceClassification` + `AutoTokenizer` 直接加载，不使用 FlagEmbedding 封装。

**理由**:
- 本机 Windows (transformers 5.9.0) 与 FlagEmbedding 1.4.0 不兼容（`XLMRobertaTokenizer has no attribute prepare_for_model`）
- Docker (transformers 4.44.x) 与 FlagEmbedding 理论上兼容，但为保持双环境一致性选择原生 API
- 原生 API 更轻量，减少依赖层数
- 已验证原生 API 在两端均可正常工作

### 4. RRF (Reciprocal Rank Fusion) 替代加权求和

**决策**: 使用 RRF (k=60) 融合向量检索和 BM25 检索结果，而非原方案的固定权重加权 (0.6 向量 + 0.4 BM25)。

**理由**:
- RRF 不依赖原始分数的可比性（向量相似度 0.8 vs BM25 分数 12.3 不可比）
- 仅依赖排序位置，对不同检索器的输出尺度不敏感
- k=60 是学术界验证的稳定值
- 业界实践（Elasticsearch 8.x, Cohere Rerank）已验证

**影响**: 当 BM25 不可用时（`use_hybrid_retrieval=False` 或异常），RRF 退化为纯向量分数排序。

### 5. LLM Query 改写作为前置步骤

**决策**: 在检索前用 LLM 将口语化查询改写为精确检索关键词（≤30 字），不判断"是否需要改写"。

**理由**:
- 精确查询 LLM 会原样返回，改写成本极低（几个 token）
- 口语化查询改写收益显著（"仓库盘点咋搞" → "仓库盘点操作流程"）
- 失败直接降级为原始 query，不阻塞主流程
- 实现简单（一个 prompt + DeepSeek API 调用）

### 6. 模型文件通过 Docker volume 挂载

**决策**: bge-reranker-v2-m3 不打包进 Docker 镜像，通过 `docker-compose.yml` volume 挂载（只读）从宿主机注入。

**理由**:
- 模型 2.2GB，打进镜像会导致镜像膨胀
- 宿主机可统一管理模型，多个服务共享
- 更新模型无需重新构建镜像
- 与现有部署模式一致

### 7. 组件级降级策略

**决策**: 每个新增组件都有独立降级路径，单点故障不影响主流程。

| 组件 | 降级行为 |
|------|----------|
| Query 改写 | 失败/超时 → 使用原始 query |
| BM25 检索 | 异常 → 仅用向量结果 |
| Reranker 加载 | 模型不可用 → 使用 RRF 分数排序 |
| Reranker 推理 | 异常 → 使用 RRF 分数排序 |

## 替代方案

| 方案 | 缺点 |
|------|------|
| SPLADE 稀疏向量 | 模型大（~400MB），需要 GPU 加速 |
| Cohere Rerank API | 外部 API 依赖，网络延迟，成本 |
| 仅增大 top_k 召回 | 噪声增加，LLM 上下文浪费 |
| 固定加权融合 (0.6/0.4) | 两种分数不可直接比较 |
| FlagEmbedding 封装 | Windows/本地环境兼容性问题 |
| llama-index-retrievers-bm25 | 依赖重，pydantic 冲突 |

## 影响

- 需要部署时挂载 bge-reranker-v2-m3 模型（Docker volume）
- 每次检索增加 LLM 改写调用（~100ms）+ BM25 索引构建（~10ms）+ Reranker 推理（~500ms）
- 总检索延迟增加约 600-800ms，但召回质量显著提升
- Docker 镜像需 `transformers>=4.44.2` + `rank-bm25>=0.2.2`
- `backend/app/rag/retriever.py` 中旧的 `HybridRetriever` 类变为死代码（保留以防回退）

## 状态

已采纳 (2026-06-11)
