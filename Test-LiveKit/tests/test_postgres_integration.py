"""Real PostgreSQL + pgvector + Ollama (embeddinggemma-2:270m) integration tests.

Uses a dedicated test database (TEST_DATABASE_URL) so production/dev data is never touched.
Automatically skips when local PostgreSQL or Ollama is unreachable (e.g. GitHub Actions unit CI).
"""

from __future__ import annotations

import asyncio
import os
import uuid

import httpx
import pytest
from sqlalchemy import text

from database.config import load_memory_env, normalize_async_database_url
from database.connection import DatabaseManager
from database.models import Base
from memory.models.memory import (
    ConsolidationAction,
    ConsolidationDecision,
    ConversationMessage,
    ExtractedMemory,
    MemoryCreate,
    MemoryUpdate,
)
from memory.providers.ollama_embedding import OllamaEmbeddingProvider
from memory.repositories.postgres_repository import PostgresMemoryRepository
from memory.services.consolidation import MemoryConsolidationService
from memory.services.extraction import MemoryExtractionService
from memory.services.memory_manager import MemoryManager, PostgresMemoryService
from memory.services.retrieval import MemoryRetrievalService


def _get_test_db_url() -> str | None:
    load_memory_env()
    url = os.getenv("TEST_DATABASE_URL", "").strip()
    return normalize_async_database_url(url) if url else None


def _get_ollama_url() -> str:
    load_memory_env()
    return (os.getenv("OLLAMA_BASE_URL") or "http://127.0.0.1:11434").rstrip("/")


def _get_embedding_model() -> str:
    load_memory_env()
    return (os.getenv("EMBEDDING_MODEL") or "embeddinggemma-2:270m").strip()


def _check_live_prereqs() -> tuple[str, str, str]:
    db_url = _get_test_db_url()
    if not db_url:
        pytest.skip("TEST_DATABASE_URL is not configured")

    ollama_url = _get_ollama_url()
    model = _get_embedding_model()

    async def probe_db() -> bool:
        db = DatabaseManager(db_url)
        try:
            return await db.health_check()
        finally:
            await db.close()

    if not asyncio.run(probe_db()):
        pytest.skip("Local PostgreSQL test database is not reachable")

    try:
        r = httpx.get(f"{ollama_url}/api/tags", timeout=3.0)
        r.raise_for_status()
        names = {m.get("name", "") for m in r.json().get("models", [])}
        if model not in names and f"{model}:latest" not in names:
            pytest.skip(f"Ollama model {model} is not pulled")
    except Exception:
        pytest.skip("Local Ollama server is not reachable")

    return db_url, ollama_url, model


class DeterministicRuleLLM:
    """Deterministic LLM stub for repeatable end-to-end DB + pgvector + Ollama integration tests."""

    async def extract_memories(
        self, messages: list[ConversationMessage], *, session_id: str
    ) -> list[ExtractedMemory]:
        extracted: list[ExtractedMemory] = []
        for msg in messages:
            if msg.role != "user":
                continue
            if "毎朝6時" in msg.content:
                extracted.append(
                    ExtractedMemory(
                        content="ユーザーは毎朝6時に起床し、散歩する習慣がある",
                        memory_type="habit",
                        importance=0.85,
                        confidence=0.95,
                        source_session_id=session_id,
                    )
                )
            elif "7時" in msg.content and "散歩" in msg.content:
                extracted.append(
                    ExtractedMemory(
                        content="ユーザーは毎朝7時に起床して散歩するように変更した",
                        memory_type="habit",
                        importance=0.85,
                        confidence=0.95,
                        source_session_id=session_id,
                    )
                )
            elif "忘れて" in msg.content:
                extracted.append(
                    ExtractedMemory(
                        content="散歩の習慣についての記憶を削除してほしい",
                        memory_type="habit",
                        importance=0.9,
                        confidence=0.95,
                        source_session_id=session_id,
                    )
                )
        return extracted

    async def decide_consolidation(self, candidate, existing_memories):
        if not existing_memories:
            return ConsolidationDecision(
                action=ConsolidationAction.ADD,
                merged_content=candidate.content,
                memory_type=candidate.memory_type,
                importance=candidate.importance,
                confidence=candidate.confidence,
                reason="no_existing_memory",
            )
        top = existing_memories[0]
        if "削除してほしい" in candidate.content:
            return ConsolidationDecision(
                action=ConsolidationAction.DELETE,
                target_memory_id=top.memory_id,
                reason="explicit_user_forget",
            )
        if "変更した" in candidate.content:
            return ConsolidationDecision(
                action=ConsolidationAction.UPDATE,
                target_memory_id=top.memory_id,
                merged_content=candidate.content,
                memory_type=candidate.memory_type,
                importance=candidate.importance,
                confidence=candidate.confidence,
                reason="routine_updated",
            )
        return ConsolidationDecision(action=ConsolidationAction.NOOP, reason="already_recorded")


def test_full_postgres_pgvector_ollama_lifecycle():
    db_url, ollama_url, model = _check_live_prereqs()
    user_a = f"test-user-a-{uuid.uuid4().hex[:8]}"
    user_b = f"test-user-b-{uuid.uuid4().hex[:8]}"

    async def scenario():
        db = DatabaseManager(db_url)
        try:
            # 1 & 2. Verify PostgreSQL connection and pgvector extension
            async with db.engine.begin() as conn:
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                await conn.run_sync(Base.metadata.create_all)
                ext = (
                    await conn.execute(
                        text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
                    )
                ).scalar_one()
                assert ext

            repo = PostgresMemoryRepository(db)
            embedder = OllamaEmbeddingProvider(base_url=ollama_url, model=model, dimension=768)
            llm = DeterministicRuleLLM()
            service = PostgresMemoryService(
                repository=repo,
                embedding_provider=embedder,
                retrieval_service=MemoryRetrievalService(repository=repo, embedding_provider=embedder),
                extraction_service=MemoryExtractionService(extractor=llm),
                consolidation_service=MemoryConsolidationService(
                    repository=repo, embedding_provider=embedder, consolidator=llm
                ),
            )
            manager = MemoryManager(service)

            # 3. EmbeddingGemma 2 embedding generation
            vec = await embedder.embed("毎朝6時に散歩しています")
            assert len(vec) == 768

            # 4, 5, 6, 7. CRUD (add, get, update, delete)
            added = await manager.add_memory(
                MemoryCreate(
                    user_id=user_a,
                    content="ユーザーは緑茶が好き",
                    memory_type="preference",
                    importance=0.7,
                    confidence=0.9,
                    source_session_id="sess-crud",
                )
            )
            fetched = await manager.get_memory(user_a, added.id)
            assert fetched is not None and fetched.content == "ユーザーは緑茶が好き"

            updated = await manager.update_memory(
                user_a,
                added.id,
                MemoryUpdate(content="ユーザーは温かい緑茶が好き", reason="refined"),
            )
            assert updated is not None and updated.content == "ユーザーは温かい緑茶が好き"
            assert updated.version == 2

            # 9. Cross-user isolation on get/delete/search
            assert await manager.get_memory(user_b, added.id) is None
            assert await manager.delete_memory(user_b, added.id) is False

            # Add a memory for user_b and ensure user_a search never returns it
            await manager.add_memory(
                MemoryCreate(
                    user_id=user_b,
                    content="ユーザーBはコーヒーが大好きで毎朝飲む",
                    memory_type="preference",
                    source_session_id="sess-b",
                )
            )
            results_a = await manager.search_memory(user_a, "好きな飲み物は何？", limit=5)
            assert any("緑茶" in r.content for r in results_a)
            assert all("ユーザーB" not in r.content for r in results_a)

            assert await manager.delete_memory(user_a, added.id, reason="cleanup") is True
            assert await manager.get_memory(user_a, added.id) is None

            # 10, 11, 12, 13. Conversation persistence, extraction, consolidation (ADD -> UPDATE -> DELETE)
            # and cross-session semantic retrieval
            session_1_msgs = [
                ConversationMessage(
                    user_id=user_a,
                    session_id="session-A",
                    role="user",
                    content="私は毎朝6時に起きて散歩しています。",
                ),
                ConversationMessage(
                    user_id=user_a,
                    session_id="session-A",
                    role="assistant",
                    content="毎朝6時の散歩は素晴らしい習慣ですね。",
                ),
            ]
            res1 = await manager.process_conversation(user_a, "session-A", session_1_msgs)
            assert res1.saved_messages == 2
            assert res1.extracted_count == 1
            assert len(res1.added_ids) == 1

            # Verify conversation persistence
            persisted_msgs = await service.list_conversation(user_a, "session-A")
            assert len(persisted_msgs) == 2
            assert persisted_msgs[0].content == "私は毎朝6時に起きて散歩しています。"

            # Cross-session retrieval in session-B
            cross_session_hits = await manager.search_memory(user_a, "朝の習慣を教えて", limit=3)
            assert len(cross_session_hits) >= 1
            assert "散歩" in cross_session_hits[0].content
            assert cross_session_hits[0].similarity_score > 0.3

            # Consolidation UPDATE in session-B
            res2 = await manager.process_conversation(
                user_a,
                "session-B",
                [
                    ConversationMessage(
                        user_id=user_a,
                        session_id="session-B",
                        role="user",
                        content="最近は毎朝7時に起きて散歩するように変えました。",
                    )
                ],
            )
            assert len(res2.updated_ids) == 1
            updated_hits = await manager.search_memory(user_a, "朝の散歩の時間", limit=3)
            assert any("7時" in h.content for h in updated_hits)

            # Consolidation DELETE in session-C
            res3 = await manager.process_conversation(
                user_a,
                "session-C",
                [
                    ConversationMessage(
                        user_id=user_a,
                        session_id="session-C",
                        role="user",
                        content="散歩の習慣の記憶は忘れてください。",
                    )
                ],
            )
            assert len(res3.deleted_ids) == 1
            after_delete = await manager.list_memories(user_a)
            assert all("散歩" not in m.content for m in after_delete)

            # Verify audit history recorded ADD, UPDATE, DELETE
            history = await repo.list_history(user_a)
            actions = {h["action"] for h in history}
            assert {"ADD", "UPDATE", "DELETE"}.issubset(actions)
        finally:
            # Clean up only this test run's users (cascade cleans their rows)
            async with db.engine.begin() as conn:
                await conn.execute(
                    text("DELETE FROM users WHERE id IN (:ua, :ub)"),
                    {"ua": user_a, "ub": user_b},
                )
            await db.close()

    asyncio.run(scenario())
