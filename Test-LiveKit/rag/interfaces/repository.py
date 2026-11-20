"""Abstract RAGRepository interface for document & vector persistence."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Any

from rag.models.rag import DocumentRecord, ParsedDocument, RetrievalResult, TextChunk


class BaseRAGRepository(ABC):
    """Storage abstraction for RAG corpora, documents, and vector chunks."""

    @abstractmethod
    async def ensure_corpus(
        self,
        corpus_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> None: ...

    @abstractmethod
    async def find_by_hash(self, corpus_id: str, file_hash: str) -> DocumentRecord | None: ...

    @abstractmethod
    async def find_by_filename(self, corpus_id: str, filename: str) -> DocumentRecord | None: ...

    @abstractmethod
    async def save_document_with_chunks(
        self,
        *,
        corpus_id: str,
        parsed: ParsedDocument,
        chunks: list[TextChunk],
        embeddings: list[list[float]],
        embedding_model: str,
        embedding_dimension: int,
        document_id: uuid.UUID | None = None,
        replace_existing: bool = False,
    ) -> DocumentRecord: ...

    @abstractmethod
    async def get_document(self, document_id: uuid.UUID) -> DocumentRecord | None: ...

    @abstractmethod
    async def list_documents(
        self, *, corpus_id: str | None = None, limit: int = 100
    ) -> list[DocumentRecord]: ...

    @abstractmethod
    async def delete_document(self, document_id: uuid.UUID) -> bool: ...

    @abstractmethod
    async def delete_corpus(self, corpus_id: str) -> bool: ...

    @abstractmethod
    async def search_similar(
        self,
        *,
        query_embedding: list[float],
        embedding_model: str,
        corpus_id: str | None = None,
        top_k: int = 5,
        min_similarity: float = 0.0,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[RetrievalResult]: ...
