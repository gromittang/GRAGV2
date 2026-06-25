"""NL2SQL 评估执行器。

用法:
    cd backend
    python -m eval.nl2sql.runner                     # 跑已审核用例
    python -m eval.nl2sql.runner --dry-run             # 快速模式（不调 Judge）
    python -m eval.nl2sql.runner --all                 # 含未审核用例
    python -m eval.nl2sql.runner --category inventory  # 只跑某分类
    python -m eval.nl2sql.runner --max-judge-calls 20  # 限制 Judge 调用次数
"""
import argparse
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# Windows 终端 UTF-8 支持
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 确保 backend/ 在 sys.path 上
_backend_dir = str(Path(__file__).resolve().parents[2])
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

_DATASETS_DIR = Path(__file__).resolve().parent / "datasets"
_RESULTS_DIR = Path(__file__).resolve().parent / "results"
_GOLDEN_FILE = _DATASETS_DIR / "golden_sql.json"

# 错误分类关键词
_ERROR_SAFETY = re.compile(r"禁止|DROP|DELETE|UPDATE|INSERT|TRUNCATE|ALTER|CREATE|安全")
_ERROR_NO_TABLE = re.compile(r"无法找到|表")
_ERROR_SQL_SYNTAX = re.compile(r"解析|parse|SQL|语法|syntax", re.IGNORECASE)
_ERROR_EXECUTION = re.compile(r"执行|execute|SQL执行", re.IGNORECASE)


def _classify_error(error_msg: str) -> str:
    """将错误信息归类。"""
    if not error_msg:
        return "other"
    if _ERROR_SAFETY.search(error_msg):
        return "safety_violation"
    if _ERROR_NO_TABLE.search(error_msg):
        return "no_table"
    if _ERROR_SQL_SYNTAX.search(error_msg):
        return "sql_syntax"
    if _ERROR_EXECUTION.search(error_msg):
        return "execution"
    return "other"


def _generate_hard_rules_cases() -> List[Dict]:
    """从 query_agent._HARD_RULES 动态生成 hard rules 测试用例。

    每个关键词只验证核心能力：LLM 是否用了关键词对应的主表。
    不要求所有辅助表都出现——简单查询通常只需要主表。
    预期表只取第一个（主表），验证"至少选对主表"而非"全部用到"。
    """
    from app.agents.query_agent import _HARD_RULES

    _MEANINGFUL_QUESTIONS: Dict[str, list[str]] = {
        "库存": ["查询所有库存记录", "库存量最低的商品有哪些"],
        "出库": ["查询最近的出库记录", "今天出库了多少"],
        "配送": ["查询今天的配送计划", "有哪些待配送的单据"],
        "收货": ["查询最近的收货记录", "今天验收了多少"],
        "验收": ["查询最近的验收记录", "哪些单据还没验收"],
        "拣货": ["查询拣货位设置", "今天的拣货任务有哪些"],
        "摘果": ["查询摘果拣货记录", "摘果拣货任务状态"],
        "商品信息": ["查询商品基础信息", "有哪些启用的商品"],
        "商品基础": ["查询商品基础表", "商品的包装规格有哪些"],
        "锁定": ["查询库存锁定情况", "有哪些被锁定的库存"],
    }

    cases = []
    for keyword, tables in _HARD_RULES.items():
        # 只测中文关键词，英文关键词是硬规则保留给国际用户的辅助映射
        if keyword.isascii():
            continue
        questions = _MEANINGFUL_QUESTIONS.get(keyword, [f"查询{keyword}相关数据"])
        for i, question in enumerate(questions, 1):
            cases.append({
                "id": f"hr_{keyword}_{i:02d}",
                "question": question,
                "expected_tables": tables,  # 命中任意一个即通过
                "expected_columns": [],
                "expected_sql": "",
                "expected_keywords": tables,  # 命中任意一个即通过
                "expected_insight_keywords": [],
                "hard_rule": keyword,
                "category": "hard_rules",
                "allow_equivalent": True,
                "_PENDING_REVIEW": False,
            })
    return cases


def _load_dataset(all_cases: bool = False, category: Optional[str] = None) -> List[Dict]:
    """加载 golden_sql.json + 动态 hard rules。"""
    cases = []

    # golden_sql.json
    if _GOLDEN_FILE.exists():
        with open(_GOLDEN_FILE, "r", encoding="utf-8") as f:
            golden = json.load(f)
            for c in golden:
                if not all_cases and c.get("_PENDING_REVIEW"):
                    continue
                if category and c.get("category") != category:
                    continue
                cases.append(c)

    # hard rules (动态生成)
    hr_cases = _generate_hard_rules_cases()
    for c in hr_cases:
        if category and c.get("category") != category:
            continue
        cases.append(c)

    return cases


async def _preflight_check() -> str:
    """前置检查：MySQL 连接 + Schema 预热。返回数据库名。"""
    from app.core.db_mysql import get_mysql_manager
    from app.core.schema_manager import get_schema_manager

    # MySQL 连接检查
    try:
        mysql = await get_mysql_manager()
        result = await mysql.execute("SELECT DATABASE() AS db")
        db_name = result.get("rows", [{}])[0].get("db", "unknown") if result.get("rows") else "unknown"
    except Exception as e:
        print(f"\n[错误] MySQL 不可用: {e}")
        sys.exit(1)

    # Schema 索引预热
    try:
        schema = await get_schema_manager()
        await schema.search_relevant_schema("预热查询")
    except Exception as e:
        print(f"\n[错误] Schema 索引构建失败: {e}")
        sys.exit(1)

    return db_name


async def _run_single_case(case: Dict, semaphore: asyncio.Semaphore) -> Dict[str, Any]:
    """执行单条测试用例。"""
    from app.agents.query_agent import get_query_agent

    case_id = case["id"]
    question = case["question"]
    expected_tables = set(t.lower() for t in case.get("expected_tables", []))
    expected_columns = set(c.lower() for c in case.get("expected_columns", []))
    expected_keywords = set(k.lower() for k in case.get("expected_keywords", []))
    expected_insight_kw = set(k.lower() for k in case.get("expected_insight_keywords", []))
    allow_equivalent = case.get("allow_equivalent", True)

    result = {
        "id": case_id,
        "question": question,
        "category": case.get("category", "general"),
        "hard_rule": case.get("hard_rule"),
        "verdict": "fail",
        "checks": {},
        "error_type": None,
        "confidence": None,
        "latency_ms": {},
        "generated_sql": None,
        "tables_used": None,
        "error": None,
        "judge": None,
    }

    t_start = time.time()

    async with semaphore:
        try:
            agent = await get_query_agent(session_id=f"eval_{case_id}")
            t0 = time.time()
            response = await agent.query(question)
            t_total = int((time.time() - t_start) * 1000)
        except Exception as e:
            result["error"] = str(e)
            result["error_type"] = "other"
            result["latency_ms"]["total"] = int((time.time() - t_start) * 1000)
            return result

    result["latency_ms"]["total"] = t_total

    # 记录基本信息
    result["confidence"] = response.get("confidence")
    result["tables_used"] = [t.lower() for t in response.get("tables_used", [])]

    if not response.get("success"):
        result["error"] = response.get("error", "未知错误")
        result["error_type"] = _classify_error(result["error"])
        result["generated_sql"] = response.get("sql")
        result["verdict"] = "fail"
        return result

    generated_sql = response.get("sql", "") or ""
    result["generated_sql"] = generated_sql
    generated_sql_lower = generated_sql.lower()

    # --- 第 1 层：表名检查 ---
    tables_used_set = set(result["tables_used"])
    if expected_tables:
        is_hard_rules = case.get("category") == "hard_rules"
        if is_hard_rules:
            # hard rules: 只要命中任意一个强制表即通过
            table_match = not expected_tables.isdisjoint(tables_used_set)
        else:
            table_match = expected_tables.issubset(tables_used_set)
    else:
        table_match = True
    result["checks"]["table_match"] = table_match

    # --- 第 2 层：关键词检查 ---
    if expected_keywords:
        is_hard_rules = case.get("category") == "hard_rules"
        if is_hard_rules:
            keyword_match = any(kw in generated_sql_lower for kw in expected_keywords)
        else:
            keyword_match = all(kw in generated_sql_lower for kw in expected_keywords)
    else:
        keyword_match = True
    result["checks"]["keyword_match"] = keyword_match

    # --- 第 3 层：字段名检查 ---
    if expected_columns:
        col_match = all(col in generated_sql_lower for col in expected_columns)
        result["checks"]["column_match"] = col_match
    else:
        result["checks"]["column_match"] = None

    # --- 第 4 层：LLM Judge ---
    if (not table_match or not keyword_match) and allow_equivalent:
        from eval.nl2sql.judges.sql_judge import judge

        expected_sql = case.get("expected_sql", "")
        exec_results = response.get("results", [])[:3]
        try:
            judge_result = await judge(
                question=question,
                expected_sql=expected_sql,
                expected_tables=list(expected_tables),
                generated_sql=generated_sql,
                execution_results=exec_results,
            )
            result["judge"] = {
                "verdict": judge_result.verdict,
                "score": judge_result.score,
                "table_match": judge_result.table_match,
                "reason": judge_result.reason,
            }
            if judge_result.verdict == "equivalent":
                result["verdict"] = "pass"
            elif judge_result.verdict == "uncertain":
                result["verdict"] = "uncertain"
            else:
                result["verdict"] = "fail"
        except Exception as e:
            result["judge"] = {"verdict": "uncertain", "score": -1, "reason": str(e)}
            result["verdict"] = "uncertain"
    else:
        result["verdict"] = "pass" if (table_match and keyword_match) else "fail"

    # --- Insight 基础检查 ---
    insight = response.get("insight", {})
    insight_checks = {
        "has_summary": bool(insight.get("summary")),
        "has_insights": bool(insight.get("insights")),
        "has_follow_ups": bool(insight.get("follow_ups")),
    }
    if expected_insight_kw and insight.get("summary"):
        summary_lower = insight["summary"].lower()
        insight_checks["keyword_hits"] = sum(1 for kw in expected_insight_kw if kw in summary_lower)
        insight_checks["keyword_total"] = len(expected_insight_kw)
    result["checks"]["insight"] = insight_checks

    return result


async def run_eval(
    all_cases: bool = False,
    category: Optional[str] = None,
    dry_run: bool = False,
    max_judge_calls: Optional[int] = None,
    concurrency: int = 3,
) -> List[Dict]:
    """主评估流程。"""
    # 前置检查
    db_name = await _preflight_check()
    print(f"数据库: {db_name}")
    print(f"模式: {'dry-run (不调 Judge)' if dry_run else '完整评估'}")

    # 加载数据集
    cases = _load_dataset(all_cases=all_cases, category=category)
    if not cases:
        print("[错误] 没有可用用例。")
        sys.exit(1)

    reviewed = sum(1 for c in cases if not c.get("_PENDING_REVIEW"))
    pending = sum(1 for c in cases if c.get("_PENDING_REVIEW"))
    print(f"用例: {len(cases)} 条 (已审核 {reviewed}, 待审核 {pending})")

    # 执行
    semaphore = asyncio.Semaphore(concurrency)
    judge_count = 0

    if dry_run:
        # dry-run: 不调 Judge，传 allow_equivalent=False 跳过 LLM 调用
        for case in cases:
            case["allow_equivalent"] = False

    if max_judge_calls is not None and max_judge_calls > 0:
        # 包装 judge 计数逻辑
        async def _run_with_limit(case, sem):
            nonlocal judge_count
            orig = case.get("allow_equivalent", True)
            if judge_count >= max_judge_calls and orig:
                case = dict(case)
                case["allow_equivalent"] = False
            result = await _run_single_case(case, sem)
            if result.get("judge"):
                judge_count += 1
            return result

        tasks = [_run_with_limit(case, semaphore) for case in cases]
    else:
        tasks = [_run_single_case(case, semaphore) for case in cases]

    print(f"\n运行中 (并发={concurrency})...\n")
    results = await asyncio.gather(*tasks)

    return results


def main():
    parser = argparse.ArgumentParser(description="NL2SQL Evals Runner")
    parser.add_argument("--all", dest="all_cases", action="store_true",
                        help="包含未审核用例")
    parser.add_argument("--category", type=str, default=None,
                        help="只跑指定分类 (inventory/outbound/hard_rules/...)")
    parser.add_argument("--dry-run", action="store_true",
                        help="快速模式：跳过 LLM Judge 调用")
    parser.add_argument("--max-judge-calls", type=int, default=None,
                        help="限制 Judge 调用次数上限")
    parser.add_argument("--concurrency", type=int, default=3,
                        help="并发数（默认 3）")
    parser.add_argument("--json-output", type=str, default=None,
                        help="JSON 报告输出路径（默认 results/ 目录）")
    args = parser.parse_args()

    results = asyncio.run(run_eval(
        all_cases=args.all_cases,
        category=args.category,
        dry_run=args.dry_run,
        max_judge_calls=args.max_judge_calls,
        concurrency=args.concurrency,
    ))

    # 生成报告
    from eval.nl2sql.reporter import print_summary, write_json_report

    print_summary(results)
    json_path = args.json_output or str(
        _RESULTS_DIR / f"{time.strftime('%Y-%m-%d-%H%M%S')}.json"
    )
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    write_json_report(results, json_path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
