"""
Agent 服务入口
整合 LangChain Agent
"""
from typing import Dict, Any, List, Optional

from app.core.llm_manager import get_llm
from app.services.rag_service import get_rag_service


class AgentService:
    """Agent 智能问答服务"""

    def __init__(self, knowledge_id: str = None, llm_provider: str = None):
        self.knowledge_id = knowledge_id
        self.llm_provider = llm_provider
        self._llm = get_llm(llm_provider)
        self._memory: List[Dict] = []

    def run(self, question: str) -> Dict[str, Any]:
        """执行 Agent 查询"""
        # 获取 RAG 服务
        rag_service = get_rag_service(self.knowledge_id)

        # 先进行 RAG 检索
        rag_result = rag_service.query(question)

        # 如果 RAG 有结果，直接返回
        if rag_result.get("has_docs") and rag_result.get("answer"):
            self._memory.append({"role": "user", "content": question})
            self._memory.append({"role": "assistant", "content": rag_result["answer"]})

            return {
                "success": True,
                "answer": rag_result["answer"],
                "source": "rag",
                "tools_used": ["knowledge_search"],
                "intermediate_steps": []
            }

        # RAG 无结果，使用 LLM 直接回答
        try:
            from langchain_core.messages import HumanMessage, AIMessage

            messages = []
            for m in self._memory[-6:]:
                if m["role"] == "user":
                    messages.append(HumanMessage(content=m["content"]))
                else:
                    messages.append(AIMessage(content=m["content"]))

            messages.append(HumanMessage(content=question))

            response = self._llm.invoke(messages)
            answer = response.content

            self._memory.append({"role": "user", "content": question})
            self._memory.append({"role": "assistant", "content": answer})

            return {
                "success": True,
                "answer": answer,
                "source": "llm",
                "tools_used": [],
                "intermediate_steps": []
            }

        except Exception as e:
            return {
                "success": False,
                "answer": f"查询失败: {str(e)}",
                "error": str(e)
            }

    def clear_memory(self):
        """清空记忆"""
        self._memory = []

    def get_memory_history(self) -> List[Dict]:
        """获取记忆历史"""
        return self._memory.copy()


# 单例
_agent_service: Optional[AgentService] = None


def get_agent_service(knowledge_id: str = None, llm_provider: str = None) -> AgentService:
    """获取 Agent 服务"""
    global _agent_service
    if _agent_service is None:
        _agent_service = AgentService(knowledge_id, llm_provider)
    return _agent_service