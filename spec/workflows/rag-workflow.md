# 知识库管理工作流规范

> 本文档描述 WMS RAG 系统中"知识库管理"模块的完整工作流、架构设计、API 接口、数据模型及已知问题。所有描述均对应 `main` 分支实际代码行为。

---

## 目录

1. [概述](#1-概述)
2. [架构总览](#2-架构总览)
3. [文档上传与处理管线](#3-文档上传与处理管线)
4. [文件解析详情](#4-文件解析详情)
5. [分块策略与行业配置](#5-分块策略与行业配置)
6. [向量嵌入与索引流程](#6-向量嵌入与索引流程)
7. [知识库 CRUD 操作](#7-知识库-crud-操作)
8. [文档 CRUD 操作](#8-文档-crud-操作)
9. [知识库隔离机制](#9-知识库隔离机制)
10. [向量管理操作](#10-向量管理操作)
11. [前端组件树与状态管理](#11-前端组件树与状态管理)
12. [API 端点汇总](#12-api-端点汇总)
13. [数据模型](#13-数据模型)
14. [已知问题与限制](#14-已知问题与限制)
15. [关键文件索引](#15-关键文件索引)

---

## 1. 概述

知识库管理模块是 WMS RAG 系统的核心组件，负责文档的全生命周期管理：上传、校验、解析、分块、向量嵌入、索引构建、检索和管理。系统采用"每个知识库独立向量集合"的隔离策略，支持多知识库独立运作。

**技术栈：**

| 层级 | 技术 |
|------|------|
| 前端框架 | Vue 3 + Pinia (V2-first, V1 fallback) |
| 后端框架 | FastAPI (Python) |
| 数据库 | SQLite (ORM: SQLAlchemy) |
| 向量存储 | ChromaDB (PersistentClient) |
| 嵌入模型 | BAAI/bge-small-zh-v1.5 |
| 全文检索 | BM25 (rank_bm25 + jieba) |
| 重排序 | bge-reranker-v2-m3 (cross-encoder) |
| Query 改写 | DeepSeek LLM |
| 检索编排 | LangGraph StateGraph |
| 文件解析 | PyMuPDF / python-docx |

---

## 2. 架构总览

### 2.1 系统分层架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                          FRONTEND (Vue 3)                           │
│                                                                     │
│  KnowledgePage.vue                                                  │
│  ├── KBCardGrid / KBCard          ← 知识库列表视图                   │
│  ├── UploadBar / DocumentTable     ← 文档列表视图 (路由 :kbId)       │
│  ├── DocumentRow / DocumentFilter  ← 文档过滤与操作                  │
│  ├── BatchActions                  ← 批量操作工具栏                  │
│  ├── PreviewModal / ProgressPoll   ← 预览 & 上传进度轮询             │
│  ├── TagManager / StatsBento       ← 标签管理 & 统计卡片             │
│  └── KBForm                        ← 知识库创建/编辑表单             │
│                                                                     │
│  Pinia Store: stores/knowledge.js                                   │
│  API Clients: api/documentsV2.js (primary), api/documents.js (V1)  │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ HTTP REST
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       BACKEND (FastAPI)                             │
│                                                                     │
│  Router: api/documents.py              Router: api/vector_admin.py  │
│  Prefix: /api/v1/docs                  Prefix: /api/v1/vector-admin │
│                                                                     │
│  ┌───────────────────┐   ┌──────────────────┐   ┌───────────────┐  │
│  │ document_processor │   │  index_builder   │   │   retriever   │  │
│  │ (parse + chunk)   │──▶│ (embed + index)  │──▶│ (hybrid search)│  │
│  └───────────────────┘   └──────────────────┘   └───────────────┘  │
│           │                        │                      │          │
│           ▼                        ▼                      ▼          │
│  ┌────────────────┐   ┌────────────────────┐   ┌───────────────┐   │
│  │    SQLite      │   │    ChromaDB        │   │   embedding   │   │
│  │  (metadata)    │   │  (vector storage)   │   │   (bge-small)  │   │
│  └────────────────┘   └────────────────────┘   └───────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 数据流向图

```
用户上传文件
     │
     ▼
┌──────────┐    ┌──────────┐    ┌──────────────┐    ┌────────────┐
│ 文件校验  │───▶│ 创建记录  │───▶│  异步处理     │───▶│ 段落拆分   │
│ (扩展名,  │    │ Document │    │ (process_    │    │ Paragraph  │
│  大小)    │    │ status=0 │    │  document_   │    │ 记录       │
└──────────┘    └──────────┘    │  async)      │    └─────┬──────┘
                                └──────┬───────┘          │
                                       ▼                  ▼
                                ┌──────────────┐    ┌────────────┐
                                │  向量索引     │◀───│ 分块嵌入   │
                                │ VectorStore  │    │ embed()    │
                                │ Index        │    │            │
                                └──────┬───────┘    └────────────┘
                                       │
                                       ▼
                                ┌──────────────┐
                                │ 更新状态     │
                                │ status=2/3  │
                                └──────────────┘
```

---

## 3. 文档上传与处理管线

### 3.1 上传阶段（同步，前端发起）

```
步骤 1: 用户选择文件
   ├── 组件: UploadBar.vue
   ├── 支持格式: .pdf / .docx / .txt / .md
   └── 前端校验: 扩展名白名单、文件非空

步骤 2: POST /api/v1/docs/upload (multipart/form-data)
   ├── 请求参数:
   │   ├── file: 文件本体
   │   ├── kb_id: 目标知识库 ID (可选，优先级高于 kb_name)
   │   └── kb_name: 知识库名称 (当 kb_id 未提供时使用)
   └── 后端处理 (upload_document):

步骤 2.1: 文件校验 (validate_upload)
   ├── 检查文件非空
   ├── 检查扩展名在 ["pdf", "docx", "txt", "md"] 中
   └── 检查文件大小 ≤ 10MB (10 * 1024 * 1024)

步骤 2.2: 解析知识库
   ├── 若提供 kb_id → 查询 Knowledge 记录，不存在则 404
   └── 若提供 kb_name → get_or_create (如存在则复用，否则创建)

步骤 2.3: 创建 Document 记录
   ├── 字段: name, knowledge_id, status="0" (PENDING)
   ├── file_path: data/uploads/{doc_id}_{原始文件名}
   └── 写入 SQLite

步骤 2.4: 保存源文件 & 创建 File 记录
   ├── 将上传文件写入 data/uploads/{doc_id}_{filename}
   ├── 创建 File 记录: id, path, doc_id, size, type
   └── 提交事务

步骤 2.5: 返回响应 (立即)
   ├── HTTP 200, 返回 document_id, status="0"
   └── 前端进入进度轮询阶段 (ProgressPoll, 每 2 秒轮询)
```

### 3.2 处理阶段（异步入口，但实际同步执行）

```
步骤 3: process_document_async(document_id)
   ├── 注意: 名称标注 "async"，但实际在请求生命周期内同步执行
   │   └── 没有使用 Celery / BackgroundTasks / 消息队列
   ├── 更新 status → "1" (PROCESSING)，提交事务

步骤 4: DocumentProcessor.process_file()
   ├── 4.1 parse_file(): 根据扩展名调用对应解析器
   │   ├── .txt / .md → 简单 UTF-8 读取
   │   ├── .pdf → PyMuPDF (fitz) 解析
   │   └── .docx → python-docx 解析
   │   └── 返回: List[Document] (LlamaIndex Document 对象)
   │
   └── 4.2 split_documents(): 使用 SentenceSplitter 分块
       ├── 读取行业配置 (chunk_size, chunk_overlap)
       ├── 保护 [IMG]...[/IMG] 标签不被分割
       └── 返回: List[Document] (分块后)

步骤 5: 创建 Paragraph 记录
   ├── 对每个 chunk 创建一条 Paragraph:
   │   ├── id, document_id, knowledge_id
   │   ├── content (chunk 文本)
   │   ├── title (从首个 chunk 提取)
   │   └── position (chunk 序号)
   └── 写入 SQLite

步骤 6: IndexBuilder.build_index()
   ├── 直接使用步骤 4 已分割的 nodes，不再二次拆分
   ├── 调用 embedding.py 进行向量嵌入
   ├── 创建/获取 ChromaDB 集合: kb_documents_{knowledge_id}
   └── 构建 VectorStoreIndex，持久化到 ChromaDB

步骤 7: 更新最终状态
   ├── 成功 → status="2" (SUCCESS), 更新 char_length
   └── 失败 → status="3" (FAILURE), 记录错误信息
```

### 3.3 文档状态生命周期

```
 ┌─────────┐    上传     ┌────────────┐    开始处理    ┌────────────┐
 │  无状态  │ ──────────▶ │  PENDING   │ ─────────────▶ │ PROCESSING │
 └─────────┘             │  status=0  │                │  status=1  │
                         └────────────┘                └─────┬──────┘
                                                            │
                                     ┌──────────────────────┼──────────────────────┐
                                     │ 成功                 │                      │ 失败
                                     ▼                      │                      ▼
                              ┌────────────┐               │               ┌────────────┐
                              │  SUCCESS   │               │               │  FAILURE   │
                              │  status=2  │               │               │  status=3  │
                              └────────────┘               │               └─────┬──────┘
                                                            │                    │
                                  (前端 ProgressPoll 每 2s 轮询状态直到 2 或 3)   │
                                                                                 │
                                                          POST /docs/{id}/reprocess
                                                          (重置 status → 0，重新处理)
```

---

## 4. 文件解析详情

### 4.1 纯文本 (.txt / .md)

```
输入: 文件路径 (UTF-8 编码)
处理: 直接读取全部内容
输出: LlamaIndex Document(text=内容, metadata={file_name, file_type})
```

### 4.2 PDF (.pdf)

```
解析引擎: PyMuPDF (fitz)

处理流程:
  1. fitz.open(filepath) 打开 PDF
  2. 逐页遍历:
     a. get_text("blocks") 提取文本块 (含坐标)
     b. get_images(full=True) 提取图像引用
     c. 按 Y 坐标排序文本块 (从上到下阅读顺序)
     d. 图像保存: data/images/{doc_id}_p{页码}_i{图片序号}.{扩展名}
     e. 图像标记: [IMG]相对路径|标签[/IMG]
     f. 文本块拼接 (块间双换行)
  3. 返回 List[Document] (每页一个 Document)

输出: LlamaIndex Document(text=页面内容, metadata={page_number, source})
```

### 4.3 Word (.docx)

```
解析引擎: python-docx

处理流程:
  1. docx.Document(filepath) 打开文档
  2. 按正文顺序遍历 (w:p 段落 + w:tbl 表格):
     a. 段落: 直接提取文本
     b. 表格: 构建 Markdown 表格 (| th | th | 格式)
     c. 图像: 遍历 document.inline_shapes / rels 提取嵌入图片
     d. 图像标记: [IMG]相对路径|图片N[/IMG]
  3. 返回 List[Document] (一个 Document 包含全文)

输出: LlamaIndex Document(text=全文, metadata={file_name, file_type})
```

### 4.4 图像标记格式

```
[IMG]data/images/{doc_id}_p1_i0.png|页面1图片1[/IMG]

格式说明:
  - 左边界: [IMG]
  - 内容: 图片路径|标签描述
  - 右边界: [/IMG]

保护机制 (token 占位符法):
  1. 分块前: 正则 r'\[IMG\].*?\[/IMG\]' 提取所有图片标记
  2. 将每个标记替换为不可分割的占位符: __IMG_TOK_N__
  3. SentenceSplitter 切分（占位符作为原子文本不会被切断）
  4. 切分后: 将 __IMG_TOK_N__ 还原为原始 [IMG]...[/IMG] 标记
  5. 前端 PreviewModal 可解析此格式渲染图片
  6. Chat Q&A: _extract_images_from_text() 解析标记提取 {url, label}
```

---

## 5. 分块策略与行业配置

### 5.1 分块器

```
SentenceSplitter (LlamaIndex)
  ├── 按句子边界分割
  ├── chunk_size: 目标块大小 (字符数)
  ├── chunk_overlap: 相邻块重叠字符数
  └── 特殊保护: [IMG]...[/IMG] 标签不拆分 (token 占位符法)
       ├── 分块前将 [IMG]...[/IMG] 替换为 __IMG_TOK_N__ 占位符
       ├── 分块后还原占位符为原始标记
       └── 处理逻辑见 DocumentProcessor.split_documents()
```

### 5.2 行业配置表

配置定义于 `backend/app/core/settings.py`，按 `industry` 字段区分：

| 行业 (industry) | chunk_size | chunk_overlap | top_k | bm25_weight |
|-----------------|-----------|---------------|-------|-------------|
| general (默认)  | 500       | 100           | 5     | 0.4         |
| wms             | 800       | 150           | 5     | 0.4         |
| medical         | 300       | 50            | 5     | 0.4         |
| legal           | 1000      | 200           | 5     | 0.4         |
| finance         | 600       | 100           | 5     | 0.4         |

配置获取逻辑: 根据知识库关联的行业设置读取对应参数，未匹配时回退到 `general`。

---

## 6. 向量嵌入与索引流程

### 6.1 嵌入模型

```
模型: BAAI/bge-small-zh-v1.5
加载: HuggingFaceEmbedding (LlamaIndex)
维度: 512
```

### 6.2 索引构建流程

```
IndexBuilder.build_index_from_docs(documents, knowledge_id)

  步骤 1: 获取 ChromaDB 集合
  ├── 集合名称: kb_documents_{knowledge_id}
  ├── PersistentClient: data/chroma_db/
  └── 获取或创建集合

  步骤 2: 分块 & 嵌入
  ├── build_index(nodes) 直接使用已分割节点，不再二次拆分
  ├── build_index_from_docs(documents) 通过 processor.split_documents() 拆分（含 IMG 保护）
  ├── 逐条调用 embedding.embed_documents()
  └── Paragraph 表与 ChromaDB 使用同一次分块结果，块边界一致

  步骤 3: 构建索引
  ├── VectorStoreIndex.from_documents()
  ├── storage_context 绑定 ChromaVectorStore
  └── 持久化向量到 ChromaDB

  步骤 4: 更新状态
  └── 成功: Document.status = "2", Document.char_length = 总字符数
```

### 6.3 混合检索（LangGraph 图版）

智能问答检索使用 `graph_rag.py:retrieve_node()` 实现多阶段混合检索链路：

```
graph_rag.py:retrieve_node() 检索链路:

  1. Query 改写 (LLM): 口语化查询 → 精确检索关键词
     │  └── 降级: 改写失败则使用原始 query
     ▼
  2. 并行检索 (向量 + BM25):
     ├── ChromaDirectRetriever: ChromaDB 向量相似度搜索 (top_k × multiplier)
     └── _bm25_search: 从 ChromaDB collection 构建 BM25Okapi 索引 (jieba 分词)
     │  └── 降级: BM25 失败则仅使用向量结果
     ▼
  3. RRF 融合 (Reciprocal Rank Fusion, k=60):
     └── 合并两路结果，按 1/(k + rank + 1) 加权计算融合分数
     ▼
  4. Reranker 精排 (bge-reranker-v2-m3 cross-encoder):
     └── 批处理打分，按 sigmoid 分数降序取 top_k
     │  └── 降级: Reranker 不可用时使用 RRF 分数排序
     ▼
  5. 返回 top_k 结果 (含 context, sources)
```

**关键模块：**

| 模块 | 文件 | 职责 |
|------|------|------|
| 检索编排 | `graph_rag.py` | LangGraph 状态图，串联改写→检索→融合→重排序→生成 |
| Query 改写 | `rag/query_rewriter.py` | LLM 改写口语化查询，失败降级 |
| BM25 检索 | `graph_rag.py:_bm25_search()` | 从 ChromaDB 构建 BM25Okapi，jieba 分词 |
| RRF 融合 | `graph_rag.py:_rrf_fusion()` | Reciprocal Rank Fusion，合并多路结果 |
| Reranker | `rag/reranker.py` | bge-reranker-v2-m3 cross-encoder 精排 |

**配置项 (config.py)：**

| 配置 | 默认值 | 说明 |
|------|--------|------|
| `retrieval_top_k` | 5 | 最终返回结果数 |
| `reranker_top_k_multiplier` | 3 | 候选数 = top_k × N，扩大召回池 |
| `use_hybrid_retrieval` | True | 是否启用 BM25 混合检索 |
| `use_query_rewrite` | True | 是否启用 LLM Query 改写 |
| `use_reranker` | True | 是否启用 Reranker 重排序 |

**多知识库检索：**
- 遍历所有 `kb_documents_*` 集合
- 每个集合内执行完整检索链路（向量+BM25→融合）
- 跨知识库合并，全局按 RRF/Reranker 分数排序

---

## 7. 知识库 CRUD 操作

### 7.1 创建知识库

```
POST /api/v1/docs/knowledge

请求体 (JSON):
  {
    "name": "知识库名称",        // 必填，1-150 字符，唯一
    "description": "描述文本",   // 可选
    "industry": "general"        // 可选，默认 general
  }

后端逻辑:
  1. 校验 name 长度 (1-150) 和非空
  2. 检查 name 唯一性 (不允许重名)
  3. 创建 Knowledge 记录，捕获 IntegrityError 防止并发竞态（依赖 DB 层 UNIQUE 约束）
  4. 返回新建记录 (含自动生成的 UUID)

状态码: 200 (成功) / 400 (名称重复或无效)
```

### 7.2 获取知识库列表

```
GET /api/v1/docs/knowledge/list

响应 (JSON):
  [
    {
      "id": "uuid",
      "name": "知识库名称",
      "description": "...",
      "industry": "general",
      "document_count": 5,       // 聚合统计: 关联文档数
      "paragraph_count": 150,    // 聚合统计: 关联段落数
      "total_char_length": 50000 // 聚合统计: 总字符数
    },
    ...
  ]

后端逻辑:
  1. 查询所有 Knowledge 记录
  2. 对每条记录聚合: COUNT(Document), COUNT(Paragraph), SUM(char_length)
  3. 返回包含统计信息的列表
```

### 7.3 删除知识库

```
DELETE /api/v1/docs/knowledge/{knowledge_id}

后端逻辑:
  1. 查询 Knowledge 记录 (不存在则 404)
  2. 级联删除关联的 Document 记录
     └── Document 删除时级联删除 Paragraph 和 File 记录
  3. 删除 Knowledge 记录本身
  4. 提交事务

⚠️ 已知问题: 不删除 ChromaDB 中对应的 kb_documents_{knowledge_id} 集合
   → 向量数据泄漏，见第 14 节。
```

---

## 8. 文档 CRUD 操作

### 8.1 上传文档

参见 [第 3 节：文档上传与处理管线](#3-文档上传与处理管线)。

### 8.2 获取文档列表

```
GET /api/v1/docs/list/{page}/{page_size}?knowledge_id={id}

查询参数:
  - page: 页码 (从 1 开始)
  - page_size: 每页数量
  - knowledge_id: 知识库过滤 (可选)
  - name: 文档名称模糊搜索 (可选)
  - status: 状态过滤 (可选, "0"/"1"/"2"/"3")

后端逻辑:
  1. 构建查询条件 (knowledge_id, name like, status)
  2. 按创建时间倒序排列
  3. 分页返回 (含 total 总数)
```

### 8.3 获取文档详情

```
GET /api/v1/docs/detail/{document_id}

后端逻辑:
  1. 查询 Document 记录 (不存在则 404)
  2. 返回完整字段 (含 char_length, status 等)
```

### 8.4 获取文档段落

```
GET /api/v1/docs/paragraphs/{document_id}

后端逻辑:
  1. 查询该文档下所有 Paragraph 记录
  2. 按 position 字段升序排列
  3. 返回段落列表 (含 id, content, title, position)

前端用途: PreviewModal 加载并渲染文档内容。
```

### 8.5 下载源文件

```
GET /api/v1/docs/download-source/{document_id}

后端逻辑:
  1. 查询 Document 记录
  2. 通过 Document.file 关系获取 File 记录
  3. 以 FileResponse 返回原始文件 (MIME: application/octet-stream)
```

### 8.6 删除文档

```
DELETE /api/v1/docs/{document_id}

后端逻辑:
  1. 查询 Document 记录 (不存在则 404)
  2. 级联删除关联 Paragraph 记录
  3. 删除关联 File 记录 (含物理文件)
  4. 删除 Document 记录

⚠️ 已知问题: 不删除 ChromaDB 中该文档对应的向量 (无文档-向量 ID 映射)
   → 向量残留，见第 14 节。
```

---

## 9. 知识库隔离机制

### 9.1 隔离层次

```
┌─────────────────────────────────────────────────────┐
│                    SQLite 层                         │
│                                                     │
│  Knowledge ──▶ Document ──▶ Paragraph ──▶ File      │
│     │              │            │                    │
│     │         knowledge_id  knowledge_id             │
│     │         (FK 约束)     (FK 约束)                │
│     │                                               │
│     └── 每个知识库独立 ID，外键关联保障数据隔离        │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│                  ChromaDB 层                         │
│                                                     │
│  Collection: kb_documents_{knowledge_id_1}           │
│  Collection: kb_documents_{knowledge_id_2}           │
│  Collection: kb_documents_{knowledge_id_3}           │
│                                                     │
│  └── 每个知识库独立向量集合，物理隔离                  │
└─────────────────────────────────────────────────────┘
```

### 9.2 集合命名规则

```
模式: kb_documents_{knowledge_id}

示例:
  - kb_documents_a1b2c3d4-...  (通用知识库)
  - kb_documents_e5f6g7h8-...  (WMS 知识库)

存储位置: data/chroma_db/ (PersistentClient 持久化目录)
```

### 9.3 跨知识库检索

采用 graph_rag.py 的 retrieve_node() 统一检索链路：

```
1. ChromaDB PersistentClient.list_collections() 发现所有集合
2. 过滤 kb_documents_* 前缀的集合
3. 对每个集合执行完整混合检索链路:
   ├── Query 改写 (LLM) → 精确检索关键词
   ├── ChromaDirectRetriever: 向量相似度搜索 (top_k × multiplier)
   ├── _bm25_search: BM25Okapi 关键词检索 (jieba 分词)
   ├── _rrf_fusion: RRF 融合两路结果 (k=60)
   └── Reranker: bge-reranker-v2-m3 cross-encoder 精排
4. 合并所有集合的结果，全局按 RRF/Reranker 分数降序排列
5. 每个组件均有降级路径，单点故障不影响主流程
```

---

## 10. 向量管理操作

### 10.1 获取向量统计

```
GET /api/v1/vector-admin/stats

后端逻辑:
  1. 遍历所有 kb_documents_* 集合
  2. 统计每个集合的: 文档数、向量维度、集合大小
  3. 返回汇总统计
```

### 10.2 健康检查

```
GET /api/v1/vector-admin/health/{knowledge_id}
  对比单个知识库:
    SQL 侧: Paragraph 记录数量
    ChromaDB 侧: 集合内向量数量
    返回差异 (如 SQL=100, Chroma=95 → 缺失 5 条)

GET /api/v1/vector-admin/health/all
  对所有知识库执行上述健康检查
```

### 10.3 重建索引

```
POST /api/v1/vector-admin/rebuild/{knowledge_id}

流程:
  1. 删除 ChromaDB 中的旧集合 kb_documents_{knowledge_id}
  2. 查询该知识库下所有 SUCCESS 状态的 Document
  3. 按 50 条一批读取 Paragraph 内容
  4. 逐批调用 embedding.embed_documents() 生成向量
  5. 创建新集合，写入向量
  6. 构建新的 VectorStoreIndex

POST /api/v1/vector-admin/rebuild/all
  对所有知识库执行上述操作
```

### 10.4 测试检索

```
GET /api/v1/vector-admin/test-retrieve/{knowledge_id}?query=测试查询

后端逻辑:
  1. 使用 HybridRetriever 在指定知识库中检索
  2. 返回 Top-K 结果 (含文档名、段落内容、相似度得分)
```

---

## 11. 前端组件树与状态管理

### 11.1 组件树

```
KnowledgePage.vue                          ← 路由页面 (根据 :kbId 参数切换视图)
│
├── [kbId 为空: 知识库列表视图]
│   ├── StatsBento                          ← 4 个聚合统计卡片
│   │   ├── 知识库总数
│   │   ├── 文档总数
│   │   ├── 段落总数
│   │   └── 总字符数
│   └── KBCardGrid                         ← 知识库卡片网格
│       └── KBCard (×N)                    ← 单个知识库卡片
│           ├── 名称 / 描述 / 行业标签
│           ├── 统计: 文档数 / 段落数 / 字符数
│           └── 3 点菜单:
│               ├── 编辑信息 → KBForm
│               ├── 清空文档
│               └── 删除知识库
│
├── [kbId 不为空: 文档列表视图]
│   ├── Breadcrumb                         ← 面包屑导航 (知识库列表 > 知识库名)
│   ├── UploadBar                          ← 文件上传区域
│   │   ├── 拖拽上传 / 点击选择
│   │   └── 文件校验 (扩展名, 大小)
│   ├── DocumentFilter                     ← 过滤栏
│   │   ├── 名称搜索 (模糊)
│   │   └── 状态筛选 (下拉: 全部/PENDING/PROCESSING/SUCCESS/FAILURE)
│   ├── BatchActions                       ← 批量操作工具栏 (选中时显示)
│   │   ├── 批量删除
│   │   └── 其他批量操作
│   ├── DocumentTable                      ← 文档表格
│   │   └── DocumentRow (×N)              ← 单行文档
│   │       ├── 复选框 (批量选择)
│   │       ├── 文件图标 (按扩展名)
│   │       ├── 文档名 / 上传日期 / 文件大小
│   │       ├── Chunk 数 / 总字符数
│   │       ├── 状态圆点 (绿=SUCCESS / 黄=PROCESSING / 红=FAILURE)
│   │       └── 操作按钮:
│   │           ├── 预览 → PreviewModal
│   │           ├── 下载源文件
│   │           └── 删除
│   ├── ProgressPoll                       ← 上传进度轮询 (上传后显示)
│   │   ├── 4 阶段进度: 导入 / 拆分 / 向量化 / 分词
│   │   ├── 每 2 秒轮询文档状态
│   │   └── 完成/失败后停止
│   ├── PreviewModal                       ← 文档预览弹窗
│   │   ├── 加载段落列表 (GET paragraphs)
│   │   ├── 渲染文本内容
│   │   ├── 解析 [IMG] 标签显示图片
│   │   └── 段落序号导航
│   ├── TagManager                         ← 标签管理 (可选功能)
│   └── KBForm (Modal)                     ← 知识库创建/编辑表单
│       ├── 名称输入 (1-150 字符)
│       ├── 描述输入
│       └── 行业选择 (下拉)
```

### 11.2 Pinia Store 模式 (V2-First, V1 Fallback)

```
stores/knowledge.js

核心模式:
  所有 API 调用采用 "V2 优先, V1 回退" 策略:
    1. 先调用 api/documentsV2.js (V2 端点 prefix: /api/v1/docs/)
    2. 若 V2 返回 404 或失败:
       → 回退到 api/documents.js (V1 端点 prefix: /api/v1/documents/)
    3. V1 端点可能已失效 (后端仅注册了 /docs/ 路由，未注册 /documents/)

主要 Actions:
  ├── fetchKnowledgeList()      → GET 知识库列表
  ├── createKnowledge(data)     → POST 创建知识库
  ├── deleteKnowledge(id)       → DELETE 删除知识库
  ├── fetchDocuments(kbId, ...) → GET 文档列表
  ├── uploadDocument(formData)  → POST 上传文档
  ├── deleteDocument(id)        → DELETE 删除文档
  ├── fetchParagraphs(docId)    → GET 文档段落
  ├── fetchDocumentDetail(id)   → GET 文档详情
  └── downloadSource(docId)     → GET 下载源文件

State:
  ├── knowledgeList: []         // 知识库列表
  ├── currentKB: null           // 当前浏览的知识库
  ├── documents: []             // 文档列表
  ├── selectedDocs: []          // 已选中文档 ID (批量操作)
  ├── uploadProgress: {}        // 上传进度轮询状态
  └── loading / error states    // 加载和错误状态
```

### 11.3 API 客户端文件

| 文件 | 用途 | 状态 |
|------|------|------|
| `api/documentsV2.js` | `/api/v1/docs/` 端点 | 主用 |
| `api/documents.js` | `/api/v1/documents/` 端点 | 回退 (可能失效) |

---

## 12. API 端点汇总

### 12.1 文档与知识库 (Prefix: /api/v1/docs)

| 方法 | 路径 | 说明 | 关键行为 |
|------|------|------|----------|
| POST | `/docs/upload` | 上传文档 | multipart, 校验→存文件→异步处理 |
| GET | `/docs/list/{page}/{size}` | 文档列表 | 分页, 支持 knowledge_id/name/status 过滤 |
| GET | `/docs/detail/{document_id}` | 文档详情 | 返回完整字段 |
| GET | `/docs/paragraphs/{document_id}` | 文档段落 | 按 position 排序 |
| GET | `/docs/download-source/{document_id}` | 下载源文件 | FileResponse |
| DELETE | `/docs/{document_id}` | 删除文档 | 级联删除 Paragraph/File |
| POST | `/docs/{document_id}/reprocess` | 重新处理文档 | status=3 → 重置为 0，重新解析/分块/向量化 |
| POST | `/docs/knowledge` | 创建知识库 | name 唯一, 1-150 字符, IntegrityError 防竞态 |
| GET | `/docs/knowledge/list` | 知识库列表 | 含 document/paragraph 聚合统计 |
| DELETE | `/docs/knowledge/{knowledge_id}` | 删除知识库 | 级联删 Document/Paragraph/File |

### 12.2 向量管理 (Prefix: /api/v1/vector-admin)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/vector-admin/stats` | 向量存储统计 |
| GET | `/vector-admin/health/{knowledge_id}` | 单个知识库健康检查 (SQL vs ChromaDB) |
| GET | `/vector-admin/health/all` | 所有知识库健康检查 |
| POST | `/vector-admin/rebuild/{knowledge_id}` | 重建单个知识库索引 (50/批) |
| POST | `/vector-admin/rebuild/all` | 重建所有知识库索引 |
| GET | `/vector-admin/test-retrieve/{knowledge_id}` | 测试检索 (query 参数) |

### 12.3 知识库统计 (Prefix: /api/v1)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/knowledge/stats` | 简单统计 (数量计数) |

---

## 13. 数据模型

### 13.1 Knowledge (知识库)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID (PK) | 主键，自动生成 |
| name | String(150) | 知识库名称，唯一，非空 |
| description | Text | 描述 (可选) |
| industry | String(50) | 行业分类，默认 "general" |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

关系: 一对多 → Document

### 13.2 Document (文档)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID (PK) | 主键，自动生成 |
| name | String(255) | 文档文件名 |
| knowledge_id | UUID (FK) | 所属知识库 ID |
| status | String(1) | 状态: 0/1/2/3 |
| char_length | Integer | 总字符数 (处理完成后更新) |
| error_message | Text | 错误信息 (status=3 时) |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

关系:
- 多对一 → Knowledge
- 一对多 → Paragraph
- 一对一 → File

### 13.3 Paragraph (段落/分块)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID (PK) | 主键，自动生成 |
| document_id | UUID (FK) | 所属文档 ID |
| knowledge_id | UUID (FK) | 所属知识库 ID |
| content | Text | 段落文本内容 |
| title | String(500) | 标题 (从首个 chunk 提取) |
| position | Integer | 段落序号 (从 0 开始) |

关系: 多对一 → Document

### 13.4 File (文件)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID (PK) | 主键 |
| doc_id | UUID (FK) | 关联文档 ID |
| path | String(500) | 文件物理路径 |
| size | Integer | 文件大小 (字节) |
| type | String(50) | 文件类型 |

关系: 一对一 → Document

### 13.5 Tag & DocumentTag (标签)

| 模型 | 字段 | 说明 |
|------|------|------|
| Tag | id, name, color, knowledge_id | 标签定义 |
| DocumentTag | id, document_id, tag_id | 文档-标签关联 |

---

## 14. 已知问题与限制

### 14.1 无真正的后台处理

**问题**: `process_document_async()` 名称暗示异步，但实际在 FastAPI 请求生命周期内同步执行。未使用 Celery、BackgroundTasks 或任何消息队列。

**影响**:
- 大文档处理可能超过 HTTP 超时，导致请求中断
- 用户等待时间不可控
- 服务端处理期间阻塞该 worker

**建议**: 集成 BackgroundTasks 或 Celery 实现真正的异步处理。

---

### 14.2 文档删除不清理向量

**问题**: `DELETE /docs/{document_id}` 删除 Document/Paragraph/File 记录，但不从 ChromaDB 中移除对应的向量嵌入。

**根因**: ChromaDB 没有维护"向量 ID → Document ID"的映射关系，无法精确删除单个文档的向量。

**影响**:
- 向量数据持续累积，存储膨胀
- 已删除文档的内容仍可能被检索到
- 健康检查 (health/) 可发现差异但无法自动修复

**建议**: 在索引构建时存储文档 ID 到 ChromaDB metadata，删除时按 metadata 过滤删除。

---

### 14.3 知识库删除不清理向量集合

**问题**: `DELETE /docs/knowledge/{knowledge_id}` 删除 Knowledge 及其关联数据，但不删除 ChromaDB 中的 `kb_documents_{knowledge_id}` 集合。

**影响**:
- 大量孤立集合占用磁盘空间
- 系统运行时间长后 ChromaDB 可能包含大量无效集合

**建议**: 删除知识库时同步调用 `chroma_client.delete_collection()`。

---

### 14.4 ~~重复分块可能导致段落与向量不一致~~ ✅ 已修复 (2026-06-10)

**问题**: 文档处理流程中发生了两次分块:
1. `DocumentProcessor.split_documents()` -- 结果写入 Paragraph 表
2. `IndexBuilder.build_index_from_docs()` -- 对原始文档再次拆分后向量化

**修复**: `process_document_async()` 改为直接调用 `builder.build_index(nodes)`，使用与 Paragraph 表相同的分块结果。`build_index_from_docs()` 作为其他入口的安全网，内部通过 `processor.split_documents()` 获得 IMG 保护。

---

### 14.5 缺少任务状态端点

**问题**: 前端 `ProgressPoll` 组件需要轮询文档处理进度，但后端未提供 `/docs/task-status/{document_id}` 端点。

**影响**:
- 前端进度轮询可能使用 `/docs/detail/{document_id}` 的 `status` 字段作为替代
- 无法获取细粒度的处理阶段信息（导入/拆分/向量化/分词）

**建议**: 实现专门的 task-status 端点，返回阶段化进度信息。

---

### 14.6 V1 API 路由可能已失效

**问题**: 前端 `stores/knowledge.js` 实现 V2-first 回退模式，但后端仅在 `api/documents.py` 注册了 `/api/v1/docs/` 前缀的路由。未发现 `/api/v1/documents/` 路由注册。

**影响**:
- V1 fallback 路径永久返回 404
- 前端已优雅降级，但回退逻辑冗余

**建议**: 确认 V1 路由状态，若已废弃则清理前端回退逻辑。

---

### 14.7 上传大小限制硬编码

**问题**: `validate_upload()` 中 10MB 上限为硬编码常量。

**影响**: 无法按知识库或用户角色灵活调整。

**建议**: 将限制值移入行业配置或环境变量。

---

## 15. 关键文件索引

### 15.1 前端

| 文件路径 | 说明 |
|----------|------|
| `src/views/KnowledgePage.vue` | 知识库管理主页面，按路由参数切换列表/文档视图 |
| `src/components/knowledge/KBCardGrid.vue` | 知识库卡片网格容器 |
| `src/components/knowledge/KBCard.vue` | 单个知识库卡片 (3 点菜单) |
| `src/components/knowledge/KBForm.vue` | 知识库创建/编辑表单弹窗 |
| `src/components/knowledge/UploadBar.vue` | 文件上传组件 (拖拽 + 点击) |
| `src/components/knowledge/DocumentTable.vue` | 文档表格 (含批量选择) |
| `src/components/knowledge/DocumentRow.vue` | 单行文档展示与操作 |
| `src/components/knowledge/DocumentFilter.vue` | 文档过滤栏 (名称 + 状态) |
| `src/components/knowledge/BatchActions.vue` | 批量操作工具栏 |
| `src/components/knowledge/PreviewModal.vue` | 文档预览弹窗 (含图片渲染) |
| `src/components/knowledge/ProgressPoll.vue` | 上传进度轮询 (4 阶段) |
| `src/components/knowledge/TagManager.vue` | 标签管理组件 |
| `src/components/knowledge/StatsBento.vue` | 统计卡片面板 (4 卡片) |
| `src/stores/knowledge.js` | Pinia 状态管理 (V2-first, V1 fallback) |
| `src/api/documentsV2.js` | V2 API 客户端 (主用) |
| `src/api/documents.js` | V1 API 客户端 (回退) |

### 15.2 后端

| 文件路径 | 说明 |
|----------|------|
| `backend/app/api/documents.py` | 文档与知识库路由 (`/api/v1/docs`) |
| `backend/app/api/vector_admin.py` | 向量管理路由 (`/api/v1/vector-admin`) |
| `backend/app/api/knowledge.py` | 知识库统计路由 (`/api/v1/knowledge`) |
| `backend/app/models/document.py` | ORM 模型: Knowledge, Document, Paragraph, File, Tag |
| `backend/app/rag/document_processor.py` | 文档解析与分块 (PDF/DOCX/TXT/MD) |
| `backend/app/rag/index_builder.py` | 向量索引构建器 (VectorStoreIndex) |
| `backend/app/rag/retriever.py` | ChromaDirectRetriever (向量检索) |
| `backend/app/rag/reranker.py` | Reranker 重排序 (bge-reranker-v2-m3 cross-encoder) |
| `backend/app/rag/query_rewriter.py` | LLM Query 改写 |
| `backend/app/agents/graph_rag.py` | LangGraph 检索编排 (BM25 + RRF + Reranker) |
| `backend/app/core/vector_store.py` | ChromaDB 连接管理 (PersistentClient) |
| `backend/app/core/embedding.py` | 嵌入模型加载 (bge-small-zh-v1.5) |
| `backend/app/core/settings.py` | 行业配置 (chunk_size, overlap 等) |

---

> **文档版本**: 1.1
> **对应分支**: main
> **最后更新**: 2026-06-11
> **代码基准提交**: 36c9540
