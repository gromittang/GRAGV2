# ADR-011: 行业自适应分块策略（Industry-Adaptive Chunk Strategy）

**日期**: 2026-07-07
**状态**: 已实施
**关联**: [rag-workflow.md](../workflows/rag-workflow.md) §5, [settings.py](../../backend/app/core/settings.py)

## 背景

RAG 系统的检索质量高度依赖文档分块策略。chunk 过小则上下文碎片化、语义不完整；chunk 过大则检索精度下降、噪声增加。不同行业场景对 chunk 粒度的需求差异显著：

- **仓库管理（WMS）**: 操作流程长（入库→验收→上架→拣货→出库），需要大块保留完整操作上下文
- **医疗健康**: 医学文档碎片化，症状/诊断/用药信息分散，需要小块精确匹配
- **法律文档**: 法律条文长且结构化，需要大块保留条款完整性

单一固定分块参数无法适配所有场景。

## 决策

**采用行业自适应分块策略**：按知识库所属行业动态选择 `chunk_size` 和 `chunk_overlap`，并在分块过程中保护嵌入式图片标记不被切断。

### 核心架构

```
知识库创建 → 选择行业(general/wms/medical/legal/finance)
                │
                ▼
         IndustrySettings
         ├── chunk_size (300~1000)
         ├── chunk_overlap (50~200)
         ├── retrieval_top_k (5~10)
         └── use_bm25 (true/false)
                │
                ▼
         DocumentProcessor.split_documents()
         ├── 1. IMG 标记 → 占位符替换
         ├── 2. SentenceSplitter 切分
         └── 3. 占位符 → IMG 标记还原
```

### 行业参数矩阵

| 行业 | chunk_size | chunk_overlap | top_k | BM25 | 设计理由 |
|------|-----------|---------------|-------|------|---------|
| **general** (默认) | 500 | 100 | 5 | ✅ | 通用平衡，适合混合内容 |
| **wms** | 800 | 150 | 8 | ✅ | 操作流程长，大窗口保留完整 SOP 上下文 |
| **medical** | 300 | 50 | 10 | ✅ | 文档碎片化，小块精确检索症状/诊断 |
| **legal** | 1000 | 200 | 5 | ❌ | 法律条文长，大块保留条款完整性；向量检索对精确法律术语更准确 |
| **finance** | 600 | 100 | 6 | ✅ | 介于通用和 WMS 之间 |

### 关键设计原则

1. **chunk_overlap ≈ chunk_size × 15~20%** — 确保语义边界不丢失，相邻块有足够上下文重叠
2. **overlap 随 chunk_size 非线性缩放** — 小块用小重叠（避免冗余），大块用大重叠（补偿信息密度）
3. **BM25 按行业开关** — 法律领域关闭 BM25 纯向量检索（精确术语匹配更重要），其他领域开启混合检索

### IMG 图片标记保护（Token 占位符法）

PDF/DOCX 解析时，图片以 `[IMG]path|label[/IMG]` 标记嵌入文本流。SentenceSplitter 按句子边界切分时可能从标记中间截断，导致前端无法渲染图片。

**保护机制**（[document_processor.py:280-304](../../backend/app/rag/document_processor.py#L280-L304)）：

```
分块前: [IMG]/images/doc123_p1_i0.png|图片1[/IMG] → __IMG_TOK_0__
         (正则 r'\[IMG\].*?\[/IMG\]' 提取 → 替换为不可分割占位符)

分块中: SentenceSplitter 切分（__IMG_TOK_0__ 作为原子文本不会被切断）

分块后: __IMG_TOK_0__ → [IMG]/images/doc123_p1_i0.png|图片1[/IMG]
         (逐节点还原)
```

**设计约束**：
- `img_map` 作用域限定在 `split_documents()` 方法内，不跨文档持久化
- 占位符格式 `__IMG_TOK_N__` 包含下划线前缀，避免与正常文本冲突
- 替换使用 `str.replace(match, token, 1)` 控制替换次数，防止重复标记出错

## 理由

1. **检索质量提升** — 行业匹配的 chunk 大小使检索相关性显著优于固定参数
2. **零额外成本** — 参数切换在配置层完成，不需要重新训练或调优
3. **运行时动态** — 知识库创建时选择行业，后续文档处理自动应用对应参数
4. **IMG 保护保证多媒体完整性** — token 占位符法比正则 lookahead 更可靠，不依赖 SentenceSplitter 内部行为
5. **检索参数联动** — `top_k` 和 `use_bm25` 与 chunk 大小协调：小块多召回（medical top_k=10），大块少召回（legal top_k=5）

## 影响

### 新增/修改文件
- `backend/app/core/settings.py` — 5 个行业配置（`IndustrySettings` dataclass）
- `backend/app/rag/document_processor.py` — `DocumentProcessor.__init__()` 按行业加载参数；`split_documents()` 含 IMG 保护
- `backend/app/models/document.py` — `Knowledge.industry` 字段（String(50)，默认 "general"）
- 前端 `KBForm.vue` — 知识库创建时行业选择下拉

### 配置获取链路
```
Knowledge.industry → get_industry_settings(industry)
  → IndustrySettings(chunk_size, chunk_overlap, ...)
  → DocumentProcessor(industry_type) → self.chunk_size / self.chunk_overlap
  → SentenceSplitter(chunk_size=..., chunk_overlap=...)
```

### 已知限制
- 行业参数基于经验值，未做系统性的 grid search 优化
- 一个知识库绑定一个行业，不支持混合行业文档
- 文件级别的行业差异（如同一个知识库包含 WMS 和法律文档）未覆盖

## 替代方案

| 方案 | 缺点 |
|------|------|
| 固定 chunk_size=500 | 无法适配不同行业的检索需求差异 |
| LLM 驱动的自适应分块 | 成本高、速度慢、边界不可预测 |
| 基于文档结构的分块（按标题/章节） | 需要文档有清晰结构，WMS 操作手册通常无规范标题层级 |
| 语义分块（Semantic Chunking） | 需要额外的 embedding 计算，增加处理延迟 |
| 完全动态的参数搜索 | 过度设计，5 档预设已覆盖当前场景 |

## 与检索链路的协同

分块策略不是孤立的——它与混合检索链路的各阶段协同工作：

```
文档上传 → 行业自适应分块 → ChromaDB 向量化
                │
用户查询 → Query 改写 → 并行检索（向量 + BM25）→ RRF 融合 → Reranker 精排
                │                                    │
           top_k × multiplier              cross-encoder 重打分
           (行业决定 top_k)                 (与 chunk 大小无关)
```

- **大 chunk（wms/legal）**: 检索到更少的块，但每块内容更完整 → Reranker 有更充分的上下文打分
- **小 chunk（medical）**: 检索更多的块（top_k=10），通过 Reranker 精排弥补精度

---

> **状态**: 已实施
> **实施时间**: 2026-06 (初始实现)
> **文档更新**: 2026-07-07
> **代码基准**: `backend/app/core/settings.py`, `backend/app/rag/document_processor.py`
