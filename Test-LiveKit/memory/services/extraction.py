"""Memory Extraction service: extracts structured long-term memories from conversations."""

from __future__ import annotations

import logging
from typing import Protocol

from memory.models.memory import ConversationMessage, ExtractedMemory

logger = logging.getLogger("care-support-voice-agent.memory.extraction")


class MemoryExtractorBackend(Protocol):
    async def extract_memories(
        self,
        messages: list[ConversationMessage],
        *,
        session_id: str,
    ) -> list[ExtractedMemory]: ...


class MemoryExtractionService:
    """Coordinates LLM-based memory extraction with safe error handling."""

    def __init__(self, *, extractor: MemoryExtractorBackend) -> None:
        self._extractor = extractor

    async def extract(
        self,
        messages: list[ConversationMessage],
        *,
        session_id: str,
        raise_on_error: bool = False,
    ) -> list[ExtractedMemory]:
        if not messages:
            return []
        try:
            extracted = await self._extractor.extract_memories(messages, session_id=session_id)
        except Exception as exc:
            logger.warning("Memory extraction failed for session %s: %s", session_id, exc)
            if raise_on_error:
                raise
            return []

        deduped: list[ExtractedMemory] = []
        seen: set[str] = set()
        for item in extracted:
            key = item.content.strip().lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(
                item.model_copy(update={"source_session_id": item.source_session_id or session_id})
            )
        return deduped
