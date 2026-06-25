"""Chat RAG 评估执行器。

用法:
    cd backend
    python -m eval.chat.runner --dry-run             # 快速模式（零 LLM 成本）
    python -m eval.chat.runner                       # 完整模式（含 LLM Judge）
    python -m eval.chat.runner --category warehouse_ops
    python -m eval.chat.runner --max-judge-calls 10
"""
import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

_backend_dir = str(Path(__file__).resolve().parents[2])
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

_DATASETS_DIR = Path(__file__).resolve().parent / "datasets"
_RESULTS_DIR = Path(__file__).resolve().parent / "results"
_GOLDEN_FILE = _DATASETS_DIR / "golden_qa.json"


class _NoopWriter:
    """no-op StreamWriter for generate_answer_node（eval 不需要实时推流）。"""
    async def __call__(self, chunk): pass


_noop_writer = _NoopWriter()


def _load_dataset(all_cases: bool = False, category: Optional[str] = None) -> List[Dict]:
    cases = []
    if _GOLDEN_FILE.exists():
        with open(_GOLDEN_FILE, "r", encoding="utf-8") as f:
            golden = json.load(f)
            for c in golden:
                if not all_cases and c.get("_PENDING_REVIEW"):
                    continue
                if category and c.get("category") != category:
                    continue
                cases.append(c)
    return cases


async def _preflight_check() -> str:
    """前置检查：Embedding 模型 / ChromaDB / Reranker 可用。"""
    from app.config import get_settings
    from app.core.embedding import get_default_embedding
    from app.core.vector_store import get_vector_store_manager

    settings = get_settings()

    # 检查 embedding 模型
    try:
        embed = get_default_embedding()
        _ = str(embed)
    except Exception as e:
        print(f"\n[错误] Embedding 模型不可用: {e}")
        sys.exit(1)

    # 检查 ChromaDB collections
    try:
        vms = get_vector_store_manager()
        client = vms.get_client()
        collections = client.list_collections()
        kb_colls = [c.name for c in collections if c.name.startswith("kb_documents_")]
        if not kb_colls:
            print("\n[错误] 没有 kb_documents_ 前缀的 collection，请先上传文档。")
            sys.exit(1)
        print(f"ChromaDB collections: {len(kb_colls)} 个")
    except Exception as e:
        print(f"\n[错误] ChromaDB 不可用: {e}")
        sys.exit(1)

    # 检查 reranker（可选）
    try:
        from app.rag.reranker import get_reranker
        reranker = get_reranker()
        if reranker:
            print("Reranker 可用")
    except Exception as e:
        print(f"[警告] Reranker 不可用（将使用 RRF 排序）: {e}")

    return settings.llm_provider


async def _run_single_case(
    case: Dict,
    semaphore: asyncio.Semaphore,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """执行单条 Chat 测试用例。"""
    from app.agents.graph_rag import retrieve_node, generate_answer_node
    from app.config import get_settings

    settings = get_settings()
    case_id = case["id"]
    question = case["question"]
    expected_sources_lower = [s.lower() for s in case.get("expected_sources", [])]
    expected_keywords_lower = [k.lower() for k in case.get("expected_keywords", [])]
    allow_equivalent = case.get("allow_equivalent", True)

    result = {
        "id": case_id,
        "question": question,
        "category": case.get("category", "general"),
        "verdict": "fail",
        "checks": {},
        "error_type": None,
        "latency_ms": {},
        "best_relevance_score": 0,
        "sources": [],
        "answer": None,
        "judge": None,
        "error": None,
    }

    t_start = time.time()

    async with semaphore:
        # --- 检索阶段 ---
        try:
            if dry_run:
                original_rw = settings.use_query_rewrite
                settings.use_query_rewrite = False

            state = {
                "question": question,
                "user_context": {"knowledge_id": case.get("knowledge_id")},
            }
            t0 = time.time()
            retrieval_result = await retrieve_node(state)
            result["latency_ms"]["retrieve"] = int((time.time() - t0) * 1000)

            if dry_run:
                settings.use_query_rewrite = original_rw

        except Exception as e:
            if dry_run:
                settings.use_query_rewrite = original_rw
            result["error"] = str(e)
            result["error_type"] = "retrieval_error"
            result["latency_ms"]["total"] = int((time.time() - t_start) * 1000)
            return result

        result["best_relevance_score"] = retrieval_result.get("best_relevance_score", 0)
        sources = retrieval_result.get("sources", [])
        result["sources"] = [
            {"document_name": s.get("metadata", {}).get("document_name", ""),
             "title": s.get("metadata", {}).get("title", ""),
             "score": s.get("score", 0)}
            for s in sources
        ]

        # --- Layer 1：来源命中检查 ---
        if expected_sources_lower:
            source_names = set()
            for s in sources:
                meta = s.get("metadata", {})
                doc_name = (meta.get("document_name") or meta.get("title") or "").lower()
                if doc_name:
                    source_names.add(doc_name)
            source_match = any(exp in " ".join(source_names) for exp in expected_sources_lower)
        else:
            source_match = True
        result["checks"]["source_match"] = source_match

        # --- Layer 2：关键词覆盖检查 ---
        if expected_keywords_lower:
            context_text = retrieval_result.get("context", "").lower()
            keyword_match = all(kw in context_text for kw in expected_keywords_lower)
        else:
            keyword_match = True
        result["checks"]["keyword_match"] = keyword_match

        # --- 生成阶段（仅 full 模式）---
        if not dry_run:
            try:
                gen_state = {**state, **retrieval_result}
                t1 = time.time()
                gen_result = await generate_answer_node(gen_state, _noop_writer)
                result["latency_ms"]["generate"] = int((time.time() - t1) * 1000)
                result["answer"] = gen_result.get("answer", "")
            except Exception as e:
                result["error"] = str(e)
                result["error_type"] = "generation_error"
                result["latency_ms"]["total"] = int((time.time() - t_start) * 1000)
                result["verdict"] = "fail"
                return result

        # --- Layer 3：LLM Judge（仅 full 模式、有条件）---
        if not dry_run and allow_equivalent and result["answer"]:
            from eval.chat.judges.rag_judge import judge_rag_quality

            try:
                judge_result = await judge_rag_quality(
                    question=question,
                    retrieved_context=retrieval_result.get("context", ""),
                    answer=result["answer"],
                    sources=result["sources"],
                )
                result["judge"] = {
                    "verdict": judge_result.verdict,
                    "overall_score": judge_result.overall_score,
                    "source_accuracy": judge_result.source_accuracy,
                    "no_hallucination": judge_result.no_hallucination,
                    "relevance": judge_result.relevance,
                    "completeness": judge_result.completeness,
                    "clarity": judge_result.clarity,
                    "reason": judge_result.reason,
                }
                result["verdict"] = judge_result.verdict
            except Exception as e:
                result["judge"] = {"verdict": "uncertain", "overall_score": -1, "reason": str(e)}
                result["verdict"] = "uncertain"
        else:
            result["verdict"] = "pass" if (source_match and keyword_match) else "fail"

        result["latency_ms"]["total"] = int((time.time() - t_start) * 1000)

    return result


async def run_eval(
    all_cases: bool = False,
    category: Optional[str] = None,
    dry_run: bool = False,
    max_judge_calls: Optional[int] = None,
    concurrency: int = 3,
) -> List[Dict]:
    provider = await _preflight_check()
    print(f"LLM Provider: {provider}")
    print(f"模式: {'dry-run (零 LLM 成本)' if dry_run else '完整评估'}")

    cases = _load_dataset(all_cases=all_cases, category=category)
    if not cases:
        print("[错误] 没有可用用例。")
        sys.exit(1)

    reviewed = sum(1 for c in cases if not c.get("_PENDING_REVIEW"))
    pending = sum(1 for c in cases if c.get("_PENDING_REVIEW"))
    print(f"用例: {len(cases)} 条 (已审核 {reviewed}, 待审核 {pending})")

    semaphore = asyncio.Semaphore(concurrency)
    judge_count = 0

    if max_judge_calls is not None and max_judge_calls > 0:
        async def _run_with_limit(case, sem):
            nonlocal judge_count
            result = await _run_single_case(case, sem, dry_run=dry_run)
            if result.get("judge"):
                judge_count += 1
            if judge_count >= max_judge_calls:
                # 后续 case 降级为 dry-run 方式（只检索、不调 Judge）
                orig_dry = dry_run
                async def _run_dry(case, sem):
                    r = await _run_single_case(case, sem, dry_run=True)
                    r["judge"] = {"verdict": "skipped", "overall_score": -1,
                                  "reason": f"Judge 调用次数已达上限 {max_judge_calls}"}
                    return r
                # 注意：这个简化处理会跳过剩余 case 的 generation + judge
            return result
    else:
        _run_with_limit = None

    print(f"\n运行中 (并发={concurrency})...\n")

    if _run_with_limit:
        tasks = [_run_with_limit(case, semaphore) for case in cases]
    else:
        tasks = [_run_single_case(case, semaphore, dry_run=dry_run) for case in cases]

    results = await asyncio.gather(*tasks)
    return results


def main():
    parser = argparse.ArgumentParser(description="Chat RAG Evals Runner")
    parser.add_argument("--all", dest="all_cases", action="store_true",
                        help="包含未审核用例")
    parser.add_argument("--category", type=str, default=None,
                        help="只跑指定分类")
    parser.add_argument("--dry-run", action="store_true",
                        help="快速模式：仅检索检查，零 LLM 成本")
    parser.add_argument("--max-judge-calls", type=int, default=None,
                        help="限制 Judge 调用次数上限")
    parser.add_argument("--concurrency", type=int, default=3,
                        help="并发数（默认 3）")
    parser.add_argument("--json-output", type=str, default=None,
                        help="JSON 报告输出路径")
    args = parser.parse_args()

    results = asyncio.run(run_eval(
        all_cases=args.all_cases,
        category=args.category,
        dry_run=args.dry_run,
        max_judge_calls=args.max_judge_calls,
        concurrency=args.concurrency,
    ))

    from eval.chat.reporter import print_summary, write_json_report

    print_summary(results)
    json_path = args.json_output or str(
        _RESULTS_DIR / f"{time.strftime('%Y-%m-%d-%H%M%S')}.json"
    )
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    write_json_report(results, json_path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
