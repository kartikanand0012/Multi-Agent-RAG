from __future__ import annotations

import asyncio
import logging
from typing import List, Tuple

from app.agents.intent_agent import IntentResult
from app.core.tracing import get_observe_decorator
from app.llm.client import llm_client
from app.retrieval.bm25_retriever import BM25Retriever
from app.retrieval.grader import GradeResult, RetrievalGrader
from app.retrieval.hybrid_search import HybridSearcher
from app.retrieval.vector_store import VectorStore, DEFAULT_NOTEBOOK

logger = logging.getLogger(__name__)
observe = get_observe_decorator()

MAX_REWRITE_ATTEMPTS = 2
QUERY_VARIATIONS_PROMPT = (
    "Generate {n} search query variations for the following question. "
    "Return only a JSON array of strings, no explanation.\n\nQuestion: {query}"
)


class RetrievalAgent:
    """
    Agent 2 — retrieves relevant chunks using hybrid search + CRAG grading.

    For each sub-query from the Intent Agent:
      1. Generate 3 query variations (VOTE-RAG technique)
      2. Run hybrid search (BM25 + vector) in parallel across all variations
      3. Deduplicate results
      4. Grade with CRAG grader
      5. If majority Incorrect → rewrite query and retry (max 2x)
    """

    def __init__(
        self,
        vector_store: VectorStore,
        bm25: BM25Retriever,
    ) -> None:
        self._searcher = HybridSearcher(vector_store, bm25)
        self._grader = RetrievalGrader()

    @observe(name="retrieval_agent")
    async def run(
        self,
        intent: IntentResult,
        notebook_id: str = DEFAULT_NOTEBOOK,
        k_final: int = 5,
    ) -> List[GradeResult]:
        """Run retrieval for all sub-queries and return merged, graded chunks."""
        all_graded: List[GradeResult] = []

        for sub_query in intent.sub_queries:
            graded = await self._retrieve_with_grading(
                sub_query, notebook_id=notebook_id, k_final=k_final
            )
            all_graded.extend(graded)

        # Deduplicate by text prefix across sub-queries
        seen: set[str] = set()
        unique: List[GradeResult] = []
        for g in all_graded:
            key = g.text[:80]
            if key not in seen:
                seen.add(key)
                unique.append(g)

        logger.info(
            f"Retrieval complete: {len(unique)} unique graded chunks "
            f"from {len(intent.sub_queries)} sub-queries"
        )
        return unique

    async def _retrieve_with_grading(
        self,
        query: str,
        notebook_id: str,
        k_final: int,
        attempt: int = 0,
    ) -> List[GradeResult]:
        """Retrieve, grade, and optionally rewrite + retry."""

        # Step 1: Generate query variations (VOTE-RAG)
        variations = await self._generate_variations(query, n=3)

        # Step 2: Search all variations in parallel
        search_tasks = [
            self._searcher.search(q, k_final=k_final, notebook_id=notebook_id)
            for q in variations
        ]
        results_per_variation = await asyncio.gather(*search_tasks)

        # Step 3: Merge and deduplicate across variations
        seen: set[str] = set()
        merged: List[Tuple[str, float, dict]] = []
        for results in results_per_variation:
            for text, score, meta in results:
                key = text[:80]
                if key not in seen:
                    seen.add(key)
                    merged.append((text, score, meta))

        if not merged:
            logger.warning(f"No results for query: {query[:60]}")
            return []

        # Step 4: Grade with CRAG
        grades = await self._grader.grade_all(query, merged)

        # Step 5: Rewrite and retry if majority Incorrect
        if self._grader.should_rewrite(grades) and attempt < MAX_REWRITE_ATTEMPTS:
            rewritten = await self._rewrite_query(query)
            logger.info(f"Query rewrite attempt {attempt + 1}: '{rewritten[:60]}'")
            return await self._retrieve_with_grading(
                rewritten, notebook_id=notebook_id, k_final=k_final, attempt=attempt + 1
            )

        relevant = self._grader.filter_relevant(grades)
        if not relevant:
            # Grader rejected everything — return top-k by retrieval score as fallback
            logger.warning(f"Grader returned 0 relevant chunks after {attempt} rewrites; using top-k fallback")
            top_k = sorted(merged, key=lambda t: t[1], reverse=True)[:k_final]
            relevant = [
                GradeResult(text=t, metadata=m, grade="Ambiguous", confidence=s, reason="score fallback")
                for t, s, m in top_k
            ]
        return relevant

    async def _generate_variations(self, query: str, n: int = 3) -> List[str]:
        """Generate n rephrasings of the query to improve recall."""
        try:
            prompt = QUERY_VARIATIONS_PROMPT.format(n=n - 1, query=query)
            raw = await llm_client.complete(
                messages=[{"role": "user", "content": prompt}],
                model=llm_client.fast_model,
                temperature=0.7,
                max_tokens=256,
            )
            import json
            variations = json.loads(raw.strip())
            if isinstance(variations, list):
                return [query] + [str(v) for v in variations[:n - 1]]
        except Exception as e:
            logger.debug(f"Variation generation failed ({e}), using original only")
        return [query]

    async def _rewrite_query(self, query: str) -> str:
        """Ask LLM to rephrase the query differently to improve retrieval."""
        prompt = (
            f"The following query returned irrelevant results. "
            f"Rephrase it to retrieve more relevant information. "
            f"Return only the rephrased query, nothing else.\n\nQuery: {query}"
        )
        try:
            return await llm_client.complete(
                messages=[{"role": "user", "content": prompt}],
                model=llm_client.fast_model,
                temperature=0.5,
                max_tokens=128,
            )
        except Exception:
            return query
