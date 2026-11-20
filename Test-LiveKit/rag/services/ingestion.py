"""Document Ingestion service: Parse -> Chunk -> Embed -> Atomic PostgreSQL save."""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Any

from memory.interfaces.embedding_provider import BaseEmbeddingProvider
from rag.interfaces.chunker import BaseTextChunker
from rag.interfaces.parser import BaseDocumentParser
from rag.interfaces.repository import BaseRAGRepository
from rag.models.rag import IngestResult
from rag.observability import NOOP_RAG_TRACER, RAGTracer

logger = logging.getLogger("care-support-voice-agent.rag.ingestion")


class DocumentIngestionService:
    """Handles document ingestion, duplicate prevention, and atomic updates."""

    def __init__(
        self,
        *,
        parser: BaseDocumentParser,
        chunker: BaseTextChunker,
        embedding_provider: BaseEmbeddingProvider,
        repository: BaseRAGRepository,
        embed_batch_size: int = 32,
        tracer: RAGTracer | None = None,
    ) -> None:
        self._parser = parser
        self._chunker = chunker
        self._embedding_provider = embedding_provider
        self._repository = repository
        self._embed_batch_size = max(1, embed_batch_size)
        self._tracer = tracer or NOOP_RAG_TRACER

    async def _embed_chunks(self, contents: list[str]) -> list[list[float]]:
        with self._tracer.span(
            "rag.embedding",
            observation_type="embedding",
            embedding_model=self._embedding_provider.model_name,
            purpose="document_chunks",
            chunk_count=len(contents),
        ) as emb_span:
            emb_span.set_model(self._embedding_provider.model_name)
            vectors: list[list[float]] = []
            for start in range(0, len(contents), self._embed_batch_size):
                batch = contents[start : start + self._embed_batch_size]
                vectors.extend(await self._embedding_provider.embed_batch(batch))
            emb_span.set(dimension=len(vectors[0]) if vectors else 0)
            return vectors

    async def ingest_file(
        self,
        path: str | Path,
        *,
        corpus_id: str = "default",
        metadata: dict[str, Any] | None = None,
    ) -> IngestResult:
        file_path = Path(path)
        with self._tracer.span(
            "rag.ingest",
            corpus_id=corpus_id,
            filename=file_path.name,
        ) as span:
            with self._tracer.span("rag.parse", filename=file_path.name) as parse_span:
                parsed = await asyncio.to_thread(self._parser.parse, file_path)
                parse_span.set(file_type=parsed.file_type, page_count=len(parsed.pages))
            if metadata:
                parsed = parsed.model_copy(update={"metadata": {**parsed.metadata, **metadata}})
            span.set(file_type=parsed.file_type)

            existing = await self._repository.find_by_hash(corpus_id, parsed.file_hash)
            if existing is not None:
                logger.info(
                    "Skipping duplicate document '%s' in corpus '%s' (doc_id=%s)",
                    parsed.filename,
                    corpus_id,
                    existing.id,
                )
                span.set(status="duplicate", document_id=str(existing.id), chunk_count=existing.chunk_count)
                return IngestResult(
                    document=existing,
                    chunk_count=existing.chunk_count,
                    status="duplicate",
                )

            doc_id = uuid.uuid4()
            with self._tracer.span("rag.chunk", filename=parsed.filename) as chunk_span:
                chunks = self._chunker.chunk(parsed, document_id=doc_id)
                chunk_span.set(chunk_count=len(chunks))
            if not chunks:
                raise ValueError(f"Chunker produced 0 chunks for '{parsed.filename}'")

            # Generate all embeddings BEFORE opening the DB write transaction so a
            # mid-flight Ollama failure never leaves partial rows in PostgreSQL.
            embeddings = await self._embed_chunks([c.content for c in chunks])

            record = await self._repository.save_document_with_chunks(
                corpus_id=corpus_id,
                parsed=parsed,
                chunks=chunks,
                embeddings=embeddings,
                embedding_model=self._embedding_provider.model_name,
                embedding_dimension=self._embedding_provider.dimension,
                document_id=doc_id,
                replace_existing=False,
            )
            span.set(status="ingested", document_id=str(record.id), chunk_count=len(chunks))
            return IngestResult(document=record, chunk_count=len(chunks), status="ingested")

    async def update_file(
        self,
        path: str | Path,
        *,
        corpus_id: str = "default",
        document_id: uuid.UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> IngestResult:
        file_path = Path(path)
        parsed = await asyncio.to_thread(self._parser.parse, file_path)
        if metadata:
            parsed = parsed.model_copy(update={"metadata": {**parsed.metadata, **metadata}})

        target_id = document_id
        if target_id is None:
            existing_by_name = await self._repository.find_by_filename(corpus_id, parsed.filename)
            if existing_by_name is not None:
                if existing_by_name.file_hash == parsed.file_hash:
                    return IngestResult(
                        document=existing_by_name,
                        chunk_count=existing_by_name.chunk_count,
                        status="duplicate",
                    )
                target_id = existing_by_name.id
        else:
            existing_by_id = await self._repository.get_document(target_id)
            if existing_by_id is not None and existing_by_id.file_hash == parsed.file_hash:
                return IngestResult(
                    document=existing_by_id,
                    chunk_count=existing_by_id.chunk_count,
                    status="duplicate",
                )

        if target_id is None:
            return await self.ingest_file(file_path, corpus_id=corpus_id, metadata=metadata)

        chunks = self._chunker.chunk(parsed, document_id=target_id)
        if not chunks:
            raise ValueError(f"Chunker produced 0 chunks for '{parsed.filename}'")

        embeddings = await self._embed_chunks([c.content for c in chunks])
        record = await self._repository.save_document_with_chunks(
            corpus_id=corpus_id,
            parsed=parsed,
            chunks=chunks,
            embeddings=embeddings,
            embedding_model=self._embedding_provider.model_name,
            embedding_dimension=self._embedding_provider.dimension,
            document_id=target_id,
            replace_existing=True,
        )
        return IngestResult(document=record, chunk_count=len(chunks), status="updated")
