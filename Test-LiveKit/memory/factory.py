"""Composition root for wiring PostgresMemoryService, MemoryManager, and MemoryBackgroundWorker."""

from __future__ import annotations

from dataclasses import dataclass

from database.config import MemorySettings
from database.connection import DatabaseManager
from memory.observability import NOOP_TRACER, MemoryTracer
from memory.providers.llm_extractor import OpenRouterMemoryLLM
from memory.providers.ollama_embedding import OllamaEmbeddingProvider
from memory.repositories.postgres_repository import PostgresMemoryRepository
from memory.services.consolidation import MemoryConsolidationService
from memory.services.extraction import MemoryExtractionService
from memory.services.memory_manager import MemoryManager, PostgresMemoryService
from memory.services.retrieval import MemoryRetrievalService
from workers.memory_worker import MemoryBackgroundWorker


@dataclass
class MemoryRuntime:
    settings: MemorySettings
    db: DatabaseManager
    repository: PostgresMemoryRepository
    embedding_provider: OllamaEmbeddingProvider
    llm: OpenRouterMemoryLLM
    service: PostgresMemoryService
    manager: MemoryManager
    worker: MemoryBackgroundWorker
    tracer: MemoryTracer = NOOP_TRACER

    async def close(self, *, drain_timeout: float = 20.0) -> None:
        await self.worker.stop(drain_timeout=drain_timeout)
        await self.db.close()


def create_memory_runtime(
    settings: MemorySettings | None = None,
    *,
    tracer: MemoryTracer | None = None,
) -> MemoryRuntime:
    """Build a complete local PostgreSQL + pgvector + Ollama memory runtime."""
    cfg = settings or MemorySettings.from_env()
    active_tracer = tracer or NOOP_TRACER
    db = DatabaseManager(cfg.database_url)
    repository = PostgresMemoryRepository(db)
    embedding_provider = OllamaEmbeddingProvider(
        base_url=cfg.ollama_base_url,
        model=cfg.embedding_model,
        dimension=cfg.embedding_dimension,
        timeout_seconds=cfg.ollama_timeout_seconds,
    )
    llm = OpenRouterMemoryLLM(
        api_key=cfg.llm_api_key,
        model=cfg.llm_model,
        base_url=cfg.llm_base_url,
        tracer=active_tracer,
    )
    retrieval = MemoryRetrievalService(
        repository=repository,
        embedding_provider=embedding_provider,
        default_limit=cfg.default_search_limit,
        default_min_similarity=cfg.similarity_threshold,
        tracer=active_tracer,
    )
    extraction = MemoryExtractionService(extractor=llm, tracer=active_tracer)
    consolidation = MemoryConsolidationService(
        repository=repository,
        embedding_provider=embedding_provider,
        consolidator=llm,
        tracer=active_tracer,
    )
    service = PostgresMemoryService(
        repository=repository,
        embedding_provider=embedding_provider,
        retrieval_service=retrieval,
        extraction_service=extraction,
        consolidation_service=consolidation,
        tracer=active_tracer,
    )
    manager = MemoryManager(service)
    worker = MemoryBackgroundWorker(manager)
    return MemoryRuntime(
        settings=cfg,
        db=db,
        repository=repository,
        embedding_provider=embedding_provider,
        llm=llm,
        service=service,
        manager=manager,
        worker=worker,
        tracer=active_tracer,
    )
