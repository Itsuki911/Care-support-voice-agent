"""Unit tests for MemoryExtractionService and OpenRouterMemoryLLM (no network required)."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from memory.models.memory import ConversationMessage, ExtractedMemory
from memory.providers.llm_extractor import LLMExtractionError, OpenRouterMemoryLLM
from memory.services.extraction import MemoryExtractionService


def _make_messages() -> list[ConversationMessage]:
    return [
        ConversationMessage(
            user_id="user-1",
            session_id="sess-1",
            role="user",
            content="私は毎朝6時に起きて散歩しています。",
        ),
        ConversationMessage(
            user_id="user-1",
            session_id="sess-1",
            role="assistant",
            content="毎朝6時の散歩は健康的ですね。",
        ),
    ]


def test_openrouter_extractor_parses_structured_json_and_sets_session_id():
    payload = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "memories": [
                                {
                                    "content": "ユーザーは毎朝6時に起床し、散歩する習慣がある",
                                    "memory_type": "habit",
                                    "importance": 0.8,
                                    "confidence": 0.95,
                                }
                            ]
                        },
                        ensure_ascii=False,
                    )
                }
            }
        ]
    }
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=payload))

    async def scenario():
        async with httpx.AsyncClient(transport=transport) as client:
            llm = OpenRouterMemoryLLM(api_key="test-key", model="test-model", client=client)
            service = MemoryExtractionService(extractor=llm)
            extracted = await service.extract(_make_messages(), session_id="sess-1")
            assert len(extracted) == 1
            assert extracted[0].content == "ユーザーは毎朝6時に起床し、散歩する習慣がある"
            assert extracted[0].memory_type == "habit"
            assert extracted[0].source_session_id == "sess-1"

    asyncio.run(scenario())


def test_extraction_service_deduplicates_and_handles_llm_error_gracefully():
    class DuplicateExtractor:
        async def extract_memories(self, messages, *, session_id):
            return [
                ExtractedMemory(content="緑茶が好き", memory_type="preference"),
                ExtractedMemory(content="  緑茶が好き ", memory_type="preference"),
            ]

    class FailingExtractor:
        async def extract_memories(self, messages, *, session_id):
            raise LLMExtractionError("invalid json")

    async def scenario():
        deduped = await MemoryExtractionService(extractor=DuplicateExtractor()).extract(
            _make_messages(), session_id="sess-2"
        )
        assert len(deduped) == 1
        assert deduped[0].source_session_id == "sess-2"

        safe_empty = await MemoryExtractionService(extractor=FailingExtractor()).extract(
            _make_messages(), session_id="sess-2", raise_on_error=False
        )
        assert safe_empty == []

        with pytest.raises(LLMExtractionError):
            await MemoryExtractionService(extractor=FailingExtractor()).extract(
                _make_messages(), session_id="sess-2", raise_on_error=True
            )

    asyncio.run(scenario())


def test_openrouter_extractor_rejects_invalid_schema():
    payload = {"choices": [{"message": {"content": '{"memories": [{"content": "", "importance": 5.0}]}'}}]}
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=payload))

    async def scenario():
        async with httpx.AsyncClient(transport=transport) as client:
            llm = OpenRouterMemoryLLM(api_key="test-key", model="test-model", client=client)
            with pytest.raises(LLMExtractionError, match="failed validation"):
                await llm.extract_memories(_make_messages(), session_id="sess-1")

    asyncio.run(scenario())
