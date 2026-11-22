"""PostgreSQL repository for TEST-Secretary mode (employee verification, events, tasks)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

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

    async def verify_employee(self, *, employee_id: str, name: str) -> VerifiedEmployee | None:
        cleaned_id = employee_id.strip()
        cleaned_name = name.strip()
        if not cleaned_id or not cleaned_name:
            return None
        async with self._db.session() as session:
            stmt = select(SecretaryEmployeeModel).where(
                SecretaryEmployeeModel.employee_id == cleaned_id,
                SecretaryEmployeeModel.name == cleaned_name,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                return None
            return VerifiedEmployee(
                employee_id=row.employee_id,
                name=row.name,
                department=row.department,
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
