"""Unit tests for MemoryConsolidationService (ADD, UPDATE, DELETE, NOOP)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from memory.interfaces.embedding_provider import BaseEmbeddingProvider
from memory.interfaces.memory_repository import BaseMemoryRepository
from memory.models.memory import (
    ConsolidationAction,
    ConsolidationDecision,
    ExtractedMemory,
    MemoryRecord,
    MemorySearchResult,
)
from memory.services.consolidation import MemoryConsolidationService


class StubEmbedder(BaseEmbeddingProvider):
    @property
    def model_name(self) -> str:
        return "embeddinggemma-2:270m"

    @property
    def dimension(self) -> int:
        return 4

    async def embed(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3, 0.4]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3, 0.4] for _ in texts]


def _make_record(user_id: str, content: str, mem_id: uuid.UUID | None = None) -> MemoryRecord:
    now = datetime.now(timezone.utc)
    return MemoryRecord(
        id=mem_id or uuid.uuid4(),
        user_id=user_id,
        content=content,
        memory_type="preference",
        embedding_model="embeddinggemma-2:270m",
        embedding_dimension=4,
        importance=0.7,
        confidence=0.9,
        source_session_id="sess-1",
        version=1,
        created_at=now,
        updated_at=now,
    )


def test_consolidation_add_update_delete_noop_and_exact_dedup():
    now = datetime.now(timezone.utc)
    existing_id = uuid.uuid4()
    existing_item = MemorySearchResult(
        memory_id=existing_id,
        content="コーヒーが好き",
        memory_type="preference",
        similarity_score=0.9,
        created_at=now,
        updated_at=now,
    )

    decisions = [
        ConsolidationDecision(action=ConsolidationAction.ADD, merged_content="紅茶も好き", reason="new"),
        ConsolidationDecision(
            action=ConsolidationAction.UPDATE,
            target_memory_id=existing_id,
            merged_content="ブラックコーヒーが好き",
            reason="refined",
        ),
        ConsolidationDecision(
            action=ConsolidationAction.DELETE,
            target_memory_id=existing_id,
            reason="user asked to forget",
        ),
        ConsolidationDecision(action=ConsolidationAction.NOOP, reason="redundant"),
    ]
    decision_iter = iter(decisions)

    class SequenceConsolidator:
        async def decide_consolidation(self, candidate, existing_memories):
            return next(decision_iter)

    repo = AsyncMock(spec=BaseMemoryRepository)
    repo.search_similar.return_value = [existing_item]
    added_rec = _make_record("u1", "紅茶も好き")
    updated_rec = _make_record("u1", "ブラックコーヒーが好き", existing_id)
    repo.insert.return_value = added_rec
    repo.update.return_value = updated_rec
    repo.delete.return_value = True

    service = MemoryConsolidationService(
        repository=repo,
        embedding_provider=StubEmbedder(),
        consolidator=SequenceConsolidator(),
    )

    candidates = [
        ExtractedMemory(content="紅茶も好き", memory_type="preference", source_session_id="s1"),
        ExtractedMemory(content="ブラックコーヒーが好き", memory_type="preference", source_session_id="s2"),
        ExtractedMemory(content="コーヒーの好みを忘れて", memory_type="preference", source_session_id="s3"),
        ExtractedMemory(content="飲み物の話", memory_type="preference", source_session_id="s4"),
        # Exact duplicate of existing_item -> fast-path NOOP without calling consolidator
        ExtractedMemory(content="コーヒーが好き", memory_type="preference", source_session_id="s5"),
    ]

    outcome = asyncio.run(service.consolidate("u1", candidates))
    assert outcome.added_ids == [added_rec.id]
    assert outcome.updated_ids == [existing_id]
    assert outcome.deleted_ids == [existing_id]
    assert outcome.noop_count == 2
    assert outcome.errors == []


def test_consolidation_ignores_unknown_target_id_on_delete():
    now = datetime.now(timezone.utc)
    existing_id = uuid.uuid4()
    repo = AsyncMock(spec=BaseMemoryRepository)
    repo.search_similar.return_value = [
        MemorySearchResult(
            memory_id=existing_id,
            content="毎朝走る",
            memory_type="habit",
            similarity_score=0.8,
            created_at=now,
            updated_at=now,
        )
    ]

    class BadTargetConsolidator:
        async def decide_consolidation(self, candidate, existing_memories):
            return ConsolidationDecision(
                action=ConsolidationAction.DELETE,
                target_memory_id=uuid.uuid4(),  # Not in existing_memories
                reason="hallucinated id",
            )

    service = MemoryConsolidationService(
        repository=repo,
        embedding_provider=StubEmbedder(),
        consolidator=BadTargetConsolidator(),
    )
    outcome = asyncio.run(
        service.consolidate("u1", [ExtractedMemory(content="走らなくなった", memory_type="habit")])
    )
    assert outcome.deleted_ids == []
    assert outcome.noop_count == 1
    repo.delete.assert_not_awaited()
