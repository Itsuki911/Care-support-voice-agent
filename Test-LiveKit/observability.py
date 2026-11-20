"""LiveKit session traces exported to Langfuse through OpenTelemetry.

This module deliberately exports operational metadata (latency, model usage,
estimated cost, tool lifecycle status, and errors) without conversational or
Gmail content. LiveKit Cloud Agent Insights continues to receive its own stream.
"""

from __future__ import annotations

import base64
import contextvars
import logging
import os
import threading
from dataclasses import dataclass
from typing import Any

from livekit.agents.telemetry import set_tracer_provider
from opentelemetry import trace as trace_api
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import Span, SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from trace_export import ReportingExporter, load_prices


_SDK_TRACER_PROVIDER = TracerProvider
logger = logging.getLogger("care-support-voice-agent.observability")

_SESSION_ATTRS: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "langfuse_session_attrs", default=None
)
_PROVIDER_LOCK = threading.Lock()
_SHARED_PROVIDER: TracerProvider | None = None


@dataclass(frozen=True)
class CostEstimate:
    """Distinguishes measured, estimated, and unavailable cost values."""

    amount_usd: float | None
    source: str  # "measured" | "estimated" | "unavailable"


# Fallback per-unit estimates (USD). Actual invoices should be reconciled with providers.
_LLM_UNIT_COST_PER_1M: dict[str, tuple[float, float]] = {
    "openai/gpt-4o-mini": (0.15, 0.60),
    "openai/gpt-4.1-mini": (0.40, 1.60),
    "google/gemini-2.5-flash": (0.15, 0.60),
    "anthropic/claude-sonnet-4.5": (3.00, 15.00),
}
_STT_COST_PER_SECOND: dict[str, float] = {
    "deepgram/nova-3": 0.0043 / 60.0,
}
_TTS_COST_PER_CHAR: dict[str, float] = {
    "cartesia/sonic-3": 0.00004,
}


def estimate_llm_cost(model: str, input_tokens: int, output_tokens: int) -> CostEstimate:
    rates = _LLM_UNIT_COST_PER_1M.get(model)
    if rates is None:
        return CostEstimate(amount_usd=None, source="unavailable")
    in_rate, out_rate = rates
    cost = (max(0, input_tokens) * in_rate + max(0, output_tokens) * out_rate) / 1_000_000.0
    return CostEstimate(amount_usd=round(cost, 8), source="estimated")


def estimate_stt_cost(model: str, audio_seconds: float) -> CostEstimate:
    rate = _STT_COST_PER_SECOND.get(model)
    if rate is None:
        return CostEstimate(amount_usd=None, source="unavailable")
    return CostEstimate(amount_usd=round(max(0.0, audio_seconds) * rate, 8), source="estimated")


def estimate_tts_cost(model: str, characters_count: int) -> CostEstimate:
    rate = _TTS_COST_PER_CHAR.get(model)
    if rate is None:
        return CostEstimate(amount_usd=None, source="unavailable")
    return CostEstimate(amount_usd=round(max(0, characters_count) * rate, 8), source="estimated")


class _SessionContextSpanProcessor(SpanProcessor):
    """Stamps per-session attributes from ContextVar on every span without cross-session leakage."""

    def on_start(self, span: Span, parent_context: Any = None) -> None:
        attrs = _SESSION_ATTRS.get()
        if attrs:
            span.set_attributes(attrs)


def bind_session_context(
    session_id: str,
    *,
    user_id: str | None = None,
    prompt_version: str | None = None,
    prompt_sha256: str | None = None,
) -> contextvars.Token[dict[str, Any] | None]:
    """Bind session-scoped attributes to the current async context."""
    attrs: dict[str, Any] = {"langfuse.session.id": session_id}
    if user_id:
        attrs["langfuse.user.id"] = user_id
    if prompt_version:
        attrs["prompt.version"] = prompt_version
    if prompt_sha256:
        attrs["prompt.sha256"] = prompt_sha256
    return _SESSION_ATTRS.set(attrs)


def unbind_session_context(token: contextvars.Token[dict[str, Any] | None]) -> None:
    _SESSION_ATTRS.reset(token)


def _allow_pii() -> bool:
    """Return whether conversational/tool payloads may be exported to Langfuse."""
    return os.getenv("LANGFUSE_ALLOW_PII", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _is_enabled() -> bool:
    """Return whether Langfuse exporting is explicitly enabled."""
    return os.getenv("LANGFUSE_TRACING_ENABLED", "true").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def setup_langfuse(
    session_id: str,
    *,
    user_id: str | None = None,
    prompt_version: str | None = "",
    prompt_hash: str | None = "",
    prompt_sha256: str | None = None,
) -> TracerProvider | None:
    """Configure a Langfuse OTLP exporter for one LiveKit agent session.

    Missing Langfuse configuration never prevents the voice agent from running.
    Set ``LANGFUSE_TRACING_ENABLED=false`` to intentionally disable exporting.
    """
    if not _is_enabled():
        logger.info("Langfuse tracing is disabled by configuration")
        return None

    public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
    secret_key = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
    base_url = os.getenv("LANGFUSE_BASE_URL", "").strip().rstrip("/")
    if not all((public_key, secret_key, base_url)):
        logger.warning(
            "Langfuse tracing is disabled because LANGFUSE_PUBLIC_KEY, "
            "LANGFUSE_SECRET_KEY, or LANGFUSE_BASE_URL is missing"
        )
        return None

    resolved_sha = prompt_sha256 or prompt_hash or None
    bind_session_context(
        session_id,
        user_id=user_id,
        prompt_version=prompt_version or None,
        prompt_sha256=resolved_sha,
    )

    basic_auth = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
    otlp_exporter = OTLPSpanExporter(
        endpoint=f"{base_url}/api/public/otel/v1/traces",
        headers={
            "Authorization": f"Basic {basic_auth}",
            "x-langfuse-ingestion-version": "4",
        },
    )
    exporter = ReportingExporter(otlp_exporter, load_prices())
    provider = TracerProvider()
    provider.export_diagnostics = exporter
    provider.add_span_processor(BatchSpanProcessor(exporter))
    if isinstance(provider, _SDK_TRACER_PROVIDER):
        provider.add_span_processor(_SessionContextSpanProcessor())

    metadata: dict[str, Any] = {
        "langfuse.session.id": session_id,
        "langfuse.environment": os.getenv("LANGFUSE_TRACING_ENVIRONMENT", "development"),
        "service.name": "care-support-voice-agent",
    }
    if prompt_version:
        metadata["langfuse.observation.metadata.prompt_version"] = prompt_version
        if prompt_hash or prompt_sha256:
            metadata["langfuse.observation.metadata.prompt_hash"] = prompt_hash or prompt_sha256
    metadata["langfuse.user.id"] = user_id or os.getenv("LOCAL_USER_ID", "local-user")
    metadata["langfuse.observation.metadata.content_policy"] = "redacted"
    release = os.getenv("LANGFUSE_RELEASE", "").strip()
    if release:
        metadata["langfuse.release"] = release

    set_tracer_provider(provider, metadata=metadata, allow_pii=_allow_pii())
    logger.info("Langfuse trace exporter configured", extra={"session_id": session_id})
    return provider


def record_usage_metrics(
    metrics: Any,
    *,
    llm_model: str = "",
    stt_model: str = "",
    tts_model: str = "",
) -> None:
    """Emit an operational span recording LLM/STT/TTS usage, latency, and cost source."""
    tracer = trace_api.get_tracer("care-support-voice-agent.metrics")
    metric_type = type(metrics).__name__
    attrs: dict[str, Any] = {"metric.type": metric_type}

    if hasattr(metrics, "prompt_tokens") and hasattr(metrics, "completion_tokens"):
        in_tok = int(getattr(metrics, "prompt_tokens", 0) or 0)
        out_tok = int(getattr(metrics, "completion_tokens", 0) or 0)
        cost = estimate_llm_cost(llm_model, in_tok, out_tok)
        attrs.update(
            {
                "gen_ai.request.model": llm_model,
                "gen_ai.usage.input_tokens": in_tok,
                "gen_ai.usage.output_tokens": out_tok,
                "gen_ai.usage.total_tokens": int(getattr(metrics, "total_tokens", in_tok + out_tok) or 0),
                "latency.ttft_seconds": float(getattr(metrics, "ttft", 0.0) or 0.0),
                "latency.duration_seconds": float(getattr(metrics, "duration", 0.0) or 0.0),
                "cost.category": "llm",
                "cost.source": cost.source,
            }
        )
        if cost.amount_usd is not None:
            attrs["cost.amount_usd"] = cost.amount_usd
    elif hasattr(metrics, "audio_duration") and not hasattr(metrics, "characters_count"):
        dur = float(getattr(metrics, "audio_duration", 0.0) or 0.0)
        cost = estimate_stt_cost(stt_model, dur)
        attrs.update(
            {
                "stt.model": stt_model,
                "stt.audio_duration_seconds": dur,
                "latency.duration_seconds": float(getattr(metrics, "duration", 0.0) or 0.0),
                "cost.category": "stt",
                "cost.source": cost.source,
            }
        )
        if cost.amount_usd is not None:
            attrs["cost.amount_usd"] = cost.amount_usd
    elif hasattr(metrics, "characters_count"):
        chars = int(getattr(metrics, "characters_count", 0) or 0)
        cost = estimate_tts_cost(tts_model, chars)
        attrs.update(
            {
                "tts.model": tts_model,
                "tts.characters_count": chars,
                "latency.ttfb_seconds": float(getattr(metrics, "ttfb", 0.0) or 0.0),
                "latency.duration_seconds": float(getattr(metrics, "duration", 0.0) or 0.0),
                "cost.category": "tts",
                "cost.source": cost.source,
            }
        )
        if cost.amount_usd is not None:
            attrs["cost.amount_usd"] = cost.amount_usd
    elif hasattr(metrics, "end_of_utterance_delay"):
        attrs.update(
            {
                "turn.end_of_utterance_delay_seconds": float(
                    getattr(metrics, "end_of_utterance_delay", 0.0) or 0.0
                ),
                "turn.transcription_delay_seconds": float(
                    getattr(metrics, "transcription_delay", 0.0) or 0.0
                ),
            }
        )

    with tracer.start_as_current_span(f"agent.metrics.{metric_type}", attributes=attrs):
        pass


def record_tool_event(payload: dict[str, Any]) -> None:
    """Emit an operational span for tool lifecycle states without PII payloads."""
    tracer = trace_api.get_tracer("care-support-voice-agent.tools")
    attrs = {
        "tool.name": str(payload.get("tool_name", "")),
        "tool.execution_id": str(payload.get("execution_id", "")),
        "tool.status": str(payload.get("status", "")),
    }
    with tracer.start_as_current_span("agent.tool.lifecycle", attributes=attrs):
        pass


def flush_traces(provider: TracerProvider) -> bool:
    """Send queued spans before a LiveKit session process exits."""
    try:
        result = provider.force_flush()
        if not result:
            logger.warning("Langfuse trace flush returned False")
        return result
    except Exception:
        logger.exception("Langfuse trace flush failed")
        return False
