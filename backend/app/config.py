"""
知识库系统配置管理
支持多LLM、行业配置
"""
from pydantic_settings import BaseSettings
from functools import lru_cache
import os
from typing import Dict, Optional


class Settings(BaseSettings):
    """应用配置"""
    # 应用基础
    app_name: str = "知识库系统"
    app_version: str = "2.0.0"
    server_port: int = 8812
    log_level: str = "INFO"

    # 数据目录
    data_dir: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

    # LLM 配置
    llm_provider: str = "deepseek"  # deepseek | openai | anthropic | local

    # DeepSeek
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

    # OpenAI
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4"

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-opus-20240229"

    # Embedding
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_device: str = "cpu"

    # 数据库
    database_url: str = "sqlite+aiosqlite:///./data/kb.db"
    chroma_persist_dir: str = ""

    # 行业配置
    industry_type: str = "general"

    # RAG 配置
    chunk_size: int = 500
    chunk_overlap: int = 100
    retrieval_top_k: int = 5

    # 混合检索
    use_hybrid_retrieval: bool = True  # BM25 + 向量

    @property
    def resolved_chroma_persist_dir(self) -> str:
        if self.chroma_persist_dir:
            return self.chroma_persist_dir
        return os.path.join(self.data_dir, "chroma")

    @property
    def resolved_database_url(self) -> str:
        if "sqlite" in self.database_url and not self.database_url.startswith("sqlite"):
            # 相对路径转绝对路径
            db_path = self.database_url.split(":///")[-1]
            abs_path = os.path.join(self.data_dir, db_path.replace("./data/", ""))
            return f"sqlite+aiosqlite:///{abs_path}"
        return self.database_url

    @property
    def sqlite_connection_url(self) -> str:
        """SQLite 连接 URL（不含 aiosqlite）"""
        url = self.resolved_database_url
        if url.startswith("sqlite+aiosqlite://"):
            return url.replace("sqlite+aiosqlite://", "sqlite://")
        return url

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()