"""Notebook data endpoints: stats, map, conversations, health."""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import HealthResponse, MapNode, MapResponse, NotebookStatsResponse
from app.auth.dependencies import get_current_user
from app.cache.redis_cache import query_cache
from app.core.tracing import observability_status
from app.db.models import User
from app.db.session import get_db
from app.retrieval.vector_store import vector_store

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["system"])
async def health():
    try:
        n_collections = len(vector_store.list_notebooks())
    except Exception:
        n_collections = 0
    try:
        langfuse_ok = observability_status().get("langfuse_enabled", False)
    except Exception:
        langfuse_ok = False
    return HealthResponse(
        status="ok",
        redis=query_cache.is_available,
        chromadb_collections=n_collections,
        langfuse=langfuse_ok,
    )


@router.get("/notebook/{notebook_id}/stats", response_model=NotebookStatsResponse, tags=["notebook"])
async def notebook_stats(
    notebook_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession   = Depends(get_db),
):
    from collections import Counter
    # Empty notebooks return empty stats (200) instead of 404 — UI renders an empty state.
    try:
        nodes = vector_store.get_tree_nodes(notebook_id)
    except Exception:
        nodes = []
    layer_counts = Counter(n["layer"] for n in nodes)
    return NotebookStatsResponse(
        notebook_id=notebook_id,
        total_nodes=len(nodes),
        layer_breakdown={str(k): v for k, v in sorted(layer_counts.items())},
    )


@router.get("/notebook/{notebook_id}/map", response_model=MapResponse, tags=["notebook"])
async def notebook_map(
    notebook_id: str,
    include_full_text: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession   = Depends(get_db),
):
    # Empty notebooks return empty graph (200) so the UI can render "no data yet" cleanly.
    try:
        raw_nodes = vector_store.get_tree_nodes(notebook_id)
    except Exception:
        raw_nodes = []

    text_limit = None if include_full_text else 200
    nodes = [
        MapNode(
            id=n["id"],
            text=n["text"] if text_limit is None else n["text"][:text_limit],
            layer=n["layer"],
            children=n["children"],
            source=n["source"],
        )
        for n in raw_nodes
    ]
    child_to_parent = {}
    for node in raw_nodes:
        for child_id in node["children"]:
            if child_id:
                child_to_parent[child_id] = node["id"]
    edges = [{"from": pid, "to": cid} for cid, pid in child_to_parent.items()]
    return MapResponse(notebook_id=notebook_id, nodes=nodes, edges=edges)
