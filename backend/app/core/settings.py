"""
行业配置管理
支持不同行业的知识库优化参数
"""
from typing import Dict, Any
from dataclasses import dataclass


@dataclass
class IndustrySettings:
    """行业特定配置"""
    name: str
    display_name: str

    # 分块参数
    chunk_size: int
    chunk_overlap: int

    # Prompt 模板
    system_prompt: str

    # 检索参数
    retrieval_top_k: int
    use_bm25: bool  # 是否启用 BM25

    # 其他参数
    extra: Dict[str, Any] = None


# 预定义行业配置
INDUSTRIES: Dict[str, IndustrySettings] = {
    "general": IndustrySettings(
        name="general",
        display_name="通用知识库",
        chunk_size=500,
        chunk_overlap=100,
        system_prompt="你是一个智能知识助手，根据知识库内容回答用户问题。",
        retrieval_top_k=5,
        use_bm25=True,
    ),

    "wms": IndustrySettings(
        name="wms",
        display_name="仓库管理",
        chunk_size=800,  # WMS操作流程较长
        chunk_overlap=150,
        system_prompt="你是仓库操作助手，熟悉入库、出库、盘点、波次等流程。请用简洁准确的语言回答操作相关问题。",
        retrieval_top_k=8,
        use_bm25=True,  # 中文关键词检索重要
    ),

    "medical": IndustrySettings(
        name="medical",
        display_name="医疗健康",
        chunk_size=300,  # 医学文档碎片化
        chunk_overlap=50,
        system_prompt="你是医疗知识助手，请根据医学知识库谨慎回答问题，重要情况请建议咨询专业医生。",
        retrieval_top_k=10,
        use_bm25=True,
    ),

    "legal": IndustrySettings(
        name="legal",
        display_name="法律文档",
        chunk_size=1000,  # 法律条文较长
        chunk_overlap=200,
        system_prompt="你是法律知识助手，请根据法律条文准确回答问题。",
        retrieval_top_k=5,
        use_bm25=False,  # 法律条文向量检索更准确
    ),

    "finance": IndustrySettings(
        name="finance",
        display_name="金融财经",
        chunk_size=600,
        chunk_overlap=100,
        system_prompt="你是金融知识助手，请根据财经资料回答问题。",
        retrieval_top_k=6,
        use_bm25=True,
    ),
}


def get_industry_settings(industry_type: str) -> IndustrySettings:
    """获取行业配置"""
    return INDUSTRIES.get(industry_type, INDUSTRIES["general"])


def get_all_industries() -> Dict[str, str]:
    """获取所有行业列表"""
    return {k: v.display_name for k, v in INDUSTRIES.items()}