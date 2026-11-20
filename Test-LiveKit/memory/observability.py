"""Vendor-neutral tracing helpers for the Agent Memory system.

Uses only the OpenTelemetry API so the same spans can be exported to Langfuse
(today) or GCP Cloud Trace (future) without changing memory components.

- When no tracer provider is configured, every call is a cheap no-op.
- Conversational content (queries, memory text, LLM prompts/outputs) is attached
  only when ``allow_content`` is True (mirrors ``LANGFUSE_ALLOW_PII``).
- Tracing failures never propagate into memory operations.
"""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from typing import Any, Iterator

logger = logging.getLogger("care-support-voice-agent.memory.tracing")

_METADATA_PREFIX = "langfuse.observation.metadata."
_MAX_CONTENT_CHARS = 8000


def _to_attr_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)) and all(isinstance(v, (bool, int, float, str)) for v in value):
        return list(value)
    return str(value)


def _dump_content(value: Any) -> str:
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            text = str(value)
    if len(text) > _MAX_CONTENT_CHARS:
        return text[:_MAX_CONTENT_CHARS] + "…(truncated)"
    return text


class MemorySpan:
    """Thin, failure-safe handle around an OpenTelemetry span."""

    def __init__(self, span: Any | None, *, allow_content: bool) -> None:
        self._span = span
        self.allow_content = allow_content

    def _set_raw(self, key: str, value: Any) -> None:
        if self._span is None:
            return
        converted = _to_attr_value(value)
        if converted is None:
            return
        try:
            self._span.set_attribute(key, converted)
        except Exception:
            logger.debug("Failed to set span attribute %s", key, exc_info=True)

    def set(self, **attributes: Any) -> None:
        """Attach non-content operational metadata (counts, latency-related, ids, actions)."""
        for key, value in attributes.items():
            self._set_raw(f"{_METADATA_PREFIX}memory.{key}", value)

    def set_model(self, model: str) -> None:
        self._set_raw("gen_ai.request.model", model)
        self._set_raw("langfuse.observation.model.name", model)

    def set_usage(self, *, input_tokens: int | None, output_tokens: int | None) -> None:
        if input_tokens is not None:
            self._set_raw("gen_ai.usage.input_tokens", int(input_tokens))
        if output_tokens is not None:
            self._set_raw("gen_ai.usage.output_tokens", int(output_tokens))

    def set_input(self, value: Any) -> None:
        if self.allow_content:
            self._set_raw("langfuse.observation.input", _dump_content(value))

    def set_output(self, value: Any) -> None:
        if self.allow_content:
            self._set_raw("langfuse.observation.output", _dump_content(value))

    def set_error(self, exc: BaseException) -> None:
        if self._span is None:
            return
        message = f"{type(exc).__name__}: {str(exc)[:300]}"
        self._set_raw("langfuse.observation.level", "ERROR")
        self._set_raw("langfuse.observation.status_message", message)
        try:
            from opentelemetry.trace import Status, StatusCode

            self._span.set_status(Status(StatusCode.ERROR, message))
        except Exception:
            logger.debug("Failed to set span error status", exc_info=True)


class MemoryTracer:
    """Creates memory spans from an injected OpenTelemetry TracerProvider (or no-ops)."""

    def __init__(
        self,
        tracer_provider: Any | None = None,
        *,
        allow_content: bool = False,
        instrumentation_name: str = "care-support-voice-agent.memory",
    ) -> None:
        self.allow_content = allow_content
        self._tracer = None
        if tracer_provider is not None:
            try:
                self._tracer = tracer_provider.get_tracer(instrumentation_name)
            except Exception:
                logger.debug("Memory tracer unavailable; continuing without tracing", exc_info=True)
                self._tracer = None

    @property
    def enabled(self) -> bool:
        return self._tracer is not None

    @contextmanager
    def span(
        self,
        name: str,
        *,
        observation_type: str = "span",
        **attributes: Any,
    ) -> Iterator[MemorySpan]:
        if self._tracer is None:
            yield MemorySpan(None, allow_content=self.allow_content)
            return

        try:
            cm = self._tracer.start_as_current_span(
                name,
                record_exception=False,
                set_status_on_exception=False,
            )
            otel_span = cm.__enter__()
        except Exception:
            logger.debug("Failed to start memory span %s", name, exc_info=True)
            yield MemorySpan(None, allow_content=self.allow_content)
            return

        handle = MemorySpan(otel_span, allow_content=self.allow_content)
        handle._set_raw("langfuse.observation.type", observation_type)
        handle.set(**attributes)
        try:
            yield handle
        except BaseException as exc:
            handle.set_error(exc)
            try:
                cm.__exit__(type(exc), exc, exc.__traceback__)
            except Exception:
                logger.debug("Failed to end memory span %s", name, exc_info=True)
            raise
        else:
            try:
                cm.__exit__(None, None, None)
            except Exception:
                logger.debug("Failed to end memory span %s", name, exc_info=True)


NOOP_TRACER = MemoryTracer(None)
