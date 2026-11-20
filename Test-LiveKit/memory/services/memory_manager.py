"""Memory Manager & PostgresMemoryService implementing BaseMemoryService."""

from __future__ import annotations

import logging
import uuid

from memory.interfaces.embedding_provider import BaseEmbeddingProvider
from memory.interfaces.memory_repository import BaseMemoryRepository
from memory.interfaces.memory_service import BaseMemoryService
from memory.models.memory import (
    ConversationMessage,
    MemoryCreate,
    MemoryRecord,
    MemorySearchResult,
    MemoryUpdate,
    ProcessConversationResult,
)
from memory.services.consolidation import MemoryConsolidationService
from memory.services.extraction import MemoryExtractionService
from memory.services.retrieval import MemoryRetrievalService

logger = logging.getLogger("care-support-voice-agent.memory.manager")


class PostgresMemoryService(BaseMemoryService):
    """Concrete local PostgreSQL + pgvector implementation of BaseMemoryService.

    Delegates all operations to Retrieval, Extraction, Consolidation, EmbeddingProvider,
    and Repository without embedding SQL or embedding transport details here.
    """

    def __init__(
        self,
        *,
        repository: BaseMemoryRepository,
        embedding_provider: BaseEmbeddingProvider,
        retrieval_service: MemoryRetrievalService,
        extraction_service: MemoryExtractionService,
        consolidation_service: MemoryConsolidationService,
    ) -> None:
        self._repository = repository
        self._embedding_provider = embedding_provider
        self._retrieval = retrieval_service
        self._extraction = extraction_service
        self._consolidation = consolidation_service

    async def search_memory(
        self,
        user_id: str,
        query: str,
        *,
        limit: int | None = None,
        min_similarity: float | None = None,
    ) -> list[MemorySearchResult]:
        return await self._retrieval.search(
            user_id, query, limit=limit, min_similarity=min_similarity
        )

    async def search_memory_safe(
        self,
        user_id: str,
        query: str,
        *,
        limit: int | None = None,
        min_similarity: float | None = None,
    ) -> list[MemorySearchResult]:
        """Search memories with graceful fallback to [] if DB or Ollama is unavailable."""
        try:
            return await self.search_memory(
                user_id, query, limit=limit, min_similarity=min_similarity
            )
        except Exception as exc:
            logger.warning("Memory retrieval unavailable (continuing conversation): %s", exc)
            return []

    async def add_memory(self, memory: MemoryCreate) -> MemoryRecord:
        embedding = await self._embedding_provider.embed(memory.content)
        return await self._repository.insert(
            memory,
            embedding=embedding,
            embedding_model=self._embedding_provider.model_name,
            embedding_dimension=self._embedding_provider.dimension,
        )

    async def get_memory(self, user_id: str, memory_id: uuid.UUID) -> MemoryRecord | None:
        return await self._repository.get(user_id, memory_id)

    async def update_memory(
        self, user_id: str, memory_id: uuid.UUID, patch: MemoryUpdate
    ) -> MemoryRecord | None:
        new_embedding: list[float] | None = None
        model_name: str | None = None
        dimension: int | None = None
        if patch.content is not None:
            new_embedding = await self._embedding_provider.embed(patch.content)
            model_name = self._embedding_provider.model_name
            dimension = self._embedding_provider.dimension
        return await self._repository.update(
            user_id,
            memory_id,
            patch,
            embedding=new_embedding,
            embedding_model=model_name,
            embedding_dimension=dimension,
        )

    async def delete_memory(
        self,
        user_id: str,
        memory_id: uuid.UUID,
        *,
        reason: str = "deleted",
        source_session_id: str | None = None,
    ) -> bool:
        return await self._repository.delete(
            user_id,
            memory_id,
            reason=reason,
            source_session_id=source_session_id,
        )

    async def list_memories(self, user_id: str, *, limit: int = 100) -> list[MemoryRecord]:
        return await self._repository.list_by_user(user_id, limit=limit)

    async def list_conversation(
        self, user_id: str, session_id: str, *, limit: int = 100
    ) -> list[ConversationMessage]:
        return await self._repository.list_conversation_messages(
            user_id, session_id, limit=limit
        )

    async def process_conversation(
        self,
        user_id: str,
        session_id: str,
        messages: list[ConversationMessage],
    ) -> ProcessConversationResult:
        result = ProcessConversationResult(session_id=session_id, user_id=user_id)
        if not messages:
            return result

        normalized = [
            m.model_copy(update={"user_id": user_id, "session_id": session_id})
            for m in messages
        ]
        saved = await self._repository.save_conversation_messages(normalized)
        result.saved_messages = len(saved)

        try:
            extracted = await self._extraction.extract(
                normalized, session_id=session_id, raise_on_error=True
            )
        except Exception as exc:
            result.errors.append(f"extraction_error: {exc}")
            return result

        result.extracted_count = len(extracted)
        if not extracted:
            return result

        consolidation = await self._consolidation.consolidate(user_id, extracted)
        result.added_ids = consolidation.added_ids
        result.updated_ids = consolidation.updated_ids
        result.deleted_ids = consolidation.deleted_ids
        result.noop_count = consolidation.noop_count
        result.errors.extend(consolidation.errors)
        return result


class MemoryManager:
    """Framework-agnostic entry point delegating to any BaseMemoryService implementation."""

    def __init__(self, service: BaseMemoryService) -> None:
        self._service = service

    async def search_memory(
        self,
        user_id: str,
        query: str,
        *,
        limit: int | None = None,
        min_similarity: float | None = None,
    ) -> list[MemorySearchResult]:
        return await self._service.search_memory(
            user_id, query, limit=limit, min_similarity=min_similarity
        )

    async def add_memory(self, memory: MemoryCreate) -> MemoryRecord:
        return await self._service.add_memory(memory)

    async def get_memory(self, user_id: str, memory_id: uuid.UUID) -> MemoryRecord | None:
        return await self._service.get_memory(user_id, memory_id)

    async def update_memory(
        self, user_id: str, memory_id: uuid.UUID, patch: MemoryUpdate
    ) -> MemoryRecord | None:
        return await self._service.update_memory(user_id, memory_id, patch)

    async def delete_memory(
        self,
        user_id: str,
        memory_id: uuid.UUID,
        *,
        reason: str = "deleted",
        source_session_id: str | None = None,
    ) -> bool:
        return await self._service.delete_memory(
            user_id,
            memory_id,
            reason=reason,
            source_session_id=source_session_id,
        )

    async def list_memories(self, user_id: str, *, limit: int = 100) -> list[MemoryRecord]:
        return await self._service.list_memories(user_id, limit=limit)

    async def process_conversation(
        self,
        user_id: str,
        session_id: str,
        messages: list[ConversationMessage],
    ) -> ProcessConversationResult:
        return await self._service.process_conversation(user_id, session_id, messages)
