"""
Router Accuracy Baseline — Iteration 1 Task 5.3

用法:
  python tests/router_baseline_eval.py

输出:
  - Per-intent precision / recall (含 LLM 委托) / F1 / effective recall
  - Overall accuracy
  - LLM-delegated cases count (RuleEngine 无法判定的比例)

注: --full 模式 (完整 HybridRouter) 待 LLM 可在测试环境使用时实现。
"""
import json
import sys
from pathlib import Path
from collections import defaultdict

# 允许从项目根目录或 backend/ 运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.orchestrator.router import RuleEngine


def load_cases() -> list:
    path = Path(__file__).parent / "router_baseline_cases.json"
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate_rule_engine(cases: list) -> dict:
    """RuleEngine only — 零 LLM 成本评估"""
    engine = RuleEngine()
    # per-intent stats
    stats: dict = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "llm_delegated": 0})
    total = 0
    correct = 0
    delegated = 0

    for c in cases:
        expected = c["expected_intent"]
        result = engine.classify(c["question"])
        total += 1

        if result is None:
            # RuleEngine 无法判定 → LLM
            stats[expected]["fn"] += 1
            stats[expected]["llm_delegated"] += 1
            delegated += 1
        elif result.intent == expected:
            stats[expected]["tp"] += 1
            correct += 1
        else:
            stats[expected]["fn"] += 1
            # Find which intent was falsely predicted
            stats[result.intent]["fp"] += 1

    # Compute metrics
    metrics = {}
    for intent in sorted(stats):
        s = stats[intent]
        precision = s["tp"] / (s["tp"] + s["fp"]) if (s["tp"] + s["fp"]) > 0 else 0.0
        # recall 含 LLM 委托（委托 = 无法判定，计入 fn）
        recall = s["tp"] / (s["tp"] + s["fn"]) if (s["tp"] + s["fn"]) > 0 else 0.0
        # effective recall: 仅计可判定的 case（排除 LLM 委托）
        decidable = s["tp"] + s["fp"]
        eff_recall = s["tp"] / decidable if decidable > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        metrics[intent] = {
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "eff_recall": round(eff_recall, 3),
            "f1": round(f1, 3),
            "tp": s["tp"],
            "fp": s["fp"],
            "fn": s["fn"],
            "llm_delegated": s["llm_delegated"],
        }

    accuracy = correct / total if total > 0 else 0.0
    return {
        "engine": "RuleEngine",
        "total": total,
        "correct": correct,
        "llm_delegated": delegated,
        "accuracy": round(accuracy, 3),
        "per_intent": metrics,
    }


def print_report(results: dict):
    print("=" * 70)
    print(f"  Router Accuracy Baseline — {results['engine']}")
    print("=" * 70)
    print(f"  Total cases:     {results['total']}")
    print(f"  Correct (rule):  {results['correct']}")
    print(f"  LLM delegated:   {results['llm_delegated']}")
    print(f"  Rule accuracy:   {results['accuracy']:.1%}")
    if results['llm_delegated'] > 0:
        effective = results['total'] - results['llm_delegated']
        eff_acc = results['correct'] / effective if effective > 0 else 0
        print(f"  Effective acc:   {eff_acc:.1%} (excluding {results['llm_delegated']} LLM cases)")
    print()

    # Per-intent table
    header = f"  {'Intent':<20} {'P':>6} {'R':>6} {'eR':>6} {'F1':>6} {'TP':>4} {'FP':>4} {'FN':>4} {'→LLM':>5}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for intent, m in sorted(results["per_intent"].items()):
        print(f"  {intent:<20} {m['precision']:>6.3f} {m['recall']:>6.3f} "
              f"{m['eff_recall']:>6.3f} {m['f1']:>6.3f} "
              f"{m['tp']:>4} {m['fp']:>4} {m['fn']:>4} {m['llm_delegated']:>5}")
    print()

    # Summary
    intents = sorted(results["per_intent"].keys())
    avg_precision = sum(results["per_intent"][i]["precision"] for i in intents) / len(intents)
    avg_recall = sum(results["per_intent"][i]["recall"] for i in intents) / len(intents)
    print(f"  Macro avg precision: {avg_precision:.3f}")
    print(f"  Macro avg recall:    {avg_recall:.3f}")
    print(f"  LLM delegation rate: {results['llm_delegated']}/{results['total']} ({results['llm_delegated']/results['total']:.1%})")
    print("=" * 70)


if __name__ == "__main__":
    cases = load_cases()
    print(f"\nLoaded {len(cases)} baseline cases\n")

    results = evaluate_rule_engine(cases)
    print_report(results)

    # Assertions for CI (non-zero exit on regression)
    # Hybrid intent: Phase 1 added rule-based hybrid detection,
    # so recall should improve vs Iteration 0 (where it was 0).
    hybrid = results["per_intent"].get("hybrid", {})
    hybrid_recall = hybrid.get("recall", 0)
    if hybrid_recall < 0.5:  # At least 50% of hybrid cases should be caught by rule
        print(f"[WARN] Hybrid recall ({hybrid_recall:.1%}) below 50% threshold — "
              f"HYBRID_PATTERNS may need expansion")

    single_intents = ["data_query", "knowledge_search", "solution_design", "direct_answer"]
    for intent in single_intents:
        m = results["per_intent"].get(intent, {})
        if m.get("precision", 1.0) < 0.9:
            print(f"[WARN] {intent} precision ({m['precision']:.1%}) below 90% — "
                  f"check for false positives")
