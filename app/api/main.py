"""FastAPI application — production-ready with auth, analytics, rate limiting."""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Dict

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api.admin_router import router as admin_router
from app.api.notebook_router import router as notebook_router
from app.api.routes import router as api_router
from app.auth.router import router as auth_router
from app.core.config import settings
from app.core.logging import logger as app_logger
from app.core.tracing import flush as flush_langfuse
from app.db.session import create_tables
from app.retrieval.bm25_retriever import BM25Retriever
from app.retrieval.vector_store import vector_store

logger = logging.getLogger(__name__)

# ── Rate limiter ──────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])

# ── BM25 registry ─────────────────────────────────────────────────────────────
_bm25_registry: Dict[str, BM25Retriever] = {}


def get_bm25(notebook_id: str) -> BM25Retriever:
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
        logger.info(f"BM25 built for '{notebook_id}': {len(nodes)} nodes")
    _bm25_registry[notebook_id] = bm25


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting Multi-Agent RAG Studio [{settings.environment}]")

    # Create DB tables on every startup (idempotent — won't overwrite existing data)
    await create_tables()

    # Build BM25 indexes for existing notebooks
    try:
        for name in vector_store.list_notebooks():
            notebook_id = name.removeprefix("rag-")
            _build_bm25(notebook_id)
        logger.info("BM25 indexes initialised")
    except Exception as e:
        logger.warning(f"BM25 pre-warm failed: {e}")

    # Compile LangGraph pipeline
    from app.orchestration.graph import get_graph
    get_graph()
    logger.info("LangGraph pipeline ready")

    yield

    logger.info("Shutting down...")
    flush_langfuse()


# ── App factory ────────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title="Multi-Agent RAG Studio",
        description="Production RAG with 4 AI agents, RAPTOR indexing, auth, and analytics.",
        version="2.0.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
    )

    # Rate limiter
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # CORS — use specific origins in production
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request logging + security headers
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        t0 = time.monotonic()
        try:
            response = await call_next(request)
        except Exception as exc:
            logger.error(f"Unhandled exception: {exc}", exc_info=True)
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": "Internal server error"},
            )
        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.info(
            f"{request.method} {request.url.path} "
            f"status={response.status_code} latency={latency_ms}ms"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    # Routers
    app.include_router(auth_router,     prefix="/api/v1")
    app.include_router(notebook_router, prefix="/api/v1")
    app.include_router(api_router,      prefix="/api/v1")
    app.include_router(admin_router,    prefix="/api/v1")

    return app


app = create_app()
