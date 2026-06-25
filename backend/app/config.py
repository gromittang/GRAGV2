"""
知识库系统配置管理
支持多LLM、行业配置
"""
from pydantic_settings import BaseSettings
from functools import lru_cache
import os
from typing import Dict, Optional


def _detect_frontend_dist() -> str:
    """自动检测前端dist目录路径"""
    # 优先使用环境变量
    env_path = os.environ.get("FRONTEND_DIST_DIR", "")
    if env_path and os.path.exists(env_path):
        return env_path

    # Docker环境：工作目录是 /app，前端在 /app/frontend/vue-app/dist
    if os.environ.get("APP_ENV") == "production":
        docker_path = "/app/frontend/vue-app/dist"
        if os.path.exists(docker_path):
            return docker_path

    # 本地开发环境：从 backend/app 向上到项目根目录
    # backend/app/main.py -> backend/app -> backend -> 项目根目录
    local_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "frontend", "vue-app", "dist"
    )
    if os.path.exists(local_path):
        return local_path

    # 兜底：尝试从当前工作目录查找
    cwd_path = os.path.join(os.getcwd(), "frontend", "vue-app", "dist")
    if os.path.exists(cwd_path):
        return cwd_path

    # 返回空字符串，表示前端未构建
    return ""


def _detect_reranker_model() -> str:
    """自动检测 Reranker 模型路径"""
    # 1. 环境变量
    env_path = os.environ.get("RERANKER_MODEL_PATH", "")
    if env_path and os.path.exists(env_path):
        return env_path

    # 2. Docker 生产环境
    docker_path = "/app/models/bge-reranker-v2-m3"
    if os.environ.get("APP_ENV") == "production" and os.path.exists(docker_path):
        return docker_path

    # 3. 本地开发环境：backend/models/bge-reranker-v2-m3
    local_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "models", "bge-reranker-v2-m3"
    )
    if os.path.exists(local_path):
        return local_path

    # 4. cwd 兜底
    cwd_path = os.path.join(os.getcwd(), "models", "bge-reranker-v2-m3")
    if os.path.exists(cwd_path):
        return cwd_path

    return ""


class Settings(BaseSettings):
    """应用配置"""
    # 应用基础
    app_name: str = "知识库系统"
    app_version: str = "2.0.0"
    server_port: int = 8912
    log_level: str = "INFO"

    # 数据目录
    data_dir: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

    # 前端静态文件目录（支持环境变量覆盖）
    frontend_dist_dir: str = ""  # 空则自动检测

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

    # MySQL 配置（数据查询模块）
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = ""
    mysql_database: str = "wms"

    @property
    def mysql_connection_url(self) -> str:
        """MySQL 连接 URL"""
        return f"mysql+aiomysql://{self.mysql_user}:{self.mysql_password}@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"

    # 行业配置
    industry_type: str = "general"

    # RAG 配置
    chunk_size: int = 500
    chunk_overlap: int = 100
    retrieval_top_k: int = 5

    # 混合检索
    use_hybrid_retrieval: bool = True  # BM25 + 向量
    use_query_rewrite: bool = True  # LLM Query 改写
    use_reranker: bool = True  # Reranker 重排序
    reranker_model_path: str = ""  # 空则自动检测
    reranker_top_k_multiplier: int = 3  # 融合时取 top_k × N 候选进 Reranker

    # 相关性阈值：最高分低于此值时判定"知识库无相关内容"
    # rerank 分阈值（sigmoid 输出，0~1，推荐配置下使用）
    retrieval_relevance_threshold_rerank: float = 0.3
    # 向量分阈值（余弦相似度，集中在 0.5~0.9，reranker 不可用时使用）
    retrieval_relevance_threshold_vector: float = 0.65

    # LangGraph 迁移已完成 — use_langgraph flag 已废弃。
    # Phase 1: DataQueryGateway 内部通过 Executor 优先级决定路径，
    # 不再需要此 flag。保留注释以免后续 git blame 混淆。
    # use_langgraph: bool = False  # REMOVED in Phase 1

    # ── MCP Data Copilot (Phase 2) ──
    mcp_enabled: bool = False
    mcp_base_url: str = "http://localhost:8922"
    mcp_api_key: str = ""
    mcp_timeout: float = 60.0
    mcp_tool_cache_ttl: int = 300       # Tool 列表缓存 TTL（秒）
    mcp_health_cache_ttl: int = 30      # 健康检查缓存 TTL（秒）

    # LangFuse 可观测性
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # 会话持久化（LangGraph Checkpointer）
    checkpoint_db_path: str = ""

    @property
    def resolved_chroma_persist_dir(self) -> str:
        if self.chroma_persist_dir:
            return self.chroma_persist_dir
        return os.path.join(self.data_dir, "chroma")

    @property
    def resolved_checkpoint_db_path(self) -> str:
        if self.checkpoint_db_path:
            return self.checkpoint_db_path
        return os.path.join(self.data_dir, "checkpoints.db")

    @property
    def langfuse_enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)

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

    @property
    def resolved_frontend_dist_dir(self) -> str:
        """获取前端dist目录路径"""
        # 优先使用配置值（可能来自环境变量）
        if self.frontend_dist_dir and os.path.exists(self.frontend_dist_dir):
            return self.frontend_dist_dir
        # 自动检测
        return _detect_frontend_dist()

    @property
    def resolved_reranker_model_path(self) -> str:
        """获取 Reranker 模型路径"""
        if self.reranker_model_path and os.path.exists(self.reranker_model_path):
            return self.reranker_model_path
        return _detect_reranker_model()

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()