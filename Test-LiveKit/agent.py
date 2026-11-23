"""Small LiveKit Agents example that runs in a local terminal.

Run it in text mode:
    uv run agent.py console --text

Run it with the local microphone and speakers:
    uv run agent.py console
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

# .env に置いた API キーやモデル名を Python の環境変数として読み込む。
# API キーをソースコードへ直接書かないための基本的な安全対策。
from dotenv import load_dotenv
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, cli, inference
from livekit.plugins import openai

from approvals import ApprovalManager, register_approval_rpc
from evaluations.post_session_pipeline import spawn_post_session_pipeline
from gmail_tools import GmailTools
from memory.factory import MemoryRuntime, create_memory_runtime
from memory.models.memory import ConversationMessage
from memory.observability import MemoryTracer
from memory_tools import MemoryTools, format_recent_memories_for_prompt
from observability import _allow_pii, flush_traces, setup_langfuse
from prompt_config import load_prompt
from rag.factory import RAGRuntime, create_rag_runtime
from rag.livekit_adapter import RAGTools
from rag.observability import RAGTracer
from session_monitor import SessionMonitor
from database.config import MemorySettings
from database.connection import DatabaseManager
from secretary.repository import SecretaryRepository
from secretary.tools import SecretaryTools
from transcript_events import TranscriptEventTracker
from web_search_tools import WebSearchTools
from uuid import uuid4


logger = logging.getLogger("care-support-voice-agent")


if sys.platform == "win32":
    # psycopg 3 async requires SelectorEventLoop on Windows instead of ProactorEventLoop.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

try:
    # Pre-import psycopg adapters at module load so entrypoint() does not block the event loop.
    import psycopg.types.net  # noqa: F401
except ImportError:
    pass


# override=False により、OS 側で明示的に指定した環境変数を .env で上書きしない。
load_dotenv(override=False)


@dataclass(frozen=True)
class Settings:
    """ソースコードではなく環境変数で管理する実行時設定。"""

    openrouter_model: str
    stt_model: str | None
    tts_model: str | None
    tts_voice: str | None

    @classmethod
    def from_env(cls) -> "Settings":
        # LLM を使うテキストモードでも必須となる設定を先に検証する。
        # OpenRouter プラグインは OPENROUTER_API_KEY を自動的に参照する。
        names = ("OPENROUTER_API_KEY", "OPENROUTER_MODEL")
        missing = [name for name in names if not os.getenv(name)]
        if missing:
            raise RuntimeError(
                "Missing configuration: "
                + ", ".join(missing)
                + ". Copy .env.example to .env and set your model values."
            )

        # 音声モードでは「音声認識・音声合成・声」の三つが一組で必要。
        # 一部だけ指定すると構成が曖昧になるため、実行前に明確なエラーにする。
        # 三つとも空なら、テキスト専用コンソールとして利用できる。
        speech_names = ("STT_MODEL", "TTS_MODEL", "TTS_VOICE")
        configured_speech = [name for name in speech_names if os.getenv(name)]
        if configured_speech and len(configured_speech) != len(speech_names):
            raise RuntimeError(
                "Voice mode needs all of STT_MODEL, TTS_MODEL, and TTS_VOICE. "
                "Leave all three blank to use text-only console mode."
            )

        return cls(
            openrouter_model=os.environ["OPENROUTER_MODEL"],
            stt_model=os.getenv("STT_MODEL") or None,
            tts_model=os.getenv("TTS_MODEL") or None,
            tts_voice=os.getenv("TTS_VOICE") or None,
        )

    @property
    def voice_enabled(self) -> bool:
        # from_env() で三つの音声設定はまとめて検証済みなので、STT の有無だけで判定できる。
        return self.stt_model is not None


class TerminalAssistant(Agent):
    def __init__(
        self,
        approvals: ApprovalManager | None = None,
        prompt=None,
        *,
        instructions: str | None = None,
        gmail_tools: GmailTools | None = None,
        memory_tools: MemoryTools | None = None,
        rag_tools: RAGTools | None = None,
        web_search_tools: WebSearchTools | None = None,
        secretary_tools: SecretaryTools | None = None,
    ) -> None:
        if instructions is not None:
            prompt_text = instructions
        else:
            prompt = prompt or load_prompt()
            prompt_text = prompt.text
        if secretary_tools is not None:
            # TEST-Secretary mode strictly restricts tools to read-only schedule and task queries.
            tools = [secretary_tools.get_schedule, secretary_tools.get_tasks]
        else:
            gmail = gmail_tools or GmailTools(approvals=approvals)
            tools = [gmail.search_emails, gmail.read_email, gmail.send_email]
            if memory_tools is not None:
                tools.extend(
                    [
                        memory_tools.search_memories,
                        memory_tools.list_recent_memories,
                        memory_tools.save_memory,
                    ]
                )
            if rag_tools is not None:
                tools.append(rag_tools.search_documents)
            if web_search_tools is not None:
                tools.append(web_search_tools.search_web)
        super().__init__(
            tools=tools,
            instructions=prompt_text,
        )


def _init_memory_runtime(tracer: MemoryTracer | None = None) -> MemoryRuntime | None:
    """Create MemoryRuntime when DATABASE_URL is configured; degrade gracefully otherwise."""
    if os.getenv("MEMORY_ENABLED", "true").strip().lower() in {"0", "false", "no", "off"}:
        return None
    if not os.getenv("DATABASE_URL", "").strip():
        return None
    try:
        runtime = create_memory_runtime(tracer=tracer)
        runtime.worker.start()
        return runtime
    except Exception as exc:
        logger.warning("Memory runtime initialization skipped (continuing without memory): %s", exc)
        return None


def _init_rag_runtime(
    tracer: RAGTracer | None = None,
    *,
    memory_runtime: MemoryRuntime | None = None,
) -> RAGRuntime | None:
    """Create RAGRuntime when DATABASE_URL is configured; degrade gracefully otherwise."""
    if os.getenv("RAG_ENABLED", "true").strip().lower() in {"0", "false", "no", "off"}:
        return None
    if not os.getenv("DATABASE_URL", "").strip():
        return None
    try:
        return create_rag_runtime(
            db=memory_runtime.db if memory_runtime is not None else None,
            embedding_provider=(
                memory_runtime.embedding_provider if memory_runtime is not None else None
            ),
            tracer=tracer,
        )
    except Exception as exc:
        logger.warning("RAG runtime initialization skipped (continuing without RAG): %s", exc)
        return None


def _prompt_recent_memory_limit() -> int:
    raw = os.getenv("MEMORY_PROMPT_RECENT_LIMIT", "5").strip()
    try:
        value = int(raw)
    except ValueError:
        return 5
    return max(1, min(value, 5))


def _resolve_participant_user_id(room: object) -> str | None:
    participants = getattr(room, "remote_participants", None)
    if isinstance(participants, dict):
        values = participants.values()
    elif participants is not None:
        values = participants
    else:
        values = ()
    for participant in values:
        identity = getattr(participant, "identity", None)
        if isinstance(identity, str) and identity.strip() and not identity.startswith("agent-"):
            return identity.strip()
    return None


# AgentServer は LiveKit から届くジョブ（ルーム参加要求）を受け取るサーバー。
# console モードでも、同じエントリポイントをローカルの模擬ルームで実行する。
server = AgentServer()


@server.rtc_session()
async def entrypoint(ctx: JobContext) -> None:
    """LiveKit のルームまたはローカル console 用に、1 会話セッションを作る。"""
    settings = Settings.from_env()
    prompt = load_prompt()
    room_name = getattr(ctx.room, "name", "") or "console"
    is_text_session = room_name.startswith("frontend-test-text-")
    is_secretary_session = (
        room_name.startswith("frontend-test-secretary-")
        or os.getenv("AGENT_MODE", "").strip().lower() == "secretary"
    )
    use_voice = settings.voice_enabled and not is_text_session
    if is_secretary_session:
        session_mode = "secretary"
    elif is_text_session or not settings.voice_enabled:
        session_mode = "text"
    else:
        session_mode = "voice"
    # A new ID even for console restarts or a reused room prevents mixed sessions.
    session_id = f"{room_name}-{uuid4().hex}"
    transcript_tracker = TranscriptEventTracker(session_id=room_name)

    def _resolve_verified_employee_id() -> str | None:
        remote_participants = getattr(ctx.room, "remote_participants", None)
        if not isinstance(remote_participants, dict):
            return None
        for participant in remote_participants.values():
            identity = getattr(participant, "identity", None)
            if isinstance(identity, str) and identity.startswith("agent-"):
                continue
            raw_meta = getattr(participant, "metadata", None)
            if not isinstance(raw_meta, str) or not raw_meta.strip():
                continue
            try:
                parsed = json.loads(raw_meta)
            except ValueError:
                continue
            if (
                isinstance(parsed, dict)
                and parsed.get("secretary_verified") is True
                and isinstance(parsed.get("employee_id"), str)
                and parsed["employee_id"].strip()
            ):
                return parsed["employee_id"].strip()
        return None

    default_user_id = os.getenv("DEFAULT_MEMORY_USER_ID", "default-user").strip() or "default-user"
    if not ctx.is_fake_job() and hasattr(ctx, "connect") and callable(ctx.connect):
        try:
            await ctx.connect()
        except Exception:
            logger.debug("Pre-start ctx.connect() failed; deferring to session.start", exc_info=True)

    user_id_state = {"user_id": _resolve_participant_user_id(ctx.room) or default_user_id}
    trace_provider = setup_langfuse(
        session_id,
        user_id=user_id_state["user_id"],
        prompt_version=prompt.version,
        prompt_hash=prompt.digest,
    )
    allow_pii = _allow_pii()
    memory_tracer = MemoryTracer(trace_provider, allow_content=allow_pii)
    rag_tracer = RAGTracer(trace_provider, allow_content=allow_pii)
    memory_runtime = None if is_secretary_session else _init_memory_runtime(memory_tracer)
    rag_runtime = (
        None
        if is_secretary_session
        else _init_rag_runtime(rag_tracer, memory_runtime=memory_runtime)
    )
    secretary_db: DatabaseManager | None = None
    if is_secretary_session:
        try:
            secretary_db = DatabaseManager(MemorySettings.from_env().database_url)
        except Exception:
            logger.warning("Failed to initialize secretary DatabaseManager", exc_info=True)
    recorded_messages: list[ConversationMessage] = []
    confirmed_turns: list[dict[str, Any]] = []
    recorded_tool_results: list[dict[str, Any]] = []

    def _record_confirmed_turn(payload: dict[str, Any]) -> None:
        if payload.get("status") not in ("final", "interrupted"):
            return
        entry = {
            "seq": payload.get("seq"),
            "turn_id": payload.get("turn_id"),
            "utterance_id": payload.get("utterance_id"),
            "role": payload.get("speaker"),
            "text": payload.get("text", ""),
            "status": payload.get("status"),
            "timestamp": payload.get("timestamp"),
        }
        utt_id = entry.get("utterance_id")
        if utt_id:
            for idx, existing in enumerate(confirmed_turns):
                if existing.get("utterance_id") == utt_id:
                    confirmed_turns[idx] = entry
                    return
        confirmed_turns.append(entry)
    memory_committed = False

    def get_memory_user_id() -> str:
        resolved = _resolve_participant_user_id(ctx.room)
        if resolved:
            user_id_state["user_id"] = resolved
        return user_id_state["user_id"]

    async def load_initial_instructions() -> str:
        if is_secretary_session:
            sec_prompt_path = Path(__file__).resolve().parent / "prompts" / "secretary_v1.txt"
            return sec_prompt_path.read_text(encoding="utf-8").strip()
        if memory_runtime is None:
            return prompt.text
        recent_limit = _prompt_recent_memory_limit()
        uid = get_memory_user_id()
        with memory_tracer.span(
            "memory.prompt_injection",
            user_id=uid,
            limit=recent_limit,
        ) as span:
            try:
                recent = await asyncio.wait_for(
                    memory_runtime.service.list_memories(uid, limit=recent_limit),
                    timeout=3.0,
                )
                span.set(status="ok", injected_count=len(recent))
                span.set_output([m.content for m in recent])
            except Exception as exc:
                logger.warning("Failed to load recent memories at session start: %s", exc)
                span.set_error(exc)
                span.set(status="fallback", injected_count=0)
                recent = []
        return prompt.text + format_recent_memories_for_prompt(recent, max_items=recent_limit)

    def submit_conversation_to_memory(trigger: str) -> bool:
        nonlocal memory_committed
        if memory_committed or memory_runtime is None or not recorded_messages:
            return False
        memory_committed = True
        uid = get_memory_user_id()
        batch = [
            m.model_copy(update={"user_id": uid, "session_id": session_id})
            for m in recorded_messages
        ]
        with memory_tracer.span(
            "memory.end_session",
            trigger=trigger,
            user_id=uid,
            session_id=session_id,
            message_count=len(batch),
        ) as span:
            queued = memory_runtime.worker.enqueue_conversation(uid, session_id, batch)
            span.set(queued=queued)
        logger.info(
            "Memory ingestion triggered (%s): user_id=%s session_id=%s messages=%d queued=%s",
            trigger,
            uid,
            session_id,
            len(batch),
            queued,
        )
        return queued

    async def publish_json_data(payload: dict[str, object]) -> None:
        local_participant = getattr(ctx.room, "local_participant", None)
        if local_participant is None:
            return
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            await local_participant.publish_data(encoded, reliable=True)
        except Exception:
            logger.debug("Failed to publish data payload to room", exc_info=True)

    # OpenRouter は OpenAI 互換の Chat Completions API を提供している。
    # LiveKit の OpenAI プラグイン経由で接続するため、API キーは
    # OPENROUTER_API_KEY、モデル名は OPENROUTER_MODEL で切り替えられる。
    # prompt_cache_key を指定し、OpenAI (gpt-5.6+) では prompt_cache_breakpoints='auto' を活用する。
    llm_instance = openai.LLM.with_openrouter(
        model=settings.openrouter_model,
        prompt_cache_key=f"care-support:{prompt.version}",
    )
    if settings.openrouter_model.startswith("anthropic/"):
        opts = getattr(llm_instance, "_opts", None)
        extra_body = getattr(opts, "extra_body", None)
        if isinstance(extra_body, dict):
            extra_body.setdefault("cache_control", {"type": "ephemeral"})
    session_options = {
        "llm": llm_instance,
    }
    if use_voice:
        # 音声専用セッションのみ、STT（音声→文字）、TTS（文字→音声）、
        # VAD（発話の開始・終了を検出）をセッションへ追加する。
        # テキスト専用セッションでは音声入出力を一切有効化しない。
        session_options.update(
            stt=inference.STT(settings.stt_model),
            tts=inference.TTS(settings.tts_model, voice=settings.tts_voice),
            vad=inference.VAD(),
        )
    # AgentSession は、音声入出力・会話履歴・LLM 呼び出し・割り込み処理を統合する。
    session = AgentSession(**session_options)

    monitor = SessionMonitor(trace_provider, session_id, mode=session_mode)

    def emit_status(
        kind: str,
        status: str,
        execution_id: str,
        label: str,
        detail: str | None = None,
    ) -> None:
        status_event = transcript_tracker.make_status_event(
            kind=kind,
            status=status,
            execution_id=execution_id,
            label=label,
            detail=detail,
        )
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(publish_json_data(status_event))

    _TOOL_LABELS: dict[str, dict[str, str]] = {
        "search_web": {
            "pending": "Web 検索の承認待ち",
            "running": "Web を検索中…",
            "succeeded": "Web 検索完了",
            "failed": "Web 検索に失敗",
            "denied": "Web 検索が拒否されました",
            "expired": "Web 検索の承認が期限切れ",
            "cancelled": "Web 検索をキャンセル",
        },
        "search_emails": {
            "pending": "Gmail 検索の承認待ち",
            "running": "Gmail を検索中…",
            "succeeded": "Gmail 検索完了",
        },
        "read_email": {
            "pending": "メール取得の承認待ち",
            "running": "メール本文を取得中…",
            "succeeded": "メール取得完了",
        },
        "send_email": {
            "pending": "メール送信の承認待ち",
            "running": "メールを送信中…",
            "succeeded": "メール送信完了",
        },
    }

    def observe_tool_state(execution_id: str, tool: str, state: str) -> None:
        monitor.tool_state(execution_id, tool, state)
        kind = "web_search" if tool == "search_web" else "tool"
        label = _TOOL_LABELS.get(tool, {}).get(state, tool)
        emit_status(kind, state, execution_id, label)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if state == "pending":
            op = approvals.operations.get(execution_id)
            if op is not None:
                args = op.arguments
                if tool == "send_email":
                    target = str(args.get("recipient", ""))
                    body = str(args.get("body", ""))
                    preview = body[:120] + ("…" if len(body) > 120 else "")
                    summary = f"件名: {args.get('subject', '')}\n本文: {preview}"
                    reversible = False
                elif tool == "read_email":
                    target = f"メールID: {args.get('message_id', '')}"
                    summary = "指定メールの本文を取得（既読にはしません）"
                    reversible = True
                elif tool == "search_web":
                    target = "Web 検索（Tavily）"
                    summary = f"検索クエリ: {args.get('query', '')}（最大 {args.get('max_results', 5)} 件）"
                    reversible = True
                else:
                    target = "Gmail 受信トレイ検索"
                    summary = f"検索条件: {args.get('query', '')}（最大 {args.get('max_results', 5)} 件）"
                    reversible = True
                loop.create_task(
                    publish_json_data(
                        {
                            "type": "approval_request",
                            "execution_id": execution_id,
                            "session_id": room_name,
                            "tool_name": tool,
                            "target": target,
                            "summary": summary,
                            "reversible": reversible,
                            "expires_at": op.expires_at,
                            "status": state,
                        }
                    )
                )

    approvals = ApprovalManager(session_id, observer=observe_tool_state)

    if hasattr(ctx.room, "on"):
        async def handle_user_text_turn(user_text: str) -> None:
            if finalizing or finished:
                return
            try:
                interrupt_fn = getattr(session, "interrupt", None)
                if callable(interrupt_fn):
                    res = interrupt_fn()
                    if asyncio.iscoroutine(res) or isinstance(res, asyncio.Future):
                        await res
            except Exception:
                logger.debug("Interrupt before text reply skipped", exc_info=True)
            try:
                reply = session.generate_reply(user_input=user_text, input_modality="text")
                if asyncio.iscoroutine(reply) or isinstance(reply, asyncio.Future):
                    await reply
            except Exception:
                logger.warning("Failed to generate reply for text input", exc_info=True)

        def handle_data_received(packet: object) -> None:
            raw = getattr(packet, "data", None)
            if not raw:
                return
            try:
                data = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return
            if not isinstance(data, dict):
                return
            msg_type = data.get("type")
            if msg_type == "approval_response":
                execution_id = data.get("execution_id")
                approved = data.get("approved")
                if isinstance(execution_id, str) and isinstance(approved, bool):
                    try:
                        approvals.decide(session_id, execution_id, approved)
                    except Exception:
                        logger.warning("Ignored invalid approval response", exc_info=True)
            elif msg_type == "user_text_input":
                if not is_text_session:
                    logger.warning("Ignored user_text_input in voice-only session")
                    return
                text_value = data.get("text")
                if isinstance(text_value, str) and text_value.strip():
                    asyncio.create_task(handle_user_text_turn(text_value.strip()))
            elif msg_type == "end_session":
                submit_conversation_to_memory("end_session_button")

        ctx.room.on("data_received", handle_data_received)

        def handle_participant_connected(participant: object) -> None:
            identity = getattr(participant, "identity", None)
            if isinstance(identity, str) and identity.strip() and not identity.startswith("agent-"):
                user_id_state["user_id"] = identity.strip()

        ctx.room.on("participant_connected", handle_participant_connected)

    @session.on("agent_state_changed")
    def handle_agent_state_changed(event: object) -> None:
        old_state = str(getattr(event, "old_state", ""))
        new_state = str(getattr(event, "new_state", ""))
        turn_id = transcript_tracker._current_turn_id
        if old_state == "thinking" and new_state != "thinking":
            emit_status("thinking", "completed", f"think-{turn_id}", "思考完了")
        if old_state == "speaking" and new_state != "speaking":
            emit_status("speaking", "completed", f"speak-{turn_id}", "回答完了")
        if new_state == "thinking":
            emit_status("thinking", "running", f"think-{turn_id}", "文章を考え中…")
        elif new_state == "speaking":
            emit_status("speaking", "running", f"speak-{turn_id}", "回答中…")

    @session.on("function_tools_executed")
    def handle_tools_executed(event: object) -> None:
        calls = getattr(event, "function_calls", None) or []
        outputs = getattr(event, "function_call_outputs", None) or []
        for call, out in zip(calls, outputs, strict=False):
            tool_name = str(getattr(call, "name", "") or getattr(out, "name", "") or "")
            raw_args = getattr(call, "arguments", "")
            raw_output = getattr(out, "output", "")
            recorded_tool_results.append(
                {
                    "tool_name": tool_name,
                    "arguments": str(raw_args)[:400],
                    "output": str(raw_output)[:1200],
                    "is_error": bool(getattr(out, "is_error", False)),
                }
            )

    @session.on("user_input_transcribed")
    def handle_user_transcribed(event: object) -> None:
        payload = transcript_tracker.on_user_transcribed(
            transcript=str(getattr(event, "transcript", "")),
            is_final=bool(getattr(event, "is_final", False)),
            item_id=getattr(event, "item_id", None),
            timestamp=getattr(event, "created_at", None),
        )
        if payload is not None:
            _record_confirmed_turn(payload)
            asyncio.create_task(publish_json_data(payload))

    def handle_conversation_item(event: object) -> None:
        item = getattr(event, "item", None)
        if item is None:
            return
        role = str(getattr(item, "role", ""))
        if role not in {"user", "assistant"}:
            return
        text_content = getattr(item, "text_content", None)
        text = text_content() if callable(text_content) else str(text_content or "")
        if text.strip():
            recorded_messages.append(
                ConversationMessage(
                    user_id=get_memory_user_id(),
                    session_id=session_id,
                    role=role,
                    content=text.strip(),
                )
            )
        payload = transcript_tracker.on_conversation_item_added(
            role=role,
            text=text,
            item_id=getattr(item, "id", None),
            interrupted=bool(getattr(item, "interrupted", False)),
            timestamp=getattr(event, "created_at", None),
        )
        if payload is not None:
            _record_confirmed_turn(payload)
            asyncio.create_task(publish_json_data(payload))

    monitor.bind(session, on_conversation_item=handle_conversation_item)
    finalizing = False
    finished = False
    finish_lock = asyncio.Lock()
    finish_task = None

    async def finalize(reason="shutdown"):
        nonlocal finalizing, finished
        async with finish_lock:
            if finished:
                return
            finalizing = True
            approvals.close()
            try:
                # The SDK ends its root span AFTER the close event.
                await session.aclose()
                monitor.finish(session, reason)
            finally:
                saved_transcript_path: Path | None = None
                if confirmed_turns and not os.getenv("PYTEST_CURRENT_TEST"):
                    try:
                        folder_name = (
                            "secretary_transcripts"
                            if is_secretary_session
                            else "session_transcripts"
                        )
                        transcript_dir = (
                            Path(__file__).resolve().parent.parent
                            / "export"
                            / folder_name
                        )
                        transcript_dir.mkdir(parents=True, exist_ok=True)
                        transcript_doc = {
                            "session_id": session_id,
                            "room_name": room_name,
                            "session_mode": session_mode,
                            "user_id": get_memory_user_id(),
                            "employee_id": (
                                _resolve_verified_employee_id()
                                if is_secretary_session
                                else None
                            ),
                            "turns": confirmed_turns,
                            "tool_results": recorded_tool_results,
                        }
                        encoded_doc = json.dumps(transcript_doc, ensure_ascii=False, indent=2)
                        saved_transcript_path = transcript_dir / f"{session_id}.json"
                        saved_transcript_path.write_text(encoded_doc, encoding="utf-8")
                        if room_name != session_id:
                            (transcript_dir / f"{room_name}.json").write_text(
                                encoded_doc, encoding="utf-8"
                            )
                    except Exception:
                        logger.warning("Failed to save local session transcript", exc_info=True)
                if secretary_db is not None:
                    try:
                        await secretary_db.close()
                    except Exception:
                        logger.warning("Failed to close secretary DB cleanly", exc_info=True)
                if rag_runtime is not None:
                    try:
                        await rag_runtime.close()
                    except Exception:
                        logger.warning("Failed to close RAG runtime cleanly", exc_info=True)
                if memory_runtime is not None:
                    try:
                        await memory_runtime.close()
                    except Exception:
                        logger.warning("Failed to close memory runtime cleanly", exc_info=True)
                if trace_provider is not None:
                    await asyncio.to_thread(flush_traces, trace_provider)
                    await asyncio.to_thread(trace_provider.shutdown)
                auto_eval_enabled = os.getenv("AUTO_EVAL_ON_SESSION_END", "true").strip().lower() not in {
                    "0",
                    "false",
                    "no",
                    "off",
                }
                has_user_turn = any(t.get("role") == "user" and t.get("text") for t in confirmed_turns)
                has_asst_turn = any(t.get("role") == "assistant" and t.get("text") for t in confirmed_turns)
                if (
                    auto_eval_enabled
                    and saved_transcript_path is not None
                    and has_user_turn
                    and has_asst_turn
                    and not ctx.is_fake_job()
                    and not os.getenv("PYTEST_CURRENT_TEST")
                ):
                    try:
                        spawn_post_session_pipeline(session_id, saved_transcript_path)
                        logger.info("Spawned background post-session evaluation pipeline for %s", session_id)
                    except Exception:
                        logger.warning("Failed to spawn post-session evaluation pipeline", exc_info=True)
                finished = True

    @session.on("close")
    def closed(event):
        nonlocal finish_task
        approvals.close()
        if not finalizing:
            finish_task = asyncio.create_task(finalize(str(event.reason)))

    async def shutdown():
        if finish_task is not None:
            await finish_task
        await finalize()

    ctx.add_shutdown_callback(shutdown)
    try:
        initial_instructions = await load_initial_instructions()
        session_memory_tools = (
            MemoryTools(
                memory_runtime.service,
                get_memory_user_id,
                get_session_id=lambda: session_id,
                on_status=emit_status,
            )
            if memory_runtime is not None
            else None
        )
        rag_corpus_id = os.getenv("RAG_CORPUS_ID", "").strip() or None
        session_rag_tools = (
            RAGTools(rag_runtime.service, corpus_id=rag_corpus_id, on_status=emit_status)
            if rag_runtime is not None
            else None
        )
        session_web_search_tools = (
            WebSearchTools(
                approvals=None if ctx.is_fake_job() else approvals,
                tracer_provider=trace_provider,
            )
            if not is_secretary_session and os.getenv("TAVILY_API_KEY", "").strip()
            else None
        )
        session_secretary_tools = (
            SecretaryTools(
                SecretaryRepository(secretary_db),
                _resolve_verified_employee_id,
                on_status=emit_status,
            )
            if is_secretary_session and secretary_db is not None
            else None
        )
        start_kwargs: dict[str, object] = {
            "agent": TerminalAssistant(
                None if ctx.is_fake_job() else approvals,
                prompt,
                instructions=initial_instructions,
                memory_tools=session_memory_tools,
                rag_tools=session_rag_tools,
                web_search_tools=session_web_search_tools,
                secretary_tools=session_secretary_tools,
            ),
            "room": ctx.room,
        }
        if not ctx.is_fake_job():
            from livekit.agents.voice import room_io

            if is_text_session:
                start_kwargs["room_options"] = room_io.RoomOptions(
                    audio_input=False,
                    audio_output=False,
                    text_input=False,
                )
            else:
                start_kwargs["room_options"] = room_io.RoomOptions(
                    text_input=False,
                )
        await session.start(**start_kwargs)
        # Console mode has no authenticated browser caller, so external tools
        # remain unavailable there. Browser approval uses authenticated room RPC.
        if not ctx.is_fake_job():
            register_approval_rpc(ctx.room, approvals)
        await session.generate_reply(
            instructions="Greet the user in Japanese in at most three sentences and briefly offer help."
        )
    except BaseException:
        await finalize("error")
        raise


if __name__ == "__main__":
    # `lk agent console`、`lk agent dev`、`uv run agent.py console` などの
    # コマンドライン引数を LiveKit の CLI に渡して、サーバーを起動する。
    cli.run_app(server)
