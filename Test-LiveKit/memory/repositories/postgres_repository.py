"""PostgreSQL + pgvector repository backed by SQLAlchemy 2.x and psycopg 3."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Select, and_, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import DatabaseManager
from database.models import (
    ConversationModel,
    MemoryHistoryModel,
    MemoryModel,
    UserModel,
)
from memory.interfaces.memory_repository import BaseMemoryRepository
from memory.models.memory import (
    ConversationMessage,
    MemoryCreate,
    MemoryRecord,
    MemorySearchResult,
    MemoryUpdate,
)


class ConcurrencyConflictError(RuntimeError):
    """Raised when optimistic version check fails during concurrent memory update."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PostgresMemoryRepository(BaseMemoryRepository):
    """Async PostgreSQL repository with strict user_id isolation and history auditing."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    async def _ensure_user_in_session(
        self, session: AsyncSession, user_id: str, display_name: str | None = None
    ) -> None:
        stmt = (
            pg_insert(UserModel)
            .values(id=user_id, display_name=display_name)
            .on_conflict_do_nothing(index_elements=[UserModel.id])
        )
        await session.execute(stmt)

    async def ensure_user(self, user_id: str, display_name: str | None = None) -> None:
        async with self._db.session() as session:
            await self._ensure_user_in_session(session, user_id, display_name)

    async def save_conversation_messages(
        self, messages: list[ConversationMessage]
    ) -> list[ConversationMessage]:
        if not messages:
            return []
        async with self._db.session() as session:
            seen_users = {m.user_id for m in messages}
            for uid in seen_users:
                await self._ensure_user_in_session(session, uid)

            orm_rows: list[ConversationModel] = []
            for msg in messages:
                row = ConversationModel(
                    id=msg.id or uuid.uuid4(),
                    user_id=msg.user_id,
                    session_id=msg.session_id,
                    role=msg.role,
                    content=msg.content,
                    created_at=msg.created_at or _utcnow(),
                )
                session.add(row)
                orm_rows.append(row)
            await session.flush()
            return [ConversationMessage.model_validate(r) for r in orm_rows]

    async def list_conversation_messages(
        self, user_id: str, session_id: str, *, limit: int = 100
    ) -> list[ConversationMessage]:
        async with self._db.session() as session:
            stmt = (
                select(ConversationModel)
                .where(
                    and_(
                        ConversationModel.user_id == user_id,
                        ConversationModel.session_id == session_id,
                    )
                )
                .order_by(ConversationModel.created_at.asc())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [ConversationMessage.model_validate(r) for r in rows]

    async def insert(
        self,
        memory: MemoryCreate,
        *,
        embedding: list[float],
        embedding_model: str,
        embedding_dimension: int,
        reason: str = "initial_add",
    ) -> MemoryRecord:
        async with self._db.session() as session:
            await self._ensure_user_in_session(session, memory.user_id)
            now = _utcnow()
            row = MemoryModel(
                id=uuid.uuid4(),
                user_id=memory.user_id,
                content=memory.content,
                memory_type=memory.memory_type,
                embedding=embedding,
                embedding_model=embedding_model,
                embedding_dimension=embedding_dimension,
                importance=memory.importance,
                confidence=memory.confidence,
                source_session_id=memory.source_session_id,
                version=1,
                created_at=now,
                updated_at=now,
                expires_at=memory.expires_at,
            )
            session.add(row)
            await session.flush()

            session.add(
                MemoryHistoryModel(
                    memory_id=row.id,
                    user_id=row.user_id,
                    action="ADD",
                    previous_content=None,
                    new_content=row.content,
                    reason=reason,
                    source_session_id=row.source_session_id,
                )
            )
            await session.flush()
            return MemoryRecord.model_validate(row)

    async def get(self, user_id: str, memory_id: uuid.UUID) -> MemoryRecord | None:
        async with self._db.session() as session:
            stmt = select(MemoryModel).where(
                and_(MemoryModel.id == memory_id, MemoryModel.user_id == user_id)
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            return MemoryRecord.model_validate(row) if row is not None else None

    async def update(
        self,
        user_id: str,
        memory_id: uuid.UUID,
        patch: MemoryUpdate,
        *,
        embedding: list[float] | None = None,
        embedding_model: str | None = None,
        embedding_dimension: int | None = None,
        expected_version: int | None = None,
    ) -> MemoryRecord | None:
        async with self._db.session() as session:
            stmt = (
                select(MemoryModel)
                .where(and_(MemoryModel.id == memory_id, MemoryModel.user_id == user_id))
                .with_for_update()
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                return None

            if expected_version is not None and row.version != expected_version:
                raise ConcurrencyConflictError(
                    f"Memory {memory_id} version mismatch: expected {expected_version}, got {row.version}"
                )

            previous_content = row.content
            if patch.content is not None:
                row.content = patch.content
            if patch.memory_type is not None:
                row.memory_type = patch.memory_type
            if patch.importance is not None:
                row.importance = patch.importance
            if patch.confidence is not None:
                row.confidence = patch.confidence
            if patch.source_session_id is not None:
                row.source_session_id = patch.source_session_id
            if patch.expires_at is not None:
                row.expires_at = patch.expires_at
            if embedding is not None:
                row.embedding = embedding
            if embedding_model is not None:
                row.embedding_model = embedding_model
            if embedding_dimension is not None:
                row.embedding_dimension = embedding_dimension

            row.version += 1
            row.updated_at = _utcnow()
            await session.flush()

            session.add(
                MemoryHistoryModel(
                    memory_id=row.id,
                    user_id=row.user_id,
                    action="UPDATE",
                    previous_content=previous_content,
                    new_content=row.content,
                    reason=patch.reason or "updated",
                    source_session_id=patch.source_session_id or row.source_session_id,
                )
            )
            await session.flush()
            return MemoryRecord.model_validate(row)

    async def delete(
        self,
        user_id: str,
        memory_id: uuid.UUID,
        *,
        reason: str = "deleted",
        source_session_id: str | None = None,
    ) -> bool:
        async with self._db.session() as session:
            stmt = (
                select(MemoryModel)
                .where(and_(MemoryModel.id == memory_id, MemoryModel.user_id == user_id))
                .with_for_update()
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                return False

            session.add(
                MemoryHistoryModel(
                    memory_id=None,
                    user_id=row.user_id,
                    action="DELETE",
                    previous_content=row.content,
                    new_content=None,
                    reason=reason,
                    source_session_id=source_session_id or row.source_session_id,
                )
            )
            await session.delete(row)
            await session.flush()
            return True

    async def search_similar(
        self,
        user_id: str,
        query_embedding: list[float],
        *,
        embedding_model: str,
        limit: int = 5,
        min_similarity: float = 0.0,
    ) -> list[MemorySearchResult]:
        if limit <= 0:
            return []
        now = _utcnow()
        distance_expr = MemoryModel.embedding.cosine_distance(query_embedding)
        similarity_expr = (1.0 - distance_expr).label("similarity_score")

        async with self._db.session() as session:
            stmt = (
                select(MemoryModel, similarity_expr)
                .where(
                    and_(
                        MemoryModel.user_id == user_id,
                        MemoryModel.embedding_model == embedding_model,
                        or_(MemoryModel.expires_at.is_(None), MemoryModel.expires_at > now),
                    )
                )
                .order_by(distance_expr.asc())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).all()

            results: list[MemorySearchResult] = []
            for mem, sim in rows:
                score = float(sim) if sim is not None else 0.0
                if score < min_similarity:
                    continue
                results.append(
                    MemorySearchResult(
                        memory_id=mem.id,
                        content=mem.content,
                        memory_type=mem.memory_type,
                        similarity_score=score,
                        importance=mem.importance,
                        confidence=mem.confidence,
                        source_session_id=mem.source_session_id,
                        created_at=mem.created_at,
                        updated_at=mem.updated_at,
                    )
                )
            return results

    async def list_by_user(
        self, user_id: str, *, limit: int = 100, include_expired: bool = False
    ) -> list[MemoryRecord]:
        now = _utcnow()
        async with self._db.session() as session:
            conditions = [MemoryModel.user_id == user_id]
            if not include_expired:
                conditions.append(
                    or_(MemoryModel.expires_at.is_(None), MemoryModel.expires_at > now)
                )
            stmt: Select[tuple[MemoryModel]] = (
                select(MemoryModel)
                .where(and_(*conditions))
                .order_by(MemoryModel.updated_at.desc())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [MemoryRecord.model_validate(r) for r in rows]

    async def list_history(self, user_id: str, *, limit: int = 100) -> list[dict[str, object]]:
        async with self._db.session() as session:
            stmt = (
                select(MemoryHistoryModel)
                .where(MemoryHistoryModel.user_id == user_id)
                .order_by(MemoryHistoryModel.created_at.desc())
                .limit(limit)
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [
                {
                    "id": r.id,
                    "memory_id": r.memory_id,
                    "action": r.action,
                    "previous_content": r.previous_content,
                    "new_content": r.new_content,
                    "reason": r.reason,
                    "source_session_id": r.source_session_id,
                    "created_at": r.created_at,
                }
                for r in rows
            ]
