"""LLM-as-Judge: 评判生成的 SQL 是否与预期等价。"""
import json
from typing import Dict, List, NamedTuple, Optional

from eval.judge_utils import get_llm, parse_judge_response


class JudgeResult(NamedTuple):
    verdict: str    # "equivalent" | "different" | "uncertain"
    score: int      # 0-100，-1 表示 Judge 调用失败
    table_match: bool
    reason: str


SQL_JUDGE_PROMPT = """你是 SQL 语义等价性评判专家。

请判断「生成的 SQL」在语义上是否等价于「预期 SQL」。
语义等价 = 在相同数据上执行会得到相同结果（允许格式差异、LIMIT 差异、列别名差异）。

## 用户问题
{user_question}

## 预期 SQL（正确答案）
{expected_sql}

## 预期使用表
{expected_tables}

## 生成的 SQL
{generated_sql}

## 执行结果（前 3 行）
{execution_results}

## 输出格式（严格 JSON）
{{
  "verdict": "equivalent 或 different 或 uncertain",
  "score": 0-100,
  "table_match": true或false,
  "reason": "一句话评判理由"
}}

评判标准：
- equivalent: 语义完全等价，差异仅限于格式、LIMIT、列顺序等
- different: 语义不同，会产生不同的查询结果
- uncertain: 无法确定（SQL 太复杂、或执行结果为空难以判断）

只输出 JSON，不要添加任何额外文字。"""


async def judge(
    question: str,
    expected_sql: str,
    expected_tables: List[str],
    generated_sql: str,
    execution_results: Optional[List[Dict]] = None,
) -> JudgeResult:
    """评判生成的 SQL 与预期 SQL 是否语义等价。

    Args:
        question: 用户原始问题
        expected_sql: 预期的正确 SQL
        expected_tables: 预期使用的表名列表
        generated_sql: 实际生成的 SQL
        execution_results: 生成 SQL 的执行结果（前 3 行），空时为 []

    Returns:
        JudgeResult(verdict, score, table_match, reason)
    """
    results_str = json.dumps(execution_results or [], ensure_ascii=False, indent=2)
    if not execution_results:
        results_str = "（执行结果为空，可能因查询条件不匹配；请基于 SQL 语句本身判断语义等价性）"

    prompt = SQL_JUDGE_PROMPT.format(
        user_question=question,
        expected_sql=expected_sql,
        expected_tables=", ".join(expected_tables),
        generated_sql=generated_sql,
        execution_results=results_str,
    )

    try:
        llm = get_llm()
        response = llm.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
    except Exception as e:
        return JudgeResult(
            verdict="uncertain",
            score=-1,
            table_match=False,
            reason=f"Judge LLM 调用失败: {e}"
        )

    parsed = parse_judge_response(content)
    if parsed is None:
        return JudgeResult(
            verdict="uncertain",
            score=-1,
            table_match=False,
            reason=f"无法解析 Judge 响应: {content[:200]}"
        )

    return JudgeResult(
        verdict=parsed.get("verdict", "uncertain"),
        score=parsed.get("score", -1),
        table_match=parsed.get("table_match", False),
        reason=parsed.get("reason", ""),
    )
