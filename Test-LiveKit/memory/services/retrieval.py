"""Memory Retrieval service: embeds queries and performs user-scoped semantic search."""

from __future__ import annotations

from memory.interfaces.embedding_provider import BaseEmbeddingProvider
from memory.interfaces.memory_repository import BaseMemoryRepository
from memory.models.memory import MemorySearchResult
from memory.observability import NOOP_TRACER, MemoryTracer


class MemoryRetrievalService:
    """Retrieves relevant memories for a user query while enforcing user & embedding-model isolation."""

    def __init__(
        self,
        *,
        repository: BaseMemoryRepository,
        embedding_provider: BaseEmbeddingProvider,
        default_limit: int = 5,
        default_min_similarity: float = 0.0,
        tracer: MemoryTracer | None = None,
    ) -> None:
        self._repository = repository
        self._embedding_provider = embedding_provider
        self._default_limit = default_limit
        self._default_min_similarity = default_min_similarity
        self._tracer = tracer or NOOP_TRACER

    async def search(
        self,
        user_id: str,
        query: str,
        *,
        limit: int | None = None,
        min_similarity: float | None = None,
    ) -> list[MemorySearchResult]:
        if not user_id or not user_id.strip():
            raise ValueError("user_id is required")
        cleaned_query = query.strip()
        if not cleaned_query:
            return []

        top_k = self._default_limit if limit is None else limit
        threshold = self._default_min_similarity if min_similarity is None else min_similarity

        with self._tracer.span(
            "memory.search",
            user_id=user_id,
            limit=top_k,
            min_similarity=threshold,
            embedding_model=self._embedding_provider.model_name,
        ) as span:
            span.set_input({"query": cleaned_query})
            with self._tracer.span(
                "memory.embedding",
                observation_type="embedding",
                embedding_model=self._embedding_provider.model_name,
                purpose="search_query",
            ) as emb_span:
                emb_span.set_model(self._embedding_provider.model_name)
                query_embedding = await self._embedding_provider.embed(cleaned_query)
                emb_span.set(dimension=len(query_embedding))
            with self._tracer.span("memory.vector_search", user_id=user_id, limit=top_k) as vs_span:
                results = await self._repository.search_similar(
                    user_id=user_id,
                    query_embedding=query_embedding,
                    embedding_model=self._embedding_provider.model_name,
                    limit=top_k,
                    min_similarity=threshold,
                )
                vs_span.set(hit_count=len(results))
            span.set(
                hit_count=len(results),
                top_similarity=round(results[0].similarity_score, 4) if results else None,
            )
            span.set_output(
                [
                    {
                        "memory_id": str(r.memory_id),
                        "memory_type": str(getattr(r.memory_type, "value", r.memory_type)),
                        "similarity_score": round(r.similarity_score, 4),
                        "content": r.content,
                    }
                    for r in results
                ]
            )
            return results

    @staticmethod
    def format_for_agent(results: list[MemorySearchResult]) -> str:
        """Format retrieved memories into a concise prompt context block for the voice/text agent."""
        if not results:
            return ""
        lines = ["関連するユーザー記憶:"]
        for item in results:
            lines.append(f"- [{item.memory_type}] {item.content}")
        return "\n".join(lines)
