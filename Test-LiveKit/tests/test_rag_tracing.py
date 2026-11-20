"""Unit tests for Level 3 RAG OpenTelemetry / Langfuse tracing spans."""

from __future__ import annotations

import asyncio
from pathlib import Path

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from rag.chunkers.recursive_chunker import RecursiveTextChunker
from rag.observability import RAGTracer
from rag.parsers.document_parser import LocalDocumentParser
from rag.services.ingestion import DocumentIngestionService
from rag.services.rag_service import PostgresRAGService
from rag.services.retriever import RAGRetrieverService
from tests.test_rag_service import _FakeEmbeddingProvider, _InMemoryRAGRepository


def _make_provider() -> tuple[TracerProvider, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider, exporter


def _build_traced_service(tracer: RAGTracer) -> PostgresRAGService:
    repo = _InMemoryRAGRepository()
    embedder = _FakeEmbeddingProvider()
    ingestion = DocumentIngestionService(
        parser=LocalDocumentParser(),
        chunker=RecursiveTextChunker(chunk_size=200, chunk_overlap=20),
        embedding_provider=embedder,
        repository=repo,
        tracer=tracer,
    )
    retriever = RAGRetrieverService(
        repository=repo,
        embedding_provider=embedder,
        default_top_k=5,
        tracer=tracer,
    )
    return PostgresRAGService(
        ingestion_service=ingestion,
        retriever_service=retriever,
        repository=repo,
        tracer=tracer,
    )


def test_rag_ingest_search_delete_emit_spans_without_content_when_pii_disabled(tmp_path: Path):
    async def scenario():
        provider, exporter = _make_provider()
        tracer = RAGTracer(provider, allow_content=False)
        service = _build_traced_service(tracer)

        doc = tmp_path / "rules.txt"
        doc.write_text("出勤打刻は毎朝トップ画面から行います。", encoding="utf-8")

        ingested = await service.ingest_document(doc, corpus_id="kb")
        resp = await service.search("打刻方法", corpus_id="kb", top_k=3)
        assert len(resp.results) == 1
        assert await service.delete_document(ingested.document.id) is True

        spans = exporter.get_finished_spans()
        names = [s.name for s in spans]
        for expected in (
            "rag.ingest",
            "rag.parse",
            "rag.chunk",
            "rag.embedding",
            "rag.search",
            "rag.vector_search",
            "rag.delete",
        ):
            assert expected in names

        for s in spans:
            assert "langfuse.observation.input" not in s.attributes
            assert "langfuse.observation.output" not in s.attributes

        search_span = next(s for s in spans if s.name == "rag.search")
        assert search_span.attributes["langfuse.observation.metadata.rag.hit_count"] == 1
        assert search_span.attributes["langfuse.observation.metadata.rag.corpus_id"] == "kb"
        assert "rules.txt" in search_span.attributes["langfuse.observation.metadata.rag.source_filenames"]

    asyncio.run(scenario())


def test_rag_search_exports_query_and_chunks_when_allow_content_enabled(tmp_path: Path):
    async def scenario():
        provider, exporter = _make_provider()
        tracer = RAGTracer(provider, allow_content=True)
        service = _build_traced_service(tracer)

        doc = tmp_path / "leave.md"
        doc.write_text("# 有給休暇\n有給は3営業日前までに申請してください。", encoding="utf-8")

        await service.ingest_document(doc, corpus_id="kb")
        await service.search("有給申請", corpus_id="kb", top_k=3)

        spans = exporter.get_finished_spans()
        search_span = next(s for s in spans if s.name == "rag.search")
        assert "有給申請" in search_span.attributes["langfuse.observation.input"]
        assert "3営業日前" in search_span.attributes["langfuse.observation.output"]

    asyncio.run(scenario())
