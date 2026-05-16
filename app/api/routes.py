"""Core RAG API routes — all notebook operations require authentication."""
from __future__ import annotations

import json
import logging
import tempfile
import time
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    HealthResponse, MapNode, MapResponse, NotebookStatsResponse,
    QueryRequest, QueryResponse, UploadResponse,
)
from app.auth.dependencies import get_current_user
from app.cache.redis_cache import query_cache
from app.core.tracing import observability_status
from app.db.models import Notebook, QueryEvent, UploadEvent, User
from app.db.session import get_db
from app.ingestion.pipeline import ingest_file
from app.llm.client import count_tokens
from app.orchestration.graph import query as run_query
from app.retrieval.vector_store import vector_store

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Ownership helper ──────────────────────────────────────────────────────────

async def _assert_owns(notebook_id: str, user: User, db: AsyncSession) -> None:
    """403 if the notebook doesn't belong to this user."""
    result = await db.execute(
        select(Notebook).where(Notebook.id == notebook_id, Notebook.user_id == user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Access denied to this notebook")


# ── Health (public) ────────────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse, tags=["system"])
async def health():
    try:
        collections = vector_store.list_notebooks()
        n_collections = len(collections)
    except Exception:
        n_collections = 0

    return HealthResponse(
        status="ok",
        redis=query_cache.is_available,
        chromadb_collections=n_collections,
        langfuse=observability_status()["langfuse_enabled"],
    )


# ── Upload ────────────────────────────────────────────────────────────────────

@router.post("/upload", response_model=UploadResponse, tags=["ingestion"])
async def upload(
    background_tasks: BackgroundTasks,
    file:        UploadFile = File(...),
    notebook_id: str        = Form(default="default"),
    use_raptor:  bool       = Form(default=True),
    current_user: User       = Depends(get_current_user),
    db: AsyncSession         = Depends(get_db),
):
    allowed = {".pdf", ".docx", ".xlsx", ".xls", ".txt", ".md", ".htm", ".html"}
    suffix = Path(file.filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported file type '{suffix}'.")

    await _assert_owns(notebook_id, current_user, db)

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    t0 = time.monotonic()
    try:
        result = await ingest_file(tmp_path, notebook_id=notebook_id, use_raptor=use_raptor)
    finally:
        tmp_path.unlink(missing_ok=True)

    processing_ms = int((time.monotonic() - t0) * 1000)
    query_cache.invalidate(notebook_id)

    # Update doc count on notebook
    nb_result = await db.execute(select(Notebook).where(Notebook.id == notebook_id))
    nb = nb_result.scalar_one_or_none()
    if nb:
        nb.doc_count = nb.doc_count + 1

    # Log upload event (background — no latency impact)
    event = UploadEvent(
        user_id=current_user.id,
        notebook_id=notebook_id,
        original_filename=file.filename or "unknown",
        file_size_bytes=len(content),
        total_nodes=result["total_nodes"],
        leaf_chunks=result["leaf_chunks"],
        use_raptor=use_raptor,
        processing_ms=processing_ms,
    )
    db.add(event)

    return UploadResponse(
        file=file.filename,
        notebook_id=result["notebook_id"],
        leaf_chunks=result["leaf_chunks"],
        total_nodes=result["total_nodes"],
        layer_breakdown={str(k): v for k, v in result["layer_breakdown"].items()},
        mode=result["mode"],
    )


# ── Query (non-streaming) ─────────────────────────────────────────────────────

@router.post("/query", response_model=QueryResponse, tags=["query"])
async def query(
    req: QueryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession   = Depends(get_db),
):
    if req.stream:
        raise HTTPException(status_code=400, detail="Use POST /query/stream for streaming.")

    await _assert_owns(req.notebook_id, current_user, db)

    cached = query_cache.get(req.query, req.notebook_id)
    if cached:
        cached["cached"] = True
        _log_query(db, current_user.id, req, cached, latency_ms=0, cached=True)
        return QueryResponse(**cached)

    if vector_store.count(req.notebook_id) == 0:
        raise HTTPException(status_code=404, detail=f"Notebook '{req.notebook_id}' has no documents.")

    t0 = time.monotonic()
    result = await run_query(req.query, notebook_id=req.notebook_id)
    latency_ms = int((time.monotonic() - t0) * 1000)

    response_data = {
        "response": result["response"],
        "intent_type": result["intent_type"],
        "sources_used": result["sources_used"],
        "validation_passed": result["validation_passed"],
        "retry_count": result["retry_count"],
        "trace_id": result.get("trace_id"),
        "cached": False,
    }
    query_cache.set(req.query, req.notebook_id, response_data)
    _log_query(db, current_user.id, req, response_data, latency_ms=latency_ms, cached=False)

    return QueryResponse(**response_data)


# ── Streaming query ────────────────────────────────────────────────────────────

@router.post("/query/stream", tags=["query"])
async def query_stream(
    req: QueryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession   = Depends(get_db),
):
    await _assert_owns(req.notebook_id, current_user, db)

    if vector_store.count(req.notebook_id) == 0:
        raise HTTPException(status_code=404, detail=f"Notebook '{req.notebook_id}' has no documents.")

    from app.agents.intent_agent import IntentAgent
    from app.agents.retrieval_agent import RetrievalAgent
    from app.agents.reasoning_agent import ReasoningAgent
    from app.agents.validation_agent import ValidationAgent
    from app.retrieval.bm25_retriever import BM25Retriever
    from app.api.main import get_bm25

    bm25             = get_bm25(req.notebook_id)
    intent_agent     = IntentAgent()
    retrieval_agent  = RetrievalAgent(vector_store, bm25)
    reasoning_agent  = ReasoningAgent()
    validation_agent = ValidationAgent()

    t_start = time.monotonic()

    async def event_generator():
        intent_type    = "factual_lookup"
        sources_found  = 0
        validation_ok  = True
        full_response  = ""

        try:
            intent = await intent_agent.run(req.query)
            intent_type = intent.intent_type
            yield f"data: {json.dumps({'type': 'intent', 'intent_type': intent.intent_type})}\n\n"

            chunks = await retrieval_agent.run(intent, notebook_id=req.notebook_id)
            sources_found = len(chunks)
            yield f"data: {json.dumps({'type': 'retrieval', 'sources_found': sources_found})}\n\n"

            async for token in reasoning_agent.stream(req.query, intent, chunks):
                full_response += token
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

            validation = await validation_agent.run(full_response, chunks)
            validation_ok = validation.passed
            yield f"data: {json.dumps({'type': 'validation', 'passed': validation.passed})}\n\n"

            if not validation.passed:
                yield f"data: {json.dumps({'type': 'warning', 'message': 'Response could not be fully verified.'})}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        finally:
            # Persist analytics (best-effort — don't raise if it fails)
            try:
                latency_ms = int((time.monotonic() - t_start) * 1000)
                tokens = count_tokens(req.query) + count_tokens(full_response)
                event = QueryEvent(
                    user_id=current_user.id,
                    notebook_id=req.notebook_id,
                    query_text=req.query[:1000],
                    intent_type=intent_type,
                    sources_found=sources_found,
                    tokens_estimated=tokens,
                    validation_passed=validation_ok,
                    latency_ms=latency_ms,
                )
                async with db.begin():
                    db.add(event)
            except Exception as ex:
                logger.warning(f"Analytics log failed: {ex}")

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ── Notebook data endpoints (read-only, auth required) ───────────────────────

@router.get("/notebook/{notebook_id}/stats", response_model=NotebookStatsResponse, tags=["notebook"])
async def notebook_stats(
    notebook_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession   = Depends(get_db),
):
    await _assert_owns(notebook_id, current_user, db)
    nodes = vector_store.get_tree_nodes(notebook_id)
    if not nodes:
        raise HTTPException(status_code=404, detail=f"Notebook '{notebook_id}' not found or empty.")

    from collections import Counter
    layer_counts = Counter(n["layer"] for n in nodes)
    return NotebookStatsResponse(
        notebook_id=notebook_id,
        total_nodes=len(nodes),
        layer_breakdown={str(k): v for k, v in sorted(layer_counts.items())},
    )


@router.get("/notebook/{notebook_id}/map", response_model=MapResponse, tags=["notebook"])
async def notebook_map(
    notebook_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession   = Depends(get_db),
):
    await _assert_owns(notebook_id, current_user, db)
    raw_nodes = vector_store.get_tree_nodes(notebook_id)
    if not raw_nodes:
        raise HTTPException(status_code=404, detail=f"Notebook '{notebook_id}' not found or empty.")

    nodes = [
        MapNode(
            id=n["id"], text=n["text"][:200], layer=n["layer"],
            children=n["children"], source=n["source"],
        )
        for n in raw_nodes
    ]

    child_to_parent = {}
    for node in raw_nodes:
        for child_id in node["children"]:
            if child_id:
                child_to_parent[child_id] = node["id"]

    edges = [{"from": parent_id, "to": child_id} for child_id, parent_id in child_to_parent.items()]
    return MapResponse(notebook_id=notebook_id, nodes=nodes, edges=edges)


@router.delete("/notebook/{notebook_id}", tags=["notebook"])
async def delete_notebook_legacy(
    notebook_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession   = Depends(get_db),
):
    """Legacy endpoint — prefer DELETE /api/v1/notebooks/{id}."""
    await _assert_owns(notebook_id, current_user, db)
    if vector_store.count(notebook_id) == 0:
        raise HTTPException(status_code=404, detail=f"Notebook '{notebook_id}' not found.")
    vector_store.delete_notebook(notebook_id)
    query_cache.invalidate(notebook_id)
    return {"message": f"Notebook '{notebook_id}' deleted.", "notebook_id": notebook_id}


# ── Internal helpers ───────────────────────────────────────────────────────────

def _log_query(db, user_id, req, result, latency_ms, cached):
    """Fire-and-forget analytics log for non-streaming queries."""
    import asyncio
    async def _insert():
        tokens = count_tokens(req.query) + count_tokens(result.get("response", ""))
        event = QueryEvent(
            user_id=user_id,
            notebook_id=req.notebook_id,
            query_text=req.query[:1000],
            intent_type=result.get("intent_type", "unknown"),
            sources_found=result.get("sources_used", 0),
            tokens_estimated=tokens,
            validation_passed=result.get("validation_passed", True),
            retry_count=result.get("retry_count", 0),
            cached=cached,
            latency_ms=latency_ms,
        )
        db.add(event)
    asyncio.create_task(_insert())
