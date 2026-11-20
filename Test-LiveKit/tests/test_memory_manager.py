"""Unit tests for MemoryManager, PostgresMemoryService fallback, and MemoryBackgroundWorker."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from memory.interfaces.embedding_provider import BaseEmbeddingProvider
from memory.interfaces.memory_repository import BaseMemoryRepository
from memory.interfaces.memory_service import BaseMemoryService
from memory.models.memory import (
    ConsolidationAction,
    ConsolidationDecision,
    ConversationMessage,
    ExtractedMemory,
    MemoryRecord,
)
from memory.services.consolidation import MemoryConsolidationService
from memory.services.extraction import MemoryExtractionService
from memory.services.memory_manager import MemoryManager, PostgresMemoryService
from memory.services.retrieval import MemoryRetrievalService
from workers.memory_worker import MemoryBackgroundWorker


class DummyEmbedder(BaseEmbeddingProvider):
    @property
    def model_name(self) -> str:
        return "embeddinggemma-2:270m"

    @property
    def dimension(self) -> int:
        return 4

    async def embed(self, text: str) -> list[float]:
        return [0.5, 0.5, 0.5, 0.5]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[0.5, 0.5, 0.5, 0.5] for _ in texts]


def test_postgres_memory_service_implements_base_interface_and_handles_db_outage():
    repo = AsyncMock(spec=BaseMemoryRepository)
    repo.search_similar.side_effect = RuntimeError("PostgreSQL connection refused")
    embedder = DummyEmbedder()

    class NoopLLM:
        async def extract_memories(self, messages, *, session_id):
            return []

        async def decide_consolidation(self, candidate, existing_memories):
            return ConsolidationDecision(action=ConsolidationAction.NOOP)

    service = PostgresMemoryService(
        repository=repo,
        embedding_provider=embedder,
        retrieval_service=MemoryRetrievalService(repository=repo, embedding_provider=embedder),
        extraction_service=MemoryExtractionService(extractor=NoopLLM()),
        consolidation_service=MemoryConsolidationService(
            repository=repo, embedding_provider=embedder, consolidator=NoopLLM()
        ),
    )
    assert isinstance(service, BaseMemoryService)

    # Graceful degradation when local PostgreSQL is stopped: returns [] instead of crashing voice session
    assert asyncio.run(service.search_memory_safe("user-1", "朝の習慣")) == []


def test_background_worker_processes_conversations_asynchronously():
    now = datetime.now(timezone.utc)
    saved_id = uuid.uuid4()
    repo = AsyncMock(spec=BaseMemoryRepository)
    repo.save_conversation_messages.side_effect = lambda msgs: msgs
    repo.search_similar.return_value = []
    repo.insert.return_value = MemoryRecord(
        id=saved_id,
        user_id="user-1",
        content="ユーザーは毎朝6時に散歩する",
        memory_type="habit",
        embedding_model="embeddinggemma-2:270m",
        embedding_dimension=4,
        importance=0.8,
        confidence=0.9,
        source_session_id="sess-a",
        version=1,
        created_at=now,
        updated_at=now,
    )
    embedder = DummyEmbedder()

    class FakeLLM:
        async def extract_memories(self, messages, *, session_id):
            return [
                ExtractedMemory(
                    content="ユーザーは毎朝6時に散歩する",
                    memory_type="habit",
                    importance=0.8,
                    confidence=0.9,
                    source_session_id=session_id,
                )
            ]

        async def decide_consolidation(self, candidate, existing_memories):
            return ConsolidationDecision(action=ConsolidationAction.ADD, reason="new")

    service = PostgresMemoryService(
        repository=repo,
        embedding_provider=embedder,
        retrieval_service=MemoryRetrievalService(repository=repo, embedding_provider=embedder),
        extraction_service=MemoryExtractionService(extractor=FakeLLM()),
        consolidation_service=MemoryConsolidationService(
            repository=repo, embedding_provider=embedder, consolidator=FakeLLM()
        ),
    )
    manager = MemoryManager(service)
    worker = MemoryBackgroundWorker(manager)

    async def scenario():
        worker.start()
        queued = worker.enqueue_conversation(
            "user-1",
            "sess-a",
            [
                ConversationMessage(
                    user_id="user-1",
                    session_id="sess-a",
                    role="user",
                    content="毎朝6時に散歩しています",
                )
            ],
        )
        assert queued is True
        await worker.stop(drain_timeout=5.0)
        assert len(worker.completed_results) == 1
        res = worker.completed_results[0]
        assert res.saved_messages == 1
        assert res.extracted_count == 1
        assert res.added_ids == [saved_id]
        assert res.errors == []

    asyncio.run(scenario())
