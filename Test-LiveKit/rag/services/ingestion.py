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
    ) -> None:
        self._parser = parser
        self._chunker = chunker
        self._embedding_provider = embedding_provider
        self._repository = repository
        self._embed_batch_size = max(1, embed_batch_size)

    async def _embed_chunks(self, contents: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(contents), self._embed_batch_size):
            batch = contents[start : start + self._embed_batch_size]
            vectors.extend(await self._embedding_provider.embed_batch(batch))
        return vectors

    async def ingest_file(
        self,
        path: str | Path,
        *,
        corpus_id: str = "default",
        metadata: dict[str, Any] | None = None,
    ) -> IngestResult:
        file_path = Path(path)
        parsed = await asyncio.to_thread(self._parser.parse, file_path)
        if metadata:
            parsed = parsed.model_copy(update={"metadata": {**parsed.metadata, **metadata}})

        existing = await self._repository.find_by_hash(corpus_id, parsed.file_hash)
        if existing is not None:
            logger.info(
                "Skipping duplicate document '%s' in corpus '%s' (doc_id=%s)",
                parsed.filename,
                corpus_id,
                existing.id,
            )
            return IngestResult(
                document=existing,
                chunk_count=existing.chunk_count,
                status="duplicate",
            )

        doc_id = uuid.uuid4()
        chunks = self._chunker.chunk(parsed, document_id=doc_id)
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
