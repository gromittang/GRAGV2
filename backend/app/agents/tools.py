"""
Agent 工具定义
知识库检索、数据库查询等工具
"""
from langchain.tools import BaseTool
from typing import Dict, Any, Optional, Type, List
from pydantic import BaseModel


class KnowledgeSearchInput(BaseModel):
    """知识库搜索输入"""
    query: str
    knowledge_id: Optional[str] = None


class KnowledgeSearchTool(BaseTool):
    """知识库搜索工具"""

    name: str = "knowledge_search"
    description: str = "从知识库中检索相关信息。输入用户问题，返回相关文档内容。"
    args_schema: Type[BaseModel] = KnowledgeSearchInput

    def __init__(self, rag_service=None):
        super().__init__()
        self._rag_service = rag_service

    def _run(self, query: str, knowledge_id: str = None) -> str:
        """执行搜索"""
        if self._rag_service is None:
            return "知识库服务未初始化"

        try:
            result = self._rag_service.query(query, knowledge_id)
            return result.get("answer", "未找到相关信息")
        except Exception as e:
            return f"搜索失败: {e}"


class IndustryInfoInput(BaseModel):
    """行业信息输入"""
    industry_type: str


class IndustryInfoTool(BaseTool):
    """行业配置查询工具"""

    name: str = "industry_info"
    description: str = "查询行业配置信息。输入行业类型，返回该行业的配置参数。"
    args_schema: Type[BaseModel] = IndustryInfoInput

    def _run(self, industry_type: str) -> str:
        """执行查询"""
        from app.core.settings import get_industry_settings

        settings = get_industry_settings(industry_type)
        return f"""
行业: {settings.display_name}
分块大小: {settings.chunk_size}
检索数量: {settings.retrieval_top_k}
BM25启用: {settings.use_bm25}
系统提示: {settings.system_prompt[:100]}...
"""


def get_default_tools(rag_service=None) -> List[BaseTool]:
    """获取默认工具列表"""
    return [
        KnowledgeSearchTool(rag_service=rag_service),
        IndustryInfoTool(),
    ]