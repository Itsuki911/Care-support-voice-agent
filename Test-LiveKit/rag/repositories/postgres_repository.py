"""PostgreSQL + pgvector repository for RAG corpora, documents, and chunks."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import DatabaseManager
from database.models import RAGChunkModel, RAGCorpusModel, RAGDocumentModel
from rag.interfaces.repository import BaseRAGRepository
from rag.models.rag import DocumentRecord, ParsedDocument, RetrievalResult, TextChunk


def _to_document_record(row: RAGDocumentModel, *, chunk_count: int = 0) -> DocumentRecord:
    return DocumentRecord(
        id=row.id,
        corpus_id=row.corpus_id,
        filename=row.filename,
        file_type=row.file_type,
        file_hash=row.file_hash,
        chunk_count=chunk_count,
        metadata=dict(row.metadata_json or {}),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class PostgresRAGRepository(BaseRAGRepository):
    """Async SQLAlchemy 2.x + pgvector implementation of BaseRAGRepository."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    async def _ensure_corpus_in_session(
        self,
        session: AsyncSession,
        corpus_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> RAGCorpusModel:
        existing = await session.get(RAGCorpusModel, corpus_id)
        if existing is not None:
            return existing
        corpus = RAGCorpusModel(
            id=corpus_id,
            name=name or corpus_id,
            description=description,
            metadata_json={},
        )
        session.add(corpus)
        await session.flush()
        return corpus

    async def ensure_corpus(
        self,
        corpus_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> None:
        async with self._db.session() as session:
            await self._ensure_corpus_in_session(
                session, corpus_id, name=name, description=description
            )

    async def _count_chunks(self, session: AsyncSession, document_id: uuid.UUID) -> int:
        stmt = select(func.count(RAGChunkModel.id)).where(
            RAGChunkModel.document_id == document_id
        )
        res = await session.execute(stmt)
        return int(res.scalar() or 0)

    async def find_by_hash(self, corpus_id: str, file_hash: str) -> DocumentRecord | None:
        async with self._db.session() as session:
            stmt = select(RAGDocumentModel).where(
                RAGDocumentModel.corpus_id == corpus_id,
                RAGDocumentModel.file_hash == file_hash,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                return None
            count = await self._count_chunks(session, row.id)
            return _to_document_record(row, chunk_count=count)

    async def find_by_filename(self, corpus_id: str, filename: str) -> DocumentRecord | None:
        async with self._db.session() as session:
            stmt = (
                select(RAGDocumentModel)
                .where(
                    RAGDocumentModel.corpus_id == corpus_id,
                    RAGDocumentModel.filename == filename,
                )
                .order_by(RAGDocumentModel.updated_at.desc())
                .limit(1)
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                return None
            count = await self._count_chunks(session, row.id)
            return _to_document_record(row, chunk_count=count)

    async def save_document_with_chunks(
        self,
        *,
        corpus_id: str,
        parsed: ParsedDocument,
        chunks: list[TextChunk],
        embeddings: list[list[float]],
        embedding_model: str,
        embedding_dimension: int,
        document_id: uuid.UUID | None = None,
        replace_existing: bool = False,
    ) -> DocumentRecord:
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"Chunk count ({len(chunks)}) does not match embedding count ({len(embeddings)})"
            )
        if not chunks:
            raise ValueError("Cannot save document with 0 chunks")

        async with self._db.session() as session:
            await self._ensure_corpus_in_session(session, corpus_id)

            doc_row: RAGDocumentModel | None = None
            if replace_existing and document_id is not None:
                doc_row = await session.get(RAGDocumentModel, document_id)
                if doc_row is not None:
                    await session.execute(
                        delete(RAGChunkModel).where(RAGChunkModel.document_id == doc_row.id)
                    )
                    doc_row.filename = parsed.filename
                    doc_row.file_type = parsed.file_type
                    doc_row.file_hash = parsed.file_hash
                    doc_row.metadata_json = dict(parsed.metadata)
                    doc_row.updated_at = datetime.now(timezone.utc)

            if doc_row is None:
                doc_row = RAGDocumentModel(
                    id=document_id or uuid.uuid4(),
                    corpus_id=corpus_id,
                    filename=parsed.filename,
                    file_type=parsed.file_type,
                    file_hash=parsed.file_hash,
                    metadata_json=dict(parsed.metadata),
                )
                session.add(doc_row)

            await session.flush()

            chunk_rows = [
                RAGChunkModel(
                    id=chunk.chunk_id,
                    document_id=doc_row.id,
                    content=chunk.content,
                    chunk_index=chunk.chunk_index,
                    page_number=chunk.page_number,
                    embedding=embedding,
                    embedding_model=embedding_model,
                    embedding_dimension=embedding_dimension,
                    metadata_json=dict(chunk.metadata),
                )
                for chunk, embedding in zip(chunks, embeddings, strict=True)
            ]
            session.add_all(chunk_rows)
            await session.flush()
            await session.refresh(doc_row)
            return _to_document_record(doc_row, chunk_count=len(chunk_rows))

    async def get_document(self, document_id: uuid.UUID) -> DocumentRecord | None:
        async with self._db.session() as session:
            row = await session.get(RAGDocumentModel, document_id)
            if row is None:
                return None
            count = await self._count_chunks(session, row.id)
            return _to_document_record(row, chunk_count=count)

    async def list_documents(
        self, *, corpus_id: str | None = None, limit: int = 100
    ) -> list[DocumentRecord]:
        async with self._db.session() as session:
            count_subq = (
                select(
                    RAGChunkModel.document_id,
                    func.count(RAGChunkModel.id).label("chunk_count"),
                )
                .group_by(RAGChunkModel.document_id)
                .subquery()
            )
            stmt = (
                select(
                    RAGDocumentModel,
                    func.coalesce(count_subq.c.chunk_count, 0).label("chunk_count"),
                )
                .outerjoin(count_subq, RAGDocumentModel.id == count_subq.c.document_id)
                .order_by(RAGDocumentModel.updated_at.desc())
                .limit(limit)
            )
            if corpus_id is not None:
                stmt = stmt.where(RAGDocumentModel.corpus_id == corpus_id)
            rows = (await session.execute(stmt)).all()
            return [_to_document_record(doc, chunk_count=int(cnt)) for doc, cnt in rows]

    async def delete_document(self, document_id: uuid.UUID) -> bool:
        async with self._db.session() as session:
            row = await session.get(RAGDocumentModel, document_id)
            if row is None:
                return False
            await session.delete(row)
            await session.flush()
            return True

    async def delete_corpus(self, corpus_id: str) -> bool:
        async with self._db.session() as session:
            row = await session.get(RAGCorpusModel, corpus_id)
            if row is None:
                return False
            await session.delete(row)
            await session.flush()
            return True

    async def search_similar(
        self,
        *,
        query_embedding: list[float],
        embedding_model: str,
        corpus_id: str | None = None,
        top_k: int = 5,
        min_similarity: float = 0.0,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[RetrievalResult]:
        if top_k <= 0:
            return []

        distance_expr = RAGChunkModel.embedding.cosine_distance(query_embedding)
        similarity_expr = (1.0 - distance_expr).label("similarity_score")

        stmt = (
            select(RAGChunkModel, RAGDocumentModel, similarity_expr)
            .join(RAGDocumentModel, RAGChunkModel.document_id == RAGDocumentModel.id)
            .where(RAGChunkModel.embedding_model == embedding_model)
        )
        if corpus_id is not None:
            stmt = stmt.where(RAGDocumentModel.corpus_id == corpus_id)
        if metadata_filter:
            stmt = stmt.where(RAGChunkModel.metadata_json.contains(metadata_filter))

        stmt = stmt.order_by(distance_expr.asc()).limit(top_k)

        async with self._db.session() as session:
            rows = (await session.execute(stmt)).all()

        results: list[RetrievalResult] = []
        for chunk, doc, sim in rows:
            score = float(sim)
            if score < min_similarity:
                continue
            results.append(
                RetrievalResult(
                    document_id=doc.id,
                    chunk_id=chunk.id,
                    corpus_id=doc.corpus_id,
                    content=chunk.content,
                    similarity_score=score,
                    filename=doc.filename,
                    file_type=doc.file_type,
                    chunk_index=chunk.chunk_index,
                    page_number=chunk.page_number,
                    metadata=dict(chunk.metadata_json or {}),
                )
            )
        return results
