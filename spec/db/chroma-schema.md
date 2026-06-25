# ChromaDB向量库

## 集合命名

- **基名**: `kb_documents`
- **知识库隔离**: `kb_documents_{knowledge_id}`（有指定KB时）
- **默认集合**: `kb_documents`（无指定KB时回退）

## 向量配置

| 参数 | 值 |
|------|------|
| 存储引擎 | PersistentClient |
| 存储路径 | data/chroma（可配置） |
| 空间度量 | cosine |
| Embedding模型 | BAAI/bge-small-zh-v1.5 |
| 向量维度 | 384 |
| Telemetry | 禁用 |

## 集合元数据

```json
{
  "hnsw:space": "cosine"
}
```

## 向量记录结构

| 字段 | 说明 |
|------|------|
| id | 段落ID (paragraph.id) |
| embedding | 384维向量 |
| document | 段落内容 (paragraph.content) |
| metadata | `{"document_id", "knowledge_id", "document_title"}` |

## 集合生命周期

| 操作 | 触发 |
|------|------|
| 创建 | get_collection() 首次调用 |
| 重建 | rebuild API / 启动修复 |
| 删除 | delete_collection() / 知识库删除 |

## 健康检查

**检查逻辑（main.py 启动时执行）：**

| 条件 | 状态 |
|------|------|
| para_count > 0 && vector_count == 0 | critical |
| para_count > 0 && vector_count < para_count × 0.8 | warning |
| 其他 | healthy |

## 启动修复

- critical 状态自动触发重建
- 加载 Embedding 模型 → encode 段落 → 写入 ChromaDB
- 覆盖模式：先 delete_collection 再 create_collection
