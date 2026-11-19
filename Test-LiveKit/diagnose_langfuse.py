"""Minimal live-connectivity diagnostic for Langfuse OTLP trace ingestion.

Run from Test-LiveKit:
    uv run python diagnose_langfuse.py
"""

from __future__ import annotations

import base64
import os
import sys
import uuid

from dotenv import load_dotenv
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExportResult


def main() -> int:
    load_dotenv(override=False)
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
    secret_key = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
    base_url = os.getenv("LANGFUSE_BASE_URL", "").strip().rstrip("/")
    if not all((public_key, secret_key, base_url)):
        print("ERROR: LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, or LANGFUSE_BASE_URL is missing.")
        return 1

    session_id = f"diagnose-{uuid.uuid4().hex[:8]}"
    endpoint = f"{base_url}/api/public/otel/v1/traces"
    basic_auth = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
    exporter = OTLPSpanExporter(
        endpoint=endpoint,
        headers={
            "Authorization": f"Basic {basic_auth}",
            "x-langfuse-ingestion-version": "4",
        },
    )

    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("care-support-voice-agent.diagnose")

    with tracer.start_as_current_span(
        "diagnose.session",
        attributes={"langfuse.session.id": session_id, "service.name": "care-support-voice-agent"},
    ) as parent:
        with tracer.start_as_current_span(
            "diagnose.child_generation",
            attributes={
                "langfuse.session.id": session_id,
                "gen_ai.request.model": "diagnose/mock",
                "gen_ai.usage.input_tokens": 10,
                "gen_ai.usage.output_tokens": 5,
            },
        ):
            pass
        parent.set_attribute("diagnose.status", "ok")

    flushed = provider.force_flush()
    provider.shutdown()
    print(f"Endpoint: {endpoint}")
    print(f"Session ID: {session_id}")
    print(f"Flush result: {flushed}")
    if not flushed:
        print("WARNING: force_flush() returned False. Check network/credentials/base URL.")
        return 2
    print("OK: Open Langfuse UI and filter by the Session ID above to verify trace visibility.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
