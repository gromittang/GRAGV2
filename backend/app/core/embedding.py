"""
Embedding 配置
支持多种 embedding 模型
"""
# sentence_transformers 必须在 HuggingFaceEmbedding 之前导入，
# 否则 transformers 5.x + torch 2.12 组合会导致 segfault (exit 139)
import sentence_transformers  # noqa: F401
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from typing import Optional
import os

from app.config import get_settings
from app.core.logging import get_logger

# 设置 HuggingFace 镜像（中国地区）
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

_settings = get_settings()
_log = get_logger("core.embedding")


def get_embedding_model(model_name: str = None, device: str = None) -> HuggingFaceEmbedding:
    model = model_name or _settings.embedding_model
    dev = device or _settings.embedding_device

    local_path = os.path.join(os.path.dirname(__file__), "..", "..", "models", "bge-small-zh-v1.5")

    if os.path.exists(local_path):
        _log.info("使用本地模型: {}", local_path)
        return HuggingFaceEmbedding(
            model_name=local_path,
            device=dev,
            local_files_only=True,
        )

    _log.info("从 HuggingFace 加载: {}", model)
    return HuggingFaceEmbedding(
        model_name=model,
        device=dev,
        local_files_only=True,
    )


# 单例缓存
_embedding_instance: Optional[HuggingFaceEmbedding] = None


def get_default_embedding() -> HuggingFaceEmbedding:
    """获取默认 embedding（单例）"""
    global _embedding_instance
    if _embedding_instance is None:
        _embedding_instance = get_embedding_model()
    return _embedding_instance