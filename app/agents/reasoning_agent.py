from __future__ import annotations

import logging
import os
from typing import AsyncIterator, List

from app.agents.intent_agent import IntentResult
from app.core.tracing import get_observe_decorator
from app.llm.client import llm_client
from app.llm.prompts import REASONING_SYNTHESIS
from app.retrieval.grader import GradeResult

logger = logging.getLogger(__name__)
observe = get_observe_decorator()

MAX_CONTEXT_CHUNKS = 8   # cap to keep prompt within token budget


def _build_context(chunks: List[GradeResult]) -> str:
    """Format graded chunks into numbered context block with source citations."""
    parts = []
    for i, g in enumerate(chunks[:MAX_CONTEXT_CHUNKS], start=1):
        source = os.path.basename(g.metadata.get("source", "unknown"))
        layer = int(g.metadata.get("layer", 0))
        layer_label = "summary" if layer > 0 else "source"
        parts.append(f"[Source {i} — {source} ({layer_label})]\n{g.text}")
    return "\n\n---\n\n".join(parts)


class ReasoningAgent:
    """
    Agent 3 — synthesises a grounded response using chain-of-thought (MA-RAG).

    Prompt structure:
      1. System: strict grounding rules + citation requirement
      2. User: numbered context chunks + question
      3. Assistant prefix: forces chain-of-thought before final answer
    """

    @observe(name="reasoning_agent")
    async def run(
        self,
        query: str,
        intent: IntentResult,
        chunks: List[GradeResult],
    ) -> str:
        if not chunks:
            return (
                "I was unable to find relevant information in the provided documents "
                "to answer this question."
            )

        context = _build_context(chunks)
        prompt = REASONING_SYNTHESIS.format(context=context, question=query)

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a precise analytical assistant. "
                    "Answer using ONLY the provided context. "
                    "Cite every claim with [Source N]. "
                    "If context is insufficient, say exactly what is missing."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        response = await llm_client.complete(
            messages=messages,
            model=llm_client.strong_model,
            temperature=0.0,
            max_tokens=1024,
        )
        logger.info(f"Reasoning complete: {len(response)} chars, {len(chunks)} chunks used")
        return response

    async def stream(
        self,
        query: str,
        intent: IntentResult,
        chunks: List[GradeResult],
    ) -> AsyncIterator[str]:
        """Token-by-token streaming version for the API SSE endpoint."""
        if not chunks:
            yield "I was unable to find relevant information in the provided documents."
            return

        context = _build_context(chunks)
        prompt = REASONING_SYNTHESIS.format(context=context, question=query)

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a precise analytical assistant. "
                    "Answer using ONLY the provided context. "
                    "Cite every claim with [Source N]."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        async for token in llm_client.stream(
            messages=messages,
            model=llm_client.strong_model,
            temperature=0.0,
            max_tokens=1024,
        ):
            yield token
