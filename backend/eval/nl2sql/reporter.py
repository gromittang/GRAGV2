"""NL2SQL Eval 报告输出：终端摘要 + JSON 详情。"""
import json
import sys
import time
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List

# Windows 终端 UTF-8 支持
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ANSI 颜色
_GREEN = "\033[92m"
_RED = "\033[91m"
_YELLOW = "\033[93m"
_CYAN = "\033[96m"
_RESET = "\033[0m"
_BOLD = "\033[1m"


def _c(text: str, color: str) -> str:
    return f"{color}{text}{_RESET}"


def print_summary(results: List[Dict]) -> None:
    """打印终端摘要报告。"""
    total = len(results)
    passes = [r for r in results if r["verdict"] == "pass"]
    fails = [r for r in results if r["verdict"] == "fail"]
    uncertain = [r for r in results if r["verdict"] == "uncertain"]
    pass_rate = len(passes) / total * 100 if total else 0

    print("\n" + "=" * 60)
    print(_c(f"NL2SQL Eval Report — {datetime.now().strftime('%Y-%m-%d %H:%M')}", _BOLD))
    print("=" * 60)
    print(f"总用例: {total}  |  "
          f"{_c(f'✓ 通过: {len(passes)}', _GREEN)}  |  "
          f"{_c(f'✗ 失败: {len(fails)}', _RED)}  |  "
          f"{_c(f'? 不确定: {len(uncertain)}', _YELLOW)}  |  "
          f"通过率: {pass_rate:.1f}%")

    # 分类明细
    by_category = defaultdict(lambda: {"total": 0, "pass": 0, "fail": 0, "uncertain": 0})
    for r in results:
        cat = r.get("category", "general")
        by_category[cat]["total"] += 1
        by_category[cat][r["verdict"]] += 1

    print(f"\n{_c('分类明细:', _BOLD)}")
    for cat, stats in sorted(by_category.items()):
        pct = stats["pass"] / stats["total"] * 100 if stats["total"] else 0
        icon = _c("✓", _GREEN) if stats["fail"] == 0 and stats["uncertain"] == 0 else _c("✗", _RED)
        parts = [f"{icon} {cat}: {stats['pass']}/{stats['total']} ({pct:.0f}%)"]
        if stats["fail"]:
            parts.append(_c(f"{stats['fail']} failed", _RED))
        if stats["uncertain"]:
            parts.append(_c(f"{stats['uncertain']} uncertain", _YELLOW))
        print("  " + ", ".join(parts))

    # Hard Rules
    hr_results = [r for r in results if r.get("hard_rule")]
    if hr_results:
        print(f"\n{_c('Hard Rules:', _BOLD)}")
        by_rule = defaultdict(lambda: {"total": 0, "tables_ok": 0})
        for r in hr_results:
            rule = r.get("hard_rule", "unknown")
            by_rule[rule]["total"] += 1
            if r["checks"].get("table_match"):
                by_rule[rule]["tables_ok"] += 1

        for rule, stats in by_rule.items():
            ok = stats["tables_ok"] == stats["total"]
            icon = _c("✓", _GREEN) if ok else _c("✗", _RED)
            print(f"  {icon} {rule}: {stats['tables_ok']}/{stats['total']} 表匹配正确")

    # 指标统计
    valid = [r for r in results if r.get("confidence") is not None]
    avg_conf = sum(r["confidence"] for r in valid) / len(valid) if valid else 0
    conf_ok = sum(1 for r in valid if r["confidence"] >= 0.6)
    table_ok = sum(1 for r in results if r["checks"].get("table_match", False))
    sql_success = sum(1 for r in results if r.get("generated_sql") and r.get("verdict") != "fail")

    print(f"\n{_c('指标:', _BOLD)}")
    print(f"  SQL 生成成功率: {sql_success}/{total} ({sql_success/total*100:.1f}%)")
    print(f"  表匹配准确率:   {table_ok}/{total} ({table_ok/total*100:.1f}%)")
    print(f"  LLM 平均置信度: {avg_conf:.2f} ({conf_ok}/{len(valid)} >= 0.6)")

    # 耗时
    latencies = [r.get("latency_ms", {}).get("total", 0) for r in results]
    if latencies:
        avg_ms = sum(latencies) / len(latencies)
        print(f"  平均端到端耗时: {avg_ms/1000:.1f}s")

    # 错误分类
    error_types = defaultdict(int)
    for r in results:
        et = r.get("error_type")
        if et:
            error_types[et] += 1
    if error_types:
        print(f"\n{_c('错误分布:', _BOLD)}")
        for et, count in sorted(error_types.items(), key=lambda x: -x[1]):
            print(f"  {et}: {count}")

    # Insight
    insight_total = sum(1 for r in results if r["checks"].get("insight"))
    insight_ok = sum(1 for r in results
                     if r["checks"].get("insight", {}).get("has_summary"))
    if insight_total:
        print(f"\n{_c('Insight 检查:', _BOLD)}")
        print(f"  summary 非空: {insight_ok}/{insight_total}")

    # 需人工介入
    needs_review = [r for r in results if r["verdict"] in ("fail", "uncertain")]
    if needs_review:
        print(f"\n{_c(f'需人工介入 ({len(needs_review)} 条):', _YELLOW)}")
        for r in needs_review[:10]:
            icon = _c("✗", _RED) if r["verdict"] == "fail" else _c("?", _YELLOW)
            info = ""
            if r.get("judge"):
                info = f" [Judge: {r['judge']['verdict']}, {r['judge']['reason'][:60]}]"
            elif r.get("error"):
                info = f" [Error: {r['error'][:80]}]"
            else:
                tc = r.get("checks", {})
                info = f" [表匹配={tc.get('table_match')}, 关键词={tc.get('keyword_match')}]"
            print(f"  {icon} {r['id']}: {r['question'][:60]}{info}")
        if len(needs_review) > 10:
            print(f"  ... 还有 {len(needs_review) - 10} 条")

    print("\n" + "=" * 60)


def write_json_report(results: List[Dict], output_path: str, dry_run: bool = False) -> None:
    """写入 JSON 详情报告。"""
    total = len(results)
    passes = sum(1 for r in results if r["verdict"] == "pass")
    fails = sum(1 for r in results if r["verdict"] == "fail")
    uncertain = sum(1 for r in results if r["verdict"] == "uncertain")

    valid = [r for r in results if r.get("confidence") is not None]
    avg_conf = sum(r["confidence"] for r in valid) / len(valid) if valid else 0

    latencies = [r.get("latency_ms", {}).get("total", 0) for r in results]
    avg_latency = sum(latencies) / len(latencies) if latencies else 0

    report = {
        "run_id": datetime.now().strftime("%Y-%m-%d-%H%M%S"),
        "timestamp": datetime.now().isoformat(),
        "mode": "dry-run" if dry_run else "full",
        "summary": {
            "total": total,
            "pass": passes,
            "fail": fails,
            "uncertain": uncertain,
            "pass_rate": round(passes / total * 100, 1) if total else 0,
            "avg_confidence": round(avg_conf, 3),
            "avg_latency_ms": round(avg_latency, 0),
        },
        "cases": results,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)

    print(f"JSON 报告已保存: {output_path}")
