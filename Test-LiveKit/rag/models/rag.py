"""Pydantic models for Level 3 RAG pipeline (parsing, chunking, storage, retrieval)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ParsedPage(BaseModel):
    """Single page or logical section extracted from a source file."""

    text: str
    page_number: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ParsedDocument(BaseModel):
    """Normalized representation produced by any DocumentParser."""

    filename: str
    file_type: str
    file_hash: str
    pages: list[ParsedPage]
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def full_text(self) -> str:
        return "\n\n".join(p.text for p in self.pages if p.text.strip())


class TextChunk(BaseModel):
    """Chunk produced by a TextChunker before embedding/storage."""

    chunk_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    document_id: uuid.UUID | None = None
    content: str
    chunk_index: int = Field(ge=0)
    page_number: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentRecord(BaseModel):
    """Persisted RAG document metadata."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    corpus_id: str
    filename: str
    file_type: str
    file_hash: str
    chunk_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class IngestResult(BaseModel):
    """Outcome of document ingestion or update."""

    document: DocumentRecord
    chunk_count: int
    status: str  # "ingested" | "duplicate" | "updated"


class RetrievalResult(BaseModel):
    """Single retrieved chunk with similarity score and citation metadata."""

    document_id: uuid.UUID
    chunk_id: uuid.UUID
    corpus_id: str
    content: str
    similarity_score: float
    filename: str
    file_type: str
    chunk_index: int
    page_number: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    """Structured search response including latency breakdown."""

    query: str
    corpus_id: str | None = None
    results: list[RetrievalResult] = Field(default_factory=list)
    embedding_ms: float = 0.0
    db_search_ms: float = 0.0
    total_ms: float = 0.0
