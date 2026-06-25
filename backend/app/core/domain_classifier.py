"""
Embedding-based 领域分类器
使用 bge-small-zh-v1.5 对用户问题做 embedding，与各域描述文本计算 cosine similarity。
比 LLM 分类更快、免费、可复现。
"""
from typing import Dict, Optional
import numpy as np

from app.core.embedding import get_default_embedding
from app.core.semantic_layer_loader import get_domains, get_domain_tables


class DomainClassifier:
    """Embedding-based 领域分类器"""

    def __init__(self):
        self._domains = get_domains()
        self._domain_embeddings: Dict[str, np.ndarray] = {}
        self._initialized = False

    def _ensure_initialized(self):
        if self._initialized:
            return
        embedding_model = get_default_embedding()
        for d in self._domains:
            desc = d.get("desc", "")
            if desc:
                emb = np.array(embedding_model.get_text_embedding(desc))
                self._domain_embeddings[d["name"]] = emb
        self._initialized = True

    def classify(self, question: str) -> dict:
        """返回 {'domain': str, 'confidence': float, 'domain_tables': [str]}"""
        self._ensure_initialized()

        if not self._domain_embeddings:
            return {"domain": "", "confidence": 0.0, "domain_tables": []}

        embedding_model = get_default_embedding()
        q_emb = np.array(embedding_model.get_text_embedding(question))

        best_domain = ""
        best_sim = -1.0

        for name, d_emb in self._domain_embeddings.items():
            sim = np.dot(q_emb, d_emb) / (
                np.linalg.norm(q_emb) * np.linalg.norm(d_emb) + 1e-8
            )
            if sim > best_sim:
                best_sim = sim
                best_domain = name

        domain_tables = get_domain_tables(best_domain) if best_domain else []

        return {
            "domain": best_domain,
            "confidence": round(float(best_sim), 4),
            "domain_tables": domain_tables,
        }


# 单例
_classifier: Optional[DomainClassifier] = None


def get_domain_classifier() -> DomainClassifier:
    global _classifier
    if _classifier is None:
        _classifier = DomainClassifier()
    return _classifier
