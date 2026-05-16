"""Integration tests — make real LLM calls. Run with: pytest -m integration"""
import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from app.orchestration.graph import query
from app.retrieval.vector_store import vector_store

NOTEBOOK = "apple-2025"
pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def require_index():
    """Skip all integration tests if apple-2025 notebook is not indexed."""
    if vector_store.count(NOTEBOOK) == 0:
        pytest.skip("apple-2025 notebook not indexed — run RAPTOR ingestion first")


@pytest.mark.asyncio
async def test_factual_query_returns_answer():
    result = await query("What are the main risks Apple faces?", notebook_id=NOTEBOOK)
    assert result["response"]
    assert len(result["response"]) > 100
    assert result["intent_type"] in ("factual_lookup", "summarization")
    assert result["sources_used"] > 0


@pytest.mark.asyncio
async def test_summarization_query():
    result = await query("Summarise Apple overall business strategy", notebook_id=NOTEBOOK)
    assert result["response"]
    assert result["intent_type"] == "summarization"


@pytest.mark.asyncio
async def test_validation_runs():
    result = await query("Who is the CEO of Apple?", notebook_id=NOTEBOOK)
    assert "validation_passed" in result


@pytest.mark.asyncio
async def test_empty_notebook_raises():
    from fastapi.testclient import TestClient
    from app.api.main import app
    client = TestClient(app)
    resp = client.post("/api/v1/query", json={
        "query": "anything", "notebook_id": "nonexistent-notebook-xyz"
    })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_retry_count_within_bounds():
    result = await query("What was Apple revenue?", notebook_id=NOTEBOOK)
    assert 0 <= result["retry_count"] <= 2
