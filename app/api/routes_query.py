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

        try:
            intent = await intent_agent.run(req.query)
            intent_type = intent.intent_type
            yield f"data: {json.dumps({'type': 'intent', 'intent_type': intent.intent_type})}\n\n"

            chunks = await retrieval_agent.run(intent, notebook_id=req.notebook_id)
            chunks_used = chunks
            sources_found = len(chunks)
            yield f"data: {json.dumps({'type': 'retrieval', 'sources_found': sources_found})}\n\n"

            async for token in reasoning_agent.stream(req.query, intent, chunks):
                full_response += token
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

            validation = await validation_agent.run(full_response, chunks)
            validation_ok = validation.passed
            unsupported   = validation.unsupported_claims
            vfeedback     = validation.feedback
            yield f"data: {json.dumps({
                'type': 'validation',
                'passed': validation.passed,
                'unsupported_claims': unsupported,
                'feedback': vfeedback,
                'confidence': validation.confidence,
            })}\n\n"

            if not validation.passed:
                yield f"data: {json.dumps({'type': 'warning', 'message': 'Response could not be fully verified.'})}\n\n"

            latency_ms = int((time.monotonic() - t_start) * 1000)
            await increment_query_quota(current_user, db)

            # Persist agent_run + steps + chunks (best-effort)
            try:
                run = await _persist_run(
                    db, current_user, req, intent_type, sources_found,
                    validation_ok, unsupported, vfeedback, latency_ms,
                    full_response, chunks_used,
                )
                run_id = run.id if run else None
            except Exception as e:
                logger.warning("agent_run persist failed", error=str(e))
                run_id = None

            yield f"data: {json.dumps({'type': 'done', 'run_id': run_id})}\n\n"

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
) -> AgentRun | None:
    """Write AgentRun + AgentSteps + RetrievedChunks to DB."""
    from app.llm.client import llm_client

    run = AgentRun(
        user_id=user.id,
        notebook_id=req.notebook_id,
        query_text=req.query[:2000],
        intent_type=intent_type,
        sources_found=sources_found,
        validation_passed=validation_ok,
        unsupported_claims={"items": unsupported} if unsupported else None,
        validation_feedback=vfeedback,
        total_tokens_in=count_tokens(req.query),
        total_tokens_out=count_tokens(full_response),
        latency_ms=latency_ms,
        status=RunStatus.done,
        model_strong=llm_client.strong_model,
        model_fast=llm_client.fast_model,
        finished_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.flush()

    # One AgentStep per agent (lightweight summary only — full trace is in Langfuse)
    steps = [
        AgentStep(agent_run_id=run.id, agent_name=AgentName.intent,     step_order=0, output_summary=intent_type[:200]),
        AgentStep(agent_run_id=run.id, agent_name=AgentName.retrieval,  step_order=1, output_summary=f"{sources_found} chunks"),
        AgentStep(agent_run_id=run.id, agent_name=AgentName.reasoning,  step_order=2, output_summary=full_response[:300]),
        AgentStep(agent_run_id=run.id, agent_name=AgentName.validation, step_order=3,
                  output_summary="PASSED" if validation_ok else f"FAILED: {vfeedback[:200]}"),
    ]
    for s in steps:
        db.add(s)

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
