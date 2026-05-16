import pytest
import json
import sys
import os
from unittest.mock import AsyncMock, patch
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from app.agents.validation_agent import ValidationAgent
from app.retrieval.grader import GradeResult


def make_chunk(text: str) -> GradeResult:
    return GradeResult(text=text, metadata={"source": "test.pdf", "layer": 0},
                       grade="Correct", confidence=0.9, reason="relevant")


class TestValidationAgent:

    @pytest.mark.asyncio
    async def test_passes_supported_response(self):
        agent = ValidationAgent()
        mock_resp = json.dumps({
            "passed": True,
            "unsupported_claims": [],
            "feedback": "All claims verified.",
        })
        chunks = [make_chunk("Apple revenue was $391 billion in 2024.")]
        with patch("app.agents.validation_agent.llm_client.complete", new_callable=AsyncMock) as mock:
            mock.return_value = mock_resp
            result = await agent.run("Apple revenue was $391 billion [Source 1].", chunks)
        assert result.passed is True
        assert result.unsupported_claims == []

    @pytest.mark.asyncio
    async def test_fails_hallucinated_claim(self):
        agent = ValidationAgent()
        mock_resp = json.dumps({
            "passed": False,
            "unsupported_claims": ["Apple revenue was $999 trillion"],
            "feedback": "The revenue figure is not supported by any source chunk.",
        })
        chunks = [make_chunk("Apple revenue was $391 billion in 2024.")]
        with patch("app.agents.validation_agent.llm_client.complete", new_callable=AsyncMock) as mock:
            mock.return_value = mock_resp
            result = await agent.run("Apple revenue was $999 trillion [Source 1].", chunks)
        assert result.passed is False
        assert len(result.unsupported_claims) == 1

    @pytest.mark.asyncio
    async def test_no_chunks_fails_immediately(self):
        agent = ValidationAgent()
        result = await agent.run("Some response.", chunks=[])
        assert result.passed is False
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_markdown_json_parsed(self):
        agent = ValidationAgent()
        mock_resp = "```json\n" + json.dumps({
            "passed": True, "unsupported_claims": [], "feedback": "All verified."
        }) + "\n```"
        chunks = [make_chunk("Some source content.")]
        with patch("app.agents.validation_agent.llm_client.complete", new_callable=AsyncMock) as mock:
            mock.return_value = mock_resp
            result = await agent.run("Response citing source.", chunks)
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_parse_error_defaults_to_passed(self):
        agent = ValidationAgent()
        chunks = [make_chunk("Some content.")]
        with patch("app.agents.validation_agent.llm_client.complete", new_callable=AsyncMock) as mock:
            mock.return_value = "not json"
            result = await agent.run("Some response.", chunks)
        assert result.passed is True   # safe default — never crash the user
