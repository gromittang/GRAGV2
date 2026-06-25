"""Chat RAG Eval 报告输出：终端摘要 + JSON 详情。"""
import json
import sys
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

_GREEN = "\033[92m"
_RED = "\033[91m"
_YELLOW = "\033[93m"
_CYAN = "\033[96m"
_RESET = "\033[0m"
_BOLD = "\033[1m"


def _c(text: str, color: str) -> str:
    return f"{color}{text}{_RESET}"


def print_summary(results: List[Dict]) -> None:
    total = len(results)
    passes = [r for r in results if r["verdict"] == "pass"]
    fails = [r for r in results if r["verdict"] == "fail"]
    uncertain = [r for r in results if r["verdict"] == "uncertain"]
    pass_rate = len(passes) / total * 100 if total else 0

    print("\n" + "=" * 60)
    print(_c(f"Chat RAG Eval Report — {datetime.now().strftime('%Y-%m-%d %H:%M')}", _BOLD))
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

    # 检索指标
    source_ok = sum(1 for r in results if r["checks"].get("source_match", False))
    keyword_ok = sum(1 for r in results if r["checks"].get("keyword_match", False) is not False)

    print(f"\n{_c('检索指标:', _BOLD)}")
    print(f"  来源命中率: {source_ok}/{total} ({source_ok/total*100:.1f}%)")
    print(f"  关键词覆盖率: {keyword_ok}/{total} ({keyword_ok/total*100:.1f}%)")

    # best_relevance_score
    scores = [r.get("best_relevance_score", 0) for r in results if r.get("best_relevance_score")]
    if scores:
        avg_score = sum(scores) / len(scores)
        print(f"  平均关联度: {avg_score:.3f}")

    # 生成指标（仅 full 模式）
    answered = [r for r in results if r.get("answer")]
    if answered:
        judge_scores = [r["judge"]["overall_score"] for r in answered
                        if r.get("judge") and r["judge"].get("overall_score", -1) >= 0]
        if judge_scores:
            avg_os = sum(judge_scores) / len(judge_scores)
            print(f"\n{_c('生成指标 (LLM Judge):', _BOLD)}")
            print(f"  平均 Overall: {avg_os:.2f}/5")
            dims = ["source_accuracy", "no_hallucination", "relevance", "completeness", "clarity"]
            for dim in dims:
                vals = [r["judge"][dim] for r in answered
                        if r.get("judge") and r["judge"].get(dim, 0) > 0]
                if vals:
                    print(f"  {dim}: {sum(vals)/len(vals):.2f}/5")

    # 延迟
    latencies = [r.get("latency_ms", {}).get("total", 0) for r in results]
    if latencies:
        avg_ms = sum(latencies) / len(latencies)
        print(f"\n{_c('延迟:', _BOLD)}")
        print(f"  平均端到端: {avg_ms/1000:.1f}s")

    # 需人工介入
    needs_review = [r for r in results if r["verdict"] in ("fail", "uncertain")]
    if needs_review:
        print(f"\n{_c(f'需人工介入 ({len(needs_review)} 条):', _YELLOW)}")
        for r in needs_review[:10]:
            icon = _c("✗", _RED) if r["verdict"] == "fail" else _c("?", _YELLOW)
            info = ""
            if r.get("judge"):
                info = f" [Judge: {r['judge']['verdict']}, {r['judge'].get('reason', '')[:60]}]"
            elif r.get("error"):
                info = f" [Error: {r['error'][:80]}]"
            else:
                tc = r.get("checks", {})
                info = f" [来源命中={tc.get('source_match')}, 关键词={tc.get('keyword_match')}]"
            print(f"  {icon} {r['id']}: {r['question'][:60]}{info}")
        if len(needs_review) > 10:
            print(f"  ... 还有 {len(needs_review) - 10} 条")

    print("\n" + "=" * 60)


def write_json_report(results: List[Dict], output_path: str, dry_run: bool = False) -> None:
    total = len(results)
    passes = sum(1 for r in results if r["verdict"] == "pass")
    fails = sum(1 for r in results if r["verdict"] == "fail")
    uncertain = sum(1 for r in results if r["verdict"] == "uncertain")

    scores = [r.get("best_relevance_score", 0) for r in results if r.get("best_relevance_score")]
    avg_score = sum(scores) / len(scores) if scores else 0

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
            "avg_relevance_score": round(avg_score, 3),
            "avg_latency_ms": round(avg_latency, 0),
        },
        "cases": results,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)

    print(f"JSON 报告已保存: {output_path}")
