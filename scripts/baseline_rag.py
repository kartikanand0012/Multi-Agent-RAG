"""
Baseline single-pipeline RAG — Phase 1 reference implementation.

This is the BEFORE system. Every metric we improve in the multi-agent
system will be measured against results from this script.

Usage:
    python scripts/baseline_rag.py --file data/raw/apple_10k_2025.htm --query "What was Apple's revenue?"
    python scripts/baseline_rag.py --query "What are the main risks Apple faces?"  # reuse existing index
"""
import argparse
import asyncio
import sys
import os
import warnings
import logging

warnings.filterwarnings("ignore")
logging.getLogger("chromadb").setLevel(logging.ERROR)
logging.getLogger("httpx").setLevel(logging.ERROR)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.ingestion.loaders import DocumentLoader
from app.ingestion.chunker import DocumentChunker
from app.retrieval.vector_store import VectorStore
from app.llm.client import llm_client

SYSTEM_PROMPT = """You are a helpful assistant. Answer the question using ONLY the provided context.
If the context does not contain enough information to answer, say "I don't have enough information to answer this."
Be concise and factual. Do not make up information."""


async def run(file_path: str | None, query: str) -> None:
    vs = VectorStore()

    # Ingest only if a file is provided
    if file_path:
        print(f"Loading {file_path}...")
        loader = DocumentLoader()
        chunker = DocumentChunker()
        doc = loader.load(file_path)
        chunks = chunker.chunk(doc)
        print(f"Indexing {len(chunks)} chunks...")
        await vs.add_documents(chunks)
        print(f"Index size: {vs.count()} chunks\n")
    else:
        print(f"Using existing index ({vs.count()} chunks)\n")

    # Retrieve
    print(f"Query: {query}")
    print("Retrieving...")
    results = await vs.similarity_search(query, k=5)

    context_parts = []
    for i, (text, score, meta) in enumerate(results, 1):
        source = os.path.basename(meta.get("source", "unknown"))
        context_parts.append(f"[Source {i} — {source}, score={score:.3f}]\n{text}")

    context = "\n\n---\n\n".join(context_parts)

    # Generate
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"},
    ]

    print("Generating answer...\n")
    print("=" * 60)
    response = await llm_client.complete(messages, model=llm_client.strong_model)
    print(response)
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="Baseline RAG pipeline")
    parser.add_argument("--file", help="Path to document to ingest (optional if index exists)")
    parser.add_argument("--query", required=True, help="Question to answer")
    args = parser.parse_args()
    asyncio.run(run(args.file, args.query))


if __name__ == "__main__":
    main()
