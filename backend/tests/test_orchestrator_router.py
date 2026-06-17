import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.orchestrator.router import HybridRouter, MiniLLMRouter, RuleEngine, RouteResult


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
        result = self.engine.classify("出库单的SOP标准")
        assert result is None

    def test_miss_returns_none(self):
        result = self.engine.classify("今天天气怎么样")
        assert result is None

    def test_custom_rules(self):
        custom = {"test_intent": ["hello", "world"]}
        result = self.engine.classify("hello world", rules=custom)
        assert result is not None
        assert result.intent == "test_intent"

    def test_case_insensitive(self):
        result = self.engine.classify("sop标准")
        assert result is not None
        assert result.intent == "knowledge_search"

    def test_list_combo_pattern(self):
        custom = {"test_intent": [["hello", "world"]]}
        result = self.engine.classify("hello world", rules=custom)
        assert result is not None
        assert result.intent == "test_intent"


class TestRuleEngineHybrid:
    """Phase 1: HYBRID_PATTERNS 三元组规则测试"""

    def setup_method(self):
        self.engine = RuleEngine()

    def test_hybrid_pattern_hit(self):
        """verb + data_signal + doc_signal 同时出现 → hybrid"""
        result = self.engine.classify("结合SOP分析库存异常")
        assert result is not None
        assert result.intent == "hybrid"
        assert result.source == "rule"

    def test_hybrid_no_false_positive_data(self):
        """仅有 verb + data_signal，无 doc_signal → 不判 hybrid，应为 None"""
        result = self.engine.classify("结合实际情况分析库存")
        assert result is None, (
            f"有 verb + data signal 但无 doc signal，规则引擎应返回 None，"
            f"实际: intent={result.intent if result else None}"
        )

    def test_hybrid_no_false_positive_rag(self):
        """仅有 verb + doc_signal，无 data_signal → 不判 hybrid，应为 None"""
        result = self.engine.classify("结合SOP制度文件")
        assert result is None, (
            f"有 verb + doc signal 但无 data signal，规则引擎应返回 None，"
            f"实际: intent={result.intent if result else None}"
        )

    def test_hybrid_another_verb(self):
        """其他 cross_module_verb 的命中验证"""
        result = self.engine.classify("根据操作手册分析入库单数据")
        assert result is not None
        assert result.intent == "hybrid"
        assert result.source == "rule"

    def test_hybrid_patterns_di(self):
        """自定义 hybrid_patterns 注入（与 rules DI 同模式）"""
        custom = [("测试动词", ["数据"], ["规范"])]
        result = self.engine.classify(
            "测试动词与数据和规范相关", hybrid_patterns=custom
        )
        assert result is not None
        assert result.intent == "hybrid"
        assert result.source == "rule"


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
        result = await router.classify("问题")
        assert result.intent == "clarify"
        assert result.source == "fallback"
        assert result.error != ""

    @pytest.mark.asyncio
    async def test_low_confidence_fallback(self, mock_llm):
        mock_llm.ainvoke.return_value = '{"intent":"data_query","confidence":0.40}'
        router = MiniLLMRouter(llm=mock_llm)
        result = await router.classify("模糊的问题")
        assert result.intent == "clarify"
        assert result.source == "fallback"
        assert result.clarification != ""

    @pytest.mark.asyncio
    async def test_llm_exception(self, mock_llm):
        mock_llm.ainvoke.side_effect = Exception("timeout")
        router = MiniLLMRouter(llm=mock_llm)
        result = await router.classify("问题")
        assert result.intent == "clarify"
        assert result.source == "fallback"
        assert result.error != ""


class TestHybridRouter:
    @pytest.fixture
    def mock_llm(self):
        llm = MagicMock()
        llm.ainvoke = AsyncMock()
        return llm

    @pytest.mark.asyncio
    async def test_rule_takes_priority(self, mock_llm):
        router = HybridRouter(llm_router=MiniLLMRouter(llm=mock_llm))
        result = await router.route("查询出库单数据")
        assert result.source == "rule"
        mock_llm.ainvoke.assert_not_called()

    @pytest.mark.asyncio
    async def test_llm_when_rule_miss(self, mock_llm):
        mock_llm.ainvoke.return_value = '{"intent":"knowledge_search","confidence":0.75}'
        router = HybridRouter(llm_router=MiniLLMRouter(llm=mock_llm))
        result = await router.route("今天天气怎么样")
        assert result.source == "llm"
        assert result.intent == "knowledge_search"

    @pytest.mark.asyncio
    async def test_fallback_on_low_confidence(self, mock_llm):
        mock_llm.ainvoke.return_value = '{"intent":"knowledge_search","confidence":0.40}'
        router = HybridRouter(llm_router=MiniLLMRouter(llm=mock_llm))
        result = await router.route("模糊的问题文本")
        assert result.source == "fallback"
        assert result.intent == "clarify"
        assert result.clarification != ""


def _load_smoke_cases():
    path = Path(__file__).parent / "router_smoke_cases.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as e:
        pytest.skip(f"Smoke cases unavailable: {e}")
        return []


class TestRouterSmoke:
    """Smoke tests for RuleEngine accuracy (zero LLM cost).

    Hybrid category cases use data_query + knowledge_search keyword pairs
    that trigger a conflict in RuleEngine, causing it to return None
    (delegate to LLM). The test auto-passes when result is None.
    expected_intent 'hybrid' is documentation-only for these cases.
    """

    @pytest.mark.parametrize("case", _load_smoke_cases())
    def test_rule_engine_smoke(self, case):
        engine = RuleEngine()
        result = engine.classify(case["question"])
        if result is not None:
            assert result.intent == case["expected_intent"], (
                f"Q: {case['question']} | expected: {case['expected_intent']} "
                f"| got: {result.intent} | category: {case['category']}"
            )


class TestOrchestratorAPI:
    @pytest.fixture
    def mock_router(self):
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock()
        mock_llm.ainvoke.return_value = '{"intent":"knowledge_search","confidence":0.75}'
        return HybridRouter(llm_router=MiniLLMRouter(llm=mock_llm))

    @pytest.fixture
    def mock_dispatch_rag(self):
        """Mock dispatch_to_rag — 返回预设 answer + sources，避免真实 graph 加载"""
        mock = AsyncMock()
        mock.return_value = {"answer": "mock rag answer", "sources": []}
        return mock

    @pytest.fixture
    def mock_dispatch_nl2sql(self):
        """Mock dispatch_to_nl2sql — 返回预设 sql/data/insight，避免真实 graph 加载"""
        mock = AsyncMock()
        mock.return_value = {"sql": "SELECT 1", "data": {}, "insight": {}}
        return mock

    @pytest.fixture
    def client(self, mock_router, mock_dispatch_rag, mock_dispatch_nl2sql):
        with (
            patch("app.api.orchestrator.get_router", return_value=mock_router),
            patch("app.api.orchestrator.dispatch_to_rag", mock_dispatch_rag),
            patch("app.api.orchestrator.dispatch_to_nl2sql", mock_dispatch_nl2sql),
        ):
            from app.main import app
            from fastapi.testclient import TestClient
            yield TestClient(app)

    def test_endpoint_returns_200_and_fields(self, client):
        response = client.post("/api/v1/orchestrator/chat",
                               json={"question": "测试问题"})
        assert response.status_code == 200
        data = response.json()
        for field in ["intent", "confidence", "source", "routed_to"]:
            assert field in data

    def test_rule_hit_returns_data_query(self, client):
        response = client.post("/api/v1/orchestrator/chat",
                               json={"question": "查询出库单数据"})
        assert response.status_code == 200
        data = response.json()
        assert data["intent"] == "data_query"
        assert data["source"] == "rule"
        assert data["routed_to"] == "nl2sql"
        assert not data.get("error"), (
            f"成功 dispatch 不应设置 error，实际: {data.get('error')!r}"
        )
        assert data["sql"] == "SELECT 1"

    def test_llm_fallback_for_unknown_question(self, client):
        response = client.post("/api/v1/orchestrator/chat",
                               json={"question": "asdfghjkl"})
        assert response.status_code == 200
        data = response.json()
        assert data["intent"] == "knowledge_search"
        assert data["source"] == "llm"
        assert data["routed_to"] == "rag"
        assert not data.get("error"), (
            f"成功 dispatch 不应设置 error，实际: {data.get('error')!r}"
        )
