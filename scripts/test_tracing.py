"""Verify Langfuse tracing is live — run after adding keys to .env."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.tracing import observability_status, start_trace, end_trace, score_trace, get_observe_decorator
from app.llm.client import llm_client

observe = get_observe_decorator()


@observe(name="intent_agent_test")
async def mock_intent_agent(query: str) -> str:
    messages = [{"role": "user", "content": f"In 5 words, what is this about: {query}"}]
    return await llm_client.complete(messages, model=llm_client.fast_model)


@observe(name="reasoning_agent_test")
async def mock_reasoning_agent(query: str) -> str:
    messages = [{"role": "user", "content": f"Answer briefly: {query}"}]
    return await llm_client.complete(messages, model=llm_client.strong_model)


async def main():
    status = observability_status()
    print(f"Langfuse enabled : {status['langfuse_enabled']}")
    print(f"Host             : {status['host']}")

    if not status["langfuse_enabled"]:
        print("\nLangfuse keys not set in .env — add them and re-run.")
        return

    query = "What are the main business risks Apple faces?"
    print(f"\nRunning traced pipeline for: '{query}'")

    # Start a trace (one per user query)
    trace_id = start_trace(query=query, session_id="test-session-001")
    print(f"Trace ID: {trace_id}")

    # Simulate 2-agent pipeline with spans
    intent_result = await mock_intent_agent(query)
    print(f"Intent span  → {intent_result.strip()}")

    reasoning_result = await mock_reasoning_agent(query)
    print(f"Reasoning span → {reasoning_result.strip()[:80]}...")

    # Close trace with final answer
    end_trace(trace_id, output=reasoning_result, metadata={"test": True})

    # Attach a mock quality score
    score_trace(trace_id, name="faithfulness", value=0.92, comment="test run")

    print(f"\nDone. View your trace at: {status['host']}/traces/{trace_id}")
    print("Open Langfuse dashboard to see spans, tokens, and latency.")


if __name__ == "__main__":
    asyncio.run(main())
