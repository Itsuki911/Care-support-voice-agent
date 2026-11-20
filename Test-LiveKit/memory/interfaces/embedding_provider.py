"""Abstract EmbeddingProvider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseEmbeddingProvider(ABC):
    """Provider-agnostic async embedding interface."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Canonical embedding model identifier stored alongside vectors."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Expected output vector dimension."""

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Generate a single embedding vector for text."""

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embedding vectors for a batch of texts."""
