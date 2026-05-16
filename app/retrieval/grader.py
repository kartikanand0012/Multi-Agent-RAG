from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import List, Tuple

from app.llm.client import llm_client
from app.llm.prompts import RETRIEVAL_GRADER

logger = logging.getLogger(__name__)


@dataclass
class GradeResult:
    text: str
    metadata: dict
    grade: str        # "Correct" | "Incorrect" | "Ambiguous"
    confidence: float
    reason: str


class RetrievalGrader:
    """
    CRAG-style grader: scores each retrieved chunk against the sub-query.

    If most chunks grade as Incorrect, the retrieval agent rewrites the query
    and retries (max 2 attempts). This catches the common failure where the
    vector store returns plausible-sounding but irrelevant chunks.
    """

    async def grade_chunk(
        self, query: str, chunk_text: str, metadata: dict
    ) -> GradeResult:
        prompt = RETRIEVAL_GRADER.format(query=query, chunk=chunk_text[:800])
        raw = await llm_client.complete(
            messages=[{"role": "user", "content": prompt}],
            model=llm_client.fast_model,
            temperature=0.0,
            max_tokens=128,
        )
        try:
            data = json.loads(raw.strip())
            grade = data.get("grade", "Ambiguous")
            if grade not in ("Correct", "Incorrect", "Ambiguous"):
                grade = "Ambiguous"
            return GradeResult(
                text=chunk_text,
                metadata=metadata,
                grade=grade,
                confidence=float(data.get("confidence", 0.5)),
                reason=data.get("reason", ""),
            )
        except (json.JSONDecodeError, ValueError):
            return GradeResult(
                text=chunk_text, metadata=metadata,
                grade="Ambiguous", confidence=0.5, reason="parse error",
            )

    async def grade_all(
        self,
        query: str,
        chunks: List[Tuple[str, float, dict]],
    ) -> List[GradeResult]:
        """Grade all chunks concurrently (each is a short LLM call)."""
        tasks = [self.grade_chunk(query, text, meta) for text, _score, meta in chunks]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        graded = []
        for r in results:
            if isinstance(r, Exception):
                logger.warning(f"Grade error: {r}")
            else:
                graded.append(r)
        return graded

    def should_rewrite(self, grades: List[GradeResult]) -> bool:
        """Return True if majority of chunks are Incorrect → trigger query rewrite."""
        if not grades:
            return False
        incorrect = sum(1 for g in grades if g.grade == "Incorrect")
        return incorrect > len(grades) / 2

    def filter_relevant(self, grades: List[GradeResult]) -> List[GradeResult]:
        """Keep only Correct and Ambiguous chunks, sorted by confidence."""
        relevant = [g for g in grades if g.grade != "Incorrect"]
        return sorted(relevant, key=lambda g: g.confidence, reverse=True)
