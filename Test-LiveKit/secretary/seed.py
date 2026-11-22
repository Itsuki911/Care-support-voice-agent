"""Idempotent seed script for TEST-Secretary mode (2 fictional employees in JST)."""

from __future__ import annotations

import asyncio
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import select

from database.config import MemorySettings
from database.connection import DatabaseManager
from database.models import (
    SecretaryEmployeeModel,
    SecretaryEventModel,
    SecretaryTaskModel,
)
from secretary.repository import JST


def build_seed_dataset(base_date: date | None = None) -> dict:
    """Build deterministic seed records relative to JST today (or a fixed base_date)."""
    today = base_date or datetime.now(JST).date()
    tomorrow = today + timedelta(days=1)
    yesterday = today - timedelta(days=1)
    day_after_tomorrow = today + timedelta(days=2)

    def jst_dt(d: date, hour: int, minute: int = 0) -> datetime:
        return datetime.combine(d, time(hour, minute), tzinfo=JST)

    employees = [
        {
            "employee_id": "EMP-1001",
            "name": "佐藤 花子",
            "department": "営業企画部",
        },
        {
            "employee_id": "EMP-1002",
            "name": "鈴木 太郎",
            "department": "開発部",
        },
    ]

    # Same date/time (today 10:00-11:00 JST) has different events per employee;
    # EMP-1002 has 0 events tomorrow; EMP-1001 has 0 events day_after_tomorrow.
    events = [
        {
            "seed_key": "emp1001-today-1000",
            "employee_id": "EMP-1001",
            "title": "営業週次定例会議",
            "event_type": "meeting",
            "start_at": jst_dt(today, 10, 0),
            "end_at": jst_dt(today, 11, 0),
            "location": "第1会議室",
        },
        {
            "seed_key": "emp1001-today-1400",
            "employee_id": "EMP-1001",
            "title": "見積書作成作業",
            "event_type": "work",
            "start_at": jst_dt(today, 14, 0),
            "end_at": jst_dt(today, 15, 30),
            "location": "自席",
        },
        {
            "seed_key": "emp1001-tomorrow-1300",
            "employee_id": "EMP-1001",
            "title": "クライアント提案打ち合わせ",
            "event_type": "meeting",
            "start_at": jst_dt(tomorrow, 13, 0),
            "end_at": jst_dt(tomorrow, 14, 0),
            "location": "オンライン",
        },
        {
            "seed_key": "emp1002-today-1000",
            "employee_id": "EMP-1002",
            "title": "アーキテクチャ設計レビュー",
            "event_type": "meeting",
            "start_at": jst_dt(today, 10, 0),
            "end_at": jst_dt(today, 11, 0),
            "location": "オンライン",
        },
        {
            "seed_key": "emp1002-today-1500",
            "employee_id": "EMP-1002",
            "title": "API性能改善作業",
            "event_type": "work",
            "start_at": jst_dt(today, 15, 0),
            "end_at": jst_dt(today, 17, 0),
            "location": "開発エリア",
        },
    ]

    # Only EMP-1001 has a task due today (and an overdue task).
    tasks = [
        {
            "seed_key": "emp1001-task-due-today",
            "employee_id": "EMP-1001",
            "title": "月次営業レポート提出",
            "due_at": jst_dt(today, 17, 0),
            "status": "pending",
            "priority": "high",
        },
        {
            "seed_key": "emp1001-task-overdue",
            "employee_id": "EMP-1001",
            "title": "顧客アンケート集計",
            "due_at": jst_dt(yesterday, 18, 0),
            "status": "pending",
            "priority": "medium",
        },
        {
            "seed_key": "emp1001-task-completed",
            "employee_id": "EMP-1001",
            "title": "請求書送付確認",
            "due_at": jst_dt(today, 12, 0),
            "status": "completed",
            "priority": "low",
        },
        {
            "seed_key": "emp1002-task-future",
            "employee_id": "EMP-1002",
            "title": "本番デプロイ手順書更新",
            "due_at": jst_dt(day_after_tomorrow, 18, 0),
            "status": "pending",
            "priority": "medium",
        },
    ]
    return {"employees": employees, "events": events, "tasks": tasks}


async def seed_secretary_data(db: DatabaseManager, *, base_date: date | None = None) -> dict[str, int]:
    """Upsert fictional employee, schedule, and task records idempotently."""
    dataset = build_seed_dataset(base_date=base_date)
    counts = {"employees": 0, "events": 0, "tasks": 0}

    async with db.session() as session:
        async with session.begin():
            for emp in dataset["employees"]:
                existing = await session.get(SecretaryEmployeeModel, emp["employee_id"])
                if existing is None:
                    session.add(SecretaryEmployeeModel(**emp))
                else:
                    existing.name = emp["name"]
                    existing.department = emp["department"]
                counts["employees"] += 1

            for ev in dataset["events"]:
                stmt = select(SecretaryEventModel).where(
                    SecretaryEventModel.seed_key == ev["seed_key"]
                )
                existing = (await session.execute(stmt)).scalar_one_or_none()
                if existing is None:
                    session.add(SecretaryEventModel(**ev))
                else:
                    existing.employee_id = ev["employee_id"]
                    existing.title = ev["title"]
                    existing.event_type = ev["event_type"]
                    existing.start_at = ev["start_at"]
                    existing.end_at = ev["end_at"]
                    existing.location = ev["location"]
                counts["events"] += 1

            for task in dataset["tasks"]:
                stmt = select(SecretaryTaskModel).where(
                    SecretaryTaskModel.seed_key == task["seed_key"]
                )
                existing = (await session.execute(stmt)).scalar_one_or_none()
                if existing is None:
                    session.add(SecretaryTaskModel(**task))
                else:
                    existing.employee_id = task["employee_id"]
                    existing.title = task["title"]
                    existing.due_at = task["due_at"]
                    existing.status = task["status"]
                    existing.priority = task["priority"]
                counts["tasks"] += 1

    return counts


async def _main() -> None:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
    db = DatabaseManager(MemorySettings.from_env().database_url)
    try:
        counts = await seed_secretary_data(db)
        print(
            f"シード投入完了: 社員={counts['employees']}件, 予定={counts['events']}件, タスク={counts['tasks']}件"
        )
    finally:
        await db.close()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(_main())
