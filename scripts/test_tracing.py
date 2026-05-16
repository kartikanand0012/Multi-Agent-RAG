"""Verify Langfuse tracing is live — run after adding keys to .env.

In Langfuse v4, @observe creates the trace. Nested @observe calls create spans.
The langfuse.openai wrapper auto-traces every LLM call with tokens + latency.
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.tracing import (
    observability_status, get_observe_decorator,
    get_current_trace_id, set_trace_io, score_trace, flush,
)
from app.llm.client import llm_client

observe = get_observe_decorator()


@observe(name="intent_agent_span")
async def mock_intent_agent(query: str) -> str:
    messages = [{"role": "user", "content": f"In 5 words, what is this about: {query}"}]
    return await llm_client.complete(messages, model=llm_client.fast_model)


@observe(name="reasoning_agent_span")
async def mock_reasoning_agent(query: str) -> str:
    messages = [{"role": "user", "content": f"Answer in 2 sentences: {query}"}]
    return await llm_client.complete(messages, model=llm_client.strong_model)


@observe(name="agentic_rag_pipeline")   # ← this creates the TRACE in Langfuse
async def run_pipeline(query: str) -> str:
    # Set trace input
    set_trace_io(input={"query": query})

    # Run 2 agent spans
    intent = await mock_intent_agent(query)
    answer = await mock_reasoning_agent(query)

    # Set trace output
    set_trace_io(output=answer)

    # Get trace ID for scoring
    trace_id = get_current_trace_id()
    score_trace(trace_id, name="faithfulness", value=0.93, comment="test run")

    return answer, trace_id


async def main():
    status = observability_status()
    print(f"Langfuse enabled : {status['langfuse_enabled']}")
    print(f"Host             : {status['host']}")
    print(f"Auth OK          : {status['auth_ok']}")

    if not status["langfuse_enabled"]:
        print("\nLangfuse keys not set in .env — add them and re-run.")
        return

    if not status["auth_ok"]:
        print("\nAuth failed — check your LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY.")
        return

    query = "What are the main business risks Apple faces?"
    print(f"\nRunning traced pipeline for: '{query}'")
    print("Each @observe function creates a span. The top-level creates the trace.\n")

    answer, trace_id = await run_pipeline(query)

    print(f"Answer     : {answer.strip()[:120]}...")
    print(f"Trace ID   : {trace_id}")

    flush()  # ensure all events are sent before script exits

    print(f"\nDone. Open Langfuse dashboard and look for trace: agentic_rag_pipeline")
    print(f"You should see 3 spans: pipeline → intent_agent → reasoning_agent")
    print(f"Each LLM call shows tokens used and latency.")


if __name__ == "__main__":
    asyncio.run(main())
