"""Unit tests for LiveKit MemoryTools, prompt injection, and end_session ingestion."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import agent
from memory.models.memory import MemoryRecord, MemorySearchResult, MemoryType
from memory_tools import MemoryTools, format_recent_memories_for_prompt


def _make_record(content: str, *, memory_type: MemoryType = MemoryType.HABIT) -> MemoryRecord:
    now = datetime.now(timezone.utc)
    return MemoryRecord(
        id=uuid.uuid4(),
        user_id="user-1",
        content=content,
        memory_type=memory_type,
        importance=0.8,
        confidence=0.9,
        embedding_model="embeddinggemma-2:270m",
        embedding_dimension=768,
        source_session_id="sess-0",
        created_at=now,
        updated_at=now,
    )


def test_format_recent_memories_respects_max_items_and_rules():
    records = [_make_record(f"記憶 {i}") for i in range(1, 8)]
    prompt_section = format_recent_memories_for_prompt(records, max_items=5)
    assert "直近のユーザー記憶" in prompt_section
    assert "明示的な指示があった場合のみ" in prompt_section
    assert "save_memory" in prompt_section
    assert "自動で長期メモリへ抽出・保存" in prompt_section
    assert "記憶 1" in prompt_section
    assert "記憶 5" in prompt_section
    assert "記憶 6" not in prompt_section


def test_memory_tools_search_and_list_scoped_to_user_id():
    async def scenario():
        now = datetime.now(timezone.utc)
        service = SimpleNamespace(
            search_memory=AsyncMock(
                return_value=[
                    MemorySearchResult(
                        memory_id=uuid.uuid4(),
                        content="毎朝6時に散歩する",
                        memory_type=MemoryType.HABIT,
                        similarity_score=0.91234,
                        importance=0.8,
                        confidence=0.9,
                        source_session_id="sess-1",
                        created_at=now,
                        updated_at=now,
                    )
                ]
            ),
            list_memories=AsyncMock(return_value=[_make_record("緑茶が好き", memory_type=MemoryType.PREFERENCE)]),
        )
        tools = MemoryTools(service, lambda: "taro-01")

        res = await tools.search_memories(query="朝の習慣", limit=3)
        assert res["ok"] is True
        assert res["count"] == 1
        assert res["memories"][0]["content"] == "毎朝6時に散歩する"
        service.search_memory.assert_awaited_once_with("taro-01", "朝の習慣", limit=3)

        listed = await tools.list_recent_memories(limit=5)
        assert listed["ok"] is True
        assert listed["count"] == 1
        assert listed["memories"][0]["content"] == "緑茶が好き"
        service.list_memories.assert_awaited_once_with("taro-01", limit=5)

    asyncio.run(scenario())


def test_memory_tools_graceful_fallback_on_db_error():
    async def scenario():
        service = SimpleNamespace(
            search_memory=AsyncMock(side_effect=RuntimeError("db down")),
            list_memories=AsyncMock(side_effect=RuntimeError("db down")),
        )
        tools = MemoryTools(service, lambda: "taro-01")

        res = await tools.search_memories(query="趣味")
        assert res["ok"] is False
        assert res["memories"] == []

        listed = await tools.list_recent_memories()
        assert listed["ok"] is False
        assert listed["memories"] == []

    asyncio.run(scenario())


def test_agent_entrypoint_injects_recent_memories_and_commits_only_on_end_session(monkeypatch):
    created_sessions = []

    class FakeSession:
        def __init__(self, **_):
            self.handlers = {}
            self.history = SimpleNamespace(items=[])
            self.start_kwargs = None
            created_sessions.append(self)

        def on(self, name):
            def decorator(f):
                self.handlers[name] = f
                return f

            return decorator

        async def start(self, **kwargs):
            self.start_kwargs = kwargs

        async def generate_reply(self, **_):
            pass

        async def aclose(self):
            if "close" in self.handlers:
                self.handlers["close"](SimpleNamespace(reason="closed"))

    class FakeRoom:
        def __init__(self, name, user_id):
            self.name = name
            self.events = {}
            self.remote_participants = {"p1": SimpleNamespace(identity=user_id)}

        def on(self, name, cb=None):
            if cb is not None:
                self.events[name] = cb
                return cb

            def decorator(f):
                self.events[name] = f
                return f

            return decorator

    recent = [_make_record("毎朝6時に散歩する"), _make_record("緑茶が好き", memory_type=MemoryType.PREFERENCE)]
    enqueued = []
    closed_count = {"n": 0}

    fake_service = SimpleNamespace(
        list_memories=AsyncMock(return_value=recent),
        search_memory=AsyncMock(return_value=[]),
    )
    fake_worker = SimpleNamespace(
        enqueue_conversation=MagicMock(
            side_effect=lambda uid, sid, msgs: enqueued.append((uid, sid, msgs)) or True
        ),
        drain=AsyncMock(return_value=None),
        completed_results=[],
    )

    async def fake_close():
        closed_count["n"] += 1

    fake_runtime = SimpleNamespace(
        service=fake_service,
        worker=fake_worker,
        close=fake_close,
    )

    monkeypatch.setattr(agent, "_init_memory_runtime", lambda *_, **__: fake_runtime)
    monkeypatch.setattr(agent, "setup_langfuse", lambda *a, **kw: None)
    monkeypatch.setattr(agent, "AgentSession", FakeSession)
    monkeypatch.setattr(agent.openai.LLM, "with_openrouter", lambda **_: "llm")
    monkeypatch.setattr(agent, "register_approval_rpc", lambda *_: None)
    monkeypatch.setattr(
        agent.Settings,
        "from_env",
        lambda: SimpleNamespace(openrouter_model="test-model", voice_enabled=False),
    )

    async def scenario():
        # Case 1: User presses End Conversation button -> end_session triggers ingestion once
        room = FakeRoom("frontend-test-text-mem1", "hanako-01")
        callbacks = []
        ctx = SimpleNamespace(
            room=room,
            add_shutdown_callback=callbacks.append,
            is_fake_job=lambda: False,
        )
        await agent.entrypoint(ctx)
        sess = created_sessions[-1]
        started_agent = sess.start_kwargs["agent"]

        assert "毎朝6時に散歩する" in started_agent.instructions
        assert "緑茶が好き" in started_agent.instructions
        assert "明示的な指示があった場合のみ" in started_agent.instructions

        # Simulate conversation turns
        conv_handler = sess.handlers["conversation_item_added"]
        conv_handler(SimpleNamespace(item=SimpleNamespace(role="user", text_content="最近は毎朝ヨガもしています", id="u1", interrupted=False), created_at=1.0))
        conv_handler(SimpleNamespace(item=SimpleNamespace(role="assistant", text_content="素敵ですね！", id="a1", interrupted=False), created_at=2.0))

        # Press end conversation button (even if sent twice, only commits once)
        room.events["data_received"](SimpleNamespace(data=b'{"type":"end_session"}'))
        room.events["data_received"](SimpleNamespace(data=b'{"type":"end_session"}'))

        assert len(enqueued) == 1
        uid, sid, msgs = enqueued[0]
        assert uid == "hanako-01"
        assert sid.startswith("frontend-test-text-mem1-")
        assert len(msgs) == 2
        assert msgs[0].content == "最近は毎朝ヨガもしています"
        await callbacks[0]()
        assert closed_count["n"] == 1

        # Case 2: Disconnect without pressing end button -> no ingestion
        enqueued.clear()
        room2 = FakeRoom("frontend-test-text-mem2", "hanako-01")
        callbacks2 = []
        ctx2 = SimpleNamespace(
            room=room2,
            add_shutdown_callback=callbacks2.append,
            is_fake_job=lambda: False,
        )
        await agent.entrypoint(ctx2)
        sess2 = created_sessions[-1]
        sess2.handlers["conversation_item_added"](
            SimpleNamespace(item=SimpleNamespace(role="user", text_content="途中で切断", id="u2", interrupted=False), created_at=3.0)
        )
        await callbacks2[0]()
        assert enqueued == []

    asyncio.run(scenario())


def test_memory_tools_save_memory_and_fallback():
    async def scenario():
        saved_record = _make_record("コーヒーはブラックが好き", memory_type=MemoryType.PREFERENCE)
        service = SimpleNamespace(add_memory=AsyncMock(return_value=saved_record))
        tools = MemoryTools(service, lambda: "taro-01", get_session_id=lambda: "sess-xyz")

        res = await tools.save_memory(content="コーヒーはブラックが好き", memory_type="preference", importance=0.9)
        assert res["ok"] is True
        assert res["content"] == "コーヒーはブラックが好き"
        assert res["memory_type"] == "preference"
        created_arg = service.add_memory.await_args.args[0]
        assert created_arg.user_id == "taro-01"
        assert created_arg.source_session_id == "sess-xyz"
        assert created_arg.importance == 0.9

        blank = await tools.save_memory(content="   ")
        assert blank["ok"] is False

        failing_service = SimpleNamespace(add_memory=AsyncMock(side_effect=RuntimeError("db down")))
        failing_tools = MemoryTools(failing_service, lambda: "taro-01")
        err = await failing_tools.save_memory(content="メモ")
        assert err["ok"] is False

    asyncio.run(scenario())
