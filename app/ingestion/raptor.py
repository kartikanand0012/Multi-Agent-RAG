"""RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval.

Algorithm per layer:
  1. Embed all nodes
  2. UMAP dimensionality reduction (cosine, 10 dims)
  3. Gaussian Mixture Model soft clustering
  4. LLM summarizes each cluster → new summary nodes
  5. Recurse on summary nodes until ≤ 2 remain or max_depth reached

All nodes (leaf + summary) are stored in the vector store so a single
similarity search across all layers picks the right granularity automatically.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from app.ingestion.chunker import Chunk
from app.llm.client import llm_client
from app.llm.prompts import CLUSTER_SUMMARIZER

logger = logging.getLogger(__name__)

# ── tuneable constants ───────────────────────────────────────────────────────
UMAP_DIMS = 10
UMAP_NEIGHBORS = 15          # reduced if corpus is small
GMM_MEMBERSHIP_THRESHOLD = 0.1
CHUNKS_PER_CLUSTER = 6       # n_clusters = max(2, n_nodes // CHUNKS_PER_CLUSTER)
MAX_DEPTH = 4
MIN_NODES_TO_RECURSE = 3     # stop recursion when this few nodes remain
SUMMARY_MAX_TOKENS = 400
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class RAPTORNode:
    """One node in the RAPTOR tree — either a raw chunk or a cluster summary."""

    node_id: str
    text: str
    layer: int                         # 0 = leaf chunk, 1+ = summary layers
    metadata: dict = field(default_factory=dict)
    children: List[str] = field(default_factory=list)   # node_ids of children

    def to_chunk(self) -> Chunk:
        """Convert to a Chunk so VectorStore.add_documents can accept it."""
        meta = {
            **self.metadata,
            "layer": self.layer,
            "children": ",".join(self.children),
            "node_id": self.node_id,
        }
        c = Chunk(text=self.text, metadata=meta)
        c.chunk_id = self.node_id
        return c


class RAPTORIndexer:
    """Build a RAPTOR tree from a flat list of leaf chunks."""

    def __init__(self) -> None:
        # In-memory summary cache keyed by SHA-256 of cluster text.
        # Prevents re-summarizing the same cluster across runs.
        self._summary_cache: Dict[str, str] = {}

    # ── public API ────────────────────────────────────────────────────────────

    async def build_tree(self, chunks: List[Chunk]) -> List[RAPTORNode]:
        """Return all nodes (leaves + summaries) that should be stored."""
        logger.info(f"RAPTOR: building tree from {len(chunks)} leaf chunks")

        # Layer 0: wrap raw chunks as RAPTORNodes
        leaf_nodes = [
            RAPTORNode(
                node_id=c.chunk_id,
                text=c.text,
                layer=0,
                metadata=c.metadata,
            )
            for c in chunks
        ]

        all_nodes: list[RAPTORNode] = list(leaf_nodes)
        current_layer_nodes = leaf_nodes
        current_layer = 0

        while len(current_layer_nodes) > MIN_NODES_TO_RECURSE and current_layer < MAX_DEPTH:
            logger.info(f"RAPTOR layer {current_layer} → {len(current_layer_nodes)} nodes, clustering...")
            summary_nodes = await self._cluster_and_summarize(
                current_layer_nodes, target_layer=current_layer + 1
            )
            if not summary_nodes:
                break
            all_nodes.extend(summary_nodes)
            current_layer_nodes = summary_nodes
            current_layer += 1

        logger.info(
            f"RAPTOR tree complete: {len(all_nodes)} total nodes across {current_layer + 1} layers"
        )
        self._log_layer_stats(all_nodes)
        return all_nodes

    # ── internals ─────────────────────────────────────────────────────────────

    async def _embed_nodes(self, nodes: List[RAPTORNode]) -> np.ndarray:
        """Return (n, embedding_dim) array of node embeddings."""
        texts = [n.text for n in nodes]
        # Embed in batches of 100
        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), 100):
            batch = texts[i : i + 100]
            vecs = await llm_client.embed(batch)
            all_embeddings.extend(vecs)
        return np.array(all_embeddings, dtype=np.float32)

    def _umap_reduce(self, embeddings: np.ndarray) -> np.ndarray:
        """Reduce high-dim embeddings to UMAP_DIMS for clustering."""
        from umap import UMAP

        n = len(embeddings)
        n_neighbors = min(UMAP_NEIGHBORS, n - 1)
        n_components = min(UMAP_DIMS, n - 2)

        if n_components < 2:
            return embeddings   # too few nodes to reduce

        reducer = UMAP(
            n_components=n_components,
            n_neighbors=n_neighbors,
            metric="cosine",
            random_state=42,
            low_memory=True,
        )
        return reducer.fit_transform(embeddings)

    def _gmm_cluster(self, reduced: np.ndarray, n_nodes: int) -> np.ndarray:
        """Return soft assignment matrix of shape (n_nodes, n_clusters)."""
        from sklearn.mixture import GaussianMixture

        n_clusters = max(2, n_nodes // CHUNKS_PER_CLUSTER)
        n_clusters = min(n_clusters, n_nodes - 1)

        gmm = GaussianMixture(
            n_components=n_clusters,
            covariance_type="full",
            random_state=42,
            max_iter=200,
        )
        gmm.fit(reduced)
        return gmm.predict_proba(reduced)   # shape: (n_nodes, n_clusters)

    async def _summarize_cluster(self, texts: List[str], layer: int) -> str:
        """LLM-summarize a cluster. Caches by content hash."""
        combined = "\n\n---\n\n".join(texts)
        cache_key = hashlib.sha256(combined.encode()).hexdigest()

        if cache_key in self._summary_cache:
            logger.debug(f"Summary cache hit (layer {layer})")
            return self._summary_cache[cache_key]

        prompt = CLUSTER_SUMMARIZER.format(text=combined)
        summary = await llm_client.complete(
            messages=[{"role": "user", "content": prompt}],
            model=llm_client.fast_model,
            max_tokens=SUMMARY_MAX_TOKENS,
            temperature=0.0,
        )
        self._summary_cache[cache_key] = summary
        return summary

    async def _cluster_and_summarize(
        self, nodes: List[RAPTORNode], target_layer: int
    ) -> List[RAPTORNode]:
        """One full RAPTOR layer: embed → UMAP → GMM → summarize each cluster."""
        embeddings = await self._embed_nodes(nodes)
        reduced = self._umap_reduce(embeddings)
        soft_assignments = self._gmm_cluster(reduced, len(nodes))

        n_clusters = soft_assignments.shape[1]

        # Build cluster membership lists (soft — a node can belong to multiple clusters)
        clusters: dict[int, list[RAPTORNode]] = {k: [] for k in range(n_clusters)}
        for i, node in enumerate(nodes):
            for k in range(n_clusters):
                if soft_assignments[i, k] >= GMM_MEMBERSHIP_THRESHOLD:
                    clusters[k].append(node)

        # Summarize each cluster concurrently
        async def summarize_one(cluster_id: int, members: List[RAPTORNode]) -> Optional[RAPTORNode]:
            if not members:
                return None
            texts = [m.text for m in members]
            summary_text = await self._summarize_cluster(texts, target_layer)

            node_id = hashlib.md5(
                f"layer{target_layer}_cluster{cluster_id}".encode()
            ).hexdigest()[:12]

            return RAPTORNode(
                node_id=node_id,
                text=summary_text,
                layer=target_layer,
                metadata={
                    "source": members[0].metadata.get("source", ""),
                    "cluster_id": cluster_id,
                    "member_count": len(members),
                },
                children=[m.node_id for m in members],
            )

        tasks = [summarize_one(k, members) for k, members in clusters.items()]
        results = await asyncio.gather(*tasks)
        return [r for r in results if r is not None]

    def _log_layer_stats(self, all_nodes: List[RAPTORNode]) -> None:
        from collections import Counter
        counts = Counter(n.layer for n in all_nodes)
        for layer in sorted(counts):
            label = "leaf chunks" if layer == 0 else f"layer-{layer} summaries"
            logger.info(f"  Layer {layer}: {counts[layer]} {label}")
