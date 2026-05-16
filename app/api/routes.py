from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.api.schemas import (
    HealthResponse, MapNode, MapResponse, NotebookStatsResponse,
    QueryRequest, QueryResponse, UploadResponse,
)
from app.cache.redis_cache import query_cache
from app.core.tracing import observability_status
from app.ingestion.pipeline import ingest_file
from app.orchestration.graph import query as run_query
from app.retrieval.vector_store import vector_store

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Health ────────────────────────────────────────────────────────────────────

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
    file: UploadFile = File(...),
    notebook_id: str = Form(default="default"),
    use_raptor: bool = Form(default=True),
):
    allowed = {".pdf", ".docx", ".xlsx", ".xls", ".txt", ".md", ".htm", ".html"}
    suffix = Path(file.filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {', '.join(allowed)}",
        )

    # Save upload to temp file then ingest
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        result = await ingest_file(tmp_path, notebook_id=notebook_id, use_raptor=use_raptor)
    finally:
        tmp_path.unlink(missing_ok=True)

    # Invalidate cached queries for this notebook since corpus changed
    query_cache.invalidate(notebook_id)

    return UploadResponse(
        file=file.filename,
        notebook_id=result["notebook_id"],
        leaf_chunks=result["leaf_chunks"],
        total_nodes=result["total_nodes"],
        layer_breakdown={str(k): v for k, v in result["layer_breakdown"].items()},
        mode=result["mode"],
    )


# ── Query ─────────────────────────────────────────────────────────────────────

@router.post("/query", response_model=QueryResponse, tags=["query"])
async def query(req: QueryRequest):
    if req.stream:
        raise HTTPException(
            status_code=400,
            detail="Use POST /query/stream for streaming responses.",
        )

    # Check cache first
    cached = query_cache.get(req.query, req.notebook_id)
    if cached:
        cached["cached"] = True
        return QueryResponse(**cached)

    if vector_store.count(req.notebook_id) == 0:
        raise HTTPException(
            status_code=404,
            detail=f"Notebook '{req.notebook_id}' has no documents. Upload files first.",
        )

    result = await run_query(req.query, notebook_id=req.notebook_id)

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
    return QueryResponse(**response_data)


@router.post("/query/stream", tags=["query"])
async def query_stream(req: QueryRequest):
    """Server-Sent Events streaming endpoint — tokens appear in real time."""
    if vector_store.count(req.notebook_id) == 0:
        raise HTTPException(
            status_code=404,
            detail=f"Notebook '{req.notebook_id}' has no documents.",
        )

    from app.agents.intent_agent import IntentAgent
    from app.agents.retrieval_agent import RetrievalAgent
    from app.agents.reasoning_agent import ReasoningAgent
    from app.agents.validation_agent import ValidationAgent
    from app.retrieval.bm25_retriever import BM25Retriever
    from app.api.main import get_bm25

    bm25 = get_bm25(req.notebook_id)
    intent_agent = IntentAgent()
    retrieval_agent = RetrievalAgent(vector_store, bm25)
    reasoning_agent = ReasoningAgent()
    validation_agent = ValidationAgent()

    async def event_generator():
        try:
            # Intent
            intent = await intent_agent.run(req.query)
            yield f"data: {json.dumps({'type': 'intent', 'intent_type': intent.intent_type})}\n\n"

            # Retrieval
            chunks = await retrieval_agent.run(intent, notebook_id=req.notebook_id)
            yield f"data: {json.dumps({'type': 'retrieval', 'sources_found': len(chunks)})}\n\n"

            # Reasoning — stream tokens
            full_response = ""
            async for token in reasoning_agent.stream(req.query, intent, chunks):
                full_response += token
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

            # Validation
            validation = await validation_agent.run(full_response, chunks)
            yield f"data: {json.dumps({'type': 'validation', 'passed': validation.passed})}\n\n"

            if not validation.passed:
                yield f"data: {json.dumps({'type': 'warning', 'message': 'Response could not be fully verified against source documents.'})}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ── Notebook management ───────────────────────────────────────────────────────

@router.get("/notebook/{notebook_id}/stats", response_model=NotebookStatsResponse, tags=["notebook"])
async def notebook_stats(notebook_id: str):
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
async def notebook_map(notebook_id: str):
    """
    Returns the RAPTOR knowledge graph for the notebook.
    Layer-0 = leaf chunks, Layer-1+ = cluster summaries.
    Use this to render the NotebookLM-style knowledge map.
    """
    raw_nodes = vector_store.get_tree_nodes(notebook_id)
    if not raw_nodes:
        raise HTTPException(status_code=404, detail=f"Notebook '{notebook_id}' not found or empty.")

    nodes = [
        MapNode(
            id=n["id"],
            text=n["text"][:200],
            layer=n["layer"],
            children=n["children"],
            source=n["source"],
        )
        for n in raw_nodes
    ]

    # Build edges from parent→child relationships
    edges = []
    child_to_parent = {}
    for node in raw_nodes:
        for child_id in node["children"]:
            if child_id:
                child_to_parent[child_id] = node["id"]

    edges = [
        {"from": parent_id, "to": child_id}
        for child_id, parent_id in child_to_parent.items()
    ]

    return MapResponse(notebook_id=notebook_id, nodes=nodes, edges=edges)


@router.delete("/notebook/{notebook_id}", tags=["notebook"])
async def delete_notebook(notebook_id: str):
    if vector_store.count(notebook_id) == 0:
        raise HTTPException(status_code=404, detail=f"Notebook '{notebook_id}' not found.")
    vector_store.delete_notebook(notebook_id)
    query_cache.invalidate(notebook_id)
    return {"message": f"Notebook '{notebook_id}' deleted.", "notebook_id": notebook_id}
