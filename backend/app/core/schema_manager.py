"""
Schema Manager
加载Schema元数据并构建Embedding索引，支持语义搜索
"""
from typing import Dict, List, Optional, Any
import json
import numpy as np

from app.core.db_mysql import get_mysql_manager
from app.core.embedding import get_default_embedding
from app.core.semantic_layer_loader import get_essential_columns, get_join_keys
from app.core.logging import get_logger

_log = get_logger("core.schema")


class SchemaManager:
    """Schema加载与Embedding索引管理"""

    def __init__(self):
        """初始化Schema管理器"""
        self._schema_cache: Dict[str, Any] = {}
        self._schema_texts: List[str] = []
        self._schema_embeddings: List[np.ndarray] = []
        self._initialized: bool = False

    async def load_schema_from_db(self) -> Dict[str, Any]:
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
                remark = col.get('remark', '')
                remark_str = f" [枚举: {remark}]" if remark else ""
                col_text = f"字段: {table_name}.{col['column_name']} ({col.get('display_name', '')}) 类型:{col.get('data_type', '')} - {col.get('description', '')}{remark_str}"
                texts.append(col_text)

        return texts

    async def build_embedding_index(self) -> None:
        """构建Embedding索引"""
        try:
            if not self._schema_cache:
                await self.load_schema_from_db()

            if not self._schema_cache:
                _log.warning("Schema为空，无法构建索引")
                return

            self._schema_texts = self._build_schema_texts()

            # 使用现有embedding模型
            embedding_model = get_default_embedding()
            self._schema_embeddings = embedding_model.get_text_embedding_batch(self._schema_texts)

            self._initialized = True
            _log.info("索引构建完成: {} 条", len(self._schema_texts))
        except Exception as e:
            _log.error("索引构建失败: {}", e)
            self._initialized = False

    async def search_relevant_schema(self, query: str, top_k: int = 5) -> Dict[str, Any]:
        """语义搜索相关Schema"""
        if not self._initialized:
            await self.build_embedding_index()

        # 计算query embedding
        embedding_model = get_default_embedding()
        query_embedding = np.array(embedding_model.get_text_embedding(query))

        # 计算相似度（余弦相似度）
        similarities = []
        for i, emb in enumerate(self._schema_embeddings):
            emb_array = np.array(emb)
            sim = np.dot(query_embedding, emb_array) / (np.linalg.norm(query_embedding) * np.linalg.norm(emb_array) + 1e-8)
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

    async def search_relevant_schema_filtered(
        self, query: str, table_filter: list, top_k: int = 5
    ) -> Dict[str, Any]:
        """语义搜索相关Schema，但只在 table_filter 中的表范围内搜索"""
        if not self._initialized:
            await self.build_embedding_index()

        embedding_model = get_default_embedding()
        query_embedding = np.array(embedding_model.get_text_embedding(query))

        # 只对 table_filter 中的表和字段计算相似度
        filter_set = set(table_filter)
        similarities = []
        for i, text in enumerate(self._schema_texts):
            emb = np.array(self._schema_embeddings[i])
            sim = np.dot(query_embedding, emb) / (
                np.linalg.norm(query_embedding) * np.linalg.norm(emb) + 1e-8
            )
            if text.startswith("表:"):
                table_name = text.split("(")[0].replace("表: ", "").strip()
                if table_name in filter_set:
                    similarities.append((i, sim))
            elif text.startswith("字段:"):
                parts = text.replace("字段: ", "").split(".")
                if len(parts) >= 2 and parts[0] in filter_set:
                    similarities.append((i, sim))

        similarities.sort(key=lambda x: x[1], reverse=True)
        top_indices = [x[0] for x in similarities[:top_k * 2]]

        relevant_tables = set()
        relevant_columns = []
        for idx in top_indices:
            text = self._schema_texts[idx]
            if text.startswith("表:"):
                table_name = text.split("(")[0].replace("表: ", "").strip()
                if table_name in filter_set:
                    relevant_tables.add(table_name)
            elif text.startswith("字段:"):
                parts = text.replace("字段: ", "").split(".")
                if len(parts) >= 2 and parts[0] in filter_set:
                    relevant_tables.add(parts[0])
                    relevant_columns.append(f"{parts[0]}.{parts[1].split('(')[0].strip()}")

        # 确保 filter_set 中的表至少都在 context 中（即使相似度不高）
        for t in filter_set:
            if t in self._schema_cache:
                relevant_tables.add(t)

        schema_context = {}
        for table in relevant_tables:
            if table in self._schema_cache:
                schema_context[table] = self._schema_cache[table]

        return {
            "tables": list(relevant_tables),
            "columns": relevant_columns[:top_k],
            "schema_context": schema_context,
            "schema_text": self._format_schema_context(schema_context),
        }

    def _format_schema_context(self, schema: Dict[str, Any]) -> str:
        """格式化schema为Prompt用的文本，仅输出 Key columns（字段白名单模式）"""
        lines = []
        for table_name, info in schema.items():
            whitelist = get_essential_columns(table_name)
            join_keys = get_join_keys(table_name)
            allowed = set(whitelist) | set(join_keys) if whitelist else set()

            lines.append(f"\n表 {table_name} ({info.get('display_name', '')}):")
            for col in info.get("columns", []):
                col_name = col["column_name"]
                # 有白名单时只输出白名单+JOIN键；无白名单时回退全部字段
                if allowed and col_name not in allowed:
                    continue
                remark = col.get("remark", "")
                remark_str = f" [枚举: {remark}]" if remark else ""
                lines.append(
                    f"  - {col_name} ({col.get('display_name', '')}): "
                    f"{col.get('data_type', '')} - {col.get('description', '')}{remark_str}"
                )
        return "\n".join(lines)

    def get_tables_schema_text(self, table_names: list) -> str:
        """获取指定表列表的格式化 schema 文本（供外部强制注入优先表）"""
        schema = {}
        for name in table_names:
            if name in self._schema_cache:
                schema[name] = self._schema_cache[name]
        return self._format_schema_context(schema)

    async def refresh_index(self) -> None:
        """刷新索引"""
        self._initialized = False
        self._schema_cache = {}
        await self.build_embedding_index()

    def get_column_display_map(self) -> Dict[str, str]:
        """构建 {column_name: display_name} 全局映射（中文名优先）"""
        col_map: Dict[str, str] = {}
        for table_info in self._schema_cache.values():
            for col in table_info.get("columns", []):
                name = col["column_name"]
                display = col.get("display_name", "")
                if display and display != name and name not in col_map:
                    col_map[name] = display
        return col_map

    def get_all_tables(self) -> List[Dict[str, Any]]:
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