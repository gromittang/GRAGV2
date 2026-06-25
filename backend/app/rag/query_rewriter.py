"""
Query 关键词增强模块
用 LLM 从口语化查询中提取关键实体和操作类型，追加到原查询后一并检索。

设计原则：原查询保留全部信息不被替换；LLM 只负责提取关键词做检索增强。
"""
import httpx

from app.config import get_settings
from app.core.logging import get_logger

_settings = get_settings()
_log = get_logger("rag.rewriter")

REWRITE_PROMPT = """你是WMS仓库管理系统的查询理解助手。用户用口语化方式描述仓库操作需求，
请从问题中提取关键检索词，帮助精确定位知识库内容。

规则：
1. 保留所有数字/字母编码（货号、SKU、库位号等），如 000800、A01-02-03
2. 保留仓库专有名词（不良仓、良品仓、拣货位、存储位、暂存区等）
3. 提取核心操作类型（移库、补货、盘点、入库、出库、拣货、移位、调整等）
4. 输出空格分隔的关键词，不超过40字，不要解释

用户: {query}
关键词:"""


class QueryRewriter:
    """LLM 关键词提取 + 原查询保留"""

    def __init__(self):
        self._api_key = _settings.deepseek_api_key
        self._base_url = _settings.deepseek_base_url
        self._model = _settings.deepseek_model

    async def rewrite(self, query: str) -> tuple:
        """从查询中提取关键词，返回 "原查询 + 关键词" 组合，失败返回 (原query, None)"""
        if not _settings.use_query_rewrite:
            return query, None

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self._model,
                        "messages": [
                            {"role": "user", "content": REWRITE_PROMPT.format(query=query)}
                        ],
                        "max_tokens": 60,
                        "temperature": 0.1
                    }
                )
                response.raise_for_status()
                result = response.json()
                keywords = result["choices"][0]["message"]["content"].strip()
                usage = result.get("usage")
                if keywords:
                    # 关键改动：保留原查询，关键词追加在后面做检索增强
                    combined = f"{query} {keywords}"
                    _log.info("关键词提取: '{}' → '{}'", query, keywords)
                    return combined, usage
        except Exception as e:
            _log.warning("关键词提取失败: {}", e)

        return query, None


# 模块级单例
_query_rewriter: QueryRewriter = None


def get_query_rewriter() -> QueryRewriter:
    global _query_rewriter
    if _query_rewriter is None:
        _query_rewriter = QueryRewriter()
    return _query_rewriter
