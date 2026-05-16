from __future__ import annotations

import asyncio
import logging
from typing import List, Tuple

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.core.config import settings
from app.core.exceptions import RetrievalError
from app.ingestion.chunker import Chunk
from app.llm.client import llm_client

logger = logging.getLogger(__name__)

COLLECTION_NAME = "multi_agent_rag"


class VectorStore:
    """ChromaDB-backed vector store with persistent storage."""

    def __init__(self) -> None:
        self._client = chromadb.PersistentClient(
            path=settings.chroma_persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(f"VectorStore ready — {self._collection.count()} docs in collection")

    async def add_documents(self, chunks: List[Chunk]) -> None:
        """Embed and store chunks. Skips duplicates by chunk_id."""
        if not chunks:
            return

        # Embed in batches of 100 (API limit)
        BATCH = 100
        for start in range(0, len(chunks), BATCH):
            batch = chunks[start : start + BATCH]
            texts = [c.text for c in batch]
            ids = [c.chunk_id for c in batch]
            metadatas = [c.metadata for c in batch]

            try:
                embeddings = await llm_client.embed(texts)
            except Exception as e:
                raise RetrievalError(f"Embedding failed for batch starting at {start}: {e}") from e

            self._collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas,
            )
            logger.info(f"Stored batch {start}–{start + len(batch)} ({len(batch)} chunks)")

    async def similarity_search(
        self,
        query: str,
        k: int = 5,
        where: dict | None = None,
    ) -> List[Tuple[str, float, dict]]:
        """Return (text, score, metadata) tuples for top-k results."""
        try:
            query_embedding = await llm_client.embed([query])
        except Exception as e:
            raise RetrievalError(f"Query embedding failed: {e}") from e

        kwargs: dict = {
            "query_embeddings": query_embedding,
            "n_results": min(k, self._collection.count() or 1),
            "include": ["documents", "distances", "metadatas"],
        }
        if where:
            kwargs["where"] = where

        results = self._collection.query(**kwargs)

        output: list[tuple[str, float, dict]] = []
        for doc, dist, meta in zip(
            results["documents"][0],
            results["distances"][0],
            results["metadatas"][0],
        ):
            score = 1.0 - dist   # cosine distance → similarity score
            output.append((doc, score, meta))

        return output

    def count(self) -> int:
        return self._collection.count()

    def delete_collection(self) -> None:
        self._client.delete_collection(COLLECTION_NAME)
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("Collection cleared")


# Module-level singleton
vector_store = VectorStore()
