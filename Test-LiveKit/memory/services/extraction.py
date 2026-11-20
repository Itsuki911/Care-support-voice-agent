"""Memory Extraction service: extracts structured long-term memories from conversations."""

from __future__ import annotations

import logging
from typing import Protocol

from memory.models.memory import ConversationMessage, ExtractedMemory
from memory.observability import NOOP_TRACER, MemoryTracer

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

    def __init__(
        self,
        *,
        extractor: MemoryExtractorBackend,
        tracer: MemoryTracer | None = None,
    ) -> None:
        self._extractor = extractor
        self._tracer = tracer or NOOP_TRACER

    async def extract(
        self,
        messages: list[ConversationMessage],
        *,
        session_id: str,
        raise_on_error: bool = False,
    ) -> list[ExtractedMemory]:
        if not messages:
            return []
        with self._tracer.span(
            "memory.extraction",
            session_id=session_id,
            message_count=len(messages),
        ) as span:
            try:
                extracted = await self._extractor.extract_memories(messages, session_id=session_id)
            except Exception as exc:
                logger.warning("Memory extraction failed for session %s: %s", session_id, exc)
                span.set_error(exc)
                span.set(status="error")
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
            span.set(
                status="ok",
                raw_extracted_count=len(extracted),
                extracted_count=len(deduped),
                memory_types=sorted({str(getattr(m.memory_type, "value", m.memory_type)) for m in deduped}),
            )
            span.set_output([m.model_dump(mode="json") for m in deduped])
            return deduped
