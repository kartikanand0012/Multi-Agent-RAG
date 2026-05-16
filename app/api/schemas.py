from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ── Request models ────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=2000)
    notebook_id: str = Field(default="default", min_length=1, max_length=64)
    stream: bool = Field(default=False)


# ── Response models ───────────────────────────────────────────────────────────

class QueryResponse(BaseModel):
    response: str
    intent_type: str
    sources_used: int
    validation_passed: bool
    retry_count: int
    trace_id: Optional[str] = None
    cached: bool = False


class UploadResponse(BaseModel):
    file: str
    notebook_id: str
    leaf_chunks: int
    total_nodes: int
    layer_breakdown: Dict[str, int]
    mode: str


class HealthResponse(BaseModel):
    status: str
    redis: bool
    chromadb_collections: int
    langfuse: bool


class NotebookStatsResponse(BaseModel):
    notebook_id: str
    total_nodes: int
    layer_breakdown: Dict[str, int]


class MapNode(BaseModel):
    id: str
    text: str
    layer: int
    children: List[str]
    source: str


class MapResponse(BaseModel):
    notebook_id: str
    nodes: List[MapNode]
    edges: List[Dict[str, str]]


class ErrorResponse(BaseModel):
    detail: str
    error_type: Optional[str] = None
