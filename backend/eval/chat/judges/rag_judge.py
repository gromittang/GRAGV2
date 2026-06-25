"""LLM-as-Judge: RAG 回答质量评估。

评判维度（5 维，1-5 分）：
- source_accuracy (35%): 回答事实是否在检索文档中有依据
- no_hallucination (25%): 是否编造了文档中没有的内容
- relevance (20%): 回答是否直接回应了用户问题
- completeness (10%): 是否覆盖了问题的关键方面
- clarity (10%): 表达是否清晰、结构是否合理
"""
import json
from typing import Dict, List, NamedTuple, Optional

from eval.judge_utils import get_llm, parse_judge_response


class RAGJudgeResult(NamedTuple):
    verdict: str         # "pass" | "fail" | "uncertain"
    overall_score: float  # 1-5 加权总分
    source_accuracy: int  # 1-5
    no_hallucination: int
    relevance: int
    completeness: int
    clarity: int
    reason: str


RAG_JUDGE_PROMPT = """你是 RAG（检索增强生成）质量评估专家。请对以下问答系统回答进行评分。

## 评估标准

请从以下 5 个维度评分（1-5 分，5=优秀）：

1. **来源准确性 (source_accuracy, 权重 35%)**：回答中的事实是否都能在检索文档中找到依据？如果有无法验证的陈述，应扣分。
2. **无幻觉 (no_hallucination, 权重 25%)**：是否编造了检索文档中没有的内容？注意区分"合理推断"和"凭空编造"。
3. **相关性 (relevance, 权重 20%)**：回答是否直接回应了用户问题？有没有答非所问或偏离主题？
4. **完整性 (completeness, 权重 10%)**：是否覆盖了问题的关键方面？检索文档中的重要信息是否被遗漏？
5. **清晰度 (clarity, 权重 10%)**：表达是否通顺、结构是否清晰、是否易于理解？

综合评分 = source_accuracy×0.35 + no_hallucination×0.25 + relevance×0.20 + completeness×0.10 + clarity×0.10

## 判定规则
- overall_score >= 3.5 → verdict: "pass"
- overall_score >= 2.5 → verdict: "uncertain"
- overall_score < 2.5 → verdict: "fail"

## 用户问题
{user_question}

## 检索到的知识库文档
{retrieved_context}

## 检索来源信息
{retrieved_sources}

## 系统回答
{generated_answer}

## 输出格式（严格 JSON）
{{
  "source_accuracy": 4,
  "no_hallucination": 5,
  "relevance": 4,
  "completeness": 3,
  "clarity": 4,
  "overall_score": 4.05,
  "verdict": "pass",
  "reason": "一句话总结评判理由"
}}

只输出 JSON，不要添加任何额外文字。"""


async def judge_rag_quality(
    question: str,
    retrieved_context: str,
    answer: str,
    sources: Optional[List[Dict]] = None,
) -> RAGJudgeResult:
    """评判 RAG 回答质量。

    Args:
        question: 用户原始问题
        retrieved_context: 检索到的文档内容（完整文本）
        answer: 系统生成的回答
        sources: 检索来源元数据列表

    Returns:
        RAGJudgeResult(verdict, overall_score, source_accuracy, ...)
    """
    # 截断 context 避免超出 LLM token 限制（取前 8000 字符）
    truncated_context = retrieved_context[:8000] if len(retrieved_context) > 8000 else retrieved_context

    sources_str = json.dumps([
        {"name": s.get("document_name", ""), "score": s.get("score", 0)}
        for s in (sources or [])
    ], ensure_ascii=False, indent=2)

    prompt = RAG_JUDGE_PROMPT.format(
        user_question=question,
        retrieved_context=truncated_context,
        retrieved_sources=sources_str,
        generated_answer=answer,
    )

    try:
        llm = get_llm()
        response = llm.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
    except Exception as e:
        return RAGJudgeResult(
            verdict="uncertain", overall_score=-1,
            source_accuracy=-1, no_hallucination=-1,
            relevance=-1, completeness=-1, clarity=-1,
            reason=f"Judge LLM 调用失败: {e}"
        )

    parsed = parse_judge_response(content)
    if parsed is None:
        return RAGJudgeResult(
            verdict="uncertain", overall_score=-1,
            source_accuracy=-1, no_hallucination=-1,
            relevance=-1, completeness=-1, clarity=-1,
            reason=f"无法解析 Judge 响应: {content[:200]}"
        )

    return RAGJudgeResult(
        verdict=parsed.get("verdict", "uncertain"),
        overall_score=parsed.get("overall_score", 0),
        source_accuracy=parsed.get("source_accuracy", -1),
        no_hallucination=parsed.get("no_hallucination", -1),
        relevance=parsed.get("relevance", -1),
        completeness=parsed.get("completeness", -1),
        clarity=parsed.get("clarity", -1),
        reason=parsed.get("reason", ""),
    )
