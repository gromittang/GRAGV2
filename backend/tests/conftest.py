"""
pytest 全局配置 — 管理重型依赖 mock + session 级清理

test_gateway.py 需要阻断 schema_manager → numpy → aiomysql 导入链。
模块级 sys.modules 注入必须在 pytest 收集期间、目标模块被 import 之前完成。
conftest.py 在 pytest 收集阶段最早执行，是正确的位置。
"""
import sys
from unittest.mock import AsyncMock, MagicMock


def pytest_configure(config):
    """pytest 启动时注入 sys.modules mock，阻断重型依赖导入链"""
    _HEAVY_DEPS = {
        "numpy": MagicMock(),
        "aiomysql": MagicMock(),
        "aiosqlite": MagicMock(),
        "chromadb": MagicMock(),
        "llama_index": MagicMock(),
        "llama_index.embeddings": MagicMock(),
        "llama_index.embeddings.huggingface": MagicMock(),
        "sentence_transformers": MagicMock(),
    }
    for _mod_name, _mock in _HEAVY_DEPS.items():
        if _mod_name not in sys.modules:
            sys.modules[_mod_name] = _mock

    _APP_STUBS = {
        "app.core.schema_manager": MagicMock(get_schema_manager=AsyncMock()),
        "app.core.db_mysql": MagicMock(get_mysql_manager=AsyncMock()),
        "app.core.embedding": MagicMock(),
        "app.core.semantic_layer_loader": MagicMock(),
        "app.core.semantic_rules": MagicMock(),
        "app.core.sql_post_process": MagicMock(),
        "app.core.domain_classifier": MagicMock(),
        "app.core.observability": MagicMock(),
        "app.models.query_history": MagicMock(save_history=AsyncMock(return_value=42)),
        "app.agents.tools_sql": MagicMock(),
        # app.agents.prompts_sql: 纯字符串常量, 不 mock — test_mcp_graph 需要真实 import
        # app.agents.query_agent: 不 mock — fallback 测试需要真实 import
    }
    for _mod_name, _mock in _APP_STUBS.items():
        if _mod_name not in sys.modules:
            sys.modules[_mod_name] = _mock


def pytest_unconfigure(config):
    """pytest 退出时清理 sys.modules 注入"""
    _CLEANUP_KEYS = [
        "numpy", "aiomysql", "aiosqlite", "chromadb",
        "llama_index", "llama_index.embeddings", "llama_index.embeddings.huggingface",
        "sentence_transformers",
        "app.core.schema_manager", "app.core.db_mysql", "app.core.embedding",
        "app.core.semantic_layer_loader", "app.core.semantic_rules",
        "app.core.sql_post_process", "app.core.domain_classifier",
        "app.core.observability",
        "app.models.query_history",
        "app.agents.tools_sql",
    ]
    for _key in _CLEANUP_KEYS:
        sys.modules.pop(_key, None)
