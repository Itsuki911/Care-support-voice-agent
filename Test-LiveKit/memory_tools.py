"""LiveKit function tools and prompt helpers for the Agent Memory system.

This module bridges LiveKit Agents (`@function_tool`) to the framework-agnostic
`BaseMemoryService` without leaking LiveKit imports into `memory/`.
"""

from __future__ import annotations

import logging
from typing import Callable

from livekit.agents import function_tool

from memory.interfaces.memory_service import BaseMemoryService
from memory.models.memory import MemoryRecord

logger = logging.getLogger("care-support-voice-agent.memory_tools")


def _memory_type_str(value: object) -> str:
    return str(getattr(value, "value", value))


def format_recent_memories_for_prompt(
    memories: list[MemoryRecord],
    *,
    max_items: int = 5,
) -> str:
    """Format the most recent user memories for injection into the system prompt."""
    lines = [
        "",
        "## 長期メモリ利用ルール",
        "- 以下は、このユーザーに関して直近で保存された記憶（最大5件）です。",
        "- 通常の会話では以下の直近記憶のみを参考にし、毎ターン自動で検索ツールを呼ばないでください。",
        "- ユーザーから「以前話したことを調べて」「記憶を検索して」「覚えていることを教えて」など明示的な指示があった場合のみ、`search_memories` または `list_recent_memories` ツールを呼び出してください。",
    ]
    selected = memories[: max(1, max_items)]
    if selected:
        lines.append("")
        lines.append("### 直近のユーザー記憶")
        for idx, mem in enumerate(selected, start=1):
            lines.append(f"{idx}. [{_memory_type_str(mem.memory_type)}] {mem.content}")
    else:
        lines.append("")
        lines.append("### 直近のユーザー記憶")
        lines.append("（まだ保存された記憶はありません）")
    return "\n".join(lines)


class MemoryTools:
    """Read-only memory search tools bound to a single session's user_id."""

    def __init__(
        self,
        memory_service: BaseMemoryService,
        get_user_id: Callable[[], str],
    ) -> None:
        self._service = memory_service
        self._get_user_id = get_user_id

    @function_tool
    async def search_memories(self, query: str, limit: int = 5) -> dict:
        """Search the user's long-term memory database by semantic similarity.

        Call this tool ONLY when the user explicitly asks to recall, check, or search
        past conversations, preferences, habits, or stored memories.
        """
        cleaned_query = query.strip()
        if not cleaned_query:
            return {"ok": True, "memories": [], "count": 0}
        safe_limit = max(1, min(limit, 20))
        user_id = self._get_user_id()
        try:
            results = await self._service.search_memory(
                user_id, cleaned_query, limit=safe_limit
            )
        except Exception as exc:
            logger.warning("search_memories tool failed (graceful fallback): %s", exc)
            return {
                "ok": False,
                "error": "記憶データベースに一時的に接続できませんでした。",
                "memories": [],
                "count": 0,
            }

        items = [
            {
                "memory_id": str(r.memory_id),
                "content": r.content,
                "memory_type": _memory_type_str(r.memory_type),
                "similarity_score": round(r.similarity_score, 4),
                "created_at": r.created_at.isoformat(),
                "updated_at": r.updated_at.isoformat(),
            }
            for r in results
        ]
        return {"ok": True, "memories": items, "count": len(items)}

    @function_tool
    async def list_recent_memories(self, limit: int = 5) -> dict:
        """List the user's most recently updated long-term memories from the database.

        Call this tool ONLY when the user explicitly asks what is currently remembered
        about them or requests a list of stored memories.
        """
        safe_limit = max(1, min(limit, 20))
        user_id = self._get_user_id()
        try:
            records = await self._service.list_memories(user_id, limit=safe_limit)
        except Exception as exc:
            logger.warning("list_recent_memories tool failed (graceful fallback): %s", exc)
            return {
                "ok": False,
                "error": "記憶データベースに一時的に接続できませんでした。",
                "memories": [],
                "count": 0,
            }

        items = [
            {
                "memory_id": str(m.id),
                "content": m.content,
                "memory_type": _memory_type_str(m.memory_type),
                "importance": m.importance,
                "created_at": m.created_at.isoformat(),
                "updated_at": m.updated_at.isoformat(),
            }
            for m in records
        ]
        return {"ok": True, "memories": items, "count": len(items)}
