"""
Agent API路由
提供智能Agent问答接口
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict

from app.services.agent_service import get_agent_service

router = APIRouter()


class AgentRequest(BaseModel):
    question: str
    use_simple: Optional[bool] = False
    clear_memory: Optional[bool] = False


class AgentResponse(BaseModel):
    success: bool
    answer: str
    tools_used: List[str] = []
    intermediate_steps: List[Dict] = []
    source: Optional[str] = None
    mode: Optional[str] = None
    error: Optional[str] = None


@router.post("/", response_model=AgentResponse)
async def agent_query(request: AgentRequest):
    """Agent智能问答接口"""
    if not request.question:
        raise HTTPException(400, "问题不能为空")

    agent = get_agent_service()

    if request.clear_memory and hasattr(agent, 'clear_memory'):
        agent.clear_memory()

    result = agent.run(request.question)

    return AgentResponse(
        success=result.get("success", True),
        answer=result.get("answer", ""),
        tools_used=result.get("tools_used", []),
        intermediate_steps=result.get("intermediate_steps", []),
        source=result.get("source"),
        mode=result.get("mode"),
        error=result.get("error"),
    )


@router.get("/status")
async def get_agent_status():
    """获取Agent状态"""
    from app.agents.tools import get_default_tools

    tools = get_default_tools()
    tool_names = [t.name for t in tools]

    agent = get_agent_service()
    memory_size = 0
    if hasattr(agent, 'memory'):
        memory_size = len(agent.memory)

    return {
        "status": "ready",
        "tools_available": tool_names,
        "memory_size": memory_size
    }


@router.post("/clear-memory")
async def clear_agent_memory():
    """清空Agent记忆"""
    agent = get_agent_service()
    if hasattr(agent, 'clear_memory'):
        agent.clear_memory()
        return {"success": True, "message": "记忆已清空"}
    return {"success": False, "message": "Agent不支持记忆清空"}


@router.get("/tools")
async def list_available_tools():
    """列出所有可用工具"""
    from app.agents.tools import get_default_tools

    tools = get_default_tools()
    tool_info = [{"name": t.name, "description": t.description[:100]} for t in tools]

    return {"success": True, "tools": tool_info, "count": len(tool_info)}