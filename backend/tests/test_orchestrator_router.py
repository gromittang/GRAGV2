from unittest.mock import AsyncMock, MagicMock

import pytest
from app.orchestrator.router import MiniLLMRouter, RuleEngine, RouteResult


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
