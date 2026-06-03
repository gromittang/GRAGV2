---
name: pm-solution-retrieval-review
description: PM方案工作室检索功能全面审查报告
type: project
---

# PM方案工作室检索功能审查报告

## 日期：2026-06-03

## 一、问题概述

用户反馈：PM方案工作室功能输入方案描述后，无法准确检索相关文档，有时不检索，有时检索无关文档。

## 二、根因分析（系统化调试）

### 2.1 数据流追踪

```
前端(PMStudioPage.vue) 
  → API(pm_solution.py:chat) 
  → Service(pm_solution_service.py:_retrieve_with_isolation) 
  → VectorStore(vector_store.py) 
  → ChromaDB 
  → Embedding(embedding.py)
```

### 2.2 发现的问题

| 问题编号 | 问题描述 | 严重程度 | 根本原因 |
|----------|---------|---------|---------|
| P1 | **无相似度阈值过滤** | 高 | 固定score=0.8，未使用ChromaDB返回的真实相似度 |
| P2 | **检索查询使用错误** | 中 | 使用session_topic而非user_input检索 |
| P3 | **n_results分配不合理** | 中 | top_k // len(collection) + 2 导致每个库取太少 |
| P4 | **无相似度排序** | 中 | 返回结果未按相似度排序 |
| P5 | **无来源去重** | 低 | 同一文档多个段落可能重复返回 |

### 2.3 证据数据

检索测试结果（查询："智能补货功能改进"）：

| 知识库 | 相似度 | 文档名 | 相关性 |
|--------|--------|--------|--------|
| WMS知识库 | 0.727 | 智能补货功能操作流程.docx | ✓ 高度相关 |
| WMS知识库 | 0.669 | 智能补货功能操作流程.docx | ✓ 相关 |
| 行业知识库 | 0.426 | 物业项目日常安全管理...docx | ✗ 不相关 |
| 预设行业知识库 | 0.435 | test_preview.txt | 部分相关 |

**结论：** 无阈值过滤时，相似度仅0.4的不相关文档也会被返回。

## 三、改进计划

### 3.1 立即修复（高优先级）

#### P1: 添加相似度阈值过滤

**修改位置：** `pm_solution_service.py:_retrieve_with_isolation()`

**修改内容：**
```python
# 原代码（问题）
all_sources.append({
    "content": text[:200] + "...",
    "score": 0.8,  # 固定值，无意义
    "metadata": {...}
})

# 改进后
SIMILARITY_THRESHOLD = 0.5  # 相似度阈值

# ChromaDB distance转相似度: similarity = 1 - distance
distance = results["distances"][0][i]
similarity = 1 - distance

if similarity >= SIMILARITY_THRESHOLD:  # 阈值过滤
    all_sources.append({
        "content": text[:200] + "...",
        "score": similarity,  # 使用真实相似度
        "metadata": {...}
    })
```

#### P2: 使用用户输入作为检索查询

**修改位置：** `pm_solution_service.py:chat_stream()`

**修改内容：**
```python
# 原代码（问题）
retrieve_query = session_topic if session_topic and len(session_topic) > len(user_input) else user_input

# 改进后：优先使用用户输入，session_topic作为补充
retrieve_query = user_input
# 如果用户输入太短（<10字符），使用session_topic补充
if len(user_input) < 10 and session_topic:
    retrieve_query = f"{user_input} {session_topic[:100]}"
```

### 3.2 短期优化（中优先级）

#### P3: 优化n_results分配

**修改内容：**
```python
# 原代码（问题）
n_results=top_k // len(active_collections) + 2

# 改进后：每个collection取足够数量，最后合并排序
n_results=min(10, top_k)  # 每个collection取10条，合并后排序取top_k
```

#### P4: 添加相似度排序

**修改内容：**
```python
# 合并所有collection结果后，按相似度排序
all_sources.sort(key=lambda x: x["score"], reverse=True)
return all_sources[:top_k]
```

### 3.3 长期改进（低优先级）

- 统一PM方案和Chat功能使用相同的LlamaIndex retriever
- 添加检索结果来源解释（显示相似度分数）
- 支持用户反馈检索结果相关性

## 四、测试计划

### 4.1 单元测试

```python
def test_similarity_threshold():
    """测试相似度阈值过滤"""
    service = PMSolutionService(knowledge_id=None)
    sources = service._retrieve_with_isolation("智能补货功能")
    
    # 所有返回的来源相似度应>=阈值
    for source in sources:
        assert source["score"] >= 0.5, f"相似度{source['score']}低于阈值"
    
    # 应返回相关文档（智能补货）
    doc_names = [s["metadata"]["document_name"] for s in sources]
    assert any("补货" in name or "WMS" in name for name in doc_names)
```

### 4.2 集成测试

测试场景：

| 场景 | 输入 | 预期结果 |
|------|------|---------|
| S1 | "智能补货功能改进" | 返回补货相关文档，相似度>=0.5 |
| S2 | "拣货位调整" | 返回拣货位相关文档 |
| S3 | "物业管理" | 返回物业相关文档（行业知识库）|
| S4 | "不限定知识库" | 检索所有知识库，返回最相关的 |

### 4.3 验收标准

- 检索结果必须相似度>=0.5
- 检索结果必须与用户输入主题相关
- 不相关文档（如物业管理文档补货查询）不应返回
- 参考来源正确显示在前端

## 五、预防机制

### 5.1 代码层面

- 添加检索质量断言：每个返回结果必须有相似度分数
- 启动时检查向量库健康状态（已实现）
- 添加检索效果日志：记录查询、相似度、返回数量

### 5.2 测试层面

- 添加自动化测试：每次提交运行检索效果测试
- 定期执行向量索引重建检查

### 5.3 文档层面

- 记录检索逻辑变更原因和效果
- 维护知识库文档类型清单

## 六、总结

**根本问题：** PM方案检索逻辑缺少相似度阈值过滤，导致不相关文档被返回。

**核心修复：** 使用ChromaDB真实相似度分数，添加0.5阈值过滤。

**预期效果：** 检索结果只返回相似度>=0.5的相关文档，提升方案质量。