"""Abstract TextChunker interface (swappable for Semantic Chunking in the future)."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from rag.models.rag import ParsedDocument, TextChunk


class BaseTextChunker(ABC):
    """Splits a ParsedDocument into indexed TextChunks."""

    @abstractmethod
    def chunk(
        self,
        document: ParsedDocument,
        *,
        document_id: uuid.UUID | None = None,
    ) -> list[TextChunk]:
        """Split ``document`` into ordered TextChunks preserving page numbers and metadata."""
