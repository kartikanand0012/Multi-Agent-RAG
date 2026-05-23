"""Query endpoints — non-streaming and streaming RAG."""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import QueryRequest, QueryResponse
from app.auth.dependencies import get_current_user
from app.cache.redis_cache import query_cache
from app.db.models import (
    AgentName, AgentRun, AgentStep, Conversation, Message, MessageRole,
    Notebook, RetrievedChunk, RunStatus, User,
)
from app.db.session import get_db
from app.llm.client import count_tokens
from app.middleware.quota import check_query_quota, increment_query_quota
from app.orchestration.graph import query as run_query
from app.retrieval.vector_store import vector_store

logger = structlog.get_logger(__name__)
router = APIRouter()


# ── Non-streaming query ────────────────────────────────────────────────────────

@router.post("/query", response_model=QueryResponse, tags=["query"])
async def query(
    req: QueryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession   = Depends(get_db),
):
    if req.stream:
        raise HTTPException(status_code=400, detail="Use POST /query/stream for streaming.")

    await check_query_quota(current_user, db)

    cached = query_cache.get(req.query, req.notebook_id)
    if cached:
        cached["cached"] = True
        return QueryResponse(**cached)

    if vector_store.count(req.notebook_id) == 0:
        raise HTTPException(status_code=404, detail=f"Notebook '{req.notebook_id}' has no documents. Upload a file first.")

    t0 = time.monotonic()
    result = await run_query(req.query, notebook_id=req.notebook_id)
    latency_ms = int((time.monotonic() - t0) * 1000)

    await increment_query_quota(current_user, db)

    response_data = {
        "response":          result["response"],
        "intent_type":       result["intent_type"],
        "sources_used":      result["sources_used"],
        "validation_passed": result["validation_passed"],
        "retry_count":       result["retry_count"],
        "trace_id":          result.get("trace_id"),
        "cached":            False,
    }
    query_cache.set(req.query, req.notebook_id, response_data)

    # Durable usage event via Celery
    try:
        from app.workers.tasks import record_usage
        record_usage.delay(
            user_id=current_user.id,
            event_type="query",
            tokens_in=count_tokens(req.query),
            tokens_out=count_tokens(result["response"]),
        )
    except Exception:
        pass  # Celery unavailable; skip analytics rather than fail the request

    return QueryResponse(**response_data)


# ── Streaming query ────────────────────────────────────────────────────────────

@router.post("/query/stream", tags=["query"])
async def query_stream(
    req: QueryRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession   = Depends(get_db),
):
    await check_query_quota(current_user, db)

    if vector_store.count(req.notebook_id) == 0:
        raise HTTPException(
            status_code=404,
            detail=f"Notebook '{req.notebook_id}' has no documents. Upload a file first.",
        )

    # Reuse pre-instantiated agent singletons from app.state
    agents       = getattr(request.app.state, "agents", {})
    intent_agent     = agents.get("intent")
    retrieval_agent  = agents.get("retrieval")
    reasoning_agent  = agents.get("reasoning")
    validation_agent = agents.get("validation")

    # Fallback: instantiate if singletons missing (e.g. lifespan error)
    if not all([intent_agent, retrieval_agent, reasoning_agent, validation_agent]):
        from app.agents.intent_agent import IntentAgent
        from app.agents.retrieval_agent import RetrievalAgent
        from app.agents.reasoning_agent import ReasoningAgent
        from app.agents.validation_agent import ValidationAgent
        from app.api.main import get_bm25
        intent_agent     = IntentAgent()
        retrieval_agent  = RetrievalAgent(vector_store, get_bm25(req.notebook_id))
        reasoning_agent  = ReasoningAgent()
        validation_agent = ValidationAgent()

    t_start = time.monotonic()

    async def event_generator():
        intent_type   = "factual_lookup"
        sources_found = 0
        validation_ok = True
        full_response = ""
        unsupported   = []
        vfeedback     = ""
        chunks_used   = []
        agent_trace   = []   # per-step metrics for UI + DB

        try:
            # Intent
            t0 = time.monotonic()
            intent = await intent_agent.run(req.query)
            intent_type = intent.intent_type
            tokens_in_intent = count_tokens(req.query)
            tokens_out_intent = count_tokens(intent_type) + sum(count_tokens(q) for q in getattr(intent, "sub_queries", []) or [])
            agent_trace.append({
                "name": "intent",
                "latency_ms": int((time.monotonic() - t0) * 1000),
                "tokens_in": tokens_in_intent,
                "tokens_out": tokens_out_intent,
                "summary": intent_type,
            })
            yield f"data: {json.dumps({'type': 'intent', 'intent_type': intent.intent_type})}\n\n"

            # Retrieval
            t0 = time.monotonic()
            chunks = await retrieval_agent.run(intent, notebook_id=req.notebook_id)
            chunks_used = chunks
            sources_found = len(chunks)
            agent_trace.append({
                "name": "retrieval",
                "latency_ms": int((time.monotonic() - t0) * 1000),
                "tokens_in": 0,  # retrieval is embedding + search, no LLM completion
                "tokens_out": 0,
                "summary": f"{sources_found} chunks",
            })
            yield f"data: {json.dumps({'type': 'retrieval', 'sources_found': sources_found})}\n\n"

            # Reasoning (streaming)
            t0 = time.monotonic()
            reasoning_input_tokens = count_tokens(req.query) + sum(
                count_tokens(getattr(c, "text", "")) for c in (chunks or [])
            )
            async for token in reasoning_agent.stream(req.query, intent, chunks):
                full_response += token
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
            agent_trace.append({
                "name": "reasoning",
                "latency_ms": int((time.monotonic() - t0) * 1000),
                "tokens_in": reasoning_input_tokens,
                "tokens_out": count_tokens(full_response),
                "summary": full_response[:120],
            })

            # Validation
            t0 = time.monotonic()
            validation = await validation_agent.run(full_response, chunks)
            validation_ok = validation.passed
            unsupported   = validation.unsupported_claims
            vfeedback     = validation.feedback
            agent_trace.append({
                "name": "validation",
                "latency_ms": int((time.monotonic() - t0) * 1000),
                "tokens_in": count_tokens(full_response),
                "tokens_out": count_tokens(vfeedback or ""),
                "summary": "PASSED" if validation_ok else f"FAILED: {(vfeedback or '')[:80]}",
            })
            validation_payload = json.dumps({
                "type": "validation",
                "passed": validation.passed,
                "unsupported_claims": unsupported,
                "feedback": vfeedback,
                "confidence": validation.confidence,
            })
            yield f"data: {validation_payload}\n\n"

            if not validation.passed:
                yield f"data: {json.dumps({'type': 'warning', 'message': 'Response could not be fully verified.'})}\n\n"

            latency_ms = int((time.monotonic() - t_start) * 1000)
            await increment_query_quota(current_user, db)

            # Persist agent_run + steps + chunks (best-effort)
            try:
                run = await _persist_run(
                    db, current_user, req, intent_type, sources_found,
                    validation_ok, unsupported, vfeedback, latency_ms,
                    full_response, chunks_used, agent_trace,
                )
                run_id = run.id if run else None
            except Exception as e:
                logger.warning("agent_run persist failed", error=str(e))
                run_id = None

            done_payload = json.dumps({
                "type": "done",
                "run_id": run_id,
                "agent_trace": agent_trace,
                "total_latency_ms": latency_ms,
                "total_tokens_in": sum(s["tokens_in"] for s in agent_trace),
                "total_tokens_out": sum(s["tokens_out"] for s in agent_trace),
            })
            yield f"data: {done_payload}\n\n"

        except Exception as e:
            logger.error("Stream error", error=str(e))
            msg = str(e)
            if "DeploymentNotFound" in msg or ("deployment" in msg.lower() and "not exist" in msg.lower()):
                msg = "AI model deployment not found. Check AZURE_OPENAI_DEPLOYMENT_GPT4O and AZURE_OPENAI_DEPLOYMENT_GPT4O_MINI env vars in Railway match your Azure deployment names."
            elif "AuthenticationError" in msg or "401" in msg:
                msg = "Azure OpenAI authentication failed. Check AZURE_OPENAI_API_KEY in Railway."
            elif "RateLimitError" in msg or "429" in msg:
                msg = "Azure OpenAI rate limit hit. Wait a moment and try again."
            yield f"data: {json.dumps({'type': 'error', 'message': msg})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


async def _persist_run(
    db, user, req, intent_type, sources_found, validation_ok,
    unsupported, vfeedback, latency_ms, full_response, chunks,
    agent_trace=None,
) -> AgentRun | None:
    """Write AgentRun + AgentSteps + RetrievedChunks to DB."""
    from app.llm.client import llm_client

    agent_trace = agent_trace or []
    total_in  = sum(s.get("tokens_in", 0)  for s in agent_trace) or count_tokens(req.query)
    total_out = sum(s.get("tokens_out", 0) for s in agent_trace) or count_tokens(full_response)

    run = AgentRun(
        user_id=user.id,
        notebook_id=req.notebook_id,
        query_text=req.query[:2000],
        intent_type=intent_type,
        sources_found=sources_found,
        validation_passed=validation_ok,
        unsupported_claims={"items": unsupported} if unsupported else None,
        validation_feedback=vfeedback,
        total_tokens_in=total_in,
        total_tokens_out=total_out,
        latency_ms=latency_ms,
        status=RunStatus.done,
        model_strong=llm_client.strong_model,
        model_fast=llm_client.fast_model,
        finished_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.flush()

    # Per-step metrics from agent_trace, with sensible fallback summaries
    _name_map = {
        "intent": AgentName.intent,
        "retrieval": AgentName.retrieval,
        "reasoning": AgentName.reasoning,
        "validation": AgentName.validation,
    }
    if agent_trace:
        for i, step in enumerate(agent_trace):
            db.add(AgentStep(
                agent_run_id=run.id,
                agent_name=_name_map.get(step.get("name"), AgentName.reasoning),
                step_order=i,
                latency_ms=int(step.get("latency_ms", 0)),
                tokens_in=int(step.get("tokens_in", 0)),
                tokens_out=int(step.get("tokens_out", 0)),
                output_summary=str(step.get("summary", ""))[:300],
            ))
    else:
        # Fallback: legacy lightweight summary if trace wasn't captured
        for i, (name, summary) in enumerate([
            (AgentName.intent,     intent_type[:200]),
            (AgentName.retrieval,  f"{sources_found} chunks"),
            (AgentName.reasoning,  full_response[:300]),
            (AgentName.validation, "PASSED" if validation_ok else f"FAILED: {(vfeedback or '')[:200]}"),
        ]):
            db.add(AgentStep(agent_run_id=run.id, agent_name=name, step_order=i, output_summary=summary))

    # Top-5 retrieved chunks
    for i, chunk in enumerate(chunks[:5]):
        text, score, meta = chunk if isinstance(chunk, tuple) else (str(chunk), 0.0, {})
        db.add(RetrievedChunk(
            agent_run_id=run.id,
            chunk_id=meta.get("id", f"{run.id}-{i}"),
            chunk_text_preview=str(text)[:300],
            score=float(score),
            layer=int(meta.get("layer", 0)),
            source=str(meta.get("source", "")),
            rank_position=i,
        ))

    # Async usage event via Celery
    try:
        from app.workers.tasks import record_usage
        record_usage.delay(
            user_id=user.id,
            event_type="query",
            tokens_in=run.total_tokens_in,
            tokens_out=run.total_tokens_out,
            agent_run_id=run.id,
        )
    except Exception:
        pass

    return run
