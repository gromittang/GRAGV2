"""
RAG Agent
使用 LangChain Agent 框架
"""
from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.language_models import BaseLLM
from typing import Dict, Any, List, Optional

from app.core.llm_manager import get_llm
from app.agents.tools import get_default_tools
from app.agents.prompts import get_prompt
from app.rag.retriever import create_retriever


class RAGAgent:
    """
    RAG Agent
    结合检索和推理
    """

    def __init__(
        self,
        index,
        llm_provider: str = None,
        industry_type: str = None,
        knowledge_id: str = None
    ):
        self._index = index
        self._llm_provider = llm_provider
        self._industry_type = industry_type
        self._knowledge_id = knowledge_id

        # 初始化组件
        self._llm = get_llm(llm_provider)
        self._retriever = create_retriever(index, knowledge_id, industry_type)
        self._tools = get_default_tools()
        self._prompt = get_prompt(industry_type)

        # 创建 Agent
        self._agent = create_react_agent(
            llm=self._llm,
            tools=self._tools,
            prompt=self._prompt
        )

        self._executor = AgentExecutor(
            agent=self._agent,
            tools=self._tools,
            verbose=True,
            max_iterations=5,
            handle_parsing_errors=True
        )

        # 会话记忆
        self._memory: List[Dict] = []

    def query(self, question: str) -> Dict[str, Any]:
        """
        执行查询

        Args:
            question: 用户问题

        Returns:
            包含答案和来源的字典
        """
        # 保存用户问题
        self._memory.append({"role": "user", "content": question})

        try:
            # 先检索相关文档
            from llama_index.core import QueryBundle
            query_bundle = QueryBundle(question)
            nodes = self._retriever.retrieve(query_bundle)

            # 构建上下文
            context = "\n".join([n.text for n in nodes[:3]])

            # 构建输入
            input_text = f"""
相关知识片段:
{context}

用户问题: {question}

请基于知识片段回答问题，如果知识片段中没有相关信息，请说明。
"""

            # 执行 Agent
            result = self._executor.invoke({"input": input_text})

            answer = result.get("output", "无法回答")

            # 保存回答
            self._memory.append({"role": "assistant", "content": answer})

            return {
                "answer": answer,
                "sources": [{"text": n.text[:200], "score": getattr(n, "score", 0)} for n in nodes[:3]],
                "industry": self._industry_type
            }

        except Exception as e:
            return {
                "answer": f"查询失败: {e}",
                "sources": [],
                "error": str(e)
            }

    def clear_memory(self):
        """清空记忆"""
        self._memory = []

    def get_memory_history(self) -> List[Dict]:
        """获取记忆历史"""
        return self._memory.copy()