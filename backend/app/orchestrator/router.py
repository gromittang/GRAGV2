import json

from dataclasses import dataclass, field
from typing import Optional, List

from app.core.llm_manager import get_llm
from app.core.logging import get_logger


@dataclass
class RouteResult:
    intent: str        # "data_query" | "knowledge_search" | "solution_design" | "hybrid" | "clarify" | "direct_answer"
    confidence: float  # 0.0 ~ 1.0
    source: str        # "rule" | "llm" | "fallback"
    sub_intents: List[str] = field(default_factory=list)
    clarification: str = ""
    error: str = ""


class RuleEngine:
    """纯函数关键词匹配。classify() 接受可选 rules 参数用于测试注入/灰度切换。"""

    DEFAULT_RULES: dict = {
        "data_query": [
            "同比", "环比", "趋势图", "占比分布", "排名前",
            "出库单", "入库单", "拣货单", "盘点单",
            ("库存量", "商品"),
            ("订单数", "仓库"),
        ],
        "solution_design": [
            "方案设计", "PRD文档", "产品需求文档",
            "功能设计方案", "系统方案设计",
            ("需求分析", "方案"),
        ],
        "knowledge_search": [
            "SOP标准", "操作流程", "操作手册",
            "管理制度", "管理办法", "规范文件",
            "安全规定", "合规要求",
        ],
        "direct_answer": [
            "几点上班", "联系方式", "系统怎么登录",
        ],
    }

    def classify(self, question: str, rules: dict = None) -> Optional[RouteResult]:
        rules = rules if rules is not None else self.DEFAULT_RULES
        lower = question.lower()
        hits: List[str] = []

        for intent, patterns in rules.items():
            for pattern in patterns:
                if isinstance(pattern, (tuple, list)):
                    if all(p.lower() in lower for p in pattern):
                        hits.append(intent)
                        break
                else:
                    if pattern.lower() in lower:
                        hits.append(intent)
                        break

        if len(hits) == 1:
            intent = hits[0]
            confidence = 1.0 if intent == "direct_answer" else 0.95
            return RouteResult(intent=intent, confidence=confidence, source="rule")

        return None


class MiniLLMRouter:
    """调用 DeepSeek API 做意图分类。llm 参数用于测试注入 mock。"""

    PROMPT = (
        "你是意图分类器。根据用户输入选择：\n"
        "1. data_query — 查询数据库、统计指标、业务数据\n"
        "2. knowledge_search — 查找文档、规范、SOP、操作流程\n"
        "3. solution_design — 设计方案、写PRD、需求分析\n"
        "4. hybrid — 同时需要查文档+查数据\n"
        "\n"
        "示例：\n"
        '"上月出库总量" → {"intent":"data_query","confidence":0.95}\n'
        '"仓库安全操作规范" → {"intent":"knowledge_search","confidence":0.90}\n'
        '"帮我设计库存预警方案" → {"intent":"solution_design","confidence":0.88}\n'
        '"结合SOP分析最近库存异常" → {"intent":"hybrid","confidence":0.82}\n'
        "\n"
        '只输出JSON：{"intent":"...","confidence":0.0}\n'
        "用户输入：{question}"
    )

    ALLOWED_INTENTS = {"data_query", "knowledge_search", "solution_design", "hybrid"}
    CONFIDENCE_THRESHOLD: float = 0.6

    def __init__(self, llm=None):
        self._llm = llm
        self._log = get_logger("orchestrator.router.llm")

    async def classify(self, question: str) -> RouteResult:
        llm = self._llm if self._llm is not None else get_llm()
        prompt = self.PROMPT.replace("{question}", question)

        try:
            raw = await llm.ainvoke(prompt)
            data = json.loads(raw.strip())
            intent = data.get("intent", "clarify")
            confidence = float(data.get("confidence", 0.0))

            if intent not in self.ALLOWED_INTENTS:
                return RouteResult(
                    intent="clarify", confidence=confidence,
                    source="fallback",
                    error=f"LLM returned unknown intent: {intent}"
                )

            if confidence < self.CONFIDENCE_THRESHOLD:
                return RouteResult(
                    intent="clarify", confidence=confidence,
                    source="fallback",
                    clarification="您想查询业务数据还是查找相关文档？"
                )

            return RouteResult(intent=intent, confidence=confidence, source="llm")

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            self._log.warning("LLM response parse error: {}", str(e)[:100])
            return RouteResult(
                intent="clarify", confidence=0.0, source="fallback",
                error=f"解析失败: {str(e)[:100]}"
            )
        except Exception as e:
            self._log.warning("LLM unavailable: {}", str(e)[:100])
            return RouteResult(
                intent="clarify", confidence=0.0, source="fallback",
                error=f"LLM 不可用: {str(e)[:100]}"
            )


class HybridRouter:
    """级联编排: RuleEngine → MiniLLMRouter → Fallback。不引入 LangGraph。"""

    def __init__(self, llm_router=None):
        self.rule_engine = RuleEngine()
        self.llm_router = llm_router if llm_router is not None else MiniLLMRouter()
        self._log = get_logger("orchestrator.router")

    async def route(self, question: str) -> RouteResult:
        result = self.rule_engine.classify(question)
        if result is not None:
            self._log.info("rule hit: intent={} question={:.60}", result.intent, question)
            return result

        result = await self.llm_router.classify(question)
        self._log.info(
            "llm result: intent={} confidence={:.2f} source={} question={:.60}",
            result.intent, result.confidence, result.source, question,
        )
        return result
