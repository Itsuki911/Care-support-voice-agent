"""Unit tests for Langfuse / OpenTelemetry memory tracing spans."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from memory.models.memory import (
    ConsolidationAction,
    ConsolidationDecision,
    ConversationMessage,
    ExtractedMemory,
    MemoryRecord,
    MemorySearchResult,
    MemoryType,
)
from memory.observability import MemoryTracer
from memory.providers.llm_extractor import OpenRouterMemoryLLM
from memory.services.consolidation import MemoryConsolidationService
from memory.services.extraction import MemoryExtractionService
from memory.services.memory_manager import PostgresMemoryService
from memory.services.retrieval import MemoryRetrievalService


def _make_provider() -> tuple[TracerProvider, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider, exporter


def test_memory_search_and_process_conversation_emit_expected_spans():
    async def scenario():
        provider, exporter = _make_provider()
        tracer = MemoryTracer(provider, allow_content=False)

        now = datetime.now(timezone.utc)
        rec_id = uuid.uuid4()
        saved_record = MemoryRecord(
            id=rec_id,
            user_id="user-1",
            content="毎朝6時に散歩する",
            memory_type=MemoryType.HABIT,
            importance=0.8,
            confidence=0.9,
            embedding_model="embeddinggemma-2:270m",
            embedding_dimension=768,
            source_session_id="sess-1",
            created_at=now,
            updated_at=now,
        )
        search_hit = MemorySearchResult(
            memory_id=rec_id,
            content="毎朝6時に散歩する",
            memory_type=MemoryType.HABIT,
            similarity_score=0.92,
            importance=0.8,
            confidence=0.9,
            source_session_id="sess-1",
            created_at=now,
            updated_at=now,
        )

        repo = SimpleNamespace(
            search_similar=AsyncMock(side_effect=[[search_hit], []]),
            save_conversation_messages=AsyncMock(side_effect=lambda msgs: msgs),
            insert=AsyncMock(return_value=saved_record),
        )
        embedder = SimpleNamespace(
            model_name="embeddinggemma-2:270m",
            dimension=768,
            embed=AsyncMock(return_value=[0.1] * 4),
        )
        extractor_backend = SimpleNamespace(
            extract_memories=AsyncMock(
                return_value=[
                    ExtractedMemory(
                        content="毎朝6時に散歩する",
                        memory_type=MemoryType.HABIT,
                        importance=0.8,
                        confidence=0.9,
                        source_session_id="sess-1",
                    )
                ]
            )
        )
        consolidator_backend = SimpleNamespace(
            decide_consolidation=AsyncMock(
                return_value=ConsolidationDecision(
                    action=ConsolidationAction.ADD,
                    merged_content="毎朝6時に散歩する",
                    reason="new",
                )
            )
        )

        retrieval = MemoryRetrievalService(repository=repo, embedding_provider=embedder, tracer=tracer)
        extraction = MemoryExtractionService(extractor=extractor_backend, tracer=tracer)
        consolidation = MemoryConsolidationService(
            repository=repo,
            embedding_provider=embedder,
            consolidator=consolidator_backend,
            tracer=tracer,
        )
        service = PostgresMemoryService(
            repository=repo,
            embedding_provider=embedder,
            retrieval_service=retrieval,
            extraction_service=extraction,
            consolidation_service=consolidation,
            tracer=tracer,
        )

        hits = await service.search_memory("user-1", "朝の習慣")
        assert len(hits) == 1

        res = await service.process_conversation(
            "user-1",
            "sess-1",
            [ConversationMessage(user_id="user-1", session_id="sess-1", role="user", content="毎朝6時に散歩しています")],
        )
        assert len(res.added_ids) == 1

        spans = exporter.get_finished_spans()
        names = [s.name for s in spans]
        for expected in (
            "memory.search",
            "memory.embedding",
            "memory.vector_search",
            "memory.process_conversation",
            "memory.extraction",
            "memory.consolidation",
        ):
            assert expected in names

        # allow_content=False must not export conversational content
        for s in spans:
            assert "langfuse.observation.input" not in s.attributes
            assert "langfuse.observation.output" not in s.attributes

        proc_span = next(s for s in spans if s.name == "memory.process_conversation")
        assert proc_span.attributes["langfuse.observation.metadata.memory.added_count"] == 1
        assert proc_span.attributes["langfuse.observation.metadata.memory.extracted_count"] == 1

    asyncio.run(scenario())


def test_llm_extractor_emits_generation_span_with_usage_and_respects_allow_content():
    async def scenario():
        provider, exporter = _make_provider()
        tracer = MemoryTracer(provider, allow_content=True)

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "model": "anthropic/claude-haiku-5.5",
                    "usage": {"prompt_tokens": 120, "completion_tokens": 45},
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "memories": [
                                            {
                                                "content": "緑茶が好き",
                                                "memory_type": "preference",
                                                "importance": 0.7,
                                                "confidence": 0.9,
                                            }
                                        ]
                                    },
                                    ensure_ascii=False,
                                )
                            }
                        }
                    ],
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            llm = OpenRouterMemoryLLM(
                api_key="test-key",
                model="anthropic/claude-haiku-5.5",
                client=client,
                tracer=tracer,
            )
            extracted = await llm.extract_memories(
                [ConversationMessage(user_id="u1", session_id="s1", role="user", content="緑茶が好きです")],
                session_id="s1",
            )
            assert len(extracted) == 1

        spans = exporter.get_finished_spans()
        gen = next(s for s in spans if s.name == "memory.llm.extraction")
        assert gen.attributes["langfuse.observation.type"] == "generation"
        assert gen.attributes["gen_ai.request.model"] == "anthropic/claude-haiku-5.5"
        assert gen.attributes["gen_ai.usage.input_tokens"] == 120
        assert gen.attributes["gen_ai.usage.output_tokens"] == 45
        assert "緑茶が好き" in gen.attributes["langfuse.observation.input"]
        assert "緑茶が好き" in gen.attributes["langfuse.observation.output"]

    asyncio.run(scenario())
