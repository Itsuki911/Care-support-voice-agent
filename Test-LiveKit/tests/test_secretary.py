"""Automated tests for TEST-Secretary mode (token server, tools, DB isolation, DeepEval/Langfuse)."""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient

import token_server
from evaluations.evaluate_secretary import (
    LangfuseResolutionError,
    evaluate_full_conversation,
    evaluate_transcript,
    load_case,
    post_scores_to_langfuse,
    resolve_unique_langfuse_trace_id,
)
from secretary.repository import JST, ScheduleEventItem, TaskItem, VerifiedEmployee
from secretary.seed import build_seed_dataset
from secretary.tools import SecretaryTools


def test_token_server_secretary_verify_and_token_metadata(monkeypatch):
    monkeypatch.setenv("LIVEKIT_URL", "wss://example.livekit.cloud")
    monkeypatch.setenv("LIVEKIT_API_KEY", "APIkey123")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "secret123456789012345678901234567890")

    async def fake_verify(*, employee_id: str, name: str):
        if employee_id == "EMP-1001" and name == "佐藤 花子":
            return VerifiedEmployee("EMP-1001", "佐藤 花子", "営業企画部")
        return None

    fake_repo = SimpleNamespace(verify_employee=fake_verify)
    monkeypatch.setattr(token_server, "get_secretary_repository", lambda: fake_repo)

    client = TestClient(token_server.app)
    headers = {"Origin": "http://localhost:5173"}

    ok_res = client.post(
        "/api/secretary/verify",
        headers=headers,
        json={"employee_name": "佐藤 花子", "employee_id": "EMP-1001"},
    )
    assert ok_res.status_code == 200
    assert ok_res.json()["verified"] is True

    bad_res = client.post(
        "/api/secretary/verify",
        headers=headers,
        json={"employee_name": "佐藤 花子", "employee_id": "EMP-9999"},
    )
    assert bad_res.status_code == 401

    tok_res = client.post(
        "/api/token",
        headers=headers,
        json={
            "mode": "secretary",
            "employee_name": "佐藤 花子",
            "employee_id": "EMP-1001",
            "user_id": "spoofed-browser-id",
        },
    )
    assert tok_res.status_code == 200
    claims = jwt.decode(
        tok_res.json()["participant_token"],
        options={"verify_signature": False},
    )
    assert claims["video"]["room"].startswith("frontend-test-secretary-")
    meta = json.loads(claims["metadata"])
    assert meta["secretary_verified"] is True
    assert meta["employee_id"] == "EMP-1001"
    assert claims["sub"].startswith("secretary-EMP-1001-")

    bad_tok = client.post(
        "/api/token",
        headers=headers,
        json={"mode": "secretary", "employee_name": "別人", "employee_id": "EMP-1001"},
    )
    assert bad_tok.status_code == 401


def test_secretary_tools_isolation_dates_zero_and_db_error():
    fixed_now = datetime(2026, 11, 22, 9, 30, tzinfo=JST)
    seed = build_seed_dataset(base_date=fixed_now.date())

    class InMemorySecretaryRepo:
        def __init__(self, fail: bool = False):
            self.fail = fail

        async def get_events_for_date(self, employee_id: str, target_date: date):
            if self.fail:
                raise RuntimeError("db connection lost")
            return [
                ScheduleEventItem(
                    title=ev["title"],
                    event_type=ev["event_type"],
                    start_at=ev["start_at"],
                    end_at=ev["end_at"],
                    location=ev["location"],
                )
                for ev in seed["events"]
                if ev["employee_id"] == employee_id and ev["start_at"].date() == target_date
            ]

        async def get_tasks(self, employee_id: str, *, filter_type: str = "due_today", now_jst=None):
            if self.fail:
                raise RuntimeError("db connection lost")
            ref = now_jst or fixed_now
            items = []
            for t in seed["tasks"]:
                if t["employee_id"] != employee_id:
                    continue
                if filter_type == "due_today" and not (
                    t["status"] == "pending" and t["due_at"].date() == ref.date()
                ):
                    continue
                if filter_type == "overdue" and not (
                    t["status"] == "pending" and t["due_at"] < ref
                ):
                    continue
                if filter_type == "pending" and t["status"] != "pending":
                    continue
                items.append(
                    TaskItem(
                        title=t["title"],
                        due_at=t["due_at"],
                        status=t["status"],
                        priority=t["priority"],
                    )
                )
            return items

    async def scenario():
        repo = InMemorySecretaryRepo()
        unverified = SecretaryTools(repo, lambda: None, now_provider=lambda: fixed_now)
        assert (await unverified.get_schedule("today"))["ok"] is False
        assert (await unverified.get_tasks("due_today"))["ok"] is False

        emp1 = SecretaryTools(repo, lambda: "EMP-1001", now_provider=lambda: fixed_now)
        emp2 = SecretaryTools(repo, lambda: "EMP-1002", now_provider=lambda: fixed_now)

        s1 = await emp1.get_schedule("today")
        s2 = await emp2.get_schedule("today")
        assert s1["ok"] is True and s1["events"][0]["title"] == "営業週次定例会議"
        assert s2["ok"] is True and s2["events"][0]["title"] == "アーキテクチャ設計レビュー"

        # EMP-1002 has 0 events tomorrow (distinct from DB error)
        s2_tomorrow = await emp2.get_schedule("tomorrow")
        assert s2_tomorrow["ok"] is True and s2_tomorrow["count"] == 0

        # EMP-1001 has due_today task; EMP-1002 has 0 due_today tasks
        t1 = await emp1.get_tasks("due_today")
        t2 = await emp2.get_tasks("due_today")
        assert t1["ok"] is True and t1["tasks"][0]["title"] == "月次営業レポート提出"
        assert t2["ok"] is True and t2["count"] == 0

        # Specific date query
        day_after = (fixed_now.date() + timedelta(days=2)).isoformat()
        s1_empty = await emp1.get_schedule("date", specific_date=day_after)
        assert s1_empty["ok"] is True and s1_empty["count"] == 0

        # DB failure returns ok=False (never confused with 0 items)
        broken = SecretaryTools(InMemorySecretaryRepo(fail=True), lambda: "EMP-1001", now_provider=lambda: fixed_now)
        err_sched = await broken.get_schedule("today")
        err_tasks = await broken.get_tasks("due_today")
        assert err_sched["ok"] is False and err_tasks["ok"] is False

    asyncio.run(scenario())


def test_deepeval_and_langfuse_scoring_and_resolution(monkeypatch):
    from deepeval.metrics import ConversationalGEval, GEval

    # Test SEC-01 (no correction -> ConversationalGEval skipped)
    _, case_no_corr = load_case("SEC-01")
    _, case_corr = load_case("SEC-03")

    class FakeMetric:
        def __init__(self, score: float, reason: str):
            self.score = score
            self.reason = reason

        def measure(self, _):
            return self.score

        def is_successful(self):
            return self.score >= 0.7

    monkeypatch.setattr(
        "deepeval.metrics.GEval",
        lambda **kwargs: FakeMetric(0.92, "予定名と時刻が正確"),
    )
    monkeypatch.setattr(
        "deepeval.metrics.ConversationalGEval",
        lambda **kwargs: FakeMetric(0.95, "訂正後の締切に回答"),
    )

    res_no_corr = evaluate_transcript(
        case=case_no_corr,
        transcript_doc={
            "turns": [
                {"role": "user", "text": "今日の10時の予定は？"},
                {"role": "assistant", "text": "10時から営業週次定例会議です。"},
            ]
        },
        judge_model="dummy",
    )
    assert res_no_corr[0].passed is True
    assert res_no_corr[1].skipped is True

    res_corr = evaluate_transcript(
        case=case_corr,
        transcript_doc={
            "turns": [
                {"role": "user", "text": "明日の予定を。あ、今日の締切を教えて"},
                {"role": "assistant", "text": "今日の締切は月次営業レポート提出です。"},
            ]
        },
        judge_model="dummy",
    )
    assert res_corr[0].passed is True
    assert res_corr[1].skipped is False and res_corr[1].passed is True

    # Langfuse trace resolution edge cases (0 traces, >1 traces, HTTP error)
    def make_client(status: int, data: list[dict]):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status, json={"data": data})
        return httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(LangfuseResolutionError) as e0:
        resolve_unique_langfuse_trace_id(
            "sess-0", host="https://lf.example", public_key="pk", secret_key="sk",
            http_client=make_client(200, []),
        )
    assert e0.value.code == "LANGFUSE_TRACE_NOT_FOUND"

    with pytest.raises(LangfuseResolutionError) as e2:
        resolve_unique_langfuse_trace_id(
            "sess-2", host="https://lf.example", public_key="pk", secret_key="sk",
            http_client=make_client(200, [{"traceId": "t1"}, {"traceId": "t2"}]),
        )
    assert e2.value.code == "LANGFUSE_TRACE_AMBIGUOUS"

    with pytest.raises(LangfuseResolutionError) as e500:
        resolve_unique_langfuse_trace_id(
            "sess-err", host="https://lf.example", public_key="pk", secret_key="sk",
            http_client=make_client(500, []),
        )
    assert e500.value.code == "LANGFUSE_API_ERROR"

    # Langfuse score posting must not include PII
    posted_bodies = []

    def score_handler(request: httpx.Request) -> httpx.Response:
        posted_bodies.append(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json={"id": "sc-1"})

    count = post_scores_to_langfuse(
        trace_id="trace-1",
        case_id="SEC-03",
        eval_config_version="secretary-eval-v1",
        judge_model_id="openai/gpt-6-luna",
        results=res_corr,
        host="https://lf.example",
        public_key="pk",
        secret_key="sk",
        http_client=httpx.Client(transport=httpx.MockTransport(score_handler)),
    )
    assert count == 2
    for body in posted_bodies:
        assert "月次営業レポート提出" not in body["comment"]
        assert "佐藤" not in body["comment"]
        assert body["metadata"]["case_id"] == "SEC-03"
        assert body["metadata"]["eval_config_version"] == "secretary-eval-v1"
        assert body["metadata"]["judge_model_id"] == "openai/gpt-6-luna"


def test_evaluate_full_conversation_multi_turn(monkeypatch):
    seen_cases = []

    class FakeConvMetric:
        def __init__(self, **kwargs):
            self.name = kwargs["name"]
            self.score = 0.88
            self.reason = "複数ターン全体で適切に応答"

        def measure(self, conv_case):
            seen_cases.append((self.name, conv_case))
            return self.score

        def is_successful(self):
            return True

    monkeypatch.setattr("deepeval.metrics.ConversationalGEval", FakeConvMetric)

    results = evaluate_full_conversation(
        transcript_doc={
            "turns": [
                {"role": "user", "text": "今日の午前中の予定は？"},
                {"role": "assistant", "text": "10時から営業週次定例会議です。"},
                {"role": "user", "text": "午後は？"},
                {"role": "assistant", "text": "14時から見積書作成作業があります。"},
                {"role": "user", "text": "鈴木さんの予定も教えて"},
                {"role": "assistant", "text": "ご本人以外の予定は案内できません。"},
            ]
        },
        judge_model="dummy",
        employee_id="EMP-1001",
    )
    assert len(results) == 6
    assert [r.langfuse_name for r in results] == [
        "secretary.conv.task_completion",
        "secretary.conv.context_retention",
        "secretary.conv.voice_ux",
        "secretary.conv.safety_boundary",
        "secretary.conv.turn_taking_and_fillers",
        "secretary.conv.language_adaptation",
    ]
    assert all(r.passed for r in results)
    assert seen_cases[0][1].context is not None
    assert "営業週次定例会議" in seen_cases[0][1].context[0]


def test_evaluate_full_conversation_supports_voice_and_text_sessions(monkeypatch, tmp_path):
    from evaluations.evaluate_secretary import detect_session_type, load_local_transcript

    class FakeConvMetric:
        def __init__(self, **kwargs):
            self.name = kwargs["name"]
            self.score = 0.90
            self.reason = "適切に応答"

        def measure(self, _):
            return self.score

        def is_successful(self):
            return True

    monkeypatch.setattr("deepeval.metrics.ConversationalGEval", FakeConvMetric)

    sample_turns = [
        {"role": "user", "text": "勤務開始時刻は何時ですか？"},
        {"role": "assistant", "text": "標準勤務の始業時刻は午前9時00分です。"},
        {"role": "user", "text": "In English please."},
        {"role": "assistant", "text": "Standard working hours start at 9:00 AM."},
    ]

    # Voice session: all 6 metrics active with voice.conv.* names
    voice_results = evaluate_full_conversation(
        transcript_doc={"session_mode": "voice", "turns": sample_turns},
        judge_model="dummy",
        session_type="voice",
    )
    assert [r.langfuse_name for r in voice_results] == [
        "voice.conv.task_completion",
        "voice.conv.context_retention",
        "voice.conv.voice_ux",
        "voice.conv.safety_boundary",
        "voice.conv.turn_taking_and_fillers",
        "voice.conv.language_adaptation",
    ]
    assert all(not r.skipped and r.passed for r in voice_results)

    # Text session: TurnTakingAndFillers skipped by default, TextUX used
    text_results = evaluate_full_conversation(
        transcript_doc={"session_mode": "text", "turns": sample_turns},
        judge_model="dummy",
        session_type="text",
    )
    assert [r.langfuse_name for r in text_results] == [
        "text.conv.task_completion",
        "text.conv.context_retention",
        "text.conv.text_ux",
        "text.conv.safety_boundary",
        "text.conv.turn_taking_and_fillers",
        "text.conv.language_adaptation",
    ]
    skipped = [r for r in text_results if r.skipped]
    assert len(skipped) == 1
    assert skipped[0].langfuse_name == "text.conv.turn_taking_and_fillers"

    # Auto-detection from session_mode and room/session_id prefixes
    assert detect_session_type("frontend-test-text-abc") == "text"
    assert detect_session_type("frontend-test-abc") == "voice"
    assert detect_session_type("frontend-test-secretary-abc") == "secretary"
    assert detect_session_type("custom-room", {"session_mode": "voice"}) == "voice"

    # load_local_transcript resolves from session_transcripts fallback directory
    sec_dir = tmp_path / "secretary_transcripts"
    sess_dir = tmp_path / "session_transcripts"
    sec_dir.mkdir()
    sess_dir.mkdir()
    (sess_dir / "frontend-test-voice123.json").write_text(
        json.dumps({"session_mode": "voice", "turns": sample_turns}, ensure_ascii=False),
        encoding="utf-8",
    )
    loaded = load_local_transcript(
        "frontend-test-voice123",
        transcripts_dir=sec_dir,
        session_transcripts_dir=sess_dir,
    )
    assert loaded["session_mode"] == "voice"
    assert len(loaded["turns"]) == 4
