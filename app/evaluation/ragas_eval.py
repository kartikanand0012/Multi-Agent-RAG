"""RAGAS evaluation — compares baseline RAG vs multi-agent system.

Metrics measured:
  faithfulness        — are claims grounded in retrieved context?
  answer_relevancy    — does the answer address the question?
  context_precision   — are retrieved chunks actually relevant?
  context_recall      — does retrieval cover the ground truth?
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import List

from datasets import Dataset

logger = logging.getLogger(__name__)

GOLDEN_SET_PATH = Path(__file__).parent.parent.parent / "data/eval/golden_test_set.json"


def load_golden_set() -> List[dict]:
    with open(GOLDEN_SET_PATH) as f:
        return json.load(f)


async def _run_multiagent(question: str, notebook_id: str) -> dict:
    """Run the full 4-agent pipeline and return answer + contexts."""
    from app.orchestration.graph import query as run_query
    from app.retrieval.vector_store import vector_store

    result = await run_query(question, notebook_id=notebook_id)
    # Fetch the actual chunks used (re-retrieve for RAGAS context)
    raw = await vector_store.similarity_search(question, k=5, notebook_id=notebook_id)
    contexts = [text for text, _, _ in raw]
    return {"answer": result["response"], "contexts": contexts}


async def _run_baseline(question: str, notebook_id: str) -> dict:
    """Simple single-step RAG for baseline comparison."""
    from app.retrieval.vector_store import vector_store
    from app.llm.client import llm_client

    raw = await vector_store.similarity_search(question, k=5, notebook_id=notebook_id)
    if not raw:
        return {"answer": "No relevant documents found.", "contexts": []}

    context = "\n\n".join(text for text, _, _ in raw)
    messages = [
        {"role": "system", "content": "Answer using only the provided context. If unsure, say so."},
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
    ]
    answer = await llm_client.complete(messages, model=llm_client.strong_model)
    contexts = [text for text, _, _ in raw]
    return {"answer": answer, "contexts": contexts}


async def run_evaluation(
    notebook_id: str = "apple-2025",
    max_questions: int = 10,
    output_path: str = "data/eval/ragas_results.json",
) -> dict:
    """
    Run RAGAS evaluation on both systems and return comparison report.
    """
    from ragas import evaluate
    from ragas.metrics import faithfulness, answer_relevancy, context_precision, context_recall
    from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings
    from app.core.config import settings

    golden = load_golden_set()[:max_questions]
    logger.info(f"Running RAGAS evaluation on {len(golden)} questions...")

    # Build datasets for both systems
    baseline_rows = {"question": [], "answer": [], "contexts": [], "ground_truth": []}
    multiagent_rows = {"question": [], "answer": [], "contexts": [], "ground_truth": []}

    for item in golden:
        q = item["question"]
        gt = item["ground_truth"]
        logger.info(f"  Evaluating: {q[:60]}...")

        b = await _run_baseline(q, notebook_id)
        m = await _run_multiagent(q, notebook_id)

        baseline_rows["question"].append(q)
        baseline_rows["answer"].append(b["answer"])
        baseline_rows["contexts"].append(b["contexts"])
        baseline_rows["ground_truth"].append(gt)

        multiagent_rows["question"].append(q)
        multiagent_rows["answer"].append(m["answer"])
        multiagent_rows["contexts"].append(m["contexts"])
        multiagent_rows["ground_truth"].append(gt)

    # LangChain-wrapped Azure models for RAGAS
    llm = AzureChatOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        azure_deployment=settings.azure_deployment_gpt4o,
        temperature=0,
    )
    embeddings = AzureOpenAIEmbeddings(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        azure_deployment=settings.azure_deployment_embedding,
    )

    metrics = [faithfulness, answer_relevancy, context_precision, context_recall]

    logger.info("Running RAGAS on baseline...")
    baseline_scores = evaluate(
        Dataset.from_dict(baseline_rows), metrics=metrics, llm=llm, embeddings=embeddings
    )

    logger.info("Running RAGAS on multi-agent...")
    multiagent_scores = evaluate(
        Dataset.from_dict(multiagent_rows), metrics=metrics, llm=llm, embeddings=embeddings
    )

    def to_dict(scores) -> dict:
        df = scores.to_pandas()
        return {col: round(float(df[col].mean()), 4)
                for col in ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]
                if col in df.columns}

    baseline_dict = to_dict(baseline_scores)
    multiagent_dict = to_dict(multiagent_scores)

    improvements = {
        k: round((multiagent_dict.get(k, 0) - baseline_dict.get(k, 0)) * 100, 1)
        for k in baseline_dict
    }

    report = {
        "questions_evaluated": len(golden),
        "notebook_id": notebook_id,
        "baseline_rag": baseline_dict,
        "multi_agent_rag": multiagent_dict,
        "improvement_pct": improvements,
    }

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)

    logger.info(f"Results saved to {output_path}")
    return report
