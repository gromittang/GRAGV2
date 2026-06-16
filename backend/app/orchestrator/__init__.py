"""Orchestrator 企业级编排层

Iteration 0: Hybrid Router + Orchestrator Skeleton
"""
from typing import Optional
from app.orchestrator.router import HybridRouter

_router: Optional[HybridRouter] = None


def get_router() -> HybridRouter:
    global _router
    if _router is None:
        _router = HybridRouter()
    return _router
