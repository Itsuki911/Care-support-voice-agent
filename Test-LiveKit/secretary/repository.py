"""PostgreSQL repository for TEST-Secretary mode (employee verification, events, tasks)."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import psycopg
from sqlalchemy import select

from database.connection import DatabaseManager
from database.models import (
    SecretaryEmployeeModel,
    SecretaryEventModel,
    SecretaryTaskModel,
)

try:
    JST = ZoneInfo("Asia/Tokyo")
except Exception:
    JST = timezone(timedelta(hours=9))


@dataclass(frozen=True)
class VerifiedEmployee:
    employee_id: str
    name: str
    department: str


@dataclass(frozen=True)
class ScheduleEventItem:
    title: str
    event_type: str
    start_at: datetime
    end_at: datetime
    location: str | None


@dataclass(frozen=True)
class TaskItem:
    title: str
    due_at: datetime
    status: str
    priority: str


class SecretaryRepository:
    """Queries TEST-Secretary tables strictly scoped to a verified employee_id."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    @staticmethod
    def _sync_dsn(database_url: str) -> str:
        if database_url.startswith("postgresql+psycopg://"):
            return "postgresql://" + database_url[len("postgresql+psycopg://") :]
        return database_url

    def _verify_employee_sync(self, *, employee_id: str, name: str) -> VerifiedEmployee | None:
        cleaned_id = employee_id.strip()
        cleaned_name = re.sub(r"[\s\u3000]+", " ", name.strip())
        if not cleaned_id or not cleaned_name:
            return None
        dsn = self._sync_dsn(self._db.database_url)
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT employee_id, name, department FROM secretary_employees "
                    "WHERE employee_id = %s AND name = %s",
                    (cleaned_id, cleaned_name),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                return VerifiedEmployee(
                    employee_id=str(row[0]),
                    name=str(row[1]),
                    department=str(row[2] or ""),
                )

    async def verify_employee(self, *, employee_id: str, name: str) -> VerifiedEmployee | None:
        # Use sync psycopg in a worker thread so uvicorn's ProactorEventLoop on Windows never fails.
        return await asyncio.to_thread(
            self._verify_employee_sync, employee_id=employee_id, name=name
        )

    async def get_events_for_date(
        self,
        employee_id: str,
        target_date: date,
    ) -> list[ScheduleEventItem]:
        day_start = datetime.combine(target_date, time.min, tzinfo=JST)
        day_end = day_start + timedelta(days=1)
        async with self._db.session() as session:
            stmt = (
                select(SecretaryEventModel)
                .where(
                    SecretaryEventModel.employee_id == employee_id,
                    SecretaryEventModel.start_at < day_end,
                    SecretaryEventModel.end_at > day_start,
                )
                .order_by(SecretaryEventModel.start_at.asc())
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [
                ScheduleEventItem(
                    title=r.title,
                    event_type=r.event_type,
                    start_at=r.start_at.astimezone(JST),
                    end_at=r.end_at.astimezone(JST),
                    location=r.location,
                )
                for r in rows
            ]

    async def get_tasks(
        self,
        employee_id: str,
        *,
        filter_type: str = "due_today",
        now_jst: datetime | None = None,
    ) -> list[TaskItem]:
        ref_now = (now_jst or datetime.now(JST)).astimezone(JST)
        day_start = datetime.combine(ref_now.date(), time.min, tzinfo=JST)
        day_end = day_start + timedelta(days=1)

        async with self._db.session() as session:
            stmt = select(SecretaryTaskModel).where(
                SecretaryTaskModel.employee_id == employee_id
            )
            if filter_type == "due_today":
                stmt = stmt.where(
                    SecretaryTaskModel.status == "pending",
                    SecretaryTaskModel.due_at >= day_start,
                    SecretaryTaskModel.due_at < day_end,
                )
            elif filter_type == "overdue":
                stmt = stmt.where(
                    SecretaryTaskModel.status == "pending",
                    SecretaryTaskModel.due_at < ref_now,
                )
            elif filter_type == "pending":
                stmt = stmt.where(SecretaryTaskModel.status == "pending")

            stmt = stmt.order_by(SecretaryTaskModel.due_at.asc())
            rows = (await session.execute(stmt)).scalars().all()
            return [
                TaskItem(
                    title=r.title,
                    due_at=r.due_at.astimezone(JST),
                    status=r.status,
                    priority=r.priority,
                )
                for r in rows
            ]
