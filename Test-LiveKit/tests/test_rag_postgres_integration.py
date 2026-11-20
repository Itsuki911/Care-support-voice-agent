"""Live integration tests for Level 3 RAG against PostgreSQL + pgvector + Ollama.

Automatically skips when local PostgreSQL or Ollama is unreachable (e.g., offline CI).
Uses a dedicated test corpus (`pytest_rag_integration_*`) and cleans up afterwards so
existing Level 2 memory data and production RAG corpora are never modified.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path

import httpx
import pytest

from database.config import load_memory_env
from rag.factory import RAGSettings, create_rag_runtime

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "rag_documents"
EVAL_DATASET_PATH = Path(__file__).resolve().parent / "fixtures" / "rag_evaluation" / "evaluation_dataset.json"


async def _live_env_available(settings: RAGSettings) -> bool:
    rt = create_rag_runtime(settings)
    try:
        db_ok = await rt.db.health_check()
        if not db_ok:
            return False
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            return resp.status_code == 200
    except Exception:
        return False
    finally:
        await rt.close()


def test_rag_end_to_end_postgres_pgvector_and_ollama():
    async def scenario():
        load_memory_env()
        test_db_url = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
        settings = RAGSettings.from_env(database_url_override=test_db_url)
        if not await _live_env_available(settings):
            pytest.skip("Local PostgreSQL or Ollama is not reachable")

        corpus_a = f"pytest_rag_a_{uuid.uuid4().hex[:8]}"
        corpus_b = f"pytest_rag_b_{uuid.uuid4().hex[:8]}"

        # Session 1: ingest all 5 fixture documents into corpus_a + 1 into corpus_b
        rt1 = create_rag_runtime(settings)
        try:
            ingested_ids = []
            for path in sorted(FIXTURES_DIR.iterdir()):
                if not path.is_file():
                    continue
                res = await rt1.service.ingest_document(path, corpus_id=corpus_a)
                assert res.status == "ingested"
                assert res.chunk_count >= 1
                ingested_ids.append(res.document.id)

            # Duplicate prevention
            dup = await rt1.service.ingest_document(
                FIXTURES_DIR / "company_rules.pdf", corpus_id=corpus_a
            )
            assert dup.status == "duplicate"

            # Separate corpus for isolation check
            b_res = await rt1.service.ingest_document(
                FIXTURES_DIR / "faq.md", corpus_id=corpus_b
            )
            assert b_res.status == "ingested"
        finally:
            await rt1.close()

        # Session 2: fresh RAGRuntime verifies persistence across sessions + search quality
        rt2 = create_rag_runtime(settings)
        try:
            docs_a = await rt2.service.list_documents(corpus_id=corpus_a)
            assert len(docs_a) == 5

            # Corpus isolation: corpus_b only returns faq.md
            b_search = await rt2.service.search("勤務開始時刻は何時ですか？", corpus_id=corpus_b, top_k=5)
            assert all(r.corpus_id == corpus_b and r.filename == "faq.md" for r in b_search.results)

            # Sample evaluation dataset check (Recall@5 & citations)
            dataset = json.loads(EVAL_DATASET_PATH.read_text(encoding="utf-8"))
            answerable = [q for q in dataset if q["answerable"]]
            hits = 0
            for item in answerable[:10]:
                resp = await rt2.service.search(item["query"], corpus_id=corpus_a, top_k=5)
                assert resp.embedding_ms > 0
                assert resp.db_search_ms > 0
                if any(r.filename == item["expected_document"] for r in resp.results):
                    hits += 1
                for r in resp.results:
                    assert r.document_id is not None
                    assert r.chunk_id is not None
                    assert r.filename
                    if r.file_type == "pdf":
                        assert r.page_number is not None and r.page_number >= 1
            assert hits / 10 >= 0.8

            # Delete one document and verify removal
            target_id = docs_a[0].id
            assert await rt2.service.delete_document(target_id) is True
            assert await rt2.service.get_document(target_id) is None
        finally:
            await rt2.service.delete_corpus(corpus_a)
            await rt2.service.delete_corpus(corpus_b)
            await rt2.close()

    asyncio.run(scenario())
