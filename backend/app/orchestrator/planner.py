"""
Planner — LLM 生成 ExecutionPlan + 内联 validator

Iteration 1: PlanStep + ExecutionPlan schema 定义
Phase 3 (Task 3.1-3.2): 扩展 Planner class + LLM prompt + _validate()
"""
from pydantic import BaseModel
from typing import List, Literal


class PlanStep(BaseModel):
    step: int       # 1-based step number
    intent: Literal["nl2sql", "rag", "synthesize"]
    goal: str       # human-readable description
    query: str      # actual query / synthesis instruction


class ExecutionPlan(BaseModel):
    steps: List[PlanStep]
