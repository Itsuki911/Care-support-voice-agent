import asyncio
from unittest.mock import MagicMock

import pytest
from livekit.agents import ToolError

import gmail_tools as gmail
from approval import ApprovalError, ApprovalManager, ApprovalStatus
from observability import (
    bind_session_context,
    estimate_llm_cost,
    estimate_stt_cost,
    estimate_tts_cost,
    unbind_session_context,
)
from prompt_store import load_system_prompt


def test_load_system_prompt_returns_version_and_digest():
    spec = load_system_prompt("v1")
    assert spec.version == "v1"
    assert len(spec.sha256) == 12
    assert "最大3文" in spec.text


def test_load_system_prompt_rejects_invalid_version():
    with pytest.raises(ValueError):
        load_system_prompt("../secret")


def test_approval_rejects_missing_ui_and_never_executes():
    client = MagicMock()
    tools = gmail.GmailTools(client, require_approval=True)
    with pytest.raises(ToolError, match="承認UI"):
        asyncio.run(tools.send_email("a@example.com", "sub", "body"))
    client.send.assert_not_called()


def test_approval_flow_executes_once_on_approve_and_blocks_duplicate():
    now = [100.0]
    manager = ApprovalManager("room-1", default_ttl_seconds=30.0, clock=lambda: now[0])
    client = MagicMock()
    client.send.return_value = {"id": "m1", "thread_id": "t1", "status": "sent"}
    events = []

    async def on_request(req):
        events.append(req.to_payload())
        manager.resolve(req.execution_id, True)
        # Duplicate approval event must not re-open or re-trigger.
        manager.resolve(req.execution_id, True)

    tools = gmail.GmailTools(
        client,
        approval_manager=manager,
        on_approval_request=on_request,
        require_approval=True,
    )
    res = asyncio.run(tools.send_email("a@example.com", "sub", "body"))
    assert res["status"] == "sent"
    client.send.assert_called_once_with("a@example.com", "sub", "body")
    req_id = events[0]["execution_id"]
    assert manager.get(req_id).status == ApprovalStatus.EXECUTED

    with pytest.raises(ApprovalError, match="二重実行"):
        manager.begin_execution(req_id, {"recipient": "a@example.com", "subject": "sub", "body": "body"})


def test_approval_rejected_never_executes():
    manager = ApprovalManager("room-1")
    client = MagicMock()

    async def on_request(req):
        manager.resolve(req.execution_id, False)

    tools = gmail.GmailTools(
        client,
        approval_manager=manager,
        on_approval_request=on_request,
        require_approval=True,
    )
    with pytest.raises(ToolError, match="拒否"):
        asyncio.run(tools.search_emails("in:inbox"))
    client.search.assert_not_called()


def test_approval_expired_never_executes():
    now = [100.0]
    manager = ApprovalManager("room-1", default_ttl_seconds=10.0, clock=lambda: now[0])
    req = manager.create_request(
        tool_name="send_email",
        args={"recipient": "a@example.com", "subject": "s", "body": "b"},
        target="a@example.com",
        summary="s",
        reversible=False,
    )
    now[0] = 115.0
    resolved = manager.resolve(req.execution_id, True)
    assert resolved.status == ApprovalStatus.EXPIRED
    with pytest.raises(ApprovalError, match="有効期限"):
        manager.begin_execution(req.execution_id, {"recipient": "a@example.com", "subject": "s", "body": "b"})


def test_approval_blocks_modified_arguments():
    manager = ApprovalManager("room-1")
    req = manager.create_request(
        tool_name="send_email",
        args={"recipient": "a@example.com", "subject": "s", "body": "original"},
        target="a@example.com",
        summary="s",
        reversible=False,
    )
    manager.resolve(req.execution_id, True)
    with pytest.raises(ApprovalError, match="変更された"):
        manager.begin_execution(
            req.execution_id,
            {"recipient": "b@example.com", "subject": "s", "body": "original"},
        )


def test_approval_session_close_cancels_pending():
    manager = ApprovalManager("room-1")
    req = manager.create_request(
        tool_name="read_email",
        args={"message_id": "123"},
        target="123",
        summary="read",
        reversible=True,
    )
    manager.close_session()
    assert manager.get(req.execution_id).status == ApprovalStatus.EXPIRED
    with pytest.raises(ApprovalError, match="セッションが終了"):
        manager.begin_execution(req.execution_id, {"message_id": "123"})


def test_uncertain_gmail_error_marks_unknown_result_without_retry():
    manager = ApprovalManager("room-1")
    client = MagicMock()
    client.send.side_effect = gmail.GmailUncertainError("uncertain")
    captured = []

    async def on_request(req):
        captured.append(req.execution_id)
        manager.resolve(req.execution_id, True)

    tools = gmail.GmailTools(
        client,
        approval_manager=manager,
        on_approval_request=on_request,
        require_approval=True,
    )
    with pytest.raises(ToolError, match="uncertain"):
        asyncio.run(tools.send_email("a@example.com", "s", "b"))
    client.send.assert_called_once()
    assert manager.get(captured[0]).status == ApprovalStatus.UNKNOWN_RESULT


def test_cost_estimation_distinguishes_estimated_and_unavailable():
    known = estimate_llm_cost("openai/gpt-4o-mini", 1_000_000, 1_000_000)
    assert known.source == "estimated"
    assert known.amount_usd == pytest.approx(0.75)

    unknown = estimate_llm_cost("custom/unknown-model", 100, 100)
    assert unknown.source == "unavailable"
    assert unknown.amount_usd is None

    assert estimate_stt_cost("deepgram/nova-3", 60.0).source == "estimated"
    assert estimate_tts_cost("cartesia/sonic-3", 100).source == "estimated"


def test_session_context_isolation():
    from observability import _SESSION_ATTRS

    t1 = bind_session_context("sess-1", prompt_version="v1")
    try:
        assert _SESSION_ATTRS.get()["langfuse.session.id"] == "sess-1"
        t2 = bind_session_context("sess-2", prompt_version="v2")
        try:
            assert _SESSION_ATTRS.get()["langfuse.session.id"] == "sess-2"
            assert _SESSION_ATTRS.get()["prompt.version"] == "v2"
        finally:
            unbind_session_context(t2)
        assert _SESSION_ATTRS.get()["langfuse.session.id"] == "sess-1"
    finally:
        unbind_session_context(t1)
    assert _SESSION_ATTRS.get() is None
