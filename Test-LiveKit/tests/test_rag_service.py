"""Offline unit tests for RAG ingestion, retriever, service, and LiveKit adapter."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from memory.interfaces.embedding_provider import BaseEmbeddingProvider
from rag.chunkers.recursive_chunker import RecursiveTextChunker
from rag.interfaces.repository import BaseRAGRepository
from rag.livekit_adapter import RAGTools
from rag.models.rag import DocumentRecord, ParsedDocument, RetrievalResult, TextChunk
from rag.parsers.document_parser import LocalDocumentParser
from rag.services.ingestion import DocumentIngestionService
from rag.services.rag_service import PostgresRAGService
from rag.services.retriever import RAGRetrieverService


class _FakeEmbeddingProvider(BaseEmbeddingProvider):
    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail
        self.calls: list[list[str]] = []

    @property
    def model_name(self) -> str:
        return "embeddinggemma-2:270m"

    @property
    def dimension(self) -> int:
        return 4

    async def embed(self, text: str) -> list[float]:
        return (await self.embed_batch([text]))[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        if self._fail:
            raise RuntimeError("Ollama unavailable")
        vectors: list[list[float]] = []
        for t in texts:
            if "打刻" in t:
                vectors.append([1.0, 0.0, 0.0, 0.0])
            elif "有給" in t:
                vectors.append([0.0, 1.0, 0.0, 0.0])
            else:
                vectors.append([0.0, 0.0, 1.0, 0.0])
        return vectors


class _InMemoryRAGRepository(BaseRAGRepository):
    def __init__(self) -> None:
        self.corpora: set[str] = set()
        self.docs: dict[uuid.UUID, DocumentRecord] = {}
        self.chunks: dict[uuid.UUID, list[tuple[TextChunk, list[float], str]]] = {}

    async def ensure_corpus(
        self, corpus_id: str, *, name: str | None = None, description: str | None = None
    ) -> None:
        self.corpora.add(corpus_id)

    async def find_by_hash(self, corpus_id: str, file_hash: str) -> DocumentRecord | None:
        for d in self.docs.values():
            if d.corpus_id == corpus_id and d.file_hash == file_hash:
                return d
        return None

    async def find_by_filename(self, corpus_id: str, filename: str) -> DocumentRecord | None:
        for d in self.docs.values():
            if d.corpus_id == corpus_id and d.filename == filename:
                return d
        return None

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
        self.corpora.add(corpus_id)
        doc_id = document_id or uuid.uuid4()
        now = datetime.now(timezone.utc)
        rec = DocumentRecord(
            id=doc_id,
            corpus_id=corpus_id,
            filename=parsed.filename,
            file_type=parsed.file_type,
            file_hash=parsed.file_hash,
            chunk_count=len(chunks),
            metadata=dict(parsed.metadata),
            created_at=now,
            updated_at=now,
        )
        self.docs[doc_id] = rec
        self.chunks[doc_id] = [
            (c.model_copy(update={"document_id": doc_id}), emb, embedding_model)
            for c, emb in zip(chunks, embeddings, strict=True)
        ]
        return rec

    async def get_document(self, document_id: uuid.UUID) -> DocumentRecord | None:
        return self.docs.get(document_id)

    async def list_documents(
        self, *, corpus_id: str | None = None, limit: int = 100
    ) -> list[DocumentRecord]:
        items = [
            d for d in self.docs.values() if corpus_id is None or d.corpus_id == corpus_id
        ]
        return items[:limit]

    async def delete_document(self, document_id: uuid.UUID) -> bool:
        existed = document_id in self.docs
        self.docs.pop(document_id, None)
        self.chunks.pop(document_id, None)
        return existed

    async def delete_corpus(self, corpus_id: str) -> bool:
        to_remove = [doc_id for doc_id, d in self.docs.items() if d.corpus_id == corpus_id]
        for doc_id in to_remove:
            self.docs.pop(doc_id, None)
            self.chunks.pop(doc_id, None)
        existed = corpus_id in self.corpora
        self.corpora.discard(corpus_id)
        return existed

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
        scored: list[RetrievalResult] = []
        for doc_id, doc in self.docs.items():
            if corpus_id is not None and doc.corpus_id != corpus_id:
                continue
            for chunk, emb, model in self.chunks.get(doc_id, []):
                if model != embedding_model:
                    continue
                if metadata_filter and any(
                    chunk.metadata.get(k) != v for k, v in metadata_filter.items()
                ):
                    continue
                sim = sum(a * b for a, b in zip(query_embedding, emb, strict=True))
                if sim < min_similarity:
                    continue
                scored.append(
                    RetrievalResult(
                        document_id=doc.id,
                        chunk_id=chunk.chunk_id,
                        corpus_id=doc.corpus_id,
                        content=chunk.content,
                        similarity_score=sim,
                        filename=doc.filename,
                        file_type=doc.file_type,
                        chunk_index=chunk.chunk_index,
                        page_number=chunk.page_number,
                        metadata=dict(chunk.metadata),
                    )
                )
        scored.sort(key=lambda r: r.similarity_score, reverse=True)
        return scored[:top_k]


def _build_service(*, fail_embed: bool = False) -> tuple[PostgresRAGService, _InMemoryRAGRepository]:
    repo = _InMemoryRAGRepository()
    embedder = _FakeEmbeddingProvider(fail=fail_embed)
    ingestion = DocumentIngestionService(
        parser=LocalDocumentParser(),
        chunker=RecursiveTextChunker(chunk_size=200, chunk_overlap=20),
        embedding_provider=embedder,
        repository=repo,
    )
    retriever = RAGRetrieverService(repository=repo, embedding_provider=embedder, default_top_k=5)
    service = PostgresRAGService(
        ingestion_service=ingestion, retriever_service=retriever, repository=repo
    )
    return service, repo


def test_rag_service_ingest_duplicate_update_search_corpus_isolation_and_delete(tmp_path: Path):
    async def scenario():
        service, _repo = _build_service()

        doc_a = tmp_path / "manual.txt"
        doc_a.write_text("出勤打刻は毎朝トップ画面から行います。", encoding="utf-8")
        doc_b = tmp_path / "rules.md"
        doc_b.write_text("# 有給休暇\n有給は3営業日前までに申請してください。", encoding="utf-8")

        r1 = await service.ingest_document(doc_a, corpus_id="corpus-a")
        assert r1.status == "ingested"
        assert r1.chunk_count >= 1

        # Duplicate prevention
        r1_dup = await service.ingest_document(doc_a, corpus_id="corpus-a")
        assert r1_dup.status == "duplicate"
        assert r1_dup.document.id == r1.document.id

        # Second corpus
        r2 = await service.ingest_document(doc_b, corpus_id="corpus-b")
        assert r2.status == "ingested"

        # Corpus-scoped search
        res_a = await service.search("打刻方法", corpus_id="corpus-a")
        assert len(res_a.results) == 1
        assert res_a.results[0].filename == "manual.txt"
        assert res_a.results[0].document_id == r1.document.id
        assert res_a.total_ms >= 0.0

        res_b = await service.search("有給申請", corpus_id="corpus-b")
        assert len(res_b.results) == 1
        assert res_b.results[0].filename == "rules.md"

        # Update document content
        doc_a.write_text("出勤打刻と退勤打刻はAobaTimeのトップ画面から行います。", encoding="utf-8")
        r1_upd = await service.update_document(doc_a, corpus_id="corpus-a")
        assert r1_upd.status == "updated"
        assert r1_upd.document.id == r1.document.id

        # Get & list & delete
        fetched = await service.get_document(r1.document.id)
        assert fetched is not None
        assert len(await service.list_documents(corpus_id="corpus-a")) == 1
        assert await service.delete_document(r1.document.id) is True
        assert await service.get_document(r1.document.id) is None

    asyncio.run(scenario())


def test_embedding_failure_leaves_no_partial_document(tmp_path: Path):
    async def scenario():
        service, repo = _build_service(fail_embed=True)
        doc = tmp_path / "guide.txt"
        doc.write_text("ログイン方法の説明テキスト。", encoding="utf-8")

        with pytest.raises(RuntimeError, match="Ollama unavailable"):
            await service.ingest_document(doc, corpus_id="corpus-fail")

        assert await repo.list_documents(corpus_id="corpus-fail") == []

    asyncio.run(scenario())


def test_livekit_adapter_and_untrusted_prompt_guard(tmp_path: Path):
    async def scenario():
        service, _ = _build_service()
        doc = tmp_path / "faq.md"
        doc.write_text("打刻できない場合はブラウザを再読み込みしてください。", encoding="utf-8")
        await service.ingest_document(doc, corpus_id="kb")

        tools = RAGTools(service, corpus_id="kb")
        out = await tools.search_documents(query="打刻できない", top_k=3)
        assert out["ok"] is True
        assert out["count"] == 1
        assert out["sources"][0]["filename"] == "faq.md"
        assert "信頼できない外部データ" in out["context"]
        assert "<retrieved_documents>" in out["context"]

        # Graceful fallback when embedding fails
        broken_service, _ = _build_service(fail_embed=True)
        broken_tools = RAGTools(broken_service, corpus_id="kb")
        err_out = await broken_tools.search_documents(query="打刻")
        assert err_out["ok"] is False
        assert err_out["count"] == 0

    asyncio.run(scenario())


def test_tool_uses_configured_retrieval_defaults_when_not_overridden():
    async def scenario():
        from unittest.mock import AsyncMock
        from rag.models.rag import SearchResponse

        service = _build_service()[0]
        service.search = AsyncMock(return_value=SearchResponse(query="query", results=[]))
        tools = RAGTools(service, corpus_id="kb")
        assert (await tools.search_documents(query="query"))["ok"] is True
        assert service.search.call_args.kwargs == {"corpus_id": "kb", "top_k": None, "min_similarity": None}
        await tools.search_documents(query="query", top_k=25)
        assert service.search.call_args.kwargs["top_k"] == 25
        await tools.search_documents(query="query", top_k=100)
        assert service.search.call_args.kwargs["top_k"] == 50

    asyncio.run(scenario())


def test_tool_forwards_runtime_defaults_through_retriever_to_repository():
    async def scenario():
        from unittest.mock import AsyncMock

        service, repo = _build_service()
        service._retriever._default_top_k = 7
        service._retriever._default_min_similarity = 0.75
        repo.search_similar = AsyncMock(return_value=[])
        tools = RAGTools(service, corpus_id="kb")
        result = await tools.search_documents(query="query")
        assert result["ok"] is True
        assert repo.search_similar.call_args.kwargs["top_k"] == 7
        assert repo.search_similar.call_args.kwargs["min_similarity"] == 0.75

    asyncio.run(scenario())
