"""Run RAGAS evaluation and print comparison report.

Usage:
    python scripts/run_eval.py
    python scripts/run_eval.py --notebook apple-2025 --questions 5
"""
import argparse
import asyncio
import json
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")


async def main(notebook_id: str, max_questions: int):
    from app.evaluation.ragas_eval import run_evaluation

    print(f"\nRunning RAGAS evaluation on notebook='{notebook_id}', questions={max_questions}")
    print("This makes real LLM calls — expect ~5-10 min depending on question count.\n")

    report = await run_evaluation(
        notebook_id=notebook_id,
        max_questions=max_questions,
        output_path="data/eval/ragas_results.json",
    )

    print("\n" + "=" * 60)
    print("RAGAS EVALUATION REPORT")
    print("=" * 60)
    print(f"Questions evaluated : {report['questions_evaluated']}")
    print()

    metrics = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]
    header = f"{'Metric':<25} {'Baseline':>10} {'Multi-Agent':>12} {'Improvement':>12}"
    print(header)
    print("-" * 62)

    for m in metrics:
        b = report["baseline_rag"].get(m, 0)
        ma = report["multi_agent_rag"].get(m, 0)
        imp = report["improvement_pct"].get(m, 0)
        sign = "+" if imp >= 0 else ""
        print(f"{m:<25} {b:>10.3f} {ma:>12.3f} {sign}{imp:>10.1f}%")

    print()
    faith_imp = report["improvement_pct"].get("faithfulness", 0)
    if faith_imp >= 15:
        print(f"✓ Faithfulness improved by {faith_imp}% — meets target (>15%)")
    else:
        print(f"  Faithfulness improved by {faith_imp}% (target: >15%)")

    print(f"\nFull results saved to: data/eval/ragas_results.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--notebook", default="apple-2025")
    parser.add_argument("--questions", type=int, default=10)
    args = parser.parse_args()
    asyncio.run(main(args.notebook, args.questions))
