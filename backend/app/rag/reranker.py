"""
Reranker 重排序模块
使用 bge-reranker-v2-m3 cross-encoder 对候选文档精排
"""
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer
from typing import List, Optional

from app.config import get_settings
from app.core.logging import get_logger

_settings = get_settings()
_log = get_logger("rag.reranker")


class Reranker:
    """Cross-encoder 重排序器，批处理 + 降级"""

    def __init__(self, model_path: str):
        self.tokenizer = AutoTokenizer.from_pretrained(model_path)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_path)
        self.model.eval()

    @torch.no_grad()
    def rerank(self, query: str, nodes: list, top_k: int) -> list:
        """批处理：一次 forward 对所有 (query, doc) 对打分

        Args:
            query: 用户查询
            nodes: 候选节点列表（需有 .text 属性）
            top_k: 返回数量

        Returns:
            按 score 降序排列的节点列表，score 写入 node.metadata["rerank_score"]
        """
        if not nodes:
            return nodes

        pairs = [(query, node.text[:512]) for node in nodes]
        inputs = self.tokenizer(
            pairs, padding=True, truncation=True,
            max_length=512, return_tensors="pt"
        )
        logits = self.model(**inputs).logits
        scores = torch.sigmoid(logits).squeeze(-1).tolist()

        # 单值兼容
        if not isinstance(scores, list):
            scores = [scores]

        for node, score in zip(nodes, scores):
            node.metadata["rerank_score"] = float(score)

        nodes.sort(key=lambda n: n.metadata.get("rerank_score", 0), reverse=True)
        return nodes[:top_k]


# 模块级单例
_reranker: Optional[Reranker] = None
_reranker_load_attempted: bool = False


def get_reranker() -> Optional[Reranker]:
    """延迟加载单例，失败返回 None"""
    global _reranker, _reranker_load_attempted
    if _reranker_load_attempted:
        return _reranker

    _reranker_load_attempted = True
    model_path = _settings.resolved_reranker_model_path
    if not model_path:
        _log.info("未找到模型路径，重排序已禁用")
        return None

    try:
        _reranker = Reranker(model_path)
        _log.info("模型已加载: {}", model_path)
        return _reranker
    except Exception as e:
        _log.error("模型加载失败: {}", e)
        return None
