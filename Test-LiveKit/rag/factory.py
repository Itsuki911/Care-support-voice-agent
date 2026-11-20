"""Composition root for Level 3 RAG runtime, reusing Level 2 DB and EmbeddingProvider."""

from __future__ import annotations

import os
from dataclasses import dataclass

from database.config import load_memory_env, normalize_async_database_url
from database.connection import DatabaseManager
from memory.interfaces.embedding_provider import BaseEmbeddingProvider
from memory.providers.ollama_embedding import OllamaEmbeddingProvider
from rag.chunkers.recursive_chunker import RecursiveTextChunker
from rag.parsers.document_parser import LocalDocumentParser
from rag.repositories.postgres_repository import PostgresRAGRepository
from rag.services.ingestion import DocumentIngestionService
from rag.services.rag_service import PostgresRAGService
from rag.services.retriever import RAGRetrieverService


@dataclass(frozen=True)
class RAGSettings:
    """OS-independent RAG runtime settings loaded from environment variables."""

    database_url: str
    ollama_base_url: str
    embedding_model: str
    embedding_dimension: int
    ollama_timeout_seconds: float
    chunk_size: int
    chunk_overlap: int
    default_top_k: int
    similarity_threshold: float

    @classmethod
    def from_env(cls, *, database_url_override: str | None = None) -> "RAGSettings":
        load_memory_env()
        raw_db_url = (
            database_url_override
            or os.getenv("DATABASE_URL")
            or "postgresql+psycopg://localhost:5432/care_support"
        )
        return cls(
            database_url=normalize_async_database_url(raw_db_url),
            ollama_base_url=(os.getenv("OLLAMA_BASE_URL") or "http://127.0.0.1:11434").rstrip("/"),
            embedding_model=(os.getenv("EMBEDDING_MODEL") or "embeddinggemma-2:270m").strip(),
            embedding_dimension=int(os.getenv("EMBEDDING_DIMENSION") or "768"),
            ollama_timeout_seconds=float(os.getenv("OLLAMA_TIMEOUT_SECONDS") or "30.0"),
            chunk_size=int(os.getenv("RAG_CHUNK_SIZE") or "450"),
            chunk_overlap=int(os.getenv("RAG_CHUNK_OVERLAP") or "80"),
            default_top_k=int(os.getenv("RAG_TOP_K") or "5"),
            similarity_threshold=float(os.getenv("RAG_SIMILARITY_THRESHOLD") or "0.0"),
        )


@dataclass
class RAGRuntime:
    settings: RAGSettings
    db: DatabaseManager
    owns_db: bool
    embedding_provider: BaseEmbeddingProvider
    parser: LocalDocumentParser
    chunker: RecursiveTextChunker
    repository: PostgresRAGRepository
    ingestion: DocumentIngestionService
    retriever: RAGRetrieverService
    service: PostgresRAGService

    async def close(self) -> None:
        if self.owns_db:
            await self.db.close()


def create_rag_runtime(
    settings: RAGSettings | None = None,
    *,
    db: DatabaseManager | None = None,
    embedding_provider: BaseEmbeddingProvider | None = None,
) -> RAGRuntime:
    """Build a complete local PostgreSQL + pgvector + Ollama RAG runtime.

    Optionally accepts an existing Level 2 DatabaseManager or EmbeddingProvider
    to share connection pools without coupling RAG and Memory services.
    """
    cfg = settings or RAGSettings.from_env()
    owns_db = db is None
    active_db = db or DatabaseManager(cfg.database_url)
    active_embedder = embedding_provider or OllamaEmbeddingProvider(
        base_url=cfg.ollama_base_url,
        model=cfg.embedding_model,
        dimension=cfg.embedding_dimension,
        timeout_seconds=cfg.ollama_timeout_seconds,
    )
    parser = LocalDocumentParser()
    chunker = RecursiveTextChunker(
        chunk_size=cfg.chunk_size,
        chunk_overlap=cfg.chunk_overlap,
    )
    repository = PostgresRAGRepository(active_db)
    ingestion = DocumentIngestionService(
        parser=parser,
        chunker=chunker,
        embedding_provider=active_embedder,
        repository=repository,
    )
    retriever = RAGRetrieverService(
        repository=repository,
        embedding_provider=active_embedder,
        default_top_k=cfg.default_top_k,
        default_min_similarity=cfg.similarity_threshold,
    )
    service = PostgresRAGService(
        ingestion_service=ingestion,
        retriever_service=retriever,
        repository=repository,
    )
    return RAGRuntime(
        settings=cfg,
        db=active_db,
        owns_db=owns_db,
        embedding_provider=active_embedder,
        parser=parser,
        chunker=chunker,
        repository=repository,
        ingestion=ingestion,
        retriever=retriever,
        service=service,
    )
