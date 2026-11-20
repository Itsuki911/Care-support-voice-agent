"""Abstract DocumentParser interface (swappable for Document AI Layout Parser / LLM Parser)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from rag.models.rag import ParsedDocument


class DocumentParseError(RuntimeError):
    """Raised when a document is unsupported, unreadable, corrupt, or empty."""


class BaseDocumentParser(ABC):
    """Parses raw files into a normalized ParsedDocument."""

    @abstractmethod
    def supports(self, path: Path) -> bool:
        """Return True if this parser handles the given file path/extension."""

    @abstractmethod
    def parse(self, path: Path) -> ParsedDocument:
        """Parse the file at ``path`` into a normalized ParsedDocument."""
