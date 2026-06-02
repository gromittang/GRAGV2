"""
LLM 管理
支持 DeepSeek、OpenAI、Claude 等多种 LLM
"""
from langchain_core.language_models import BaseLLM
from langchain_openai import ChatOpenAI
from typing import Optional, Dict, Any, List
from langchain_core.callbacks.manager import CallbackManagerForLLMRun
import httpx

from app.config import get_settings

_settings = get_settings()


class DeepSeekLLM(BaseLLM):
    """
    DeepSeek LLM 封装
    直接使用 httpx 调用 API
    """

    api_key: str = ""
    base_url: str = "https://api.deepseek.com/v1"
    model: str = "deepseek-chat"
    temperature: float = 0.7
    max_tokens: int = 1000

    def __init__(self, api_key: str, base_url: str, model: str, **kwargs):
        super().__init__(**kwargs)
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    def _generate(
        self,
        prompts: List[str],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> List[str]:
        """生成响应"""
        results = []
        for prompt in prompts:
            response = self._call_api(prompt)
            results.append(response)
        return results

    def _call_api(self, prompt: str) -> str:
        """调用 DeepSeek API"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens
        }

        with httpx.Client(timeout=30) as client:
            response = client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=data
            )
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"]

    def _llm_type(self) -> str:
        return "deepseek"

    @property
    def _identifying_params(self) -> Dict[str, Any]:
        return {"model": self.model, "base_url": self.base_url}


# LLM 工厂
_llm_instances: Dict[str, BaseLLM] = {}


def get_llm(provider: str = None) -> BaseLLM:
    """
    获取 LLM 实例

    Args:
        provider: LLM 提供商

    Returns:
        LLM 实例
    """
    prov = provider or _settings.llm_provider

    if prov in _llm_instances:
        return _llm_instances[prov]

    if prov == "deepseek":
        llm = DeepSeekLLM(
            api_key=_settings.deepseek_api_key,
            base_url=_settings.deepseek_base_url,
            model=_settings.deepseek_model
        )

    elif prov == "openai":
        llm = ChatOpenAI(
            api_key=_settings.openai_api_key,
            base_url=_settings.openai_base_url,
            model=_settings.openai_model
        )

    elif prov == "anthropic":
        from langchain_anthropic import ChatAnthropic
        llm = ChatAnthropic(
            api_key=_settings.anthropic_api_key,
            model=_settings.anthropic_model
        )

    else:
        raise ValueError(f"不支持的 LLM provider: {prov}")

    _llm_instances[prov] = llm
    print(f"[LLM] 初始化 {prov} LLM")
    return llm


def get_llm_providers() -> Dict[str, str]:
    """获取可用的 LLM 提供商"""
    providers = {}

    if _settings.deepseek_api_key:
        providers["deepseek"] = "DeepSeek"
    if _settings.openai_api_key:
        providers["openai"] = "OpenAI"
    if _settings.anthropic_api_key:
        providers["anthropic"] = "Claude"

    return providers