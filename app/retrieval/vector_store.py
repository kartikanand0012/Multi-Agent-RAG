"""ChromaDB-backed vector store with per-notebook collection isolation.

Each notebook gets its own ChromaDB collection so documents from different
users/sessions never bleed into each other — same pattern as NotebookLM.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.core.config import settings
from app.core.exceptions import RetrievalError
from app.ingestion.chunker import Chunk
from app.llm.client import llm_client

logger = logging.getLogger(__name__)

DEFAULT_NOTEBOOK = "default"


def _collection_name(notebook_id: str) -> str:
    # ChromaDB collection names must be 3-63 chars, alphanumeric + hyphens
    safe = "".join(c if c.isalnum() or c == "-" else "-" for c in notebook_id)
    return f"rag-{safe}"[:63]


class VectorStore:
    """
    Per-notebook vector store backed by ChromaDB.

    Usage:
        vs = VectorStore()
        await vs.add_documents(chunks, notebook_id="my-notebook")
        results = await vs.similarity_search("query", notebook_id="my-notebook")
    """

    def __init__(self) -> None:
        self._client = chromadb.PersistentClient(
            path=settings.chroma_persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        # Cache open collection handles
        self._collections: Dict[str, chromadb.Collection] = {}
        logger.info("VectorStore initialised")

    def _get_collection(self, notebook_id: str) -> chromadb.Collection:
        if notebook_id not in self._collections:
            name = _collection_name(notebook_id)
            col = self._client.get_or_create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"},
            )
            self._collections[notebook_id] = col
            logger.info(f"Collection '{name}' opened ({col.count()} existing docs)")
        return self._collections[notebook_id]

    # ── write ────────────────────────────────────────────────────────────────

    async def add_documents(
        self,
        chunks: List[Chunk],
        notebook_id: str = DEFAULT_NOTEBOOK,
    ) -> None:
        """Embed and upsert chunks into the notebook's collection."""
        if not chunks:
            return

        col = self._get_collection(notebook_id)
        BATCH = 100

        for start in range(0, len(chunks), BATCH):
            batch = chunks[start : start + BATCH]
            texts = [c.text for c in batch]
            ids = [c.chunk_id for c in batch]
            metadatas = []
            for c in batch:
                # ChromaDB metadata values must be str/int/float/bool
                safe_meta = {
                    k: (str(v) if not isinstance(v, (str, int, float, bool)) else v)
                    for k, v in c.metadata.items()
                }
                metadatas.append(safe_meta)

            try:
                embeddings = await llm_client.embed(texts)
            except Exception as e:
                raise RetrievalError(f"Embedding failed at batch {start}: {e}") from e

            col.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas,
            )
            logger.info(f"[{notebook_id}] stored batch {start}–{start + len(batch)}")

    # ── read ─────────────────────────────────────────────────────────────────

    async def similarity_search(
        self,
        query: str,
        k: int = 5,
        notebook_id: str = DEFAULT_NOTEBOOK,
        where: Optional[dict] = None,
    ) -> List[Tuple[str, float, dict]]:
        """Return (text, similarity_score, metadata) for top-k results."""
        col = self._get_collection(notebook_id)
        count = col.count()
        if count == 0:
            logger.warning(f"[{notebook_id}] collection is empty")
            return []

        try:
            query_embedding = await llm_client.embed([query])
        except Exception as e:
            raise RetrievalError(f"Query embedding failed: {e}") from e

        kwargs: dict = {
            "query_embeddings": query_embedding,
            "n_results": min(k, count),
            "include": ["documents", "distances", "metadatas"],
        }
        if where:
            kwargs["where"] = where

        results = col.query(**kwargs)

        output: list[tuple[str, float, dict]] = []
        for doc, dist, meta in zip(
            results["documents"][0],
            results["distances"][0],
            results["metadatas"][0],
        ):
            output.append((doc, 1.0 - dist, meta))   # distance → similarity

        return output

    # ── map / tree ───────────────────────────────────────────────────────────

    def get_tree_nodes(self, notebook_id: str = DEFAULT_NOTEBOOK) -> List[dict]:
        """Return all RAPTOR nodes with layer info — used by the /map endpoint."""
        col = self._get_collection(notebook_id)
        if col.count() == 0:
            return []

        results = col.get(include=["documents", "metadatas"])
        nodes = []
        for doc_id, doc, meta in zip(
            results["ids"], results["documents"], results["metadatas"]
        ):
            nodes.append({
                "id": doc_id,
                "text": doc[:300],   # truncate for map view
                "layer": int(meta.get("layer", 0)),
                "children": meta.get("children", "").split(",") if meta.get("children") else [],
                "source": meta.get("source", ""),
                "cluster_id": meta.get("cluster_id", ""),
            })
        return nodes

    # ── admin ────────────────────────────────────────────────────────────────

    def count(self, notebook_id: str = DEFAULT_NOTEBOOK) -> int:
        return self._get_collection(notebook_id).count()

    def list_notebooks(self) -> List[str]:
        return [col.name for col in self._client.list_collections()]

    def delete_notebook(self, notebook_id: str) -> None:
        name = _collection_name(notebook_id)
        self._client.delete_collection(name)
        self._collections.pop(notebook_id, None)
        logger.info(f"Deleted notebook collection '{name}'")


# Module-level singleton
vector_store = VectorStore()
