# Multi-Agent RAG Studio — Complete Technical Documentation

> **Version:** 1.0.0  
> **Stack:** FastAPI · LangGraph · ChromaDB · BM25 · React 19 · Vite  
> **Architecture:** 4-agent pipeline (Intent → Retrieval → Reasoning → Validation) with RAPTOR hierarchical indexing

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [System Architecture](#2-system-architecture)
3. [Technology Stack](#3-technology-stack)
4. [Complete File Reference](#4-complete-file-reference)
5. [Backend Deep-Dive](#5-backend-deep-dive)
   - 5.1 [RAPTOR Ingestion Pipeline](#51-raptor-ingestion-pipeline)
   - 5.2 [Intent Agent](#52-intent-agent)
   - 5.3 [Retrieval Agent (CRAG + VOTE-RAG)](#53-retrieval-agent-crag--vote-rag)
   - 5.4 [Reasoning Agent](#54-reasoning-agent)
   - 5.5 [Validation Agent](#55-validation-agent)
   - 5.6 [Vector Store & Hybrid Search](#56-vector-store--hybrid-search)
   - 5.7 [LangGraph Orchestration](#57-langgraph-orchestration)
   - 5.8 [API Endpoints](#58-api-endpoints)
6. [Frontend Deep-Dive](#6-frontend-deep-dive)
7. [Data Flow](#7-data-flow)
   - 7.1 [Upload Flow](#71-upload-flow)
   - 7.2 [Query Flow](#72-query-flow)
8. [Configuration Reference](#8-configuration-reference)
9. [Running Locally](#9-running-locally)
10. [Testing](#10-testing)
11. [Deployment](#11-deployment)
    - 11.1 [Docker Compose (Self-hosted)](#111-docker-compose-self-hosted)
    - 11.2 [Railway (Easiest — share with friends)](#112-railway-easiest--share-with-friends)
    - 11.3 [Render](#113-render)
    - 11.4 [Fly.io](#114-flyio)
    - 11.5 [Manual VPS / Cloud VM](#115-manual-vps--cloud-vm)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. Project Overview

**Multi-Agent RAG Studio** is a production-grade Retrieval-Augmented Generation system that uses four specialised AI agents working in a pipeline to answer questions about uploaded documents with high accuracy and transparency.

### What makes it different from basic RAG

| Basic RAG | Multi-Agent RAG Studio |
|-----------|----------------------|
| Single vector similarity search | Hybrid search (vector + BM25 keyword) |
| Flat chunk indexing | RAPTOR hierarchical tree (leaf → cluster → global summaries) |
| Direct LLM call | 4-agent pipeline with validation |
| No quality control | CRAG grader rejects irrelevant chunks |
| Single query | VOTE-RAG (3 query variations run in parallel) |
| No re-ranking | Corrective RAG rewrites bad queries (up to 2×) |

### Core user journey

1. Create a **notebook** (isolated knowledge space)
2. **Upload** PDFs, Word docs, Excel, HTML, or plain text
3. System builds a **RAPTOR knowledge tree** (5–15 seconds per MB)
4. **Ask questions** — the 4-agent pipeline retrieves, reasons, validates
5. Explore the **Knowledge Map** — interactive graph of the RAPTOR tree
6. Review **agent traces** per answer

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Browser (React)                          │
│  Sidebar │ Chat │ Knowledge Map │ Stats │ Sources │ Settings     │
└────────────────────────┬────────────────────────────────────────┘
                         │  HTTP / SSE (EventSource)
┌────────────────────────▼────────────────────────────────────────┐
│                     FastAPI Backend (:8000)                       │
│  POST /upload   POST /query   POST /query/stream   GET /map      │
└──┬──────────────────────────────────────────────────────────────┘
   │
   ├─── LangGraph Pipeline (graph.py) ──────────────────────────────┐
   │    Intent Agent → Retrieval Agent → Reasoning Agent → Validation│
   └────────────────────────────────────────────────────────────────┘
   │
   ├─── ChromaDB (PersistentClient) ── per-notebook collections
   │    • text embeddings (text-embedding-3-large, 3072 dims)
   │    • RAPTOR tree nodes (layer 0/1/2)
   │
   ├─── BM25 Index (in-memory, rebuilt on startup)
   │
   ├─── Redis (optional) ── query result cache (1h TTL)
   │
   └─── OpenAI / Azure OpenAI ── LLM calls (GPT-4o, GPT-4o-mini)
```

### Notebook isolation

Each notebook maps to its own ChromaDB **collection** (`rag-{notebook-id}`). Documents from different notebooks never mix in retrieval — the same architecture as Google NotebookLM.

---

## 3. Technology Stack

### Backend

| Package | Version | Purpose |
|---------|---------|---------|
| `fastapi` | 0.115 | REST API framework |
| `uvicorn[standard]` | 0.32 | ASGI server |
| `langgraph` | 0.2.73 | Agent orchestration graph |
| `langchain` | 0.3.25 | LLM abstractions |
| `langchain-openai` | 0.2.14 | OpenAI/Azure chat + embeddings |
| `openai` | 1.82 | Direct SDK (streaming) |
| `chromadb` | 0.5.23 | Vector store (local, persistent) |
| `rank-bm25` | 0.2.2 | Keyword search |
| `umap-learn` | 0.5.7 | Dimensionality reduction for RAPTOR |
| `scikit-learn` | 1.5.2 | K-means clustering for RAPTOR |
| `pypdf` | 5.1 | PDF text extraction |
| `python-docx` | 1.1.2 | Word document parsing |
| `openpyxl` | 3.1.5 | Excel parsing |
| `langfuse` | optional | LLM observability / tracing |
| `redis` | optional | Query caching |
| `tiktoken` | — | Token counting |
| `tenacity` | — | Retry with exponential backoff |

### Frontend

| Package | Version | Purpose |
|---------|---------|---------|
| `react` | 19 | UI framework |
| `react-dom` | 19 | DOM renderer |
| `vite` | 8 | Build tool / dev server |
| `axios` | 1.16 | HTTP client |

---

## 4. Complete File Reference

```
multi-agent-rag/
├── app/                          # FastAPI backend
│   ├── api/
│   │   ├── main.py               # App factory, startup/shutdown lifecycle
│   │   ├── routes.py             # All HTTP endpoints (upload, query, map, etc.)
│   │   └── schemas.py            # Pydantic request/response models
│   ├── agents/
│   │   ├── intent_agent.py       # Agent 1: classify query intent
│   │   ├── retrieval_agent.py    # Agent 2: CRAG + VOTE-RAG retrieval
│   │   ├── reasoning_agent.py    # Agent 3: synthesise answer
│   │   └── validation_agent.py   # Agent 4: fact-check against sources
│   ├── ingestion/
│   │   ├── pipeline.py           # Orchestrates parse → chunk → embed → store
│   │   ├── chunker.py            # Recursive text splitter, structured chunking
│   │   ├── raptor.py             # RAPTOR tree builder (cluster → summarise)
│   │   └── loaders.py            # File format handlers (PDF, DOCX, XLSX, etc.)
│   ├── retrieval/
│   │   ├── vector_store.py       # ChromaDB wrapper, per-notebook collections
│   │   ├── bm25_retriever.py     # BM25 keyword search
│   │   ├── hybrid_search.py      # Fuse vector + BM25 with RRF
│   │   └── grader.py             # CRAG relevance grader
│   ├── llm/
│   │   ├── client.py             # LLMClient: complete(), stream(), embed()
│   │   └── prompts.py            # All prompt templates
│   ├── orchestration/
│   │   └── graph.py              # LangGraph state machine
│   ├── cache/
│   │   └── redis_cache.py        # Redis query cache
│   └── core/
│       ├── config.py             # Settings (pydantic-settings, reads .env)
│       ├── exceptions.py         # Custom exception types
│       ├── logging.py            # Structured logging setup
│       └── tracing.py            # Langfuse integration
├── frontend/
│   ├── src/
│   │   ├── App.jsx               # Root: routing, notebook state, modals
│   │   ├── main.jsx              # React DOM entry point
│   │   ├── styles.css            # All CSS (design tokens, components, responsive)
│   │   ├── components/
│   │   │   ├── Sidebar.jsx       # Left nav: notebook list, health, settings button
│   │   │   ├── NotebookView.jsx  # Chat column + resizable right panel
│   │   │   ├── KnowledgeMap.jsx  # SVG graph: zoom/pan/click nodes & edges
│   │   │   ├── AgentTrace.jsx    # Collapsible agent pipeline trace per message
│   │   │   ├── Dashboard.jsx     # Home/empty state with feature cards
│   │   │   ├── UploadModal.jsx   # File upload modal with RAPTOR toggle
│   │   │   ├── Settings.jsx      # System health, model config, danger zone
│   │   │   └── Icons.jsx         # SVG icon registry (Lucide-style)
│   │   └── services/
│   │       └── api.js            # All API calls + SSE streaming client
│   ├── index.html                # Vite HTML template
│   ├── vite.config.js            # Vite config
│   └── package.json
├── docker/
│   ├── Dockerfile                # Multi-stage: builder (pip) + runtime
│   ├── docker-compose.yml        # Full stack: redis + app + frontend + nginx
│   └── nginx.conf                # Serves React, proxies /api/ to FastAPI
├── tests/                        # pytest test suite
├── scripts/                      # Helper scripts (seed data, health checks)
├── requirements.txt              # Python dependencies
├── pyproject.toml                # Project metadata
└── .env.example                  # Environment variable template
```

---

## 5. Backend Deep-Dive

### 5.1 RAPTOR Ingestion Pipeline

**File:** `app/ingestion/pipeline.py`, `app/ingestion/raptor.py`

RAPTOR (Recursive Abstractive Processing for Tree-Organized Retrieval) builds a multi-level knowledge tree from raw documents.

```
Raw document
    │
    ▼ parse (loaders.py)
Plain text
    │
    ▼ chunk (chunker.py) — 500 tokens, 100 overlap
Layer 0: Leaf chunks  [chunk_0, chunk_1, ..., chunk_N]
    │
    ▼ embed + cluster (UMAP → K-means)
    ▼ summarise each cluster (GPT-4o-mini)
Layer 1: Cluster summaries  [summary_A, summary_B, ..., summary_K]
    │
    ▼ embed + cluster again
    ▼ summarise each cluster (GPT-4o-mini)
Layer 2: Top-level summaries  [global_X, global_Y, ...]
    │
    ▼ all layers stored in ChromaDB with metadata {layer, source, children}
```

**Why RAPTOR matters:** When you ask "what is the main theme of this document?", a leaf-only RAG retrieves random chunks and misses the big picture. RAPTOR's L2 nodes answer global questions; L0 nodes answer specific factual questions. The retrieval agent searches across all layers simultaneously.

**Chunker (`chunker.py`):**
- Uses `RecursiveCharacterTextSplitter` with token counting via `tiktoken`
- Respects document structure (headers, paragraphs before hard cuts)
- Each chunk carries metadata: `source`, `layer`, `chunk_id`

**RAPTOR builder (`raptor.py`):**
1. Embed all chunks → high-dimensional vectors
2. UMAP → reduce to 10D for clustering
3. K-means with automatic K selection (elbow method)
4. Call GPT-4o-mini to summarise each cluster → Layer 1 nodes
5. Repeat steps 1-4 on Layer 1 → Layer 2 nodes
6. Build parent-child edge map stored in node metadata

### 5.2 Intent Agent

**File:** `app/agents/intent_agent.py`

The first agent in the pipeline. Classifies the user's query and decomposes complex questions.

**Output:**
```python
@dataclass
class IntentResult:
    intent_type: str     # "factual_lookup" | "analytical" | "comparison" | "summary"
    sub_queries: list[str]  # 1–3 decomposed questions
    requires_sql: bool   # True if query is about structured data
    confidence: float    # 0.0–1.0
```

**Example:**
- Input: *"Compare the revenue growth of APAC vs EMEA and explain the key drivers"*
- Output: `intent_type="comparison"`, `sub_queries=["APAC revenue growth", "EMEA revenue growth", "key revenue drivers"]`

This decomposition means three parallel retrieval chains run, returning more comprehensive results than a single query.

### 5.3 Retrieval Agent (CRAG + VOTE-RAG)

**File:** `app/agents/retrieval_agent.py`

The most complex agent. Combines three advanced RAG techniques:

**VOTE-RAG (Query Variation):**
```
Original query: "What is Kartik's background?"
         │
         ├─ Variation 1: "Who is Kartik and what is he known for?"
         ├─ Variation 2: "Kartik's professional history and achievements"
         └─ Variation 3: (original)
         │
         ▼ 3 parallel hybrid searches → merge → deduplicate
```
Running multiple phrasings improves recall by ~25–40% (one phrasing may match vocabulary in the document better).

**Hybrid Search (in `hybrid_search.py`):**
```
Query → Vector search (ChromaDB cosine similarity, top-k=5)
      → BM25 keyword search (rank-bm25, top-k=5)
      → Reciprocal Rank Fusion (RRF)
      → Fused top-5 results
```

**CRAG (Corrective RAG) — the grader loop:**
```
Retrieved chunks
      │
      ▼ grade_all() — each chunk graded by GPT-4o-mini
      │   Returns: "Correct" | "Incorrect" | "Ambiguous" per chunk
      │
      ├─ Majority Correct → return filter_relevant(grades)
      │
      └─ Majority Incorrect + attempt < 2 → rewrite query → retry
                │
                ▼ _rewrite_query() (GPT-4o-mini)
                → run _retrieve_with_grading() again
```

**Fallback:** After 2 rewrites, if still 0 relevant chunks, returns top-k by retrieval score marked as `Ambiguous` (prevents empty responses).

### 5.4 Reasoning Agent

**File:** `app/agents/reasoning_agent.py`

Uses GPT-4o to synthesise a grounded answer from retrieved chunks.

**Prompt structure:**
```
SYSTEM: You are a precise analytical assistant.
        Answer using ONLY the provided context.
        Cite every claim with [Source N].

USER:   [Source 1 — file.pdf (source)]
        <chunk text>
        ---
        [Source 2 — file.pdf (summary)]
        <chunk text>
        ---
        Question: {user_query}
```

**Streaming:** For the `/query/stream` endpoint, this agent uses `async for token in llm_client.stream(...)` which yields tokens via OpenAI's `stream=True` SSE API, forwarded to the browser as Server-Sent Events.

### 5.5 Validation Agent

**File:** `app/agents/validation_agent.py`

Final quality gate. Checks whether the reasoning agent's answer is actually supported by the retrieved chunks.

- Passes: answer is grounded in sources → `validation.passed = True`
- Fails: answer contains hallucinated claims → `validation.passed = False` + frontend shows "Unverified" badge

### 5.6 Vector Store & Hybrid Search

**File:** `app/retrieval/vector_store.py`

**Collection naming:** `rag-{notebook-id}` (alphanumeric + hyphens, 3–63 chars — ChromaDB constraint).

```python
# Per-notebook isolation — same pattern as NotebookLM
col = self._client.get_or_create_collection(
    name=_collection_name(notebook_id),
    metadata={"hnsw:space": "cosine"},
)
```

**Embedding model:** `text-embedding-3-large` (3072 dimensions) on OpenAI, or Azure equivalent. Every node in the RAPTOR tree is embedded — including summaries — so semantic search works at all abstraction levels.

**BM25 (`bm25_retriever.py`):** In-memory index rebuilt at startup from ChromaDB. Complements vector search for exact keyword matches (names, codes, abbreviations that embeddings blur).

**RRF fusion (`hybrid_search.py`):**
```python
score = 1/(k + vector_rank) + 1/(k + bm25_rank)  # k=60
```
Merges both ranking lists without needing score normalisation.

### 5.7 LangGraph Orchestration

**File:** `app/orchestration/graph.py`

The 4 agents are wired as a directed graph using LangGraph:

```
START → intent_node → retrieval_node → reasoning_node → validation_node → END
```

Each node receives the `RAGState` TypedDict and appends its output. LangGraph handles the async execution, state passing, and error propagation between nodes.

### 5.8 API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/health` | Checks Redis, Langfuse, ChromaDB collections |
| `POST` | `/api/v1/upload` | Upload file, run ingestion, return chunk counts |
| `POST` | `/api/v1/query` | Non-streaming query, returns full response |
| `POST` | `/api/v1/query/stream` | SSE streaming — yields intent/retrieval/token/validation events |
| `GET` | `/api/v1/notebook/{id}/stats` | Layer breakdown (total nodes, L0/L1/L2 counts) |
| `GET` | `/api/v1/notebook/{id}/map` | Full RAPTOR tree (nodes + edges) for visualisation |
| `DELETE` | `/api/v1/notebook/{id}` | Delete collection + invalidate cache |

**SSE event stream format:**
```
data: {"type": "intent",      "intent_type": "factual_lookup"}
data: {"type": "retrieval",   "sources_found": 5}
data: {"type": "token",       "content": "Kartik "}
data: {"type": "token",       "content": "is a "}
...
data: {"type": "validation",  "passed": true}
data: {"type": "done"}
```

---

## 6. Frontend Deep-Dive

### `App.jsx` — Root component
Manages global state: active notebook, routing (`home` / `notebook` / `settings`), and the upload modal. Notebooks are persisted to `localStorage` so they survive page refresh.

### `Sidebar.jsx`
- Lists all notebooks with doc count badge
- Hover reveals delete button (absolute-positioned, padding-right: 36px prevents overlap)
- Footer shows system health dot + version + settings gear

### `NotebookView.jsx`
The main workspace. Two columns:
- **Left (chat-col):** message history, streaming pipeline indicator, input bar
- **Resize handle:** 5px draggable divider — drag left to widen the right panel (desktop only, 300–720px range)
- **Right (right-col):** tabs for Knowledge Map / Stats / Sources

Key behaviours:
- `streamQuery()` reads SSE events and progressively updates UI (pipeline stages light up green as they complete)
- Source citations `[Source N]` in answers are clickable — clicking opens the Sources tab
- `fetchStats()` called on notebook change to populate the stats tab

### `KnowledgeMap.jsx`
SVG-based interactive graph with three rendering layers:

**Layout algorithm:**
```
L2 nodes → centre (small cluster if >1)
L1 nodes → inner ring at radius 155
L0 nodes → outer ring at radius 234, SORTED by parent L1 index
           (siblings adjacent = visible grouping without explicit borders)
```

**Zoom:** `wheel` event on wrapper `div` (`passive: false`). Mouse position in SVG viewBox coordinates used to zoom towards cursor. Scale range: 0.2× – 7×.

**Pan:** `mousedown` on background/edges starts drag; `mousemove` updates `translate`.

**Selection states:**
- No selection: L2→L1 edges shown; L1→L0 edges hidden
- Node selected: neighbors highlighted, non-related nodes dimmed (10% opacity), L1→L0 edges for selected node revealed
- Edge selected: orange highlight, both endpoint nodes highlighted, edge detail shown

**Detail panel tabs:**
- *Node Info:* layer, source file, node description, full chunk text
- *Connections:* clickable parent + child nodes (click to jump to that node)
- *Edge Info:* relationship type label, both endpoint text previews

### `AgentTrace.jsx`
Collapsible trace showing each agent's result, timing, and badges. Shown per-message after streaming completes.

### `UploadModal.jsx`
Drag-and-drop or file-picker upload. Supports multi-file. RAPTOR toggle (on by default). Shows progress bars for each processing stage. Posts to `/api/v1/upload`.

### `Settings.jsx`
- **API Connection Status:** measures real round-trip latency on mount
- **Model Configuration:** shows current model names, chunk size, retry config
- **Danger Zone:** "Clear all data" with two-step confirmation

### `api.js` — Service layer
- `fetchHealth()` — GET /health
- `uploadFile(file, notebookId, useRaptor)` — multipart POST
- `streamQuery(query, notebookId, callbacks)` — fetch + ReadableStream; returns AbortController
- `fetchStats(id)`, `fetchMap(id)`, `deleteNotebook(id)`

---

## 7. Data Flow

### 7.1 Upload Flow

```
Browser: user drops file.pdf
  │
  ▼ POST /api/v1/upload (multipart)
  │
  ▼ routes.py: save to /tmp, call ingest_file()
  │
  ▼ pipeline.py:
  │   1. loaders.py → extract text (pypdf / python-docx / openpyxl)
  │   2. chunker.py → split into 500-token chunks → Layer 0 chunks
  │   3. raptor.py (if use_raptor=True):
  │       a. embed all L0 chunks (text-embedding-3-large)
  │       b. UMAP(n_components=10) → reduce dimensionality
  │       c. KMeans(k=auto) → cluster
  │       d. GPT-4o-mini → summarise each cluster → Layer 1 nodes
  │       e. repeat on L1 → Layer 2 nodes
  │       f. build children metadata (parent → [child_ids])
  │   4. vector_store.add_documents() → upsert all nodes to ChromaDB
  │
  ▼ response: { leaf_chunks, total_nodes, layer_breakdown, mode }
```

### 7.2 Query Flow

```
Browser: user types "Who is Kartik?"
  │
  ▼ POST /api/v1/query/stream (SSE)
  │
  ▼ Intent Agent:
  │   prompt GPT-4o-mini → { intent_type: "factual_lookup", sub_queries: ["Who is Kartik?"] }
  │   SSE: {"type":"intent","intent_type":"factual_lookup"}
  │
  ▼ Retrieval Agent (per sub_query):
  │   1. generate 2 query variations (GPT-4o-mini)
  │   2. 3 parallel hybrid searches (vector + BM25)
  │   3. merge + deduplicate
  │   4. CRAG grade each chunk (GPT-4o-mini × N)
  │   5. if majority Incorrect → rewrite → retry (max 2×)
  │   6. filter_relevant() → top chunks
  │   SSE: {"type":"retrieval","sources_found":5}
  │
  ▼ Reasoning Agent:
  │   stream GPT-4o with numbered context chunks
  │   SSE: {"type":"token","content":"Kartik "} × many
  │
  ▼ Validation Agent:
  │   GPT-4o-mini verifies answer vs. sources
  │   SSE: {"type":"validation","passed":true}
  │   SSE: {"type":"done"}
```

---

## 8. Configuration Reference

All configuration via environment variables. Copy `.env.example` to `.env`.

### Required

| Variable | Description | Example |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key | `sk-...` |

### Optional — Azure OpenAI (use instead of OpenAI)

| Variable | Description |
|----------|-------------|
| `AZURE_OPENAI_API_KEY` | Azure key |
| `AZURE_OPENAI_ENDPOINT` | `https://yourresource.openai.azure.com/` |
| `AZURE_OPENAI_API_VERSION` | e.g. `2024-02-01` |
| `AZURE_DEPLOYMENT_GPT4O` | Deployment name for GPT-4o |
| `AZURE_DEPLOYMENT_GPT4O_MINI` | Deployment name for GPT-4o-mini |
| `AZURE_DEPLOYMENT_EMBEDDING` | Deployment name for embedding model |

### Infrastructure

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `None` (disabled) | `redis://localhost:6379` |
| `CHROMA_PERSIST_DIR` | `./chroma_db` | Where ChromaDB stores data |
| `LANGFUSE_PUBLIC_KEY` | `None` | Langfuse observability |
| `LANGFUSE_SECRET_KEY` | `None` | Langfuse secret |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | Langfuse host |

### Frontend

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_URL` | `http://localhost:8000/api/v1` | Backend URL (set at build time) |

---

## 9. Running Locally

### Prerequisites

- Python 3.11+
- Node.js 20+
- An OpenAI API key (or Azure OpenAI credentials)
- Redis (optional, for caching)

### Step 1 — Clone and configure

```bash
git clone <your-repo>
cd multi-agent-rag
cp .env.example .env
# Edit .env — add OPENAI_API_KEY at minimum
```

### Step 2 — Backend

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# Install dependencies (~2 min first time, umap-learn compiles)
pip install -r requirements.txt

# Start the API server
uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000
```

The API is now at `http://localhost:8000`. Docs at `http://localhost:8000/docs`.

### Step 3 — Frontend

```bash
cd frontend
npm install
npm run dev
```

The app is now at `http://localhost:5173`.

### Step 4 — Verify

1. Open `http://localhost:5173`
2. Click **Settings** → check API Connection Status shows green
3. Click **New Notebook** → upload a PDF
4. Wait for ingestion (watch the terminal for RAPTOR logs)
5. Type a question → answer should stream in

---

## 10. Testing

### Run the test suite

```bash
# From project root with venv active
pytest tests/ -v

# With coverage
pytest tests/ --cov=app --cov-report=html
```

### Manual API testing

```bash
# Health check
curl http://localhost:8000/api/v1/health

# Upload a document
curl -X POST http://localhost:8000/api/v1/upload \
  -F "file=@/path/to/document.pdf" \
  -F "notebook_id=test-notebook" \
  -F "use_raptor=true"

# Query (non-streaming)
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the main topic?", "notebook_id": "test-notebook"}'

# Query (streaming) — watch SSE events
curl -X POST http://localhost:8000/api/v1/query/stream \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the main topic?", "notebook_id": "test-notebook"}' \
  --no-buffer
```

### What to test

| Test case | Expected behaviour |
|-----------|-------------------|
| Upload PDF | `total_nodes > 0`, `layer_breakdown` shows L0/L1/L2 |
| Upload same PDF twice | Chunks upserted (no duplicates) |
| Query before upload | HTTP 404 "Notebook has no documents" |
| Simple factual query | Answer cites `[Source N]`, validation passes |
| Complex/ambiguous query | May trigger CRAG rewrites (check backend logs) |
| Knowledge Map | Nodes render in 3 concentric rings; click node shows text |
| Sources tab | Lists filenames with chunk counts |
| Settings page | Latency shows ms value, not `—` |

---

## 11. Deployment

### 11.1 Docker Compose (Self-hosted)

The fastest way to run the full stack locally or on a VM.

```bash
# Build and start everything
cd docker
docker compose up --build

# First run takes ~5 min (pip install + npm build)
# After that:
#   Frontend: http://localhost:3000
#   Backend:  http://localhost:8000
#   API docs: http://localhost:8000/docs
```

**Environment:** Docker Compose reads `.env` from the project root. Create it before running:

```bash
cp .env.example .env
# Edit .env with your API keys
```

**Volumes:**
- `chroma_data` — ChromaDB persists across container restarts
- `redis_data` — Redis cache persists

**Stop:**
```bash
docker compose down          # keep data
docker compose down -v       # wipe data volumes too
```

---

### 11.2 Railway (Easiest — share with friends)

Railway gives you a public URL in minutes. No infrastructure knowledge needed.

#### Deploy the backend

1. Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub**
2. Select your repo
3. Railway auto-detects Python → add these environment variables in the Railway dashboard:
   ```
   OPENAI_API_KEY=sk-...
   CHROMA_PERSIST_DIR=/app/chroma_db
   PORT=8000
   ```
4. Add a **Redis** plugin from the Railway dashboard (click + → Database → Redis)
5. Railway sets `REDIS_URL` automatically
6. Set **Start Command** in Railway settings:
   ```
   uvicorn app.api.main:app --host 0.0.0.0 --port $PORT
   ```
7. Add a **Volume** mount at `/app/chroma_db` for persistent ChromaDB storage

#### Deploy the frontend

1. In the same Railway project → **New Service** → **GitHub Repo** (same repo, different service)
2. Set **Root Directory** to `frontend`
3. Set environment variable:
   ```
   VITE_API_URL=https://your-backend-railway-url.railway.app/api/v1
   ```
4. Set **Build Command:** `npm run build`
5. Set **Start Command:** (leave empty, Railway serves static via built-in static server)

Or use **Vercel** for the frontend (free):
```bash
cd frontend
VITE_API_URL=https://your-backend-url.railway.app/api/v1 npm run build
npx vercel deploy dist/
```

#### Share the URL

Once deployed, send your friend the Railway/Vercel frontend URL. They can create notebooks, upload documents, and chat — all from their browser with no local setup.

---

### 11.3 Render

Similar to Railway.

1. **render.com** → New → **Web Service** → connect GitHub
2. **Environment:** Docker (use `docker/Dockerfile`)
3. Add env vars (same as above)
4. For ChromaDB persistence: **Render Disk** → mount at `/app/chroma_db` (500MB free tier)
5. Add a **Redis** instance from Render dashboard
6. Deploy frontend as a **Static Site** on Render, build command `cd frontend && npm run build`, publish directory `frontend/dist`

---

### 11.4 Fly.io

Good for global low-latency deployment.

```bash
# Install flyctl
brew install flyctl
fly auth login

# Deploy backend
fly launch --dockerfile docker/Dockerfile
fly secrets set OPENAI_API_KEY=sk-...
fly volumes create chroma_data --size 1 --region iad
# Add volume mount in fly.toml: [[mounts]] source="chroma_data" destination="/app/chroma_db"
fly deploy

# Add Redis
fly redis create
fly secrets set REDIS_URL=$(fly redis status <name> | grep Private)

# Deploy frontend (separate app)
cd frontend
fly launch
fly secrets set VITE_API_URL=https://your-backend.fly.dev/api/v1
fly deploy
```

---

### 11.5 Manual VPS / Cloud VM

For full control (AWS EC2, DigitalOcean Droplet, Hetzner, etc.).

```bash
# 1. SSH into your VM
ssh user@your-server-ip

# 2. Install dependencies
sudo apt update && sudo apt install -y docker.io docker-compose-plugin nginx certbot

# 3. Clone your repo
git clone <your-repo>
cd multi-agent-rag
cp .env.example .env
nano .env  # add API keys

# 4. Run with Docker Compose
docker compose -f docker/docker-compose.yml up -d

# 5. Point nginx at port 3000 and configure SSL
sudo certbot --nginx -d yourdomain.com

# App is now live at https://yourdomain.com
```

**Minimum VM specs:**
- 2 vCPU, 4GB RAM (umap-learn needs RAM for RAPTOR building)
- 20GB SSD (ChromaDB + models cache)
- Ubuntu 22.04 LTS

---

## 12. Troubleshooting

### Upload returns 500

```
ValueError: Expected collection name... got rag-who-is-kartik--
```
→ Notebook ID ends with special characters. Fixed in `vector_store.py` `_collection_name()` — strips trailing hyphens.

### Streaming returns error: `'AsyncCompletions' object has no attribute 'stream'`

→ The Langfuse OpenAI wrapper doesn't implement `.stream()`. Fixed in `llm/client.py` to use `create(stream=True)` instead.

### Retrieval returns 0 chunks consistently

The CRAG grader is rejecting all chunks. Check:
1. Is the notebook indexed? `GET /api/v1/notebook/{id}/stats` should return `total_nodes > 0`
2. Is the query related to the uploaded document?
3. Fixed: a fallback now returns top-k by retrieval score when the grader rejects everything.

### Knowledge map scroll-zoom not working

The wheel event must be `passive: false` to call `preventDefault()`. Fixed: listener now on the wrapper `div` (not the SVG), ensuring it intercepts the browser scroll before the page scrolls.

### ChromaDB collections not found after restart

ChromaDB uses `PersistentClient` → data is stored in `./chroma_db`. If you move or delete this directory, collections are lost. In Docker, ensure the volume mount at `/app/chroma_db` is persistent.

### BM25 index empty after startup

BM25 is rebuilt in-memory from ChromaDB on startup. If ChromaDB is empty, BM25 is also empty. After uploading a document, BM25 is rebuilt immediately. If you just restarted the server with existing data, check that `vector_store.list_notebooks()` returns your collections.

### Redis connection refused

Redis is **optional**. If `REDIS_URL` is not set, the cache is disabled and every query hits the LLM. No functionality is lost, only latency/cost benefits.

### RAPTOR takes too long

UMAP + K-means is CPU-bound. On a single-core VM, a 200-page PDF may take 3–5 minutes to ingest with RAPTOR. Options:
- Toggle RAPTOR **off** in the upload modal (faster, but no hierarchical summaries)
- Use a machine with more cores
- Pre-process large documents offline

### Frontend shows blank page after deployment

Check `VITE_API_URL` is set correctly at **build time** (not runtime — Vite bakes it in). Rebuild the frontend after changing it:
```bash
VITE_API_URL=https://your-backend.com/api/v1 npm run build
```

---

*Documentation generated 2026-05-17 — covers codebase version 1.0.0*
