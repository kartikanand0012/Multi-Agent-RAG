"""Langfuse observability layer.

Architecture:
  - One TRACE per user query (full journey: Intent → Retrieval → Reasoning → Validation)
  - One SPAN per agent (automatic via @observe decorator)
  - LLM calls auto-traced with tokens + latency via langfuse.openai drop-in wrapper

Graceful degradation: if LANGFUSE_PUBLIC_KEY is not set, all functions are no-ops
and the system runs normally without tracing.
"""
from __future__ import annotations

import logging
import os
from contextvars import ContextVar
from typing import Optional

logger = logging.getLogger(__name__)

# Holds the active Langfuse trace for the current async task.
# contextvars are safe across asyncio — each coroutine tree gets its own value.
_current_trace_id: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)

_langfuse_enabled = bool(os.getenv("LANGFUSE_PUBLIC_KEY"))


def _get_client():
    """Lazily return the Langfuse client, or None if not configured."""
    if not _langfuse_enabled:
        return None
    try:
        from langfuse import get_client
        return get_client()
    except Exception as e:
        logger.warning(f"Langfuse client unavailable: {e}")
        return None


def start_trace(query: str, session_id: str | None = None) -> Optional[str]:
    """
    Open a new Langfuse trace for one user query.
    Returns the trace_id (used to attach scores later), or None if disabled.
    """
    client = _get_client()
    if client is None:
        return None
    try:
        trace = client.trace(
            name="agentic_rag_pipeline",
            input={"query": query},
            session_id=session_id,
            tags=["capstone", "multi-agent-rag"],
        )
        _current_trace_id.set(trace.id)
        logger.debug(f"Langfuse trace started: {trace.id}")
        return trace.id
    except Exception as e:
        logger.warning(f"Failed to start trace: {e}")
        return None


def end_trace(trace_id: str | None, output: str, metadata: dict | None = None) -> None:
    """Close the trace with the final response and any quality metadata."""
    if not trace_id:
        return
    client = _get_client()
    if client is None:
        return
    try:
        client.trace(id=trace_id, output=output, metadata=metadata or {})
        client.flush()
    except Exception as e:
        logger.warning(f"Failed to end trace: {e}")


def score_trace(trace_id: str | None, name: str, value: float, comment: str = "") -> None:
    """
    Attach an evaluation score to a trace (e.g. faithfulness=0.91).
    Called by the RAGAS evaluator in Phase 5.
    """
    if not trace_id:
        return
    client = _get_client()
    if client is None:
        return
    try:
        client.score(trace_id=trace_id, name=name, value=value, comment=comment)
    except Exception as e:
        logger.warning(f"Failed to score trace: {e}")


def get_observe_decorator():
    """
    Returns the @observe decorator if Langfuse is enabled, otherwise a pass-through.
    Usage in agents:
        from app.core.tracing import get_observe_decorator
        observe = get_observe_decorator()

        @observe(name="intent_agent")
        async def run(self, query): ...
    """
    if _langfuse_enabled:
        try:
            from langfuse import observe
            return observe
        except Exception:
            pass

    # No-op decorator when Langfuse is not configured
    def _noop(name: str | None = None, **kwargs):
        def decorator(fn):
            return fn
        return decorator

    return _noop


# ── status helper ─────────────────────────────────────────────────────────────

def observability_status() -> dict:
    return {
        "langfuse_enabled": _langfuse_enabled,
        "host": os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
    }
