"""Unit tests for MemoryRetrievalService and OllamaEmbeddingProvider (no DB/network required)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import httpx
import pytest

from memory.interfaces.embedding_provider import BaseEmbeddingProvider
from memory.interfaces.memory_repository import BaseMemoryRepository
from memory.models.memory import MemorySearchResult
from memory.providers.ollama_embedding import EmbeddingError, OllamaEmbeddingProvider
from memory.services.retrieval import MemoryRetrievalService


class FakeEmbeddingProvider(BaseEmbeddingProvider):
    def __init__(self, model: str = "embeddinggemma-2:270m", dim: int = 4) -> None:
        self._model = model
        self._dim = dim
        self.calls: list[str] = []

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        return self._dim

    async def embed(self, text: str) -> list[float]:
        self.calls.append(text)
        return [0.25] * self._dim

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(t) for t in texts]


def test_retrieval_delegates_with_user_and_model_filter():
    now = datetime.now(timezone.utc)
    expected = [
        MemorySearchResult(
            memory_id=uuid.uuid4(),
            content="毎朝6時に散歩する",
            memory_type="habit",
            similarity_score=0.92,
            created_at=now,
            updated_at=now,
        )
    ]
    repo = AsyncMock(spec=BaseMemoryRepository)
    repo.search_similar.return_value = expected
    embedder = FakeEmbeddingProvider()

    service = MemoryRetrievalService(
        repository=repo,
        embedding_provider=embedder,
        default_limit=5,
        default_min_similarity=0.3,
    )

    results = asyncio.run(service.search("user-1", "朝の習慣は？"))
    assert results == expected
    assert embedder.calls == ["朝の習慣は？"]
    repo.search_similar.assert_awaited_once_with(
        user_id="user-1",
        query_embedding=[0.25, 0.25, 0.25, 0.25],
        embedding_model="embeddinggemma-2:270m",
        limit=5,
        min_similarity=0.3,
    )

    formatted = MemoryRetrievalService.format_for_agent(results)
    assert "[habit] 毎朝6時に散歩する" in formatted


def test_retrieval_blank_query_returns_empty_without_embedding():
    repo = AsyncMock(spec=BaseMemoryRepository)
    embedder = FakeEmbeddingProvider()
    service = MemoryRetrievalService(repository=repo, embedding_provider=embedder)

    assert asyncio.run(service.search("user-1", "   ")) == []
    assert embedder.calls == []
    repo.search_similar.assert_not_awaited()


def test_ollama_provider_validates_dimension():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"embeddings": [[0.1, 0.2, 0.3]]})
    )

    async def scenario():
        async with httpx.AsyncClient(transport=transport) as client:
            provider = OllamaEmbeddingProvider(
                model="embeddinggemma-2:270m",
                dimension=768,
                client=client,
            )
            with pytest.raises(EmbeddingError, match="dimension mismatch"):
                await provider.embed("テスト")

    asyncio.run(scenario())


def test_ollama_provider_returns_valid_vector():
    vec = [0.5] * 4
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"embeddings": [vec]})
    )

    async def scenario():
        async with httpx.AsyncClient(transport=transport) as client:
            provider = OllamaEmbeddingProvider(
                model="embeddinggemma-2:270m",
                dimension=4,
                client=client,
            )
            out = await provider.embed("私は毎朝散歩します")
            assert out == vec

    asyncio.run(scenario())
