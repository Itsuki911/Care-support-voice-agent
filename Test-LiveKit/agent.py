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
from dataclasses import dataclass

# .env に置いた API キーやモデル名を Python の環境変数として読み込む。
# API キーをソースコードへ直接書かないための基本的な安全対策。
from dotenv import load_dotenv
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, cli, inference
from livekit.plugins import openai

from approvals import ApprovalManager, register_approval_rpc
from gmail_tools import GmailTools
from observability import flush_traces, setup_langfuse
from prompt_config import load_prompt
from session_monitor import SessionMonitor
from transcript_events import TranscriptEventTracker
from uuid import uuid4


logger = logging.getLogger("care-support-voice-agent")


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
    ) -> None:
        gmail = gmail_tools or GmailTools(approvals=approvals)
        if instructions is not None:
            prompt_text = instructions
        else:
            prompt = prompt or load_prompt()
            prompt_text = prompt.text
        super().__init__(
            tools=[gmail.search_emails, gmail.read_email, gmail.send_email],
            instructions=prompt_text,
        )


# AgentServer は LiveKit から届くジョブ（ルーム参加要求）を受け取るサーバー。
# console モードでも、同じエントリポイントをローカルの模擬ルームで実行する。
server = AgentServer()


@server.rtc_session()
async def entrypoint(ctx: JobContext) -> None:
    """LiveKit のルームまたはローカル console 用に、1 会話セッションを作る。"""
    settings = Settings.from_env()
    prompt = load_prompt()
    room_name = getattr(ctx.room, "name", "") or "console"
    # A new ID even for console restarts or a reused room prevents mixed sessions.
    session_id = f"{room_name}-{uuid4().hex}"
    transcript_tracker = TranscriptEventTracker(session_id=room_name)

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
    session_options = {
        "llm": openai.LLM.with_openrouter(model=settings.openrouter_model),
    }
    if settings.voice_enabled:
        # 音声モードだけ、STT（音声→文字）、TTS（文字→音声）、
        # VAD（発話の開始・終了を検出）をセッションへ追加する。
        # これらは LiveKit Inference を利用し、モデル ID は .env から渡す。
        session_options.update(
            stt=inference.STT(settings.stt_model),
            tts=inference.TTS(settings.tts_model, voice=settings.tts_voice),
            vad=inference.VAD(),
        )
    # AgentSession は、音声入出力・会話履歴・LLM 呼び出し・割り込み処理を統合する。
    session = AgentSession(**session_options)

    trace_provider = setup_langfuse(
        session_id, prompt_version=prompt.version, prompt_hash=prompt.digest
    )
    monitor = SessionMonitor(trace_provider, session_id)

    def observe_tool_state(execution_id: str, tool: str, state: str) -> None:
        monitor.tool_state(execution_id, tool, state)
        status_event = transcript_tracker.make_status_event(
            kind="tool",
            status=state,
            execution_id=execution_id,
            label=tool,
        )
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(publish_json_data(status_event))
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
        def handle_data_received(packet: object) -> None:
            raw = getattr(packet, "data", None)
            if not raw:
                return
            try:
                data = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return
            if not isinstance(data, dict) or data.get("type") != "approval_response":
                return
            execution_id = data.get("execution_id")
            approved = data.get("approved")
            if isinstance(execution_id, str) and isinstance(approved, bool):
                try:
                    approvals.decide(session_id, execution_id, approved)
                except Exception:
                    logger.warning("Ignored invalid approval response", exc_info=True)

        ctx.room.on("data_received", handle_data_received)

    @session.on("user_input_transcribed")
    def handle_user_transcribed(event: object) -> None:
        payload = transcript_tracker.on_user_transcribed(
            transcript=str(getattr(event, "transcript", "")),
            is_final=bool(getattr(event, "is_final", False)),
            item_id=getattr(event, "item_id", None),
            timestamp=getattr(event, "created_at", None),
        )
        if payload is not None:
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
        payload = transcript_tracker.on_conversation_item_added(
            role=role,
            text=text,
            item_id=getattr(item, "id", None),
            interrupted=bool(getattr(item, "interrupted", False)),
            timestamp=getattr(event, "created_at", None),
        )
        if payload is not None:
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
                if trace_provider is not None:
                    await asyncio.to_thread(flush_traces, trace_provider)
                    await asyncio.to_thread(trace_provider.shutdown)
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
        await session.start(
            agent=TerminalAssistant(None if ctx.is_fake_job() else approvals, prompt),
            room=ctx.room,
        )
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
