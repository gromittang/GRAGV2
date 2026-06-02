"""
Schema Manager
加载Schema元数据并构建Embedding索引，支持语义搜索
"""
from typing import Dict, List, Optional
import json
import numpy as np

from app.core.db_mysql import get_mysql_manager
from app.core.embedding import get_default_embedding


class SchemaManager:
    """Schema加载与Embedding索引管理"""

    _schema_cache: Dict = {}
    _schema_texts: List[str] = []  # 用于embedding的文本列表
    _schema_embeddings: List = []  # embedding向量列表
    _initialized: bool = False

    async def load_schema_from_db(self) -> Dict:
        """从数据库加载Schema"""
        mysql = await get_mysql_manager()
        self._schema_cache = await mysql.get_full_schema()
        return self._schema_cache

    def _build_schema_texts(self) -> List[str]:
        """将Schema转为文本列表用于embedding"""
        texts = []
        for table_name, table_info in self._schema_cache.items():
            # 表级文本
            table_text = f"表: {table_name} ({table_info.get('display_name', '')}) - {table_info.get('description', '')}"
            texts.append(table_text)

            # 字段级文本
            for col in table_info.get("columns", []):
                col_text = f"字段: {table_name}.{col['column_name']} ({col.get('display_name', '')}) 类型:{col.get('data_type', '')} - {col.get('description', '')}"
                texts.append(col_text)

        return texts

    async def build_embedding_index(self) -> None:
        """构建Embedding索引"""
        if not self._schema_cache:
            await self.load_schema_from_db()

        self._schema_texts = self._build_schema_texts()

        # 使用现有embedding模型
        embedding_model = get_default_embedding()
        self._schema_embeddings = embedding_model.get_text_embedding_batch(self._schema_texts)

        self._initialized = True
        print(f"[SchemaManager] 索引构建完成: {len(self._schema_texts)} 条")

    async def search_relevant_schema(self, query: str, top_k: int = 5) -> Dict:
        """语义搜索相关Schema"""
        if not self._initialized:
            await self.build_embedding_index()

        # 计算query embedding
        embedding_model = get_default_embedding()
        query_embedding = embedding_model.get_text_embedding(query)

        # 计算相似度（余弦相似度）
        similarities = []
        for i, emb in enumerate(self._schema_embeddings):
            sim = np.dot(query_embedding, emb) / (np.linalg.norm(query_embedding) * np.linalg.norm(emb) + 1e-8)
            similarities.append((i, sim))

        # 排序取top_k
        similarities.sort(key=lambda x: x[1], reverse=True)
        top_indices = [x[0] for x in similarities[:top_k * 2]]  # 多取一些

        # 提取相关表和字段
        relevant_tables = set()
        relevant_columns = []

        for idx in top_indices:
            text = self._schema_texts[idx]
            if text.startswith("表:"):
                # 提取表名
                parts = text.split("(")[0].replace("表: ", "").strip()
                relevant_tables.add(parts)
            elif text.startswith("字段:"):
                # 提取表名和字段名
                parts = text.replace("字段: ", "").split(".")
                if len(parts) >= 2:
                    table = parts[0]
                    col = parts[1].split("(")[0].strip()
                    relevant_tables.add(table)
                    relevant_columns.append(f"{table}.{col}")

        # 构建schema_context
        schema_context = {}
        for table in relevant_tables:
            if table in self._schema_cache:
                schema_context[table] = self._schema_cache[table]

        return {
            "tables": list(relevant_tables),
            "columns": relevant_columns[:top_k],
            "schema_context": schema_context,
            "schema_text": self._format_schema_context(schema_context)
        }

    def _format_schema_context(self, schema: Dict) -> str:
        """格式化schema为Prompt用的文本"""
        lines = []
        for table_name, info in schema.items():
            lines.append(f"\n表 {table_name} ({info.get('display_name', '')}):")
            for col in info.get("columns", []):
                lines.append(f"  - {col['column_name']} ({col.get('display_name', '')}): {col.get('data_type', '')} - {col.get('description', '')}")
        return "\n".join(lines)

    async def refresh_index(self) -> None:
        """刷新索引"""
        self._initialized = False
        self._schema_cache = {}
        await self.build_embedding_index()

    def get_all_tables(self) -> List[Dict]:
        """获取所有表列表"""
        return [
            {
                "name": table_name,
                "display_name": info.get("display_name", table_name),
                "columns": info.get("columns", [])
            }
            for table_name, info in self._schema_cache.items()
        ]


# 单例和锁
_schema_manager: Optional[SchemaManager] = None
_init_lock = None  # 延迟初始化


async def get_schema_manager() -> SchemaManager:
    """获取Schema管理器（单例）"""
    global _schema_manager, _init_lock

    if _schema_manager is None:
        import asyncio
        if _init_lock is None:
            _init_lock = asyncio.Lock()

        async with _init_lock:
            if _schema_manager is None:
                _schema_manager = SchemaManager()
                await _schema_manager.build_embedding_index()

    return _schema_manager