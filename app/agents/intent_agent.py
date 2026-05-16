from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import List

from app.core.exceptions import LLMError
from app.core.tracing import get_observe_decorator
from app.llm.client import llm_client
from app.llm.prompts import INTENT_CLASSIFICATION

logger = logging.getLogger(__name__)
observe = get_observe_decorator()

VALID_INTENTS = {
    "factual_lookup",
    "comparison",
    "multi_hop",
    "tabular_aggregation",
    "summarization",
}


@dataclass
class IntentResult:
    intent_type: str
    sub_queries: List[str]
    requires_sql: bool
    confidence: float


class IntentAgent:
    """
    Agent 1 — classifies query intent and decomposes complex queries.
    Uses fast_model (lightweight) since classification doesn't need deep reasoning.
    """

    @observe(name="intent_agent")
    async def run(self, query: str) -> IntentResult:
        prompt = INTENT_CLASSIFICATION.format(query=query)
        messages = [{"role": "user", "content": prompt}]

        raw = await llm_client.complete(
            messages=messages,
            model=llm_client.fast_model,
            temperature=0.0,
            max_tokens=256,
        )

        try:
            clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            data = json.loads(clean)
            intent_type = data.get("intent_type", "factual_lookup")
            if intent_type not in VALID_INTENTS:
                intent_type = "factual_lookup"

            sub_queries = data.get("sub_queries", [query])
            if not sub_queries:
                sub_queries = [query]

            result = IntentResult(
                intent_type=intent_type,
                sub_queries=sub_queries,
                requires_sql=bool(data.get("requires_sql", False)),
                confidence=float(data.get("confidence", 0.8)),
            )
            logger.info(
                f"Intent: {result.intent_type} | sub_queries={len(result.sub_queries)} "
                f"| sql={result.requires_sql} | conf={result.confidence:.2f}"
            )
            return result

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Intent parse failed ({e}), defaulting to factual_lookup")
            return IntentResult(
                intent_type="factual_lookup",
                sub_queries=[query],
                requires_sql=False,
                confidence=0.5,
            )
