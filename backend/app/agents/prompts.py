"""
Agent Prompt 模板
"""
from langchain.prompts import PromptTemplate
from app.core.settings import get_industry_settings
from app.config import get_settings


# 默认 ReAct Prompt
REACT_PROMPT_TEMPLATE = """
你是一个智能知识助手，可以使用工具来回答问题。

可用工具:
{tool_names}

工具使用格式:
Thought: 思考下一步
Action: 工具名称
Action Input: 工具输入
Observation: 工具输出
... (重复 Thought/Action/Action Input/Observation)
Thought: 我现在知道答案了
Final Answer: 最终答案

开始!

问题: {input}
Thought: {agent_scratchpad}
"""


def get_prompt(industry_type: str = None) -> PromptTemplate:
    """
    获取行业特定的 Prompt

    Args:
        industry_type: 行业类型

    Returns:
        PromptTemplate
    """
    settings = get_industry_settings(industry_type or get_settings().industry_type)

    # 行业特定的系统提示
    system_prompt = settings.system_prompt

    template = f"""
{system_prompt}

你可以使用以下工具来帮助回答问题:
{tool_names}

工具使用格式:
Thought: 思考下一步应该做什么
Action: 工具名称
Action Input: 工具的输入参数
Observation: 工具返回的结果
... (可以多次使用工具)
Thought: 我现在知道最终答案了
Final Answer: 用简洁准确的语言回答用户问题

开始!

用户问题: {input}
{agent_scratchpad}
"""

    return PromptTemplate.from_template(template)