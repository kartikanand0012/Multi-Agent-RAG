"""Langfuse v4 observability layer.

In Langfuse v4, the primary mechanism is the @observe decorator:
  - @observe(name="pipeline") on the top-level function → creates a TRACE
  - @observe(name="intent_agent") on each agent → creates a nested SPAN
  - langfuse.openai drop-in wrapper → auto-creates GENERATION spans with tokens

Graceful degradation: if LANGFUSE_PUBLIC_KEY is not set, all tracing is skipped
and the system runs normally.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()  # ensure .env is loaded before reading env vars

logger = logging.getLogger(__name__)

_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "")
_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "")
_HOST = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
_langfuse_enabled = bool(_PUBLIC_KEY and _SECRET_KEY)

# Singleton Langfuse client — only created when credentials are present
_lf = None


def _get_lf():
    global _lf
    if not _langfuse_enabled:
        return None
    if _lf is None:
        try:
            from langfuse import Langfuse
            _lf = Langfuse(public_key=_PUBLIC_KEY, secret_key=_SECRET_KEY, host=_HOST)
        except Exception as e:
            logger.warning(f"Langfuse init failed: {e}")
    return _lf


# ── decorator ─────────────────────────────────────────────────────────────────

def get_observe_decorator():
    """
    Returns the Langfuse @observe decorator when enabled, else a no-op.

    Usage in any agent:
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

    def _noop(name: str | None = None, **kwargs):
        def decorator(fn):
            return fn
        return decorator

    return _noop


# ── trace helpers ─────────────────────────────────────────────────────────────

def get_current_trace_id() -> Optional[str]:
    """
    Returns the active trace ID when called inside an @observe-decorated function.
    Used by agents to attach metadata to the current trace.
    """
    lf = _get_lf()
    if lf is None:
        return None
    try:
        return lf.get_current_trace_id()
    except Exception:
        return None


def set_trace_io(input: dict | None = None, output: str | None = None) -> None:
    """Set the input/output on the current trace (called from pipeline entry point)."""
    lf = _get_lf()
    if lf is None:
        return
    try:
        kwargs = {}
        if input is not None:
            kwargs["input"] = input
        if output is not None:
            kwargs["output"] = output
        lf.set_current_trace_io(**kwargs)
    except Exception as e:
        logger.debug(f"set_trace_io failed: {e}")


def score_trace(trace_id: str | None, name: str, value: float, comment: str = "") -> None:
    """
    Attach a quality score to a completed trace.
    Called by RAGAS evaluator in Phase 5.
    """
    if not trace_id:
        return
    lf = _get_lf()
    if lf is None:
        return
    try:
        lf.create_score(trace_id=trace_id, name=name, value=value, comment=comment)
    except Exception as e:
        logger.warning(f"score_trace failed: {e}")


def flush() -> None:
    """Flush all pending events to Langfuse (call at shutdown or end of test)."""
    lf = _get_lf()
    if lf:
        try:
            lf.flush()
        except Exception:
            pass


# ── status ────────────────────────────────────────────────────────────────────

def observability_status() -> dict:
    return {
        "langfuse_enabled": _langfuse_enabled,
        "host": _HOST,
        "auth_ok": _get_lf().auth_check() if _langfuse_enabled else False,
    }
