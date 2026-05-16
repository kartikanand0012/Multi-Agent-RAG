import pytest
import asyncio
import json
import sys
import os
from unittest.mock import AsyncMock, patch
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from app.agents.intent_agent import IntentAgent, IntentResult


def make_mock_response(intent_type, sub_queries, requires_sql=False, confidence=0.9):
    return json.dumps({
        "intent_type": intent_type,
        "sub_queries": sub_queries,
        "requires_sql": requires_sql,
        "confidence": confidence,
    })


class TestIntentAgent:

    @pytest.mark.asyncio
    async def test_factual_query(self):
        agent = IntentAgent()
        mock_resp = make_mock_response("factual_lookup", ["What was Apple revenue?"])
        with patch("app.agents.intent_agent.llm_client.complete", new_callable=AsyncMock) as mock:
            mock.return_value = mock_resp
            result = await agent.run("What was Apple revenue?")
        assert result.intent_type == "factual_lookup"
        assert result.requires_sql is False
        assert len(result.sub_queries) == 1

    @pytest.mark.asyncio
    async def test_multihop_decomposition(self):
        agent = IntentAgent()
        mock_resp = make_mock_response(
            "multi_hop",
            ["What was the profit margin?", "What was the headcount?"],
            confidence=0.85,
        )
        with patch("app.agents.intent_agent.llm_client.complete", new_callable=AsyncMock) as mock:
            mock.return_value = mock_resp
            result = await agent.run("Did profit margin improve as headcount grew?")
        assert result.intent_type == "multi_hop"
        assert len(result.sub_queries) == 2

    @pytest.mark.asyncio
    async def test_tabular_sets_requires_sql(self):
        agent = IntentAgent()
        mock_resp = make_mock_response(
            "tabular_aggregation", ["Total employees by region"], requires_sql=True
        )
        with patch("app.agents.intent_agent.llm_client.complete", new_callable=AsyncMock) as mock:
            mock.return_value = mock_resp
            result = await agent.run("How many employees in each region?")
        assert result.requires_sql is True

    @pytest.mark.asyncio
    async def test_invalid_json_falls_back_gracefully(self):
        agent = IntentAgent()
        with patch("app.agents.intent_agent.llm_client.complete", new_callable=AsyncMock) as mock:
            mock.return_value = "not valid json at all"
            result = await agent.run("some query")
        assert result.intent_type == "factual_lookup"
        assert result.sub_queries == ["some query"]
        assert result.confidence == 0.5

    @pytest.mark.asyncio
    async def test_unknown_intent_defaults_to_factual(self):
        agent = IntentAgent()
        mock_resp = make_mock_response("unknown_type", ["query"])
        with patch("app.agents.intent_agent.llm_client.complete", new_callable=AsyncMock) as mock:
            mock.return_value = mock_resp
            result = await agent.run("query")
        assert result.intent_type == "factual_lookup"

    @pytest.mark.asyncio
    async def test_markdown_wrapped_json_parsed(self):
        agent = IntentAgent()
        mock_resp = "```json\n" + make_mock_response("summarization", ["Summarise Apple strategy"]) + "\n```"
        with patch("app.agents.intent_agent.llm_client.complete", new_callable=AsyncMock) as mock:
            mock.return_value = mock_resp
            result = await agent.run("Summarise Apple strategy")
        assert result.intent_type == "summarization"
