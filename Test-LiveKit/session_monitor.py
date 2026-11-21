"""Content-free lifecycle, approval and per-turn records attached to SDK traces."""
from __future__ import annotations

import json
from time import time_ns
from opentelemetry import trace


class SessionMonitor:
    def __init__(self, provider, session_id, *, mode='voice'):
        self.tracer = provider.get_tracer('care-support.level0') if provider else None
        self.session_id = session_id
        self.mode = mode
        self.tools = {}
        self.started = time_ns()
        self.usage = []

    def attrs(self):
        return {'langfuse.session.id': self.session_id}

    def tool_state(self, execution_id, tool, state):
        if self.tracer is None:
            return
        span = self.tools.get(execution_id)
        if span is None:
            span = self.tracer.start_span('external_tool', attributes={**self.attrs(),
                'langfuse.observation.type': 'tool', 'tool.name': tool,
                'execution.id': execution_id})
            self.tools[execution_id] = span
        span.set_attribute('tool.state', state)
        span.add_event(state)
        if state in ('denied', 'expired', 'cancelled', 'succeeded', 'failed', 'result_unknown'):
            if state in ('failed', 'result_unknown', 'expired', 'cancelled'):
                span.set_status(trace.Status(trace.StatusCode.ERROR, f'Tool approval {state}'))
            span.end()
            self.tools.pop(execution_id, None)

    def bind(self, session, on_conversation_item=None):
        @session.on('session_usage_updated')
        def usage(ev):
            # Cumulative snapshots replace previous values; never sum them.
            self.usage = [item.model_dump() for item in ev.usage.model_usage]

        @session.on('conversation_item_added')
        def turn(ev):
            self.record_turn(ev.item, 'conversation_turn')
            if on_conversation_item is not None:
                on_conversation_item(ev)

        @session.on('error')
        def error(ev):
            if self.tracer:
                with self.tracer.start_as_current_span('session_error', attributes=self.attrs()) as span:
                    span.set_attribute('error.type', type(ev.error).__name__)
                    span.set_status(trace.Status(trace.StatusCode.ERROR))

    def record_turn(self, item, name):
        if not self.tracer or getattr(item, 'type', '') != 'message':
            return
        attrs = {**self.attrs(), 'turn.id': item.id, 'turn.role': item.role,
                 'turn.state': 'interrupted' if item.interrupted else 'completed'}
        for key, value in (item.metrics or {}).items():
            if isinstance(value, (int, float)):
                attrs[f'turn.metrics.{key}'] = value
        with self.tracer.start_as_current_span(name, attributes=attrs):
            pass

    def finish(self, session, reason):
        for span in self.tools.values():
            span.set_attribute('tool.state', 'cancelled')
            span.end()
        self.tools.clear()
        if self.tracer:
            # End-of-session snapshot captures metrics populated after item_added.
            for item in session.history.items:
                self.record_turn(item, 'conversation_turn_final')
            with self.tracer.start_as_current_span('session_summary', start_time=self.started,
                    attributes={**self.attrs(), 'session.mode': self.mode,
                                'session.end_reason': reason,
                                'usage.models': json.dumps(self.usage),
                                'cost.stt': 'unavailable', 'cost.tts': 'unavailable',
                                'cost.other': 'not_instrumented'}) as span:
                if reason == 'error':
                    span.set_status(trace.Status(trace.StatusCode.ERROR))
