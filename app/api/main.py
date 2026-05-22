"""FastAPI application — Phase 2: Sentry, request IDs, agent singletons, quota."""
from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Dict

import structlog
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.admin_router import router as admin_router
from app.api.conversation_router import router as conversation_router
from app.api.notebook_router import router as notebook_router
from app.api.routes_query import router as query_router
from app.api.routes_upload import router as upload_router
from app.api.routes_notebook import router as nb_data_router
from app.auth.router import router as auth_router
from app.core.config import settings
from app.core.sentry import init_sentry
from app.core.tracing import flush as flush_langfuse
from app.middleware.request_id import RequestIDMiddleware
from app.retrieval.bm25_retriever import BM25Retriever
from app.retrieval.vector_store import vector_store

logger = structlog.get_logger(__name__)

# ── Rate limiter (per-user when authed, per-IP otherwise) ─────────────────────

def _rate_limit_key(request: Request) -> str:
    user = getattr(request.state, "user_id", None)
    return user or request.client.host or "unknown"


limiter = Limiter(key_func=_rate_limit_key, default_limits=["300/minute"])

# ── BM25 in-memory registry ───────────────────────────────────────────────────

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
        logger.info("BM25 built", notebook_id=notebook_id, nodes=len(nodes))
    _bm25_registry[notebook_id] = bm25


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting", environment=settings.environment)

    # Alembic now owns schema — create_tables is kept as a safety fallback
    try:
        from app.db.session import create_tables
        await create_tables()
        logger.info("DB ready")
    except Exception as e:
        logger.error("DB init failed (non-fatal)", error=str(e))

    try:
        for name in vector_store.list_notebooks():
            _build_bm25(name.removeprefix("rag-"))
        logger.info("BM25 indexes warmed")
    except Exception as e:
        logger.warning("BM25 pre-warm failed", error=str(e))

    # Pre-compile agent singletons — stored on app.state for route reuse
    try:
        from app.agents.intent_agent import IntentAgent
        from app.agents.retrieval_agent import RetrievalAgent
        from app.agents.reasoning_agent import ReasoningAgent
        from app.agents.validation_agent import ValidationAgent
        from app.orchestration.graph import get_graph

        app.state.agents = {
            "intent":     IntentAgent(),
            "retrieval":  RetrievalAgent(vector_store, get_bm25),
            "reasoning":  ReasoningAgent(),
            "validation": ValidationAgent(),
        }
        get_graph()
        logger.info("Agents + LangGraph ready")
    except Exception as e:
        logger.error("Agent init failed (non-fatal)", error=str(e))
        app.state.agents = {}

    yield

    logger.info("Shutting down")
    flush_langfuse()


# ── App factory ────────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    # Sentry must be first so all subsequent errors are captured
    init_sentry()

    app = FastAPI(
        title="Multi-Agent RAG Studio",
        version="2.0.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
    )

    # Rate limiter
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # Middleware (innermost → outermost, applied in reverse order)
    app.add_middleware(RequestIDMiddleware)
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
            logger.error("Unhandled exception", error=str(exc), exc_info=True)
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": "Internal server error"},
            )
        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.info(
            "request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            latency_ms=latency_ms,
            request_id=getattr(request.state, "request_id", None),
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    # Routers
    app.include_router(auth_router,         prefix="/api/v1")
    app.include_router(notebook_router,     prefix="/api/v1")   # notebook CRUD
    app.include_router(conversation_router, prefix="/api/v1")   # conversation history
    app.include_router(query_router,        prefix="/api/v1")   # query + stream
    app.include_router(upload_router,       prefix="/api/v1")   # upload + job status
    app.include_router(nb_data_router,      prefix="/api/v1")   # /notebook/{id}/stats + map
    app.include_router(admin_router,        prefix="/api/v1")

    return app


app = create_app()
