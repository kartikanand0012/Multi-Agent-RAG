import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from app.retrieval.bm25_retriever import BM25Retriever


DOCS = [
    "Apple revenue grew significantly in fiscal year 2024",
    "The iPhone remains Apple's primary revenue driver",
    "Apple faces risks from supply chain disruptions",
    "Tim Cook is the Chief Executive Officer of Apple",
    "Google and Microsoft compete with Apple in cloud services",
]
METAS = [{"source": f"doc{i}.txt"} for i in range(len(DOCS))]


class TestBM25Retriever:

    def setup_method(self):
        self.bm25 = BM25Retriever()
        self.bm25.index(DOCS, METAS)

    def test_is_ready_after_index(self):
        assert self.bm25.is_ready is True

    def test_not_ready_before_index(self):
        bm25 = BM25Retriever()
        assert bm25.is_ready is False

    def test_search_returns_results(self):
        results = self.bm25.search("Apple revenue", k=3)
        assert len(results) > 0

    def test_exact_keyword_ranked_first(self):
        results = self.bm25.search("Tim Cook Chief Executive Officer", k=5)
        assert len(results) > 0
        top_text = results[0][0]
        assert "Tim Cook" in top_text

    def test_irrelevant_query_returns_empty(self):
        results = self.bm25.search("quantum physics particle accelerator", k=3)
        # BM25 returns zero-score results filtered out
        assert all(score > 0 for _, score, _ in results)

    def test_search_empty_index(self):
        bm25 = BM25Retriever()
        results = bm25.search("anything", k=3)
        assert results == []

    def test_k_limits_results(self):
        results = self.bm25.search("Apple", k=2)
        assert len(results) <= 2
