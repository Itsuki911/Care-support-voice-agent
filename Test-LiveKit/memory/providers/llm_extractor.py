"""OpenAI/OpenRouter-compatible structured-output LLM client for memory extraction and consolidation."""

from __future__ import annotations

import json
import logging
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from memory.models.memory import (
    ConsolidationAction,
    ConsolidationDecision,
    ConversationMessage,
    ExtractedMemory,
    ExtractionResponse,
    MemorySearchResult,
)
from memory.observability import NOOP_TRACER, MemorySpan, MemoryTracer

logger = logging.getLogger("care-support-voice-agent.memory.llm")

T = TypeVar("T", bound=BaseModel)


class LLMExtractionError(RuntimeError):
    """Raised when structured LLM extraction or consolidation fails."""


EXTRACTION_SYSTEM_PROMPT = """\
You are a precise long-term memory extractor for a Japanese/English voice assistant.
Analyze the conversation and extract ONLY durable, factual long-term memories about the user.

Extract:
- User preferences (好み)
- Habits and routines (習慣)
- Profile / basic facts about the user (基本情報)
- Ongoing interests or topics (継続的な関心・話題)
- Important life events useful in future conversations (重要な出来事)

Strict rules:
- NEVER invent, infer, or speculate facts not explicitly stated in the conversation.
- NEVER store hypothetical statements (仮定の話) as user facts.
- NEVER store facts about other people (他人についての話) as if they were the user's own facts.
- Do NOT store greetings, transient small talk, or one-off requests (e.g. checking today's weather).
- Return an empty list {"memories": []} if nothing worth long-term storage was stated.
- Write concise, clear memory content in the same language as the conversation.

Respond ONLY with valid JSON matching this schema:
{
  "memories": [
    {
      "content": "string",
      "memory_type": "preference | habit | profile | interest | event | topic | fact",
      "importance": 0.0 to 1.0,
      "confidence": 0.0 to 1.0
    }
  ]
}
"""

CONSOLIDATION_SYSTEM_PROMPT = """\
You are a careful memory consolidation engine.
Compare ONE candidate new memory against existing similar memories for the same user, and decide ONE action:
- "ADD": Truly new information not covered by existing memories.
- "UPDATE": Refines, corrects, or updates an existing memory (e.g., preference changed or detail added). Must specify target_memory_id and merged_content.
- "DELETE": The user explicitly asked to forget/remove an existing memory, or clearly invalidated it. Must specify target_memory_id. Never delete without clear evidence.
- "NOOP": The candidate is already accurately captured by an existing memory, or lacks sufficient evidence to change existing memory.

Rules:
- Respect chronology: the candidate comes from a newer conversation turn.
- Never delete or overwrite an existing memory without clear evidence in the candidate.
- Respond ONLY with valid JSON matching:
{
  "action": "ADD | UPDATE | DELETE | NOOP",
  "target_memory_id": "uuid-string or null",
  "merged_content": "string or null",
  "memory_type": "string or null",
  "importance": 0.0 to 1.0 or null,
  "confidence": 0.0 to 1.0 or null,
  "reason": "short explanation"
}
"""


def _extract_json_block(raw_text: str) -> str:
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


class OpenRouterMemoryLLM:
    """Calls OpenRouter/OpenAI-compatible Chat Completions API with Pydantic-validated JSON output."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://openrouter.ai/api/v1",
        timeout_seconds: float = 30.0,
        client: httpx.AsyncClient | None = None,
        tracer: MemoryTracer | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._external_client = client
        self._tracer = tracer or NOOP_TRACER

    async def _complete_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
        operation: str = "structured",
    ) -> T:
        with self._tracer.span(
            f"memory.llm.{operation}",
            observation_type="generation",
            operation=operation,
        ) as span:
            span.set_model(self._model)
            span.set_input(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ]
            )
            return await self._complete_structured_inner(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=response_model,
                span=span,
            )

    async def _complete_structured_inner(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
        span: MemorySpan,
    ) -> T:
        if not self._api_key:
            raise LLMExtractionError("LLM_API_KEY / OPENROUTER_API_KEY is not configured")

        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self._model,
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if self._model.startswith("anthropic/"):
            payload["cache_control"] = {"type": "ephemeral"}
        try:
            if self._external_client is not None:
                resp = await self._external_client.post(
                    url, headers=headers, json=payload, timeout=self._timeout_seconds
                )
            else:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMExtractionError(f"Structured LLM request failed: {exc}") from None

        usage = data.get("usage") if isinstance(data, dict) else None
        if isinstance(usage, dict):
            span.set_usage(
                input_tokens=usage.get("prompt_tokens"),
                output_tokens=usage.get("completion_tokens"),
            )
        response_model_name = data.get("model") if isinstance(data, dict) else None
        if isinstance(response_model_name, str) and response_model_name:
            span.set(response_model=response_model_name)
        span.set_output(str(content))

        try:
            parsed = json.loads(_extract_json_block(str(content)))
            result = response_model.model_validate(parsed)
        except (ValueError, ValidationError) as exc:
            span.set(validation="failed")
            raise LLMExtractionError(f"Structured LLM output failed validation: {exc}") from None
        span.set(validation="ok")
        return result

    async def extract_memories(
        self,
        messages: list[ConversationMessage],
        *,
        session_id: str,
    ) -> list[ExtractedMemory]:
        transcript = "\n".join(f"{m.role}: {m.content}" for m in messages)
        result = await self._complete_structured(
            system_prompt=EXTRACTION_SYSTEM_PROMPT,
            user_prompt=f"Conversation (session_id={session_id}):\n{transcript}",
            response_model=ExtractionResponse,
            operation="extraction",
        )
        return [
            item.model_copy(update={"source_session_id": item.source_session_id or session_id})
            for item in result.memories
        ]

    async def decide_consolidation(
        self,
        candidate: ExtractedMemory,
        existing_memories: list[MemorySearchResult],
    ) -> ConsolidationDecision:
        if not existing_memories:
            return ConsolidationDecision(
                action=ConsolidationAction.ADD,
                merged_content=candidate.content,
                memory_type=candidate.memory_type,
                importance=candidate.importance,
                confidence=candidate.confidence,
                reason="no_similar_existing_memories",
            )

        existing_payload = [
            {
                "memory_id": str(m.memory_id),
                "content": m.content,
                "memory_type": m.memory_type,
                "similarity_score": round(m.similarity_score, 4),
                "updated_at": m.updated_at.isoformat(),
            }
            for m in existing_memories
        ]
        user_prompt = json.dumps(
            {
                "candidate_memory": candidate.model_dump(mode="json"),
                "existing_similar_memories": existing_payload,
            },
            ensure_ascii=False,
            indent=2,
        )
        return await self._complete_structured(
            system_prompt=CONSOLIDATION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_model=ConsolidationDecision,
            operation="consolidation",
        )
