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


class TestOrchestratorAPI:
    @pytest.fixture
    def mock_router(self):
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock()
        mock_llm.ainvoke.return_value = '{"intent":"knowledge_search","confidence":0.75}'
        return HybridRouter(llm_router=MiniLLMRouter(llm=mock_llm))

    @pytest.fixture
    def client(self, mock_router):
        with patch("app.api.orchestrator.get_router", return_value=mock_router):
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

    def test_llm_fallback_for_unknown_question(self, client):
        response = client.post("/api/v1/orchestrator/chat",
                               json={"question": "asdfghjkl"})
        assert response.status_code == 200
        data = response.json()
        assert data["intent"] == "knowledge_search"
        assert data["source"] == "llm"
        assert data["routed_to"] == "rag"
