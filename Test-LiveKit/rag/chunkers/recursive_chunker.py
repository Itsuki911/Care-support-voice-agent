"""Recursive character text chunker backed by langchain-text-splitters."""

from __future__ import annotations

import uuid

from langchain_text_splitters import RecursiveCharacterTextSplitter

from rag.interfaces.chunker import BaseTextChunker
from rag.models.rag import ParsedDocument, TextChunk

DEFAULT_SEPARATORS: list[str] = ["\n\n", "\n", "。", "、", " ", ""]


class RecursiveTextChunker(BaseTextChunker):
    """Splits documents using RecursiveCharacterTextSplitter while preserving page numbers."""

    def __init__(
        self,
        *,
        chunk_size: int = 450,
        chunk_overlap: int = 80,
        separators: list[str] | None = None,
    ) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be >= 0 and < chunk_size")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = list(separators) if separators is not None else list(DEFAULT_SEPARATORS)
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=self.separators,
            keep_separator=False,
        )

    def chunk(
        self,
        document: ParsedDocument,
        *,
        document_id: uuid.UUID | None = None,
    ) -> list[TextChunk]:
        chunks: list[TextChunk] = []
        chunk_index = 0
        for page in document.pages:
            page_text = page.text.strip()
            if not page_text:
                continue
            pieces = self._splitter.split_text(page_text)
            for piece in pieces:
                cleaned = piece.strip()
                if not cleaned:
                    continue
                meta = {
                    **document.metadata,
                    **page.metadata,
                    "filename": document.filename,
                    "file_type": document.file_type,
                }
                if page.page_number is not None:
                    meta["page_number"] = page.page_number
                chunks.append(
                    TextChunk(
                        document_id=document_id,
                        content=cleaned,
                        chunk_index=chunk_index,
                        page_number=page.page_number,
                        metadata=meta,
                    )
                )
                chunk_index += 1
        return chunks
