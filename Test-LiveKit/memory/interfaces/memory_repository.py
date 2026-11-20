"""Abstract MemoryRepository interface."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from memory.models.memory import (
    ConversationMessage,
    MemoryCreate,
    MemoryRecord,
    MemorySearchResult,
    MemoryUpdate,
)


class BaseMemoryRepository(ABC):
    """Storage-agnostic async repository for users, conversations, and memories."""

    @abstractmethod
    async def ensure_user(self, user_id: str, display_name: str | None = None) -> None:
        """Idempotently ensure a user row exists."""

    @abstractmethod
    async def save_conversation_messages(
        self, messages: list[ConversationMessage]
    ) -> list[ConversationMessage]:
        """Persist conversation turns in order."""

    @abstractmethod
    async def list_conversation_messages(
        self, user_id: str, session_id: str, *, limit: int = 100
    ) -> list[ConversationMessage]:
        """Retrieve conversation history for a user's session."""

    @abstractmethod
    async def insert(
        self,
        memory: MemoryCreate,
        *,
        embedding: list[float],
        embedding_model: str,
        embedding_dimension: int,
        reason: str = "initial_add",
    ) -> MemoryRecord:
        """Insert a new memory and record an ADD history entry."""

    @abstractmethod
    async def get(self, user_id: str, memory_id: uuid.UUID) -> MemoryRecord | None:
        """Fetch one memory scoped strictly to user_id."""

    @abstractmethod
    async def update(
        self,
        user_id: str,
        memory_id: uuid.UUID,
        patch: MemoryUpdate,
        *,
        embedding: list[float] | None = None,
        embedding_model: str | None = None,
        embedding_dimension: int | None = None,
        expected_version: int | None = None,
    ) -> MemoryRecord | None:
        """Update an existing memory scoped strictly to user_id and record an UPDATE history entry."""

    @abstractmethod
    async def delete(
        self,
        user_id: str,
        memory_id: uuid.UUID,
        *,
        reason: str = "deleted",
        source_session_id: str | None = None,
    ) -> bool:
        """Delete a memory scoped strictly to user_id and record a DELETE history entry."""

    @abstractmethod
    async def search_similar(
        self,
        user_id: str,
        query_embedding: list[float],
        *,
        embedding_model: str,
        limit: int = 5,
        min_similarity: float = 0.0,
    ) -> list[MemorySearchResult]:
        """Search memories by vector cosine similarity, strictly filtered by user_id and embedding_model."""

    @abstractmethod
    async def list_by_user(
        self, user_id: str, *, limit: int = 100, include_expired: bool = False
    ) -> list[MemoryRecord]:
        """List memories belonging strictly to user_id."""
