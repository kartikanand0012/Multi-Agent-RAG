from __future__ import annotations

import logging
import re
from typing import List, Tuple

from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)


def _tokenize(text: str) -> List[str]:
    return re.findall(r"\b\w+\b", text.lower())


class BM25Retriever:
    """
    In-memory BM25 keyword retriever built from the same chunks as ChromaDB.
    Complements vector search — strong on exact keywords, model names, numbers.
    """

    def __init__(self) -> None:
        self._docs: List[str] = []
        self._metadatas: List[dict] = []
        self._bm25: BM25Okapi | None = None

    def index(self, texts: List[str], metadatas: List[dict]) -> None:
        self._docs = texts
        self._metadatas = metadatas
        tokenized = [_tokenize(t) for t in texts]
        self._bm25 = BM25Okapi(tokenized)
        logger.info(f"BM25 index built: {len(texts)} documents")

    def search(self, query: str, k: int = 10) -> List[Tuple[str, float, dict]]:
        if self._bm25 is None or not self._docs:
            logger.warning("BM25 index is empty — call index() first")
            return []

        tokens = _tokenize(query)
        scores = self._bm25.get_scores(tokens)

        # Pair with docs and sort descending
        ranked = sorted(
            zip(self._docs, scores.tolist(), self._metadatas),
            key=lambda x: x[1],
            reverse=True,
        )
        top_k = [(doc, score, meta) for doc, score, meta in ranked[:k] if score > 0]
        return top_k

    @property
    def is_ready(self) -> bool:
        return self._bm25 is not None and len(self._docs) > 0
