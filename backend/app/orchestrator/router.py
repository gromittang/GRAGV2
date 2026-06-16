from dataclasses import dataclass, field
from typing import Optional, List


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
