"""Ollama embedding provider (defaults to embeddinggemma-2:270m)."""

from __future__ import annotations

import httpx

from memory.interfaces.embedding_provider import BaseEmbeddingProvider


class EmbeddingError(RuntimeError):
    """Raised when embedding generation fails or returns an unexpected dimension."""


class OllamaEmbeddingProvider(BaseEmbeddingProvider):
    """Async embedding client backed by a local Ollama server."""

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "embeddinggemma-2:270m",
        dimension: int = 768,
        timeout_seconds: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._dimension = dimension
        self._timeout_seconds = timeout_seconds
        self._external_client = client

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        return self._dimension

    def _validate_vector(self, vec: object) -> list[float]:
        if not isinstance(vec, list) or not vec:
            raise EmbeddingError("Ollama returned an empty embedding vector")
        if len(vec) != self._dimension:
            raise EmbeddingError(
                f"Embedding dimension mismatch for {self._model}: "
                f"expected {self._dimension}, got {len(vec)}"
            )
        return [float(x) for x in vec]

    async def _post_embed(self, payload: dict[str, object]) -> dict[str, object]:
        url = f"{self._base_url}/api/embed"
        try:
            if self._external_client is not None:
                resp = await self._external_client.post(url, json=payload, timeout=self._timeout_seconds)
            else:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            raise EmbeddingError(f"Ollama embedding request failed: {exc}") from None
        except ValueError:
            raise EmbeddingError("Ollama returned invalid JSON") from None
        if not isinstance(data, dict):
            raise EmbeddingError("Unexpected Ollama response payload")
        return data

    async def embed(self, text: str) -> list[float]:
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("Cannot embed empty text")
        vectors = await self.embed_batch([cleaned])
        return vectors[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        cleaned_texts = [t.strip() for t in texts]
        if any(not t for t in cleaned_texts):
            raise ValueError("Cannot embed empty text in batch")

        data = await self._post_embed({"model": self._model, "input": cleaned_texts})
        raw_embeddings = data.get("embeddings")
        if not isinstance(raw_embeddings, list) or len(raw_embeddings) != len(cleaned_texts):
            raise EmbeddingError(
                f"Expected {len(cleaned_texts)} embeddings from Ollama, "
                f"got {len(raw_embeddings) if isinstance(raw_embeddings, list) else type(raw_embeddings).__name__}"
            )
        return [self._validate_vector(vec) for vec in raw_embeddings]
