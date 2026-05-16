from __future__ import annotations

import hashlib
import logging
from typing import List

from langchain.text_splitter import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.ingestion.loaders import LoadedDocument
from app.llm.client import count_tokens

logger = logging.getLogger(__name__)


class Chunk:
    """A single text chunk with source metadata."""

    def __init__(self, text: str, metadata: dict):
        self.text = text
        self.metadata = metadata
        self.chunk_id = hashlib.md5(text.encode()).hexdigest()[:12]

    def token_count(self) -> int:
        return count_tokens(self.text)

    def __repr__(self) -> str:
        return f"Chunk(id={self.chunk_id}, tokens={self.token_count()}, source={self.metadata.get('source', '?')})"


class DocumentChunker:
    """Splits a LoadedDocument into token-bounded chunks with metadata."""

    def __init__(
        self,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ):
        self.chunk_size = chunk_size or settings.chunk_size
        self.chunk_overlap = chunk_overlap or settings.chunk_overlap

        # Use character-based splitter; we verify token counts after splitting
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size * 4,   # ~4 chars per token on average
            chunk_overlap=self.chunk_overlap * 4,
            separators=["\n\n", "\n", ". ", " ", ""],
            length_function=len,
        )

    def chunk(self, doc: LoadedDocument) -> List[Chunk]:
        raw_chunks = self._splitter.split_text(doc.text_content)
        chunks: list[Chunk] = []

        for i, text in enumerate(raw_chunks):
            text = text.strip()
            if not text:
                continue
            metadata = {
                **doc.metadata,
                "chunk_index": i,
                "layer": 0,   # Layer 0 = raw leaf chunks (RAPTOR will add higher layers later)
            }
            chunks.append(Chunk(text=text, metadata=metadata))

        over_limit = [c for c in chunks if c.token_count() > self.chunk_size * 1.2]
        if over_limit:
            logger.warning(f"{len(over_limit)} chunks exceed token limit — consider smaller chunk_size")

        logger.info(
            f"Chunked '{doc.metadata.get('source', 'unknown')}': "
            f"{len(chunks)} chunks, avg {sum(c.token_count() for c in chunks) // max(len(chunks), 1)} tokens each"
        )
        return chunks
