"""Pydantic domain models for Agent Memory."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MemoryType(str, Enum):
    PREFERENCE = "preference"
    HABIT = "habit"
    PROFILE = "profile"
    INTEREST = "interest"
    EVENT = "event"
    TOPIC = "topic"
    FACT = "fact"


class ConsolidationAction(str, Enum):
    ADD = "ADD"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    NOOP = "NOOP"


class ConversationMessage(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID | None = None
    user_id: str = Field(min_length=1, max_length=128)
    session_id: str = Field(min_length=1, max_length=255)
    role: Literal["user", "assistant", "system"]
    content: str = Field(min_length=1)
    created_at: datetime | None = None


class MemoryRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: str
    content: str
    memory_type: str
    embedding_model: str
    embedding_dimension: int
    importance: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    source_session_id: str | None = None
    version: int = 1
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None = None


class MemoryCreate(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    content: str = Field(min_length=1)
    memory_type: str = Field(default=MemoryType.FACT.value, min_length=1, max_length=64)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    source_session_id: str | None = Field(default=None, max_length=255)
    expires_at: datetime | None = None

    @field_validator("content")
    @classmethod
    def _strip_content(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("content must not be blank")
        return cleaned


class MemoryUpdate(BaseModel):
    content: str | None = None
    memory_type: str | None = Field(default=None, min_length=1, max_length=64)
    importance: float | None = Field(default=None, ge=0.0, le=1.0)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source_session_id: str | None = Field(default=None, max_length=255)
    expires_at: datetime | None = None
    reason: str | None = None

    @field_validator("content")
    @classmethod
    def _strip_optional_content(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("content must not be blank")
        return cleaned


class MemorySearchResult(BaseModel):
    memory_id: uuid.UUID
    content: str
    memory_type: str
    similarity_score: float
    importance: float = 0.5
    confidence: float = 0.8
    source_session_id: str | None = None
    created_at: datetime
    updated_at: datetime


class ExtractedMemory(BaseModel):
    content: str = Field(min_length=1)
    memory_type: str = Field(default=MemoryType.FACT.value)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    source_session_id: str | None = None

    @field_validator("content")
    @classmethod
    def _strip_content(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("extracted memory content must not be blank")
        return cleaned


class ExtractionResponse(BaseModel):
    memories: list[ExtractedMemory] = Field(default_factory=list)


class ConsolidationDecision(BaseModel):
    action: ConsolidationAction
    target_memory_id: uuid.UUID | None = None
    merged_content: str | None = None
    memory_type: str | None = None
    importance: float | None = Field(default=None, ge=0.0, le=1.0)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    reason: str = ""


class ProcessConversationResult(BaseModel):
    session_id: str
    user_id: str
    saved_messages: int = 0
    extracted_count: int = 0
    added_ids: list[uuid.UUID] = Field(default_factory=list)
    updated_ids: list[uuid.UUID] = Field(default_factory=list)
    deleted_ids: list[uuid.UUID] = Field(default_factory=list)
    noop_count: int = 0
    errors: list[str] = Field(default_factory=list)
