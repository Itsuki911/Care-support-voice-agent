"""Structured transcript and agent status event emitters for LiveKit data channel."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


@dataclass
class TranscriptEventTracker:
    """Tracks session_id, turn_id, utterance_id, and monotonic sequence numbers."""

    session_id: str
    _seq: int = 0
    _turn_index: int = 0
    _current_turn_id: str = "turn-0"
    _active_user_utterance_id: str | None = None

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _start_new_turn(self) -> str:
        self._turn_index += 1
        self._current_turn_id = f"turn-{self._turn_index}"
        return self._current_turn_id

    def on_user_transcribed(
        self,
        *,
        transcript: str,
        is_final: bool,
        item_id: str | None = None,
        timestamp: float | None = None,
    ) -> dict[str, Any] | None:
        text = transcript.strip()
        if not text:
            return None

        if self._active_user_utterance_id is None:
            self._start_new_turn()
            self._active_user_utterance_id = item_id or f"utt-user-{uuid4().hex[:10]}"

        utterance_id = self._active_user_utterance_id
        if is_final:
            self._active_user_utterance_id = None

        return {
            "type": "transcript_event",
            "session_id": self.session_id,
            "turn_id": self._current_turn_id,
            "utterance_id": utterance_id,
            "seq": self._next_seq(),
            "speaker": "user",
            "timestamp": timestamp if timestamp is not None else time.time(),
            "status": "final" if is_final else "interim",
            "text": text,
        }

    def on_conversation_item_added(
        self,
        *,
        role: str,
        text: str,
        item_id: str | None = None,
        interrupted: bool = False,
        generated_text: str | None = None,
        timestamp: float | None = None,
    ) -> dict[str, Any] | None:
        cleaned = text.strip()
        if not cleaned and not interrupted:
            return None

        speaker = "assistant" if role == "assistant" else "user"
        if speaker == "user":
            utterance_id = self._active_user_utterance_id or item_id or f"utt-user-{uuid4().hex[:10]}"
            self._active_user_utterance_id = None
            status = "final"
        else:
            utterance_id = item_id or f"utt-asst-{uuid4().hex[:10]}"
            status = "interrupted" if interrupted else "final"

        payload: dict[str, Any] = {
            "type": "transcript_event",
            "session_id": self.session_id,
            "turn_id": self._current_turn_id,
            "utterance_id": utterance_id,
            "seq": self._next_seq(),
            "speaker": speaker,
            "timestamp": timestamp if timestamp is not None else time.time(),
            "status": status,
            "text": cleaned,
        }
        if speaker == "assistant":
            payload["spoken_text"] = cleaned
            payload["generated_text"] = (generated_text or cleaned).strip()
        return payload

    def make_status_event(
        self,
        *,
        kind: str,
        status: str,
        execution_id: str,
        label: str = "",
        timestamp: float | None = None,
    ) -> dict[str, Any]:
        """Build a shared status event payload (reused by Memory/RAG/Web search in Level 2-4)."""
        return {
            "type": "agent_status_event",
            "session_id": self.session_id,
            "turn_id": self._current_turn_id,
            "execution_id": execution_id,
            "kind": kind,
            "status": status,
            "seq": self._next_seq(),
            "timestamp": timestamp if timestamp is not None else time.time(),
            "label": label,
        }
