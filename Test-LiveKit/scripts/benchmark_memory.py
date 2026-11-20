"""Performance benchmark for Level 2 Agent Memory (PostgreSQL + pgvector + Ollama).

Measures real wall-clock timings (mean, p50, p95 in ms) for:
- Embedding generation (Ollama embeddinggemma-2:270m)
- PostgreSQL pgvector similarity search
- End-to-end Memory Retrieval (embed + pgvector search)
- Optional: LLM Memory Extraction & Consolidation (when --with-llm is passed)

Usage:
    cd Test-LiveKit
    uv run python scripts/benchmark_memory.py --iterations 15
    uv run python scripts/benchmark_memory.py --iterations 15 --with-llm
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from database.config import MemorySettings
from database.connection import DatabaseManager
from memory.models.memory import ConversationMessage, MemoryCreate
from memory.providers.llm_extractor import OpenRouterMemoryLLM
from memory.providers.ollama_embedding import OllamaEmbeddingProvider
from memory.repositories.postgres_repository import PostgresMemoryRepository
from memory.services.consolidation import MemoryConsolidationService
from memory.services.extraction import MemoryExtractionService
from memory.services.retrieval import MemoryRetrievalService


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = (len(ordered) - 1) * pct
    lower = int(idx)
    upper = min(lower + 1, len(ordered) - 1)
    weight = idx - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _summarize(samples_ms: list[float]) -> dict[str, float]:
    return {
        "count": len(samples_ms),
        "mean_ms": round(statistics.mean(samples_ms), 2),
        "p50_ms": round(_percentile(samples_ms, 0.50), 2),
        "p95_ms": round(_percentile(samples_ms, 0.95), 2),
        "min_ms": round(min(samples_ms), 2),
        "max_ms": round(max(samples_ms), 2),
    }


async def run_benchmark(iterations: int, with_llm: bool) -> dict[str, object]:
    test_db = os.getenv("TEST_DATABASE_URL") or None
    settings = MemorySettings.from_env(database_url_override=test_db)
    db = DatabaseManager(settings.database_url)
    repo = PostgresMemoryRepository(db)
    embedder = OllamaEmbeddingProvider(
        base_url=settings.ollama_base_url,
        model=settings.embedding_model,
        dimension=settings.embedding_dimension,
    )
    retrieval = MemoryRetrievalService(
        repository=repo,
        embedding_provider=embedder,
        default_limit=5,
    )

    user_id = f"bench-user-{uuid.uuid4().hex[:8]}"
    seed_memories = [
        ("ユーザーは毎朝6時に起きて散歩する習慣がある", "habit"),
        ("ユーザーは温かい緑茶を好んで飲む", "preference"),
        ("ユーザーは毎週火曜日の午前に通院している", "event"),
        ("ユーザーは庭でトマトとバジルを育てている", "interest"),
        ("ユーザーは大きめの声でゆっくり話してほしいと希望している", "preference"),
        ("ユーザーは最近、膝の調子が少し気になっている", "topic"),
        ("ユーザーは孫の健太くんのサッカー観戦を楽しみにしている", "interest"),
        ("ユーザーは夜10時には就寝するようにしている", "habit"),
    ]
    queries = [
        "朝の習慣は何ですか？",
        "好きな飲み物を教えて",
        "病院の予定はいつ？",
        "趣味や楽しみはありますか？",
        "話し方で気をつけることは？",
    ]

    try:
        # Warm-up embedding call so steady-state latency is measured cleanly
        t_warm0 = time.perf_counter()
        first_vec = await embedder.embed("ウォームアップ")
        first_embed_ms = round((time.perf_counter() - t_warm0) * 1000.0, 2)

        for content, mtype in seed_memories:
            vec = await embedder.embed(content)
            await repo.insert(
                MemoryCreate(
                    user_id=user_id,
                    content=content,
                    memory_type=mtype,
                    source_session_id="bench-seed",
                ),
                embedding=vec,
                embedding_model=embedder.model_name,
                embedding_dimension=embedder.dimension,
            )

        embed_samples: list[float] = []
        pg_search_samples: list[float] = []
        retrieval_samples: list[float] = []

        for i in range(iterations):
            q = queries[i % len(queries)]

            t0 = time.perf_counter()
            q_vec = await embedder.embed(q)
            embed_samples.append((time.perf_counter() - t0) * 1000.0)

            t1 = time.perf_counter()
            await repo.search_similar(
                user_id=user_id,
                query_embedding=q_vec,
                embedding_model=embedder.model_name,
                limit=5,
            )
            pg_search_samples.append((time.perf_counter() - t1) * 1000.0)

            t2 = time.perf_counter()
            await retrieval.search(user_id, q, limit=5)
            retrieval_samples.append((time.perf_counter() - t2) * 1000.0)

        report: dict[str, object] = {
            "embedding_model": embedder.model_name,
            "embedding_dimension": len(first_vec),
            "first_call_ms": first_embed_ms,
            "seed_memory_count": len(seed_memories),
            "embedding_generation": _summarize(embed_samples),
            "postgres_vector_search": _summarize(pg_search_samples),
            "memory_retrieval_e2e": _summarize(retrieval_samples),
        }

        if with_llm and settings.llm_api_key:
            llm = OpenRouterMemoryLLM(
                api_key=settings.llm_api_key,
                model=settings.llm_model,
                base_url=settings.llm_base_url,
            )
            extractor = MemoryExtractionService(extractor=llm)
            consolidator = MemoryConsolidationService(
                repository=repo,
                embedding_provider=embedder,
                consolidator=llm,
            )
            extract_samples: list[float] = []
            consolidate_samples: list[float] = []
            sample_conversations = [
                [
                    ConversationMessage(
                        user_id=user_id,
                        session_id="bench-llm-1",
                        role="user",
                        content="最近は夜にストレッチを10分ほどするようになりました。",
                    ),
                    ConversationMessage(
                        user_id=user_id,
                        session_id="bench-llm-1",
                        role="assistant",
                        content="夜のストレッチはリラックスできて良さそうですね。",
                    ),
                ],
                [
                    ConversationMessage(
                        user_id=user_id,
                        session_id="bench-llm-2",
                        role="user",
                        content="やっぱり毎朝の散歩は6時半からにすることにしました。",
                    ),
                    ConversationMessage(
                        user_id=user_id,
                        session_id="bench-llm-2",
                        role="assistant",
                        content="6時半の散歩ですね、承知しました。",
                    ),
                ],
                [
                    ConversationMessage(
                        user_id=user_id,
                        session_id="bench-llm-3",
                        role="user",
                        content="甘いものだと和菓子、特に羊羹が好きです。",
                    ),
                    ConversationMessage(
                        user_id=user_id,
                        session_id="bench-llm-3",
                        role="assistant",
                        content="羊羹はお茶にも合いますよね。",
                    ),
                ],
            ]
            for idx, conv in enumerate(sample_conversations, start=1):
                te0 = time.perf_counter()
                extracted = await extractor.extract(conv, session_id=f"bench-llm-{idx}")
                extract_samples.append((time.perf_counter() - te0) * 1000.0)

                tc0 = time.perf_counter()
                await consolidator.consolidate(user_id, extracted)
                consolidate_samples.append((time.perf_counter() - tc0) * 1000.0)

            report["llm_model"] = settings.llm_model
            report["memory_extraction"] = _summarize(extract_samples)
            report["memory_consolidation"] = _summarize(consolidate_samples)

        return report
    finally:
        async with db.engine.begin() as conn:
            await conn.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": user_id})
        await db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark Level 2 Agent Memory latency")
    parser.add_argument("--iterations", type=int, default=15)
    parser.add_argument("--with-llm", action="store_true")
    args = parser.parse_args()

    result = asyncio.run(run_benchmark(args.iterations, args.with_llm))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
