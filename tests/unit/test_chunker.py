import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from app.ingestion.chunker import DocumentChunker, Chunk
from app.ingestion.loaders import LoadedDocument


def make_doc(text: str, source: str = "test.txt") -> LoadedDocument:
    return LoadedDocument(text_content=text, metadata={"source": source, "type": "text"})


class TestDocumentChunker:

    def test_basic_chunking(self):
        chunker = DocumentChunker(chunk_size=100, chunk_overlap=20)
        doc = make_doc("word " * 300)
        chunks = chunker.chunk(doc)
        assert len(chunks) > 1

    def test_metadata_preserved(self):
        chunker = DocumentChunker()
        doc = make_doc("hello world " * 50, source="my_file.pdf")
        chunks = chunker.chunk(doc)
        for c in chunks:
            assert c.metadata["source"] == "my_file.pdf"
            assert c.metadata["layer"] == 0
            assert "chunk_index" in c.metadata

    def test_chunk_ids_unique(self):
        chunker = DocumentChunker()
        doc = make_doc("unique content " * 100)
        chunks = chunker.chunk(doc)
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids)), "Chunk IDs must be unique"

    def test_empty_text_returns_no_chunks(self):
        chunker = DocumentChunker()
        doc = make_doc("")
        chunks = chunker.chunk(doc)
        assert chunks == []

    def test_token_count(self):
        chunk = Chunk(text="hello world", metadata={})
        assert chunk.token_count() > 0
        assert chunk.token_count() <= 5
