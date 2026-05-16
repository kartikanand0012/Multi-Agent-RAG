import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from app.retrieval.hybrid_search import HybridSearcher, _reciprocal_rank_fusion
from app.retrieval.bm25_retriever import BM25Retriever


def make_result(text: str, score: float) -> tuple:
    return (text, score, {"source": "test.pdf", "layer": 0})


class TestRRF:

    def test_single_list_preserves_order(self):
        ranked = [make_result(f"doc{i}", 1.0 - i * 0.1) for i in range(5)]
        fused = _reciprocal_rank_fusion([ranked])
        texts = [r[0] for r in fused]
        assert texts[0] == "doc0"

    def test_doc_in_both_lists_gets_boosted(self):
        list1 = [make_result("shared", 0.9), make_result("only_in_1", 0.8)]
        list2 = [make_result("shared", 0.7), make_result("only_in_2", 0.6)]
        fused = _reciprocal_rank_fusion([list1, list2])
        top = fused[0][0]
        assert top == "shared"

    def test_empty_lists_handled(self):
        fused = _reciprocal_rank_fusion([[], []])
        assert fused == []

    def test_deduplication(self):
        doc = make_result("duplicate", 0.9)
        fused = _reciprocal_rank_fusion([[doc, doc]])
        texts = [r[0] for r in fused]
        assert texts.count("duplicate") == 1


class TestHybridSearcher:

    @pytest.mark.asyncio
    async def test_falls_back_to_vector_when_bm25_empty(self):
        mock_vs = MagicMock()
        mock_vs.similarity_search = AsyncMock(return_value=[
            make_result("vector result", 0.85)
        ])
        bm25 = BM25Retriever()   # empty — not indexed

        searcher = HybridSearcher(mock_vs, bm25)
        results = await searcher.search("test query", k_final=3, notebook_id="nb1")

        assert len(results) > 0
        assert results[0][0] == "vector result"

    @pytest.mark.asyncio
    async def test_fuses_both_retrievers(self):
        mock_vs = MagicMock()
        mock_vs.similarity_search = AsyncMock(return_value=[
            make_result("vec_doc_1", 0.9), make_result("shared_doc", 0.8)
        ])
        bm25 = BM25Retriever()
        bm25.index(["shared_doc content", "bm25_doc_1 content"],
                   [{"source": "f1"}, {"source": "f2"}])

        searcher = HybridSearcher(mock_vs, bm25)
        results = await searcher.search("shared", k_initial=5, k_final=5, notebook_id="nb1")

        assert len(results) > 0
