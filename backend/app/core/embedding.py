"""
Embedding 配置
支持多种 embedding 模型
"""
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from typing import Optional
import os

from app.config import get_settings

# 设置 HuggingFace 镜像（中国地区）
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

_settings = get_settings()


def get_embedding_model(model_name: str = None, device: str = None) -> HuggingFaceEmbedding:
    """
    获取 Embedding 模型

    Args:
        model_name: 模型名称，默认从配置读取
        device: 设备 (cpu/cuda)

    Returns:
        HuggingFaceEmbedding 实例
    """
    model = model_name or _settings.embedding_model
    dev = device or _settings.embedding_device

    # 检查本地预下载模型
    local_path = os.path.join(os.path.dirname(__file__), "..", "..", "models", "bge-small-zh-v1.5")

    if os.path.exists(local_path):
        print(f"[Embedding] 使用本地模型: {local_path}")
        return HuggingFaceEmbedding(
            model_name=local_path,
            device=dev
        )

    print(f"[Embedding] 从 HuggingFace 加载: {model}")
    return HuggingFaceEmbedding(
        model_name=model,
        device=dev
    )


# 单例缓存
_embedding_instance: Optional[HuggingFaceEmbedding] = None


def get_default_embedding() -> HuggingFaceEmbedding:
    """获取默认 embedding（单例）"""
    global _embedding_instance
    if _embedding_instance is None:
        _embedding_instance = get_embedding_model()
    return _embedding_instance