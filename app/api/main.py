"""FastAPI application entry point.

Lifecycle:
  startup  → build BM25 index from existing ChromaDB data, warm up graph
  shutdown → flush Langfuse, close Redis
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.logging import logger as app_logger
from app.core.tracing import flush as flush_langfuse
from app.retrieval.bm25_retriever import BM25Retriever
from app.retrieval.vector_store import vector_store

logger = logging.getLogger(__name__)

# Per-notebook BM25 index registry — populated at startup and on upload
_bm25_registry: Dict[str, BM25Retriever] = {}


def get_bm25(notebook_id: str) -> BM25Retriever:
    """Return BM25 index for a notebook, build it if missing."""
    if notebook_id not in _bm25_registry:
        _build_bm25(notebook_id)
    return _bm25_registry[notebook_id]


def _build_bm25(notebook_id: str) -> None:
    nodes = vector_store.get_tree_nodes(notebook_id)
    bm25 = BM25Retriever()
    if nodes:
        bm25.index(
            texts=[n["text"] for n in nodes],
            metadatas=[{"source": n["source"], "layer": n["layer"]} for n in nodes],
        )
        logger.info(f"BM25 index built for notebook '{notebook_id}': {len(nodes)} nodes")
    _bm25_registry[notebook_id] = bm25


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────────
    logger.info("Starting Multi-Agent RAG API...")

    # Build BM25 indexes for any existing notebooks
    try:
        existing = vector_store.list_notebooks()
        for name in existing:
            # ChromaDB collection names are prefixed with "rag-"
            notebook_id = name.replace("rag-", "", 1) if name.startswith("rag-") else name
            _build_bm25(notebook_id)
        logger.info(f"Initialized {len(existing)} notebook BM25 indexes")
    except Exception as e:
        logger.warning(f"BM25 pre-warm failed: {e}")

    # Warm up the LangGraph pipeline (compiles the graph)
    from app.orchestration.graph import get_graph
    get_graph()
    logger.info("LangGraph pipeline compiled and ready")

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────────
    logger.info("Shutting down...")
    flush_langfuse()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Multi-Agent RAG API",
        description=(
            "Production-grade Agentic RAG system with 4 specialized agents: "
            "Intent → Retrieval → Reasoning → Validation"
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router, prefix="/api/v1")
    return app


app = create_app()
