"""RAG Retriever service: embeds queries and runs pgvector cosine similarity search."""

from __future__ import annotations

import time
from typing import Any

from memory.interfaces.embedding_provider import BaseEmbeddingProvider
from rag.interfaces.repository import BaseRAGRepository
from rag.models.rag import SearchResponse


class RAGRetrieverService:
    """Retrieves top-K document chunks with latency breakdown and citation metadata."""

    def __init__(
        self,
        *,
        repository: BaseRAGRepository,
        embedding_provider: BaseEmbeddingProvider,
        default_top_k: int = 5,
        default_min_similarity: float = 0.0,
    ) -> None:
        self._repository = repository
        self._embedding_provider = embedding_provider
        self._default_top_k = default_top_k
        self._default_min_similarity = default_min_similarity

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

        t0 = time.perf_counter()
        query_embedding = await self._embedding_provider.embed(cleaned)
        t1 = time.perf_counter()

        results = await self._repository.search_similar(
            query_embedding=query_embedding,
            embedding_model=self._embedding_provider.model_name,
            corpus_id=corpus_id,
            top_k=k,
            min_similarity=threshold,
            metadata_filter=metadata_filter,
        )
        t2 = time.perf_counter()

        return SearchResponse(
            query=cleaned,
            corpus_id=corpus_id,
            results=results,
            embedding_ms=round((t1 - t0) * 1000.0, 3),
            db_search_ms=round((t2 - t1) * 1000.0, 3),
            total_ms=round((t2 - t0) * 1000.0, 3),
        )
