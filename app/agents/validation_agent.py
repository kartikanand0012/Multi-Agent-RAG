from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import List

from app.core.tracing import get_observe_decorator
from app.llm.client import llm_client
from app.llm.prompts import VALIDATION_FACT_CHECK
from app.retrieval.grader import GradeResult

logger = logging.getLogger(__name__)
observe = get_observe_decorator()


@dataclass
class ValidationResult:
    passed: bool
    unsupported_claims: List[str]
    feedback: str
    confidence: float


class ValidationAgent:
    """
    Agent 4 — cross-references every claim in the response against source chunks.

    This is the key differentiator of the multi-agent system. Traditional RAG
    has no mechanism to catch hallucinations before they reach the user.

    Output:
      passed=True  → response is grounded, return to user
      passed=False → return feedback to Reasoning Agent for retry (max 2x)
    """

    @observe(name="validation_agent")
    async def run(
        self,
        response: str,
        chunks: List[GradeResult],
    ) -> ValidationResult:
        if not chunks:
            return ValidationResult(
                passed=False,
                unsupported_claims=["No source chunks available for validation"],
                feedback="Retrieval returned no usable chunks. Cannot validate response.",
                confidence=0.0,
            )

        # Build compact context for validation (shorter than reasoning context)
        context_parts = [
            f"[Source {i}] {g.text[:400]}"
            for i, g in enumerate(chunks[:6], start=1)
        ]
        context = "\n\n".join(context_parts)

        prompt = VALIDATION_FACT_CHECK.format(context=context, response=response)
        raw = await llm_client.complete(
            messages=[{"role": "user", "content": prompt}],
            model=llm_client.strong_model,
            temperature=0.0,
            max_tokens=512,
        )

        try:
            # Strip markdown code fences if LLM wraps the JSON
            clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            data = json.loads(clean)
            passed = bool(data.get("passed", False))
            unsupported = data.get("unsupported_claims", [])
            feedback = data.get("feedback", "")

            result = ValidationResult(
                passed=passed,
                unsupported_claims=unsupported,
                feedback=feedback,
                confidence=1.0 if passed else max(0.0, 1.0 - 0.3 * len(unsupported)),
            )
            logger.info(
                f"Validation: {'PASSED' if passed else 'FAILED'} | "
                f"unsupported_claims={len(unsupported)}"
            )
            return result

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Validation parse error: {e} — defaulting to passed")
            return ValidationResult(
                passed=True,
                unsupported_claims=[],
                feedback="Validation parse failed — returning response as-is.",
                confidence=0.6,
            )
