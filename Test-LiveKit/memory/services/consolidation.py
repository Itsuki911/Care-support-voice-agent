"""Memory Consolidation service: decides ADD / UPDATE / DELETE / NOOP against existing memories."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Protocol

from memory.interfaces.embedding_provider import BaseEmbeddingProvider
from memory.interfaces.memory_repository import BaseMemoryRepository
from memory.models.memory import (
    ConsolidationAction,
    ConsolidationDecision,
    ExtractedMemory,
    MemoryCreate,
    MemorySearchResult,
    MemoryUpdate,
)

logger = logging.getLogger("care-support-voice-agent.memory.consolidation")


class MemoryConsolidatorBackend(Protocol):
    async def decide_consolidation(
        self,
        candidate: ExtractedMemory,
        existing_memories: list[MemorySearchResult],
    ) -> ConsolidationDecision: ...


@dataclass
class ConsolidationOutcome:
    added_ids: list[uuid.UUID] = field(default_factory=list)
    updated_ids: list[uuid.UUID] = field(default_factory=list)
    deleted_ids: list[uuid.UUID] = field(default_factory=list)
    noop_count: int = 0
    errors: list[str] = field(default_factory=list)


class MemoryConsolidationService:
    """Reconciles candidate memories with existing user memories safely and idempotently."""

    def __init__(
        self,
        *,
        repository: BaseMemoryRepository,
        embedding_provider: BaseEmbeddingProvider,
        consolidator: MemoryConsolidatorBackend,
        similar_limit: int = 5,
        candidate_similarity_threshold: float = 0.35,
    ) -> None:
        self._repository = repository
        self._embedding_provider = embedding_provider
        self._consolidator = consolidator
        self._similar_limit = similar_limit
        self._candidate_similarity_threshold = candidate_similarity_threshold
        self._user_locks: dict[str, asyncio.Lock] = {}

    def _lock_for_user(self, user_id: str) -> asyncio.Lock:
        lock = self._user_locks.get(user_id)
        if lock is None:
            lock = asyncio.Lock()
            self._user_locks[user_id] = lock
        return lock

    async def consolidate(
        self,
        user_id: str,
        candidates: list[ExtractedMemory],
    ) -> ConsolidationOutcome:
        outcome = ConsolidationOutcome()
        if not candidates:
            return outcome

        # Serialize consolidation per user within the process to prevent race conditions.
        async with self._lock_for_user(user_id):
            for candidate in candidates:
                try:
                    await self._consolidate_one(user_id, candidate, outcome)
                except Exception as exc:
                    logger.warning(
                        "Consolidation failed for user %s candidate %r: %s",
                        user_id,
                        candidate.content[:60],
                        exc,
                    )
                    outcome.errors.append(str(exc))
        return outcome

    async def _consolidate_one(
        self,
        user_id: str,
        candidate: ExtractedMemory,
        outcome: ConsolidationOutcome,
    ) -> None:
        candidate_embedding = await self._embedding_provider.embed(candidate.content)
        existing = await self._repository.search_similar(
            user_id=user_id,
            query_embedding=candidate_embedding,
            embedding_model=self._embedding_provider.model_name,
            limit=self._similar_limit,
            min_similarity=self._candidate_similarity_threshold,
        )

        # Fast-path exact duplicate suppression without extra LLM call
        normalized_candidate = candidate.content.strip().lower()
        if any(item.content.strip().lower() == normalized_candidate for item in existing):
            outcome.noop_count += 1
            return

        decision = await self._consolidator.decide_consolidation(candidate, existing)
        valid_ids = {item.memory_id for item in existing}

        if decision.action == ConsolidationAction.ADD:
            record = await self._repository.insert(
                MemoryCreate(
                    user_id=user_id,
                    content=decision.merged_content or candidate.content,
                    memory_type=decision.memory_type or candidate.memory_type,
                    importance=(
                        decision.importance
                        if decision.importance is not None
                        else candidate.importance
                    ),
                    confidence=(
                        decision.confidence
                        if decision.confidence is not None
                        else candidate.confidence
                    ),
                    source_session_id=candidate.source_session_id,
                ),
                embedding=candidate_embedding,
                embedding_model=self._embedding_provider.model_name,
                embedding_dimension=self._embedding_provider.dimension,
                reason=decision.reason or "consolidation_add",
            )
            outcome.added_ids.append(record.id)
            return

        if decision.action == ConsolidationAction.UPDATE:
            if decision.target_memory_id is None or decision.target_memory_id not in valid_ids:
                outcome.noop_count += 1
                return
            merged_text = (decision.merged_content or candidate.content).strip()
            new_embedding = (
                candidate_embedding
                if merged_text == candidate.content.strip()
                else await self._embedding_provider.embed(merged_text)
            )
            updated = await self._repository.update(
                user_id,
                decision.target_memory_id,
                MemoryUpdate(
                    content=merged_text,
                    memory_type=decision.memory_type,
                    importance=decision.importance,
                    confidence=decision.confidence,
                    source_session_id=candidate.source_session_id,
                    reason=decision.reason or "consolidation_update",
                ),
                embedding=new_embedding,
                embedding_model=self._embedding_provider.model_name,
                embedding_dimension=self._embedding_provider.dimension,
            )
            if updated is not None:
                outcome.updated_ids.append(updated.id)
            else:
                outcome.noop_count += 1
            return

        if decision.action == ConsolidationAction.DELETE:
            if decision.target_memory_id is None or decision.target_memory_id not in valid_ids:
                outcome.noop_count += 1
                return
            deleted = await self._repository.delete(
                user_id,
                decision.target_memory_id,
                reason=decision.reason or "consolidation_delete",
                source_session_id=candidate.source_session_id,
            )
            if deleted:
                outcome.deleted_ids.append(decision.target_memory_id)
            else:
                outcome.noop_count += 1
            return

        outcome.noop_count += 1
