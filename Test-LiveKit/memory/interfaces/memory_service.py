"""Abstract BaseMemoryService interface for local PostgreSQL and future GCP Memory Bank."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from memory.models.memory import (
    ConversationMessage,
    MemoryCreate,
    MemoryRecord,
    MemorySearchResult,
    MemoryUpdate,
    ProcessConversationResult,
)


class BaseMemoryService(ABC):
    """High-level memory service contract.

    Implementations:
    - PostgresMemoryService (Level 2 local PostgreSQL + pgvector)
    - GCPMemoryBankService (future migration target)
    """

    @abstractmethod
    async def search_memory(
        self,
        user_id: str,
        query: str,
        *,
        limit: int | None = None,
        min_similarity: float | None = None,
    ) -> list[MemorySearchResult]:
        """Retrieve relevant long-term memories for a user query."""

    @abstractmethod
    async def add_memory(self, memory: MemoryCreate) -> MemoryRecord:
        """Directly add a memory for a user."""

    @abstractmethod
    async def get_memory(self, user_id: str, memory_id: uuid.UUID) -> MemoryRecord | None:
        """Fetch a specific memory for a user."""

    @abstractmethod
    async def update_memory(
        self, user_id: str, memory_id: uuid.UUID, patch: MemoryUpdate
    ) -> MemoryRecord | None:
        """Update an existing memory for a user."""

    @abstractmethod
    async def delete_memory(
        self,
        user_id: str,
        memory_id: uuid.UUID,
        *,
        reason: str = "deleted",
        source_session_id: str | None = None,
    ) -> bool:
        """Delete a memory for a user."""

    @abstractmethod
    async def list_memories(self, user_id: str, *, limit: int = 100) -> list[MemoryRecord]:
        """List all active memories for a user."""

    @abstractmethod
    async def process_conversation(
        self,
        user_id: str,
        session_id: str,
        messages: list[ConversationMessage],
    ) -> ProcessConversationResult:
        """Persist conversation turns, extract candidate memories, and consolidate them."""
