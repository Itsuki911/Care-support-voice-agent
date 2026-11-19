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

from approval import ApprovalManager, ApprovalRequest
from gmail_tools import GmailTools
from observability import (
    flush_traces,
    record_tool_event,
    record_usage_metrics,
    setup_langfuse,
)
from prompt_store import load_system_prompt
from transcript_events import TranscriptEventTracker


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
        *,
        instructions: str | None = None,
        gmail_tools: GmailTools | None = None,
    ) -> None:
        # Agent は会話の人格・指示・ツールをまとめる LiveKit の基本単位。
        # 実際にどの LLM を使うかは下の AgentSession で注入する。
        prompt_text = instructions or load_system_prompt().text
        gmail = gmail_tools or GmailTools(require_approval=True)
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
    prompt_spec = load_system_prompt()
    approval_manager = ApprovalManager(session_id=ctx.room.name)
    transcript_tracker = TranscriptEventTracker(session_id=ctx.room.name)

    # Start tracing before the session so LiveKit's complete conversation trace
    # reaches Langfuse and LiveKit Agent Insights. Missing Langfuse settings only
    # disable the external exporter; they never prevent the agent from starting.
    trace_provider = setup_langfuse(
        ctx.room.name,
        prompt_version=prompt_spec.version,
        prompt_sha256=prompt_spec.sha256,
    )

    async def shutdown_session() -> None:
        approval_manager.close_session()
        if trace_provider is not None:
            await asyncio.to_thread(flush_traces, trace_provider)

    ctx.add_shutdown_callback(shutdown_session)

    async def publish_json_data(payload: dict[str, object]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            await ctx.room.local_participant.publish_data(encoded, reliable=True)
        except Exception:
            logger.debug("Failed to publish data payload to room", exc_info=True)

    async def publish_approval_request(req: ApprovalRequest) -> None:
        await publish_json_data(req.to_payload())

    def emit_tool_lifecycle(payload: dict[str, object]) -> None:
        record_tool_event(payload)
        status_event = transcript_tracker.make_status_event(
            kind="tool",
            status=str(payload.get("status", "")),
            execution_id=str(payload.get("execution_id", "")),
            label=str(payload.get("tool_name", "")),
        )
        asyncio.create_task(publish_json_data(status_event))

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
                approval_manager.resolve(execution_id, approved)
            except Exception:
                logger.warning("Ignored invalid approval response", exc_info=True)

    ctx.room.on("data_received", handle_data_received)

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
    session.on(
        "metrics_collected",
        lambda event: record_usage_metrics(
            getattr(event, "metrics", event),
            llm_model=settings.openrouter_model,
            stt_model=settings.stt_model or "",
            tts_model=settings.tts_model or "",
        ),
    )

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

    session.on("user_input_transcribed", handle_user_transcribed)
    session.on("conversation_item_added", handle_conversation_item)

    gmail_tools = GmailTools(
        approval_manager=approval_manager,
        on_approval_request=publish_approval_request,
        on_tool_event=emit_tool_lifecycle,
        require_approval=True,
    )
    assistant = TerminalAssistant(instructions=prompt_spec.text, gmail_tools=gmail_tools)

    # ルームにエージェントを参加させる。console モードではローカルの模擬ルームへ参加する。
    await session.start(agent=assistant, room=ctx.room)
    # 接続直後に一度だけ挨拶を生成する。ここから OpenRouter への LLM 呼び出しが発生する。
    await session.generate_reply(
        instructions="Greet the user in Japanese and briefly offer your help."
    )


if __name__ == "__main__":
    # `lk agent console`、`lk agent dev`、`uv run agent.py console` などの
    # コマンドライン引数を LiveKit の CLI に渡して、サーバーを起動する。
    cli.run_app(server)
