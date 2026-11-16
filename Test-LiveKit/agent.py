"""Small LiveKit Agents example that runs in a local terminal.

Run it in text mode:
    uv run agent.py console --text

Run it with the local microphone and speakers:
    uv run agent.py console
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, cli, inference
from livekit.plugins import openai


load_dotenv(override=False)


@dataclass(frozen=True)
class Settings:
    """Configuration deliberately kept in environment variables, not source code."""

    openrouter_model: str
    stt_model: str | None
    tts_model: str | None
    tts_voice: str | None

    @classmethod
    def from_env(cls) -> "Settings":
        names = ("OPENROUTER_API_KEY", "OPENROUTER_MODEL")
        missing = [name for name in names if not os.getenv(name)]
        if missing:
            raise RuntimeError(
                "Missing configuration: "
                + ", ".join(missing)
                + ". Copy .env.example to .env and set your model values."
            )

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
        return self.stt_model is not None


class TerminalAssistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=(
                "You are a concise and friendly Japanese voice assistant. "
                "Answer the user naturally and helpfully."
            )
        )


server = AgentServer()


@server.rtc_session()
async def entrypoint(ctx: JobContext) -> None:
    """Create one realtime voice session for a LiveKit room or local console."""
    settings = Settings.from_env()

    # The LLM is sent to OpenRouter. Add speech components only when all voice
    # settings are configured, so `lk agent console --text` works with an LLM alone.
    session_options = {
        "llm": openai.LLM.with_openrouter(model=settings.openrouter_model),
    }
    if settings.voice_enabled:
        session_options.update(
            stt=inference.STT(settings.stt_model),
            tts=inference.TTS(settings.tts_model, voice=settings.tts_voice),
            vad=inference.VAD(),
        )
    session = AgentSession(**session_options)

    await session.start(agent=TerminalAssistant(), room=ctx.room)
    await session.generate_reply(
        instructions="Greet the user in Japanese and briefly offer your help."
    )


if __name__ == "__main__":
    cli.run_app(server)
