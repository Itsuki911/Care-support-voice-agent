import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from livekit.agents.telemetry import set_tracer_provider, tracer
from livekit.agents.llm import ChatMessage
from livekit.agents.metrics.usage import LLMModelUsage, AgentSessionUsage
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExportResult
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from session_monitor import SessionMonitor
from trace_export import ReportingExporter
from prompt_config import load_prompt


def test_native_sdk_trace_parent_usage_privacy_and_prompt():
    sink = InMemorySpanExporter()
    exporter = ReportingExporter(sink, {'test-model': {'input_per_million': 2, 'output_per_million': 4, 'cached_input_per_million': 1}})
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    set_tracer_provider(provider, metadata={'langfuse.session.id': 'session-a', 'langfuse.observation.metadata.prompt_version': 'v1'}, allow_pii=False)
    try:
        with tracer.start_as_current_span('agent_session') as root:
            with tracer.start_as_current_span('llm_request', attributes={
                'gen_ai.operation.name': 'chat', 'gen_ai.request.model': 'test-model',
                'gen_ai.provider.name': 'test-provider', 'gen_ai.usage.input_tokens': 100,
                'gen_ai.usage.cache_read.input_tokens': 20, 'gen_ai.usage.output_tokens': 10,
                'gen_ai.input.messages': 'PRIVATE EMAIL BODY',
            }):
                pass
            monitor = SessionMonitor(provider, 'session-a')
            monitor.tool_state('execution', 'send_email', 'pending')
            monitor.tool_state('execution', 'send_email', 'denied')
        assert provider.force_flush()
        spans = sink.get_finished_spans()
        generation = next(s for s in spans if s.name == 'llm_request')
        assert generation.parent.span_id == root.get_span_context().span_id
        assert generation.context.trace_id == root.get_span_context().trace_id
        assert generation.attributes['langfuse.session.id'] == 'session-a'
        assert generation.attributes['langfuse.observation.type'] == 'generation'
        assert 'PRIVATE' not in str(generation.attributes)
        assert json.loads(generation.attributes['langfuse.observation.usage_details']) == {'input': 80, 'output': 10, 'cache_read_input_tokens': 20}
        assert abs(sum(json.loads(generation.attributes['langfuse.observation.cost_details']).values()) - 0.00022) < 1e-10
        tool = next(s for s in spans if s.name == 'external_tool')
        assert tool.parent.span_id == root.get_span_context().span_id
        assert tool.attributes['tool.state'] == 'denied'
        assert exporter.accepted == 3 and exporter.failed == 0
    finally:
        provider.shutdown()
        set_tracer_provider(TracerProvider())


def test_flush_success_does_not_hide_export_failure():
    sink = MagicMock()
    sink.export.return_value = SpanExportResult.FAILURE
    exporter = ReportingExporter(sink)
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    with provider.get_tracer('test').start_as_current_span('test'):
        pass
    assert provider.force_flush() is True
    assert exporter.failed == 1 and exporter.accepted == 0
    provider.shutdown()


def test_no_prices_does_not_fabricate_costs():
    sink = InMemorySpanExporter()
    provider = TracerProvider(); provider.add_span_processor(SimpleSpanProcessor(ReportingExporter(sink)))
    with provider.get_tracer('test').start_as_current_span('llm_request', attributes={'gen_ai.request.model': 'unknown', 'gen_ai.usage.input_tokens': 1, 'gen_ai.usage.output_tokens': 1}):
        pass
    assert 'langfuse.observation.cost_details' not in sink.get_finished_spans()[0].attributes
    provider.shutdown()


def test_usage_snapshots_and_final_turn_metrics():
    sink = InMemorySpanExporter()
    provider = TracerProvider(); provider.add_span_processor(SimpleSpanProcessor(sink))
    handlers = {}
    session = SimpleNamespace(on=lambda name: lambda fn: handlers.setdefault(name, fn), history=SimpleNamespace(items=[]))
    monitor = SessionMonitor(provider, 'a'); monitor.bind(session)
    for count in (10, 20):
        handlers['session_usage_updated'](SimpleNamespace(usage=AgentSessionUsage(model_usage=[LLMModelUsage(provider='openrouter', model='model', input_tokens=count)])))
    assert monitor.usage[0]['input_tokens'] == 20
    item = ChatMessage(role='assistant', content=['PRIVATE'], interrupted=True, metrics={'e2e_latency': 1.2})
    session.history.items.append(item)
    monitor.finish(session, 'closed')
    attrs = sink.get_finished_spans()[0].attributes
    assert attrs['turn.state'] == 'interrupted'
    assert attrs['turn.metrics.e2e_latency'] == 1.2
    assert 'PRIVATE' not in str(sink.get_finished_spans())
    provider.shutdown()


def test_prompt_is_versioned_and_path_is_constrained(monkeypatch):
    monkeypatch.setenv('SYSTEM_PROMPT_VERSION', 'v1')
    prompt = load_prompt()
    assert prompt.version == 'v1' and len(prompt.digest) == 64
    assert '最大3文' in prompt.text and '分かりません' in prompt.text
    monkeypatch.setenv('SYSTEM_PROMPT_VERSION', '../secrets')
    import pytest
    with pytest.raises(ValueError): load_prompt()


def test_default_prompt_is_v2(monkeypatch):
    monkeypatch.delenv('SYSTEM_PROMPT_VERSION', raising=False)
    prompt = load_prompt()
    assert prompt.version == 'v2'
    assert 'ローカル文書' in prompt.text
    assert '承認フロー' in prompt.text


def test_agent_session_promoted_to_root_when_job_entrypoint_unexported():
    from opentelemetry import trace as trace_api

    unexported_provider = TracerProvider()
    sink = InMemorySpanExporter()
    langfuse_provider = TracerProvider()
    langfuse_provider.add_span_processor(SimpleSpanProcessor(ReportingExporter(sink)))

    try:
        # Simulate LiveKit starting job_entrypoint on its internal provider before setup_langfuse()
        job_span = unexported_provider.get_tracer('livekit-agents').start_span('job_entrypoint')
        with trace_api.use_span(job_span, end_on_exit=False):
            lk_tracer = langfuse_provider.get_tracer('livekit-agents')
            with lk_tracer.start_as_current_span('agent_session') as session_span:
                with lk_tracer.start_as_current_span(
                    'agent_turn',
                    attributes={
                        'lk.pii.user_input': 'こんにちは',
                        'lk.pii.response.text': 'こんにちは、いかがなさいましたか？',
                    },
                ):
                    pass
            # Sibling span created directly under job_entrypoint (e.g. job_shutdown)
            with lk_tracer.start_as_current_span('job_shutdown'):
                pass
        job_span.end()

        assert langfuse_provider.force_flush()
        spans = {s.name: s for s in sink.get_finished_spans()}
        assert spans['agent_session'].parent is None
        assert spans['agent_session'].attributes['langfuse.trace.name'] == 'care-support-conversation'
        assert spans['agent_session'].attributes['langfuse.trace.input'] == 'こんにちは'
        assert spans['agent_session'].attributes['langfuse.trace.output'] == 'こんにちは、いかがなさいましたか？'
        assert spans['agent_turn'].parent.span_id == session_span.get_span_context().span_id
        assert spans['job_shutdown'].parent.span_id == session_span.get_span_context().span_id
    finally:
        langfuse_provider.shutdown()
        unexported_provider.shutdown()
