"""OS-independent configuration for the Agent Memory system."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent


def load_memory_env() -> None:
    """Load Test-LiveKit/.env without overriding explicit process environment variables."""
    load_dotenv(BASE_DIR / ".env", override=False)


def normalize_async_database_url(url: str) -> str:
    """Ensure SQLAlchemy uses the psycopg 3 async driver regardless of URL prefix."""
    cleaned = url.strip()
    if cleaned.startswith("postgresql+psycopg://"):
        return cleaned
    if cleaned.startswith("postgresql://"):
        return "postgresql+psycopg://" + cleaned[len("postgresql://") :]
    if cleaned.startswith("postgres://"):
        return "postgresql+psycopg://" + cleaned[len("postgres://") :]
    return cleaned


@dataclass(frozen=True)
class MemorySettings:
    """Runtime settings for PostgreSQL memory storage, Ollama embeddings, and LLM extraction."""

    database_url: str
    ollama_base_url: str
    embedding_model: str
    embedding_dimension: int
    default_search_limit: int
    similarity_threshold: float
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    db_timeout_seconds: float
    ollama_timeout_seconds: float

    @classmethod
    def from_env(cls, *, database_url_override: str | None = None) -> "MemorySettings":
        load_memory_env()
        raw_db_url = (
            database_url_override
            or os.getenv("DATABASE_URL")
            or "postgresql+psycopg://localhost:5432/care_support"
        )
        raw_llm_key = os.getenv("LLM_API_KEY") or os.getenv("OPENROUTER_API_KEY") or ""
        raw_llm_model = os.getenv("MEMORY_LLM_MODEL") or os.getenv("OPENROUTER_MODEL") or "anthropic/claude-haiku-5.5"
        raw_llm_base = os.getenv("LLM_BASE_URL") or "https://openrouter.ai/api/v1"

        return cls(
            database_url=normalize_async_database_url(raw_db_url),
            ollama_base_url=(os.getenv("OLLAMA_BASE_URL") or "http://127.0.0.1:11434").rstrip("/"),
            embedding_model=(os.getenv("EMBEDDING_MODEL") or "embeddinggemma-2:270m").strip(),
            embedding_dimension=int(os.getenv("EMBEDDING_DIMENSION") or "768"),
            default_search_limit=int(os.getenv("MEMORY_SEARCH_LIMIT") or "5"),
            similarity_threshold=float(os.getenv("MEMORY_SIMILARITY_THRESHOLD") or "0.0"),
            llm_base_url=raw_llm_base.rstrip("/"),
            llm_api_key=raw_llm_key.strip(),
            llm_model=raw_llm_model.strip(),
            db_timeout_seconds=float(os.getenv("MEMORY_DB_TIMEOUT_SECONDS") or "10.0"),
            ollama_timeout_seconds=float(os.getenv("OLLAMA_TIMEOUT_SECONDS") or "30.0"),
        )
