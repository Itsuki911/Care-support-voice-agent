"""RAG Retriever service: embeds queries and runs pgvector cosine similarity search."""

from __future__ import annotations

import time
from typing import Any

from memory.interfaces.embedding_provider import BaseEmbeddingProvider
from rag.interfaces.repository import BaseRAGRepository
from rag.models.rag import SearchResponse
from rag.observability import NOOP_RAG_TRACER, RAGTracer


class RAGRetrieverService:
    """Retrieves top-K document chunks with latency breakdown and citation metadata."""

    def __init__(
        self,
        *,
        repository: BaseRAGRepository,
        embedding_provider: BaseEmbeddingProvider,
        default_top_k: int = 5,
        default_min_similarity: float = 0.0,
        tracer: RAGTracer | None = None,
    ) -> None:
        self._repository = repository
        self._embedding_provider = embedding_provider
        self._default_top_k = default_top_k
        self._default_min_similarity = default_min_similarity
        self._tracer = tracer or NOOP_RAG_TRACER

    async def retrieve(
        self,
        query: str,
        *,
        corpus_id: str | None = None,
        top_k: int | None = None,
        min_similarity: float | None = None,
        metadata_filter: dict[str, Any] | None = None,
    ) -> SearchResponse:
        cleaned = query.strip()
        if not cleaned:
            return SearchResponse(query="", corpus_id=corpus_id, results=[])

        k = self._default_top_k if top_k is None else top_k
        threshold = self._default_min_similarity if min_similarity is None else min_similarity

        with self._tracer.span(
            "rag.search",
            corpus_id=corpus_id or "all",
            top_k=k,
            min_similarity=threshold,
            embedding_model=self._embedding_provider.model_name,
        ) as span:
            span.set_input({"query": cleaned, "corpus_id": corpus_id, "top_k": k})
            t0 = time.perf_counter()
            with self._tracer.span(
                "rag.embedding",
                observation_type="embedding",
                embedding_model=self._embedding_provider.model_name,
                purpose="search_query",
            ) as emb_span:
                emb_span.set_model(self._embedding_provider.model_name)
                query_embedding = await self._embedding_provider.embed(cleaned)
                emb_span.set(dimension=len(query_embedding))
            t1 = time.perf_counter()

            with self._tracer.span(
                "rag.vector_search",
                corpus_id=corpus_id or "all",
                top_k=k,
            ) as vs_span:
                results = await self._repository.search_similar(
                    query_embedding=query_embedding,
                    embedding_model=self._embedding_provider.model_name,
                    corpus_id=corpus_id,
                    top_k=k,
                    min_similarity=threshold,
                    metadata_filter=metadata_filter,
                )
                vs_span.set(hit_count=len(results))
            t2 = time.perf_counter()

            embedding_ms = round((t1 - t0) * 1000.0, 3)
            db_search_ms = round((t2 - t1) * 1000.0, 3)
            total_ms = round((t2 - t0) * 1000.0, 3)

            span.set(
                hit_count=len(results),
                top_similarity=round(results[0].similarity_score, 4) if results else None,
                embedding_ms=embedding_ms,
                db_search_ms=db_search_ms,
                total_ms=total_ms,
                source_filenames=sorted({r.filename for r in results}),
            )
            span.set_output(
                [
                    {
                        "document_id": str(r.document_id),
                        "chunk_id": str(r.chunk_id),
                        "filename": r.filename,
                        "page_number": r.page_number,
                        "similarity_score": round(r.similarity_score, 4),
                        "content": r.content,
                    }
                    for r in results
                ]
            )
            return SearchResponse(
                query=cleaned,
                corpus_id=corpus_id,
                results=results,
                embedding_ms=embedding_ms,
                db_search_ms=db_search_ms,
                total_ms=total_ms,
            )
