"""
Planner 真实 LLM smoke test — 验证 PROMPT 质量

用法:
  cd backend
  python tests/smoke_planner_live.py

不依赖 MySQL / ChromaDB，仅需 DeepSeek API key。
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.orchestrator.planner import Planner

TEST_QUESTIONS = [
    "查最近7天出库异常的记录",
    "结合SOP分析最近库存异常的原因",
    "仓库安全操作规范是什么",
    "对比管理制度分析入库单数据是否合规",
]


async def main():
    planner = Planner()
    for q in TEST_QUESTIONS:
        print(f"\n{'='*60}")
        print(f"  Q: {q}")
        print(f"{'='*60}")
        try:
            plan = await planner.plan(q)
            for s in plan.steps:
                print(f"  [{s.step}] {s.intent:12s} | {s.goal}")
                print(f"       query: {s.query[:100]}")
            print(f"  => {len(plan.steps)} steps, last is {plan.steps[-1].intent}")
        except Exception as e:
            print(f"  FAIL: {e}")

    print(f"\n{'='*60}")
    print("  Planner smoke test complete")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
