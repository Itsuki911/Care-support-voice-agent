"""Add Level 3 RAG tables (rag_corpora, rag_documents, rag_chunks + HNSW index).

Revision ID: 0002_rag_schema
Revises: 0001_initial_memory_schema
Create Date: 2026-11-20
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "0002_rag_schema"
down_revision = "0001_initial_memory_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "rag_corpora",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "rag_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("corpus_id", sa.String(length=128), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("file_type", sa.String(length=32), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["corpus_id"], ["rag_corpora.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_rag_documents_corpus_created", "rag_documents", ["corpus_id", "created_at"]
    )
    op.create_index(
        "ix_rag_documents_corpus_filename", "rag_documents", ["corpus_id", "filename"]
    )
    op.create_index(
        "uq_rag_documents_corpus_hash",
        "rag_documents",
        ["corpus_id", "file_hash"],
        unique=True,
    )

    op.create_table(
        "rag_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("embedding", Vector(768), nullable=False),
        sa.Column("embedding_model", sa.String(length=128), nullable=False),
        sa.Column("embedding_dimension", sa.Integer(), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("chunk_index >= 0", name="ck_rag_chunks_chunk_index"),
        sa.CheckConstraint("embedding_dimension > 0", name="ck_rag_chunks_embedding_dimension"),
        sa.ForeignKeyConstraint(["document_id"], ["rag_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_rag_chunks_document_index",
        "rag_chunks",
        ["document_id", "chunk_index"],
        unique=True,
    )
    op.create_index("ix_rag_chunks_embedding_model", "rag_chunks", ["embedding_model"])
    op.execute(
        "CREATE INDEX ix_rag_chunks_embedding_hnsw "
        "ON rag_chunks USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_rag_chunks_embedding_hnsw")
    op.drop_index("ix_rag_chunks_embedding_model", table_name="rag_chunks")
    op.drop_index("ix_rag_chunks_document_index", table_name="rag_chunks")
    op.drop_table("rag_chunks")

    op.drop_index("uq_rag_documents_corpus_hash", table_name="rag_documents")
    op.drop_index("ix_rag_documents_corpus_filename", table_name="rag_documents")
    op.drop_index("ix_rag_documents_corpus_created", table_name="rag_documents")
    op.drop_table("rag_documents")

    op.drop_table("rag_corpora")
