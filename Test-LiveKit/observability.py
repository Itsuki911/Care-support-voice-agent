"""LiveKit session traces exported to Langfuse through OpenTelemetry.

This module deliberately exports operational metadata (latency, model usage,
tool status, and errors) without conversational or Gmail content. LiveKit
Cloud Agent Insights continues to receive its own trace stream.
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Any

from livekit.agents.telemetry import set_tracer_provider
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


logger = logging.getLogger("care-support-voice-agent.observability")


def _is_enabled() -> bool:
    """Return whether Langfuse exporting is explicitly enabled."""
    return os.getenv("LANGFUSE_TRACING_ENABLED", "true").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def setup_langfuse(session_id: str) -> TracerProvider | None:
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

    # Langfuse accepts OTLP/HTTP traces at this endpoint. The API key pair is
    # sent as HTTP Basic authentication, never written to logs or spans.
    basic_auth = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
    exporter = OTLPSpanExporter(
        endpoint=f"{base_url}/api/public/otel/v1/traces",
        headers={
            "Authorization": f"Basic {basic_auth}",
            # Enables Langfuse's real-time OpenTelemetry ingestion format.
            "x-langfuse-ingestion-version": "4",
        },
    )
    provider = TracerProvider()
    provider.add_span_processor(BatchSpanProcessor(exporter))

    metadata: dict[str, Any] = {
        "langfuse.session.id": session_id,
        "langfuse.environment": os.getenv("LANGFUSE_TRACING_ENVIRONMENT", "development"),
        "service.name": "care-support-voice-agent",
    }
    release = os.getenv("LANGFUSE_RELEASE", "").strip()
    if release:
        metadata["langfuse.release"] = release

    # This lets LiveKit attach its Agent Insights exporter as well. PII stripping
    # affects the third-party exporter: Gmail content, transcripts, and tool
    # arguments stay out of Langfuse while timing and usage data remain visible.
    set_tracer_provider(provider, metadata=metadata, allow_pii=False)
    logger.info("Langfuse trace exporter configured", extra={"session_id": session_id})
    return provider


def flush_traces(provider: TracerProvider) -> bool:
    """Send queued spans before a LiveKit session process exits."""
    return provider.force_flush()
