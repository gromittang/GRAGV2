# Iteration 0: Router Skeleton + /orchestrator MVP

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用户从 `/orchestrator` 输入问题，系统自动判断意图并路由到对应模块执行，返回结果 + 路由决策元数据。

**Architecture:** HybridRouter（RuleEngine → MiniLLMRouter → Fallback）作为纯 Python 模块，不引入新 LangGraph 图。API 端点 `/api/v1/orchestrator/chat` 接收问题、调用 Router、通过薄封装函数 `_dispatch_to_*()` 分发到现有 graph/service、返回统一响应。前端 OrchestratorPage 展示路由决策 + 结果。

**Tech Stack:** FastAPI + existing LangGraph graphs (graph_rag, graph_nl2sql) + Vue 3 + existing DeepSeek LLM

**Accepted Tech Debt (documented):**
- API endpoint 的 `_dispatch_to_rag()` / `_dispatch_to_nl2sql()` / `_dispatch_to_pm()` 在 Iteration 1 会被替换为 service 层调用。已用薄函数隔离，替换时只改函数体。
- Iteration 0 不建 `OrchestratorState`（没有 graph，不需要 TypedDict）。Iteration 1 建 graph 时再定义。

---

## 1. Iteration Goal

交付可用的统一智能入口：用户输入 → 意图分类 → 路由到正确模块 → 返回结果。验证 Router 三层级联（Rule → Mini LLM → Fallback）在实际场景中的准确率。

## 2. Scope

**包含：**
- `RouteResult` — 路由结果 dataclass
- `RuleEngine` — 关键词/组合模式匹配，<1ms
- `MiniLLMRouter` — 调用 DeepSeek API 做意图分类，~500ms
- `HybridRouter` — 编排 Rule → LLM → Fallback 级联
- `POST /api/v1/orchestrator/chat` — 非流式 API 端点（含 3 个 dispatch 薄函数）
- `OrchestratorPage.vue` — 对话界面 + 路由决策 badge + 结果展示
- 前端路由 + 侧边栏入口
- 20 条 smoke test（pytest 参数化，覆盖 5 类场景）

**不包含：**
- `OrchestratorState` TypedDict（没有 graph，不需要。Iteration 1 再建）
- Planner、Workflow Registry、Executor、Validator、Synthesize（Iteration 1-2）
- Auth、RBAC、Data Scope（Iteration 3-4）
- SSE 流式输出（v1 用非流式）
- Hybrid 意图的实际执行（返回 placeholder）
- `ExecutionPlanPanel`（Iteration 2）
- Eval framework / runner 脚本 / 50 条标注测试集（MVP 用 smoke test + 浏览器验证）

## 3. Dependency Analysis

```
现有依赖（只读）:
  llm_manager.py::get_llm()                → MiniLLMRouter
  tracing.py::TraceContext                 → API 端点 span（可选，建议加）
  logging.py::get_logger()                 → 日志
  config.py::get_settings()                → 配置
  agents/graph_rag.py::get_rag_graph()     → dispatch to RAG
  agents/graph_nl2sql.py::get_query_graph() → dispatch to NL2SQL
  services/query_service.py::QueryService  → dispatch to NL2SQL (legacy)

新增依赖:
  无。不引入新 PyPI 包。
```

## 4. File-level Change Plan

### 新增文件

| 文件 | 职责 |
|------|------|
| `backend/app/orchestrator/__init__.py` | 包初始化 + `get_router()` 单例 |
| `backend/app/orchestrator/router.py` | `RouteResult` + `RuleEngine` + `MiniLLMRouter` + `HybridRouter` |
| `backend/app/api/orchestrator.py` | `POST /api/v1/orchestrator/chat` + 3 个 `_dispatch_to_*()` 薄函数 |
| `backend/tests/test_orchestrator_router.py` | Router 单元测试 + 集成测试 + smoke tests |
| `backend/tests/router_smoke_cases.json` | 20 条标注 smoke test 用例 |
| `frontend/vue-app/src/api/orchestrator.js` | API 客户端 |
| `frontend/vue-app/src/views/OrchestratorPage.vue` | 统一智能入口页面 |

### 修改文件

| 文件 | 修改 |
|------|------|
| `backend/app/main.py` | `from app.api import orchestrator` + `app.include_router(orchestrator.router, prefix="/api/v1/orchestrator", tags=["智能助手"])` |
| `frontend/vue-app/src/router/index.js` | 新增 `/orchestrator` 路由 |
| `frontend/vue-app/src/components/sidebar/SidebarNav.vue` | `navItems` 最前面插入"智能助手" |

## 5. Class / Function Design

### 5.1 RouteResult（`orchestrator/router.py`）

```python
from dataclasses import dataclass, field
from typing import Optional, List, Literal

IntentType = Literal["data_query", "knowledge_search", "solution_design", "hybrid", "clarify", "direct_answer"]
SourceType = Literal["rule", "llm", "fallback"]

@dataclass
class RouteResult:
    intent: IntentType
    confidence: float       # 0.0 ~ 1.0
    source: SourceType
    sub_intents: List[str] = field(default_factory=list)
    clarification: str = "" # 仅 clarify
    error: str = ""         # 路由异常信息
```

### 5.2 RuleEngine（`orchestrator/router.py`）

```python
class RuleEngine:
    """纯函数，无外部依赖。classify() 接受可选的 rules 参数（测试注入/灰度切换）"""

    DEFAULT_RULES: dict = {
        "data_query": [
            "同比", "环比", "趋势图", "占比分布", "排名前",
            "出库单", "入库单", "拣货单", "盘点单",
            ("库存量", "商品"),
            ("订单数", "仓库"),
        ],
        "solution_design": [
            "方案设计", "PRD文档", "产品需求文档",
            "功能设计方案", "系统方案设计",
            ("需求分析", "方案"),
        ],
        "knowledge_search": [
            "SOP标准", "操作流程", "操作手册",
            "管理制度", "管理办法", "规范文件",
            "安全规定", "合规要求",
        ],
        "direct_answer": [
            "几点上班", "联系方式", "系统怎么登录",
        ],
    }

    def classify(self, question: str, rules: dict = None) -> Optional[RouteResult]:
        """
        输入: 用户原始问题字符串
        输出: RouteResult 如果高置信度命中；None 如果 miss 或信号冲突
        rules 参数优先于 DEFAULT_RULES（测试注入/灰度用）
        """
```

### 5.3 MiniLLMRouter（`orchestrator/router.py`）

```python
class MiniLLMRouter:
    """调用 DeepSeek API 做意图分类。llm 参数用于测试注入 mock"""

    PROMPT = (
        "你是意图分类器。根据用户输入选择：\n"
        "1. data_query — 查询数据库、统计指标、业务数据\n"
        "2. knowledge_search — 查找文档、规范、SOP、操作流程\n"
        "3. solution_design — 设计方案、写PRD、需求分析\n"
        "4. hybrid — 同时需要查文档+查数据\n"
        "\n"
        "示例：\n"
        '"上月出库总量" → {"intent":"data_query","confidence":0.95}\n'
        '"仓库安全操作规范" → {"intent":"knowledge_search","confidence":0.90}\n'
        '"帮我设计库存预警方案" → {"intent":"solution_design","confidence":0.88}\n'
        '"结合SOP分析最近库存异常" → {"intent":"hybrid","confidence":0.82}\n'
        "\n"
        '只输出JSON：{"intent":"...","confidence":0.0}\n'
        "用户输入：{question}"
    )

    CONFIDENCE_THRESHOLD: float = 0.6

    def __init__(self, llm=None):
        """llm 参数用于测试注入 mock；None 则使用 get_llm()"""

    async def classify(self, question: str) -> RouteResult:
        """
        LLM 不可用 / JSON 解析失败 → RouteResult(intent="clarify", source="fallback", error=...)
        """
```

**实现注意事项**：
- 施工前先跑 `verify_llm_async.py` 确认 `get_llm().ainvoke()` 是否真正的 async
- 如果不是（LangChain 包装的同步调用），需 `asyncio.to_thread(get_llm().invoke, prompt)`

### 5.4 HybridRouter（`orchestrator/router.py`）

```python
class HybridRouter:
    """级联: RuleEngine → MiniLLMRouter → Fallback。不引入 LangGraph。"""

    def __init__(self):
        self.rule_engine = RuleEngine()
        self.llm_router = MiniLLMRouter()
        self._log = get_logger("orchestrator.router")

    async def route(self, question: str) -> RouteResult:
        """1. Rule → 2. LLM → 3. Fallback"""
```

### 5.5 API 端点（`api/orchestrator.py`）

```python
router = APIRouter()

class OrchestratorRequest(BaseModel):
    question: str

class OrchestratorResponse(BaseModel):
    """
    结果字段互斥说明:
      routed_to="nl2sql" → sql, data, insight 有值
      routed_to="rag"    → answer, sources 有值
      routed_to="pm" / "hybrid_placeholder" / "none" → 无结果字段
    """
    intent: str
    confidence: float
    source: str
    routed_to: str
    clarification: Optional[str] = None
    answer: Optional[str] = None
    sources: Optional[list] = None
    sql: Optional[str] = None
    data: Optional[dict] = None
    insight: Optional[dict] = None
    error: Optional[str] = None

# === 薄封装函数（Iteration 1 会被替换为 service 层调用） ===

async def _dispatch_to_rag(question: str) -> dict:
    """封装 graph_rag.ainvoke()。Iteration 1 替换为 RAGService.search()"""
    from app.agents.graph_rag import get_rag_graph
    graph = get_rag_graph()
    result = await graph.ainvoke({"question": question, "messages": []})
    return {"answer": result.get("answer", ""), "sources": result.get("sources", [])}

async def _dispatch_to_nl2sql(question: str) -> dict:
    """封装 graph_nl2sql.ainvoke()。Iteration 1 替换为 QueryService.natural_query()"""
    from app.agents.graph_nl2sql import get_query_graph
    graph = get_query_graph()
    result = await graph.ainvoke({"question": question})
    if result.get("error"):
        raise RuntimeError(result["error"])
    return {
        "sql": result.get("sql", ""),
        "data": result.get("query_result", {}),
        "insight": result.get("insight", {}),
    }

def _dispatch_to_pm() -> dict:
    """PM Studio 不在此端点内执行，返回跳转提示"""
    return {"routed_to": "pm"}

# === API Handler ===

@router.post("/chat", response_model=OrchestratorResponse)
async def orchestrator_chat(request: OrchestratorRequest):
    """
    1. HybridRouter.route(question) → RouteResult
    2. 按 intent 分发到 _dispatch_to_*()
    3. 返回 OrchestratorResponse
    """
```

### 5.6 全局 Router 单例（`orchestrator/__init__.py`）

```python
from app.orchestrator.router import HybridRouter

_router: Optional[HybridRouter] = None

def get_router() -> HybridRouter:
    global _router
    if _router is None:
        _router = HybridRouter()
    return _router
```

## 6. API Contract

### POST /api/v1/orchestrator/chat

**data_query → NL2SQL:**
```json
{"intent":"data_query","confidence":0.95,"source":"rule","routed_to":"nl2sql",
 "sql":"SELECT ...","data":{"rows":[...],"columns":[...],"total":23},
 "insight":{"summary":"...","insights":[...],"follow_ups":[...]}}
```

**knowledge_search → RAG:**
```json
{"intent":"knowledge_search","confidence":0.88,"source":"llm","routed_to":"rag",
 "answer":"根据知识库...","sources":[{"document_title":"...","content":"..."}]}
```

**hybrid → placeholder:**
```json
{"intent":"hybrid","confidence":0.78,"source":"llm","routed_to":"hybrid_placeholder",
 "answer":"跨模块综合分析功能即将在下一版本上线..."}
```

**clarify → 反问:**
```json
{"intent":"clarify","confidence":0.0,"source":"fallback","routed_to":"none",
 "clarification":"您想查询业务数据还是查找相关文档？"}
```

**error:**
```json
{"intent":"data_query","confidence":0.95,"source":"rule","routed_to":"nl2sql",
 "error":"数据库查询失败：Connection refused"}
```

## 7. Test Plan

### 7.1 单元测试（`tests/test_orchestrator_router.py`）

| 测试 | 输入 | 预期 | 类型 |
|------|------|------|------|
| `test_rule_data_query_hit` | "查询出库单数据" | RouteResult(intent="data_query", source="rule") | 确定性 |
| `test_rule_combo_hit` | "帮我查库存量最高的商品" | intent="data_query" (组合命中) | 确定性 |
| `test_rule_conflict_returns_none` | "出库单的操作规范" | None（冲突→降级 LLM） | 确定性 |
| `test_rule_miss_returns_none` | "今天天气怎么样" | None | 确定性 |
| `test_rule_custom_rules` | 注入自定义 rules | 按注入规则命中 | 确定性 |
| `test_mini_llm_data_query` | mock LLM → `{"intent":"data_query","confidence":0.88}` | intent="data_query", source="llm" | Mock |
| `test_mini_llm_parse_error` | mock LLM → `"invalid json"` | intent="clarify", source="fallback", error 非空 | Mock |
| `test_mini_llm_exception` | mock LLM → raise Exception | intent="clarify", source="fallback", error 非空 | Mock |
| `test_hybrid_rule_first` | "查询出库单" | source="rule"（不调 LLM） | Mock |
| `test_hybrid_llm_fallback` | "模糊问题" + mock LLM | source="llm"（Rule miss → LLM） | Mock |
| `test_hybrid_below_threshold` | mock LLM confidence=0.4 | source="fallback" | Mock |

### 7.2 集成测试

| 测试 | 方法 | 验证点 |
|------|------|--------|
| `test_api_endpoint_returns_200` | TestClient POST | 200, 含 intent/confidence/source/routed_to |
| `test_api_clarify_on_gibberish` | TestClient POST "asdfghjkl" | intent="clarify" |

### 7.3 Smoke Tests（`tests/router_smoke_cases.json` + pytest parametrize）

```json
[
  {"question":"查询最近7天的入库单","expected_intent":"data_query","category":"SQL"},
  {"question":"上个月销售额同比增长率","expected_intent":"data_query","category":"SQL"},
  {"question":"出库单明细","expected_intent":"data_query","category":"SQL"},
  {"question":"库存量最高的10个商品","expected_intent":"data_query","category":"SQL"},
  {"question":"SOP标准操作流程是什么","expected_intent":"knowledge_search","category":"RAG"},
  {"question":"仓库安全管理制度","expected_intent":"knowledge_search","category":"RAG"},
  {"question":"操作手册在哪里","expected_intent":"knowledge_search","category":"RAG"},
  {"question":"合规要求有哪些","expected_intent":"knowledge_search","category":"RAG"},
  {"question":"帮我做一个库存管理方案设计","expected_intent":"solution_design","category":"PM"},
  {"question":"写一个仓库布局优化的PRD","expected_intent":"solution_design","category":"PM"},
  {"question":"功能设计方案怎么做","expected_intent":"solution_design","category":"PM"},
  {"question":"需求分析方案","expected_intent":"solution_design","category":"PM"},
  {"question":"结合SOP分析最近库存异常原因","expected_intent":"hybrid","category":"Hybrid"},
  {"question":"查规范并对比实际库存数据","expected_intent":"hybrid","category":"Hybrid"},
  {"question":"根据管理制度检查最近的出库记录","expected_intent":"hybrid","category":"Hybrid"},
  {"question":"参考操作流程分析拣货效率","expected_intent":"hybrid","category":"Hybrid"},
  {"question":"管理制度","expected_intent":"knowledge_search","category":"Ambiguous"},
  {"question":"出库","expected_intent":"data_query","category":"Ambiguous"},
  {"question":"安全","expected_intent":"knowledge_search","category":"Ambiguous"},
  {"question":"库存","expected_intent":"data_query","category":"Ambiguous"}
]
```

20 条，每类 4 条。测试只跑 RuleEngine（零 LLM 成本），验证 Rule 层覆盖率。

```python
import json, pytest
from pathlib import Path

def load_smoke_cases():
    path = Path(__file__).parent / "router_smoke_cases.json"
    return json.loads(path.read_text())

class TestRouterSmoke:
    @pytest.mark.parametrize("case", load_smoke_cases())
    def test_rule_engine_smoke(self, case):
        """验证 RuleEngine 对标注用例的命中/不误判"""
        engine = RuleEngine()
        result = engine.classify(case["question"])
        if result is not None:
            # Rule 命中了 → intent 必须正确
            assert result.intent == case["expected_intent"], \
                f"Q: {case['question']} | expected: {case['expected_intent']} | got: {result.intent}"
        # Rule 返回 None 是合法的（降级到 LLM），不 fail
```

Smoke test 不替代 LLM 评估。LLM 准确率通过**浏览器人工验证**。

## 8. Acceptance Criteria

- [ ] `POST /api/v1/orchestrator/chat` 返回 200，含 intent + confidence + source + routed_to
- [ ] "出库单" → source="rule", intent="data_query"
- [ ] "SOP标准" → source="rule", intent="knowledge_search"
- [ ] "方案设计" → source="rule", intent="solution_design"
- [ ] Rule miss 的问题 → source="llm"
- [ ] 信号冲突 → 降级到 LLM（不走 Rule）
- [ ] LLM 不可用 → source="fallback", clarification 非空
- [ ] data_query → 成功调用 NL2SQL 并返回 sql + data + insight
- [ ] knowledge_search → 成功调用 RAG 并返回 answer + sources
- [ ] hybrid → 返回 placeholder
- [ ] NL2SQL dispatch 异常 → 返回 error（不 500）
- [ ] `/orchestrator` 页面可访问，发送问题后展示路由决策 + 结果
- [ ] 侧边栏"智能助手"入口可点击跳转
- [ ] 现有 `/chat`, `/query`, `/pm-studio` 不受影响
- [ ] 20 条 smoke test 全部通过（Rule 命中时不误判）

## 9. Risks & Rollback

| 风险 | 缓解 |
|------|------|
| `get_llm().ainvoke()` 不是真 async | **施工前**跑 `verify_llm_async.py` 验证 |
| graph_rag.ainvoke() 缺字段行为未知 | 集成测试 mock graph 调用，不测真实 graph |
| Mini LLM 准确率不达标 | 增加 few-shot examples + 扩展 Rule 覆盖。必要时接受 80% 先上线 |
| NL2SQL dispatch 抛异常 500 | `_dispatch_to_nl2sql()` 内部 try/except + error 字段返回 |

**Rollback**：删除 `main.py` 的 orchestrator import/include + 删除前端路由和侧边栏项。

## 10. Implementation Order (8 Tasks)

```
Task 1: RouteResult + RuleEngine + 单元测试
Task 2: MiniLLMRouter + 单元测试             ← Task 1-2 可并行
Task 3: HybridRouter + 单元测试              ← 依赖 Task 1+2
Task 4: 注册路由 + skeleton 端点             ← 1行import + 1行include + 返回{"status":"ok"}
Task 5: API 完整实现 + 集成测试              ← 依赖 Task 3+4
Task 6: 前端全部（client + page + route + sidebar） ← 依赖 API contract 确定
Task 7: 20 条 smoke test                    ← 依赖 Task 3
Task 8: 浏览器 E2E 验证                      ← 依赖 Task 5+6
```

Task 1 和 Task 2 可并行（独立模块）。Task 6 和 Task 7 可并行（前端 vs 后端测试）。

---

## Task Breakdown

### Task 1: RouteResult + RuleEngine + 单元测试

**Files:**
- Create: `backend/app/orchestrator/__init__.py`（空包）
- Create: `backend/app/orchestrator/router.py`（RouteResult + RuleEngine）
- Create: `backend/tests/test_orchestrator_router.py`（RuleEngine tests）

- [ ] **Step 1: Write failing tests for RuleEngine**

```python
import pytest
from app.orchestrator.router import RuleEngine, RouteResult

class TestRuleEngine:
    def setup_method(self):
        self.engine = RuleEngine()

    def test_data_query_hit(self):
        result = self.engine.classify("查询出库单数据")
        assert result is not None
        assert result.intent == "data_query"
        assert result.source == "rule"

    def test_combo_pattern_hit(self):
        result = self.engine.classify("帮我查库存量最高的商品")
        assert result is not None
        assert result.intent == "data_query"

    def test_conflict_returns_none(self):
        result = self.engine.classify("出库单的操作规范")
        assert result is None  # data_query + knowledge_search 冲突

    def test_miss_returns_none(self):
        result = self.engine.classify("今天天气怎么样")
        assert result is None

    def test_custom_rules(self):
        custom = {"test_intent": ["hello", "world"]}
        result = self.engine.classify("hello world", rules=custom)
        assert result is not None
        assert result.intent == "test_intent"

    def test_case_insensitive(self):
        result = self.engine.classify("SOP标准")
        assert result is not None
        assert result.intent == "knowledge_search"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_orchestrator_router.py::TestRuleEngine -v`
Expected: all FAIL

- [ ] **Step 3: Implement RouteResult + RuleEngine**

RouteResult 按 5.1 节。RuleEngine 按 5.2 节。
关键逻辑：
- `question.lower()` 做大小写不敏感
- 先遍历所有 intent → 收集命中的 intent 列表
- 命中的 intent > 1 → 返回 None（冲突）
- 命中的 intent = 1 → 返回 RouteResult
- 命中的 intent = 0 → 返回 None
- `classify(question, rules=None)` — rules 参数优先于 DEFAULT_RULES

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_orchestrator_router.py::TestRuleEngine -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/orchestrator/__init__.py backend/app/orchestrator/router.py backend/tests/test_orchestrator_router.py
git commit -m "feat(orchestrator): add RuleEngine with keyword + combo-pattern classification"
```

---

### Task 2: MiniLLMRouter + 单元测试

**Pre-flight checklist (MUST run before implementation):**

```bash
# 验证 get_llm().ainvoke() 是否真正的 async
cd backend
python -c "
import asyncio
from app.core.llm_manager import get_llm
async def main():
    llm = get_llm()
    r = await llm.ainvoke('say hello')
    print(f'type={type(r).__name__}, len={len(str(r))}')
asyncio.run(main())
"
# 如果输出正常 → ainvoke 是真 async
# 如果卡死/报错 → 改用 asyncio.to_thread(get_llm().invoke, prompt)
```

**Files:**
- Modify: `backend/app/orchestrator/router.py` (add MiniLLMRouter)
- Modify: `backend/tests/test_orchestrator_router.py` (add MiniLLMRouter tests)

- [ ] **Step 1: Write failing tests for MiniLLMRouter**

```python
from unittest.mock import AsyncMock, MagicMock

class TestMiniLLMRouter:
    @pytest.fixture
    def mock_llm(self):
        llm = MagicMock()
        llm.ainvoke = AsyncMock()
        return llm

    @pytest.mark.asyncio
    async def test_data_query_classification(self, mock_llm):
        mock_llm.ainvoke.return_value = '{"intent":"data_query","confidence":0.88}'
        router = MiniLLMRouter(llm=mock_llm)
        result = await router.classify("上月销售额")
        assert result.intent == "data_query"
        assert result.source == "llm"
        assert result.confidence == 0.88

    @pytest.mark.asyncio
    async def test_json_parse_error(self, mock_llm):
        mock_llm.ainvoke.return_value = "invalid json"
        router = MiniLLMRouter(llm=mock_llm)
        result = await router.classify("任意问题")
        assert result.intent == "clarify"
        assert result.source == "fallback"
        assert result.error != ""

    @pytest.mark.asyncio
    async def test_llm_exception(self, mock_llm):
        mock_llm.ainvoke.side_effect = Exception("timeout")
        router = MiniLLMRouter(llm=mock_llm)
        result = await router.classify("任意问题")
        assert result.intent == "clarify"
        assert result.source == "fallback"
        assert result.error != ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_orchestrator_router.py::TestMiniLLMRouter -v`
Expected: all FAIL

- [ ] **Step 3: Implement MiniLLMRouter**

按 5.3 节实现。注意 `json.loads()` 解析 + try/except。置信度 < CONFIDENCE_THRESHOLD → fallback。

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_orchestrator_router.py::TestMiniLLMRouter -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/orchestrator/router.py backend/tests/test_orchestrator_router.py
git commit -m "feat(orchestrator): add MiniLLMRouter with LLM intent classification"
```

---

### Task 3: HybridRouter + 单元测试

**Files:**
- Modify: `backend/app/orchestrator/router.py` (add HybridRouter)
- Modify: `backend/tests/test_orchestrator_router.py` (add HybridRouter tests)

- [ ] **Step 1: Write failing tests**

```python
class TestHybridRouter:
    @pytest.fixture
    def mock_llm(self):
        llm = MagicMock()
        llm.ainvoke = AsyncMock()
        return llm

    @pytest.mark.asyncio
    async def test_rule_takes_priority(self, mock_llm):
        router = HybridRouter()
        router.llm_router = MiniLLMRouter(llm=mock_llm)
        result = await router.route("查询出库单数据")
        assert result.source == "rule"

    @pytest.mark.asyncio
    async def test_llm_when_rule_miss(self, mock_llm):
        mock_llm.ainvoke.return_value = '{"intent":"knowledge_search","confidence":0.75}'
        router = HybridRouter()
        router.llm_router = MiniLLMRouter(llm=mock_llm)
        result = await router.route("模糊问题")
        assert result.source == "llm"

    @pytest.mark.asyncio
    async def test_fallback_on_low_confidence(self, mock_llm):
        mock_llm.ainvoke.return_value = '{"intent":"knowledge_search","confidence":0.40}'
        router = HybridRouter()
        router.llm_router = MiniLLMRouter(llm=mock_llm)
        result = await router.route("模糊问题")
        assert result.source == "fallback"
        assert result.intent == "clarify"
```

- [ ] **Step 2-4: TDD cycle (fail → implement → pass)**

- [ ] **Step 5: Commit**

```bash
git add backend/app/orchestrator/router.py backend/tests/test_orchestrator_router.py
git commit -m "feat(orchestrator): add HybridRouter with Rule→LLM→Fallback cascade"
```

---

### Task 4: 注册路由 + skeleton 端点

**Files:**
- Create: `backend/app/api/orchestrator.py`（skeleton）
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create skeleton `api/orchestrator.py`**

```python
from fastapi import APIRouter

router = APIRouter()

@router.post("/chat")
async def orchestrator_chat():
    return {"status": "ok"}
```

- [ ] **Step 2: Register in `main.py`**

Import 行加入 `orchestrator`，include 行加入：
```python
app.include_router(orchestrator.router, prefix="/api/v1/orchestrator", tags=["智能助手"])
```

- [ ] **Step 3: Verify**

```bash
curl -s http://localhost:8812/health          # {"status":"healthy",...}
curl -s -X POST http://localhost:8812/api/v1/orchestrator/chat \
  -H "Content-Type: application/json" -d '{}'  # {"status":"ok"}
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/orchestrator.py backend/app/main.py
git commit -m "feat(orchestrator): register orchestrator route with skeleton endpoint"
```

---

### Task 5: API 完整实现 + 集成测试

**Files:**
- Modify: `backend/app/api/orchestrator.py`（完整 dispatch 逻辑）
- Modify: `backend/app/orchestrator/__init__.py`（加 `get_router()`）
- Modify: `backend/tests/test_orchestrator_router.py`（加集成测试）

- [ ] **Step 1: Update `orchestrator/__init__.py`**

按 5.6 节实现 `get_router()` 单例。

- [ ] **Step 2: Write integration test**

```python
from fastapi.testclient import TestClient

class TestOrchestratorAPI:
    @pytest.fixture
    def client(self):
        from app.main import app
        return TestClient(app)

    def test_endpoint_returns_200(self, client):
        response = client.post("/api/v1/orchestrator/chat",
                               json={"question": "测试"})
        assert response.status_code == 200
        data = response.json()
        for field in ["intent", "confidence", "source", "routed_to"]:
            assert field in data
```

- [ ] **Step 3: Run test to verify FAIL (endpoint returns {"status":"ok"} today)**

- [ ] **Step 4: Implement full dispatch logic in `api/orchestrator.py`**

按 5.5 节实现：`_dispatch_to_rag()` + `_dispatch_to_nl2sql()` + `_dispatch_to_pm()` + handler。
- `_dispatch_to_nl2sql()` 内部 try/except → raise RuntimeError
- handler 根据 intent 选择 dispatch 函数
- handler 内部 try/except 整个 dispatch 过程 → error 字段

- [ ] **Step 5: Run integration test to verify PASS**

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/orchestrator.py backend/app/orchestrator/__init__.py backend/tests/test_orchestrator_router.py
git commit -m "feat(orchestrator): implement dispatch logic with thin graph wrappers"
```

---

### Task 6: 前端全部

**Files:**
- Create: `frontend/vue-app/src/api/orchestrator.js`
- Create: `frontend/vue-app/src/views/OrchestratorPage.vue`
- Modify: `frontend/vue-app/src/router/index.js`
- Modify: `frontend/vue-app/src/components/sidebar/SidebarNav.vue`

- [ ] **Step 1: Create API client**

```javascript
import axios from 'axios'
export function orchestratorChat(question) {
  return axios.post('/api/v1/orchestrator/chat', { question })
}
```

- [ ] **Step 2: Create OrchestratorPage.vue**

最小可用版本：
- 输入框 + 发送按钮
- 路由决策 badge：`[数据查询 · 95% · 规则命中]`
- 结果区（防御性渲染）：
  - `v-if="routed_to === 'nl2sql' && sql"` → SQL + 数据表格
  - `v-else-if="routed_to === 'rag' && answer"` → 文本 + 来源
  - `v-else-if="routed_to === 'hybrid_placeholder'"` → placeholder 文本
  - `v-else-if="clarification"` → 反问文本
  - `v-else-if="error"` → 错误提示
- 加载/错误状态

- [ ] **Step 3: Add route + sidebar nav item**

路由：`{ path: '/orchestrator', name: 'Orchestrator', component: () => import('../views/OrchestratorPage.vue') }`
侧边栏最前面：`{ id: 'orchestrator', label: '智能助手', icon: 'lucide:sparkles', to: '/orchestrator' }`

- [ ] **Step 4: Verify build**

Run: `cd frontend/vue-app && npm run build`
Expected: build success

- [ ] **Step 5: Commit**

```bash
git add frontend/vue-app/src/api/orchestrator.js frontend/vue-app/src/views/OrchestratorPage.vue frontend/vue-app/src/router/index.js frontend/vue-app/src/components/sidebar/SidebarNav.vue
git commit -m "feat(orchestrator): add OrchestratorPage with routing badge + sidebar entry"
```

---

### Task 7: Smoke Tests

**Files:**
- Create: `backend/tests/router_smoke_cases.json`（20 条）
- Modify: `backend/tests/test_orchestrator_router.py`（加 smoke test class）

- [ ] **Step 1: Create `router_smoke_cases.json`**

按 7.3 节的 20 条 cases。

- [ ] **Step 2: Add parametrized test**

```python
import json
from pathlib import Path

def _load_smoke_cases():
    path = Path(__file__).parent / "router_smoke_cases.json"
    return json.loads(path.read_text())

class TestRouterSmoke:
    @pytest.mark.parametrize("case", _load_smoke_cases())
    def test_rule_engine_smoke(self, case):
        engine = RuleEngine()
        result = engine.classify(case["question"])
        if result is not None:
            assert result.intent == case["expected_intent"], \
                f"Q: {case['question']} | expected: {case['expected_intent']} | got: {result.intent}"
```

- [ ] **Step 3: Run smoke tests**

Run: `cd backend && python -m pytest tests/test_orchestrator_router.py::TestRouterSmoke -v`
Expected: 20 PASS（Rule 命中时 intent 正确；Rule miss 时自动通过）

- [ ] **Step 4: Commit**

```bash
git add backend/tests/router_smoke_cases.json backend/tests/test_orchestrator_router.py
git commit -m "test(orchestrator): add 20-case router smoke test suite"
```

---

### Task 8: 浏览器 E2E 验证

启动后端和前端：

```bash
# Terminal 1: backend
cd backend && uvicorn app.main:app --app-dir . --host 0.0.0.0 --port 8812 --reload

# Terminal 2: frontend
cd frontend/vue-app && npm run dev
```

手动验证清单：

- [ ] 访问 http://localhost:5173/orchestrator — 页面加载，输入框可见
- [ ] 输入 "查询出库单数据" → badge 显示 `[数据查询 · rule]`，返回 SQL + 数据
- [ ] 输入 "SOP标准操作流程" → badge 显示 `[文档检索 · rule]`，返回 RAG 答案
- [ ] 输入 "帮我做方案设计" → badge 显示 `[方案设计 · rule]`，提示跳转 PM Studio
- [ ] 输入 "今天天气怎么样" → badge 显示 `[llm]`（Rule miss → LLM）
- [ ] 输入 "asdfghjkl" → 显示反问文本
- [ ] 点击侧边栏"智能助手" → 页面跳转
- [ ] 访问 /chat、/query、/pm-studio → 功能不受影响

---

## 施工总览

```
Task 1: RuleEngine + 单元测试（6 case）
Task 2: MiniLLMRouter + 单元测试（3 case）    ← 可并行
Task 3: HybridRouter + 单元测试（3 case）
Task 4: 注册路由 + skeleton 端点
Task 5: API 完整实现 + 集成测试（2 case）
Task 6: 前端全部（client + page + route + sidebar）
Task 7: Smoke tests（20 条参数化）            ← 可并行
Task 8: 浏览器 E2E 验证
```

**8 个 Task，预计 1.5-2 天。相较于 v1 减少了 1 个 Task（9→8），消除了孤立的 OrchestratorState 和过度投入的 eval framework。**
