"""Read-only schedule and task tools for TEST-Secretary mode."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, Callable, Literal
from uuid import uuid4

from livekit.agents import function_tool

from secretary.repository import JST, SecretaryRepository

logger = logging.getLogger("care-support-voice-agent.secretary_tools")


class SecretaryTools:
    """Read-only schedule and task tools strictly scoped to the server-verified employee."""

    def __init__(
        self,
        repository: SecretaryRepository,
        get_verified_employee_id: Callable[[], str | None],
        *,
        now_provider: Callable[[], datetime] | None = None,
        on_status: Callable[..., None] | None = None,
    ) -> None:
        self._repo = repository
        self._get_verified_employee_id = get_verified_employee_id
        self._now_provider = now_provider or (lambda: datetime.now(JST))
        self._on_status = on_status

    def _emit_status(self, status: str, execution_id: str, label: str, detail: str | None = None) -> None:
        if self._on_status is not None:
            self._on_status(
                kind="secretary",
                status=status,
                execution_id=execution_id,
                label=label,
                detail=detail,
            )

    def _require_employee_id(self) -> str | None:
        emp_id = self._get_verified_employee_id()
        if not emp_id or not emp_id.strip():
            return None
        return emp_id.strip()

    @function_tool
    async def get_schedule(
        self,
        date_range: Literal["today", "tomorrow", "date"] = "today",
        specific_date: str | None = None,
    ) -> dict[str, Any]:
        """Get the verified employee's scheduled meetings and work blocks in Japan Standard Time (JST).

        date_range: "today", "tomorrow", or "date" (with specific_date in YYYY-MM-DD).
        Always scoped to the signed-in employee; never accepts another employee's ID.
        """
        emp_id = self._require_employee_id()
        if emp_id is None:
            return {
                "ok": False,
                "error": "社員の本人確認ができていないため予定を取得できません。",
                "count": 0,
                "events": [],
            }

        now_jst = self._now_provider().astimezone(JST)
        if date_range == "today":
            target_date = now_jst.date()
        elif date_range == "tomorrow":
            target_date = now_jst.date() + timedelta(days=1)
        elif date_range == "date":
            if not specific_date:
                return {
                    "ok": False,
                    "error": "日付指定の場合は YYYY-MM-DD 形式で specific_date を指定してください。",
                    "count": 0,
                    "events": [],
                }
            try:
                target_date = date.fromisoformat(specific_date.strip())
            except ValueError:
                return {
                    "ok": False,
                    "error": "日付の形式が正しくありません。YYYY-MM-DD 形式で指定してください。",
                    "count": 0,
                    "events": [],
                }
        else:
            return {
                "ok": False,
                "error": "date_range は today / tomorrow / date のいずれかを指定してください。",
                "count": 0,
                "events": [],
            }

        exec_id = f"sec-sched-{uuid4().hex[:8]}"
        self._emit_status("running", exec_id, "予定を確認中…")
        try:
            events = await self._repo.get_events_for_date(emp_id, target_date)
        except Exception as exc:
            logger.warning("get_schedule failed: %s", exc)
            self._emit_status("failed", exec_id, "予定の取得に失敗")
            return {
                "ok": False,
                "error": "予定データベースに接続できないため取得できませんでした。",
                "count": 0,
                "events": [],
            }

        self._emit_status("completed", exec_id, "予定の確認完了", f"{len(events)}件")
        return {
            "ok": True,
            "date": target_date.isoformat(),
            "timezone": "Asia/Tokyo",
            "count": len(events),
            "events": [
                {
                    "title": ev.title,
                    "event_type": ev.event_type,
                    "start_time": ev.start_at.strftime("%H:%M"),
                    "end_time": ev.end_at.strftime("%H:%M"),
                    "location": ev.location or "",
                }
                for ev in events
            ],
        }

    @function_tool
    async def get_tasks(
        self,
        filter_type: Literal["due_today", "pending", "overdue", "all"] = "due_today",
    ) -> dict[str, Any]:
        """Get the verified employee's tasks in Japan Standard Time (JST).

        filter_type:
        - "due_today": pending tasks due today (JST)
        - "pending": all incomplete tasks
        - "overdue": pending tasks past their deadline
        - "all": all tasks including completed
        Always scoped to the signed-in employee; never accepts another employee's ID.
        """
        emp_id = self._require_employee_id()
        if emp_id is None:
            return {
                "ok": False,
                "error": "社員の本人確認ができていないためタスクを取得できません。",
                "count": 0,
                "tasks": [],
            }

        if filter_type not in ("due_today", "pending", "overdue", "all"):
            return {
                "ok": False,
                "error": "filter_type が不正です。",
                "count": 0,
                "tasks": [],
            }

        now_jst = self._now_provider().astimezone(JST)
        exec_id = f"sec-task-{uuid4().hex[:8]}"
        self._emit_status("running", exec_id, "タスクを確認中…")
        try:
            tasks = await self._repo.get_tasks(emp_id, filter_type=filter_type, now_jst=now_jst)
        except Exception as exc:
            logger.warning("get_tasks failed: %s", exc)
            self._emit_status("failed", exec_id, "タスクの取得に失敗")
            return {
                "ok": False,
                "error": "タスクデータベースに接続できないため取得できませんでした。",
                "count": 0,
                "tasks": [],
            }

        self._emit_status("completed", exec_id, "タスクの確認完了", f"{len(tasks)}件")
        return {
            "ok": True,
            "filter_type": filter_type,
            "timezone": "Asia/Tokyo",
            "count": len(tasks),
            "tasks": [
                {
                    "title": t.title,
                    "due_date": t.due_at.strftime("%Y-%m-%d"),
                    "due_time": t.due_at.strftime("%H:%M"),
                    "status": t.status,
                    "priority": t.priority,
                }
                for t in tasks
            ],
        }
