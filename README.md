# Multi-Agent RAG System

A production-grade, domain-agnostic Retrieval-Augmented Generation system built as an IIT Bombay capstone project.

## Architecture

```
User Query
    │
    ▼
Intent Agent          ← classifies query type, decomposes multi-hop queries
    │
    ▼
Retrieval Agent       ← hybrid BM25 + vector search, CRAG grading, query rewriting
    │
    ▼
Reasoning Agent       ← chain-of-thought synthesis with mandatory source citations
    │
    ▼
Validation Agent      ← claim-level fact-checking, triggers retry on hallucination
    │
    ▼
Final Response (with disclaimer if validation failed after 2 retries)
```

**Indexing:** RAPTOR hierarchical tree (leaf chunks → cluster summaries → top summaries)
**Observability:** Langfuse traces + spans for every agent call
**Caching:** Redis query result cache (1h TTL)
**API:** FastAPI with SSE streaming

---

## Quick Start (Local)

### Prerequisites
- Python 3.11+
- Redis (`brew install redis && brew services start redis`)
- Azure OpenAI with deployments: `gpt-4o`, `gpt-4o-2`, `text-embedding-3-large`

### Setup

```bash
git clone https://github.com/kartikanand0012/Multi-Agent-RAG.git
cd Multi-Agent-RAG

python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Fill in your Azure OpenAI credentials in .env
```

### Run the API

```bash
uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --reload
```

### Upload a document and query

```bash
# Upload a document (RAPTOR indexing runs automatically)
curl -X POST http://localhost:8000/api/v1/upload \
  -F "file=@your_document.pdf" \
  -F "notebook_id=my-notebook"

# Query the multi-agent system
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What are the main risks?", "notebook_id": "my-notebook"}'

# View the RAPTOR knowledge map
curl http://localhost:8000/api/v1/notebook/my-notebook/map
```

---

## Run with Docker

```bash
cp .env.example .env   # fill in credentials

docker compose -f docker/docker-compose.yml up --build
# API available at http://localhost:8000
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/health` | Liveness probe |
| `POST` | `/api/v1/upload` | Upload document, triggers RAPTOR ingestion |
| `POST` | `/api/v1/query` | Full 4-agent pipeline query |
| `POST` | `/api/v1/query/stream` | SSE streaming response |
| `GET` | `/api/v1/notebook/{id}/stats` | RAPTOR layer node counts |
| `GET` | `/api/v1/notebook/{id}/map` | Knowledge graph (nodes + edges) |
| `DELETE` | `/api/v1/notebook/{id}` | Delete notebook |

Interactive docs: `http://localhost:8000/docs`

---

## Run Tests

```bash
# Unit tests — fast, zero API calls
python -m pytest tests/unit/ -v

# Integration tests — real LLM calls
python -m pytest tests/integration/ -m integration -v

# RAGAS evaluation — baseline vs multi-agent comparison
python scripts/run_eval.py --notebook apple-2025 --questions 10
```

---

## Project Structure

```
app/
├── agents/          # Intent, Retrieval, Reasoning, Validation agents
├── api/             # FastAPI routes, schemas, main app
├── cache/           # Redis query cache
├── core/            # Config, logging, tracing (Langfuse)
├── evaluation/      # RAGAS evaluation
├── ingestion/       # Loaders, chunker, RAPTOR, pipeline
├── llm/             # LLM client (Azure OpenAI), prompts
├── orchestration/   # LangGraph state machine
└── retrieval/       # BM25, vector store, hybrid search, CRAG grader
```

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI resource endpoint |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI API key |
| `AZURE_OPENAI_API_VERSION` | API version |
| `AZURE_DEPLOYMENT_GPT4O` | GPT-4o deployment name (strong model) |
| `AZURE_DEPLOYMENT_GPT4O_MINI` | Lightweight model deployment name |
| `AZURE_DEPLOYMENT_EMBEDDING` | Embedding model deployment name |
| `REDIS_URL` | Redis connection URL |
| `LANGFUSE_PUBLIC_KEY` | Langfuse public key (optional) |
| `LANGFUSE_SECRET_KEY` | Langfuse secret key (optional) |

---

## Observability

- **Langfuse**: every query creates a trace with one span per agent — view at cloud.langfuse.com
- **Health endpoint**: `/api/v1/health` reports Redis, ChromaDB, Langfuse status live
- **RAGAS**: `scripts/run_eval.py` produces faithfulness, relevancy, precision, recall scores

---

## Tech Stack

Python 3.11 · LangChain 0.3 · LangGraph 0.2 · ChromaDB · FastAPI · Redis · Azure OpenAI · RAGAS · Langfuse · Docker · Azure Kubernetes Service