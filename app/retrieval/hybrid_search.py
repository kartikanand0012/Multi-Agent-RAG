from __future__ import annotations

import logging
from typing import Dict, List, Tuple

from app.retrieval.bm25_retriever import BM25Retriever
from app.retrieval.vector_store import VectorStore

logger = logging.getLogger(__name__)

# RRF constant — higher k reduces impact of top ranks, standard value is 60
RRF_K = 60


def _reciprocal_rank_fusion(
    ranked_lists: List[List[Tuple[str, float, dict]]],
) -> List[Tuple[str, float, dict]]:
    """
    Merge multiple ranked lists using Reciprocal Rank Fusion.
    score(doc) = sum over retrievers of 1 / (RRF_K + rank)
    Documents appearing in multiple lists get boosted.
    """
    rrf_scores: Dict[str, float] = {}
    doc_store: Dict[str, Tuple[str, dict]] = {}  # id → (text, metadata)

    for ranked in ranked_lists:
        for rank, (text, _score, meta) in enumerate(ranked, start=1):
            # Use first 100 chars as dedup key (chunk text is unique)
            doc_id = text[:100]
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (RRF_K + rank)
            doc_store[doc_id] = (text, meta)

    merged = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    return [(doc_store[doc_id][0], score, doc_store[doc_id][1]) for doc_id, score in merged]


class HybridSearcher:
    """
    Combines BM25 (keyword) + vector (semantic) retrieval via RRF.

    Why both?
    - Vector search finds semantically similar chunks even with different words.
    - BM25 finds exact keyword matches (model names, numbers, legal terms).
    - RRF merges both lists without needing to normalise scores.
    """

    def __init__(self, vector_store: VectorStore, bm25: BM25Retriever) -> None:
        self._vs = vector_store
        self._bm25 = bm25

    async def search(
        self,
        query: str,
        k_initial: int = 20,
        k_final: int = 5,
        notebook_id: str = "default",
    ) -> List[Tuple[str, float, dict]]:
        """
        Retrieve k_initial candidates from each retriever, fuse, return k_final.
        """
        # Run vector search
        vector_results = await self._vs.similarity_search(
            query, k=k_initial, notebook_id=notebook_id
        )

        # Run BM25 search (sync — in-memory, instant)
        bm25_results = self._bm25.search(query, k=k_initial) if self._bm25.is_ready else []

        if not bm25_results:
            logger.debug("BM25 not ready — returning vector-only results")
            return vector_results[:k_final]

        # Fuse and return top-k_final
        fused = _reciprocal_rank_fusion([vector_results, bm25_results])
        logger.info(
            f"Hybrid search: vector={len(vector_results)} bm25={len(bm25_results)} "
            f"fused={len(fused)} → top {k_final}"
        )
        return fused[:k_final]
