"""End-to-end ingestion pipeline: load → chunk → RAPTOR → store."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List

from app.ingestion.chunker import DocumentChunker
from app.ingestion.loaders import DocumentLoader
from app.ingestion.raptor import RAPTORIndexer
from app.retrieval.vector_store import vector_store as _vector_store, DEFAULT_NOTEBOOK

logger = logging.getLogger(__name__)

_loader = DocumentLoader()
_chunker = DocumentChunker()


async def ingest_file(
    file_path: str | Path,
    notebook_id: str = DEFAULT_NOTEBOOK,
    use_raptor: bool = True,
    display_name: str | None = None,
) -> dict:
    """
    Full ingestion pipeline for a single file.

    `display_name` overrides the chunk metadata source — pass the user's
    original filename here so citations and the knowledge map show "Q4-Report.pdf"
    instead of the worker's temp path.

    Returns a summary dict with counts for the API response.
    """
    path = Path(file_path)
    logger.info(f"Ingesting '{display_name or path.name}' into notebook '{notebook_id}'")

    # Step 1: Load — use display_name as the source metadata
    doc = _loader.load(path, display_name=display_name or path.name)

    # Step 2: Chunk
    chunks = _chunker.chunk(doc)
    logger.info(f"Created {len(chunks)} leaf chunks")

    if use_raptor:
        # Step 3: Build RAPTOR tree
        indexer = RAPTORIndexer()
        tree_nodes = await indexer.build_tree(chunks)

        # Step 4: Store all nodes (leaf + summary layers)
        raptor_chunks = [node.to_chunk() for node in tree_nodes]
        await _vector_store.add_documents(raptor_chunks, notebook_id=notebook_id)

        layer_counts: dict[int, int] = {}
        for node in tree_nodes:
            layer_counts[node.layer] = layer_counts.get(node.layer, 0) + 1

        return {
            "file": path.name,
            "notebook_id": notebook_id,
            "leaf_chunks": len(chunks),
            "total_nodes": len(tree_nodes),
            "layer_breakdown": layer_counts,
            "mode": "raptor",
        }
    else:
        # Flat ingestion (baseline mode)
        await _vector_store.add_documents(chunks, notebook_id=notebook_id)
        return {
            "file": path.name,
            "notebook_id": notebook_id,
            "leaf_chunks": len(chunks),
            "total_nodes": len(chunks),
            "layer_breakdown": {0: len(chunks)},
            "mode": "flat",
        }


async def ingest_files(
    file_paths: List[str | Path],
    notebook_id: str = DEFAULT_NOTEBOOK,
    use_raptor: bool = True,
) -> List[dict]:
    """Ingest multiple files into the same notebook."""
    results = []
    for path in file_paths:
        result = await ingest_file(path, notebook_id=notebook_id, use_raptor=use_raptor)
        results.append(result)
    return results
