"""SQLAlchemy 2.x ORM models for users, conversations, memories, and memory_history."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
        server_default=func.now(),
    )

    conversations: Mapped[list["ConversationModel"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    memories: Mapped[list["MemoryModel"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class ConversationModel(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant', 'system')", name="ck_conversations_role"),
        Index("ix_conversations_user_session_created", "user_id", "session_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, server_default=func.now()
    )

    user: Mapped["UserModel"] = relationship(back_populates="conversations")


class MemoryModel(Base):
    __tablename__ = "memories"
    __table_args__ = (
        CheckConstraint("importance >= 0.0 AND importance <= 1.0", name="ck_memories_importance"),
        CheckConstraint("confidence >= 0.0 AND confidence <= 1.0", name="ck_memories_confidence"),
        CheckConstraint("embedding_dimension > 0", name="ck_memories_embedding_dimension"),
        Index("ix_memories_user_updated", "user_id", "updated_at"),
        Index("ix_memories_user_model", "user_id", "embedding_model"),
        Index("ix_memories_user_type", "user_id", "memory_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    memory_type: Mapped[str] = mapped_column(String(64), nullable=False, default="fact")
    embedding: Mapped[list[float]] = mapped_column(Vector(768), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    importance: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.8)
    source_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
        server_default=func.now(),
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["UserModel"] = relationship(back_populates="memories")
    history_entries: Mapped[list["MemoryHistoryModel"]] = relationship(
        back_populates="memory", passive_deletes=True
    )


class MemoryHistoryModel(Base):
    """Audit trail for ADD / UPDATE / DELETE operations on memories."""

    __tablename__ = "memory_history"
    __table_args__ = (
        CheckConstraint("action IN ('ADD', 'UPDATE', 'DELETE')", name="ck_memory_history_action"),
        Index("ix_memory_history_user_created", "user_id", "created_at"),
        Index("ix_memory_history_memory_created", "memory_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    memory_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("memories.id", ondelete="SET NULL"), nullable=True
    )
    user_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    previous_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, server_default=func.now()
    )

    memory: Mapped["MemoryModel | None"] = relationship(back_populates="history_entries")


class RAGCorpusModel(Base):
    """Logical collection of external documents for RAG."""

    __tablename__ = "rag_corpora"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
        server_default=func.now(),
    )

    documents: Mapped[list["RAGDocumentModel"]] = relationship(
        back_populates="corpus", cascade="all, delete-orphan"
    )


class RAGDocumentModel(Base):
    """Source document metadata stored for RAG ingestion and citation tracking."""

    __tablename__ = "rag_documents"
    __table_args__ = (
        Index("ix_rag_documents_corpus_created", "corpus_id", "created_at"),
        Index("ix_rag_documents_corpus_filename", "corpus_id", "filename"),
        Index("uq_rag_documents_corpus_hash", "corpus_id", "file_hash", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    corpus_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("rag_corpora.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_type: Mapped[str] = mapped_column(String(32), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
        server_default=func.now(),
    )

    corpus: Mapped["RAGCorpusModel"] = relationship(back_populates="documents")
    chunks: Mapped[list["RAGChunkModel"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class RAGChunkModel(Base):
    """Chunked text and pgvector embedding belonging to a RAG document."""

    __tablename__ = "rag_chunks"
    __table_args__ = (
        CheckConstraint("chunk_index >= 0", name="ck_rag_chunks_chunk_index"),
        CheckConstraint("embedding_dimension > 0", name="ck_rag_chunks_embedding_dimension"),
        Index("ix_rag_chunks_document_index", "document_id", "chunk_index", unique=True),
        Index("ix_rag_chunks_embedding_model", "embedding_model"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rag_documents.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(768), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, server_default=func.now()
    )

    document: Mapped["RAGDocumentModel"] = relationship(back_populates="chunks")
