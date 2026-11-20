"""Abstract BaseRAGService interface (PostgresRAGService now; VertexRAGEngineService in future)."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from rag.models.rag import DocumentRecord, IngestResult, SearchResponse


class BaseRAGService(ABC):
    """Framework- and cloud-agnostic RAG service entry point."""

    @abstractmethod
    async def ingest_document(
        self,
        path: str | Path,
        *,
        corpus_id: str = "default",
        metadata: dict[str, Any] | None = None,
    ) -> IngestResult: ...

    @abstractmethod
    async def update_document(
        self,
        path: str | Path,
        *,
        corpus_id: str = "default",
        document_id: uuid.UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> IngestResult: ...

    @abstractmethod
    async def search(
        self,
        query: str,
        *,
        corpus_id: str | None = None,
        top_k: int | None = None,
        min_similarity: float | None = None,
        metadata_filter: dict[str, Any] | None = None,
    ) -> SearchResponse: ...

    @abstractmethod
    async def get_document(self, document_id: uuid.UUID) -> DocumentRecord | None: ...

    @abstractmethod
    async def list_documents(
        self, *, corpus_id: str | None = None, limit: int = 100
    ) -> list[DocumentRecord]: ...

    @abstractmethod
    async def delete_document(self, document_id: uuid.UUID) -> bool: ...
