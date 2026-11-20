"""Langfuse mapping at the export boundary, after LiveKit's privacy filter."""
from __future__ import annotations

import json
import logging
import math
import os
from pathlib import Path
from threading import Lock

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

logger = logging.getLogger(__name__)


def load_prices() -> dict:
    name = os.getenv('OBSERVABILITY_PRICES_FILE', '')
    if not name:
        return {}
    path = Path(name)
    if not path.is_absolute():
        path = Path(__file__).parent / path
    try:
        value = json.loads(path.read_text())
        if not isinstance(value, dict):
            raise ValueError()
        for rates in value.values():
            if not isinstance(rates, dict) or any(type(v) not in (float, int) or not math.isfinite(v) or v < 0 for v in rates.values()):
                raise ValueError()
        return value
    except (OSError, ValueError):
        logger.warning('Invalid price configuration; cost estimates are unavailable')
        return {}


def enrich(span, prices: dict, *, root_context=None, orphan_parent_id=None, trace_io=None):
    attrs = dict(span.attributes or {})
    attrs['langfuse.trace.name'] = 'care-support-conversation'
    if 'lk.speech_id' in attrs:
        attrs['langfuse.observation.metadata.turn_id'] = attrs['lk.speech_id']

    parent = span.parent
    if span.name == 'agent_session':
        # LiveKit starts job_entrypoint on its internal TracerProvider before entrypoint()
        # runs and ends it after shutdown callbacks. Clear agent_session's parent so Langfuse
        # always receives agent_session as the true Root Observation (Is Root Observation = True).
        parent = None
        attrs.setdefault('langfuse.observation.type', 'agent')
        if trace_io:
            if trace_io.get('input') and 'langfuse.trace.input' not in attrs:
                attrs['langfuse.trace.input'] = trace_io['input']
            if trace_io.get('output') and 'langfuse.trace.output' not in attrs:
                attrs['langfuse.trace.output'] = trace_io['output']
    elif root_context is not None and span.context.span_id != root_context.span_id:
        if parent is None or (orphan_parent_id is not None and parent.span_id == orphan_parent_id):
            parent = root_context

    if span.name == 'llm_request':
        attrs['langfuse.observation.type'] = 'generation'
        model = attrs.get('gen_ai.response.model') or attrs.get('gen_ai.request.model', 'unknown')
        attrs['langfuse.observation.model.name'] = model
        attrs['langfuse.observation.metadata.provider'] = attrs.get('gen_ai.provider.name', 'unknown')
        total_input = attrs.get('gen_ai.usage.input_tokens')
        output = attrs.get('gen_ai.usage.output_tokens')
        attrs['langfuse.observation.metadata.cost_source'] = 'unavailable_or_langfuse_model_price'
        if total_input is not None and output is not None:
            cached = attrs.get('gen_ai.usage.cache_read.input_tokens', 0)
            created = attrs.get('gen_ai.usage.cache_write.input_tokens', 0)
            usage = {'input': max(0, total_input - cached - created), 'output': output}
            if cached: usage['cache_read_input_tokens'] = cached
            if created: usage['cache_creation_input_tokens'] = created
            attrs['langfuse.observation.usage_details'] = json.dumps(usage)
            rates = prices.get(model, {})
            keys = {'input': 'input_per_million', 'output': 'output_per_million',
                    'cache_read_input_tokens': 'cached_input_per_million',
                    'cache_creation_input_tokens': 'cache_creation_input_per_million'}
            if all(keys[key] in rates for key in usage):
                cost = {key: count * rates[keys[key]] / 1_000_000 for key, count in usage.items()}
                attrs['langfuse.observation.cost_details'] = json.dumps(cost)
                attrs['langfuse.observation.metadata.cost_source'] = 'configured_rate_estimate_usd'
        ttft = attrs.get('gen_ai.response.time_to_first_chunk')
        if isinstance(ttft, (int, float)) and ttft >= 0 and span.start_time:
            from datetime import datetime, timezone
            attrs['langfuse.observation.completion_start_time'] = datetime.fromtimestamp(span.start_time / 1e9 + ttft, timezone.utc).isoformat()
    if span.status.is_ok is False:
        attrs['langfuse.observation.level'] = 'ERROR'
    return ReadableSpan(name=span.name, context=span.context, parent=parent,
                        resource=span.resource, attributes=attrs, events=span.events,
                        links=span.links, kind=span.kind, status=span.status,
                        start_time=span.start_time, end_time=span.end_time,
                        instrumentation_scope=span.instrumentation_scope)


class ReportingExporter(SpanExporter):
    def __init__(self, exporter, prices=None):
        self.exporter = exporter
        self.prices = prices or {}
        self.accepted = 0
        self.failed = 0
        self._lock = Lock()
        self._trace_roots = {}
        self._orphan_parents = {}
        self._trace_io = {}

    def _collect_trace_context(self, spans):
        with self._lock:
            for span in spans:
                trace_id = span.context.trace_id
                attrs = span.attributes or {}
                if span.name == 'agent_session':
                    self._trace_roots[trace_id] = span.context
                    if span.parent is not None:
                        self._orphan_parents[trace_id] = span.parent.span_id
                # Only populate trace-level input/output when unredacted PII attributes exist on spans.
                user_text = attrs.get('lk.pii.user_input') or attrs.get('lk.pii.user_transcript')
                asst_text = attrs.get('lk.pii.response.text')
                if user_text or asst_text:
                    io_state = self._trace_io.setdefault(trace_id, {})
                    if user_text:
                        io_state['input'] = str(user_text)
                    if asst_text:
                        io_state['output'] = str(asst_text)

    def export(self, spans):
        try:
            self._collect_trace_context(spans)
            enriched = [
                enrich(
                    span,
                    self.prices,
                    root_context=self._trace_roots.get(span.context.trace_id),
                    orphan_parent_id=self._orphan_parents.get(span.context.trace_id),
                    trace_io=self._trace_io.get(span.context.trace_id),
                )
                for span in spans
            ]
            result = self.exporter.export(enriched)
        except Exception:
            # Never include transport exception text (may contain credentials/content).
            result = SpanExportResult.FAILURE
        with self._lock:
            if result == SpanExportResult.SUCCESS:
                self.accepted += len(spans)
            else:
                self.failed += len(spans)
                logger.warning('Langfuse OTLP export failed; check endpoint, keys and connectivity')
        return result

    def shutdown(self):
        self.exporter.shutdown()

    def force_flush(self, timeout_millis=30000):
        return self.exporter.force_flush(timeout_millis)
