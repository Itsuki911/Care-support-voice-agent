"""Non-blocking background worker for LiveKit Agents memory extraction & consolidation.

Voice turns call `enqueue_conversation(...)` which returns immediately without blocking
audio playback or LLM replies. Errors are logged and isolated so DB/Ollama outages
never interrupt an active voice conversation.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from memory.models.memory import ConversationMessage, ProcessConversationResult
from memory.services.memory_manager import MemoryManager

logger = logging.getLogger("care-support-voice-agent.workers.memory")


@dataclass(frozen=True)
class _ConversationJob:
    user_id: str
    session_id: str
    messages: list[ConversationMessage]


class MemoryBackgroundWorker:
    """Bounded async queue processing conversation memory extraction off the voice path."""

    def __init__(self, manager: MemoryManager, *, max_queue_size: int = 100) -> None:
        self._manager = manager
        self._queue: asyncio.Queue[_ConversationJob] = asyncio.Queue(maxsize=max_queue_size)
        self._task: asyncio.Task[None] | None = None
        self._completed: list[ProcessConversationResult] = []

    @property
    def completed_results(self) -> list[ProcessConversationResult]:
        return list(self._completed)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="memory-background-worker")

    def enqueue_conversation(
        self,
        user_id: str,
        session_id: str,
        messages: list[ConversationMessage],
    ) -> bool:
        """Non-blocking enqueue; returns False if the queue is full."""
        if not messages:
            return False
        try:
            self._queue.put_nowait(
                _ConversationJob(user_id=user_id, session_id=session_id, messages=list(messages))
            )
            return True
        except asyncio.QueueFull:
            logger.warning("Memory background queue is full; dropping conversation batch")
            return False

    async def _run(self) -> None:
        while True:
            job = await self._queue.get()
            try:
                res = await self._manager.process_conversation(
                    job.user_id, job.session_id, job.messages
                )
                self._completed.append(res)
            except Exception:
                logger.exception(
                    "Background memory processing failed for session %s", job.session_id
                )
            finally:
                self._queue.task_done()

    async def drain(self, *, timeout_seconds: float = 10.0) -> None:
        """Wait for queued jobs to finish (used on graceful session shutdown)."""
        await asyncio.wait_for(self._queue.join(), timeout=timeout_seconds)

    async def stop(self, *, drain_timeout: float = 5.0) -> None:
        if self._task is None:
            return
        try:
            await self.drain(timeout_seconds=drain_timeout)
        except asyncio.TimeoutError:
            logger.warning("Timed out draining memory background worker")
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
