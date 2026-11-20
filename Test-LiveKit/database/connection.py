"""Async SQLAlchemy 2.x + psycopg 3 connection management."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from database.config import normalize_async_database_url


class DatabaseManager:
    """Owns the SQLAlchemy AsyncEngine and sessionmaker lifecycle."""

    def __init__(self, database_url: str, *, echo: bool = False) -> None:
        self.database_url = normalize_async_database_url(database_url)
        self.engine: AsyncEngine = create_async_engine(
            self.database_url,
            echo=echo,
            pool_pre_ping=True,
        )
        self.session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as sess:
            try:
                yield sess
                await sess.commit()
            except Exception:
                await sess.rollback()
                raise

    async def health_check(self) -> bool:
        """Return True if PostgreSQL responds to a lightweight probe."""
        try:
            async with self.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    async def close(self) -> None:
        await self.engine.dispose()
