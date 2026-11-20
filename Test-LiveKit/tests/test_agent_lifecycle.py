import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
import agent


@pytest.mark.parametrize('fake_job', [False, True])
@pytest.mark.parametrize('failure', [None, 'start', 'reply'])
def test_finalize_closes_sdk_before_flush_and_runs_once(monkeypatch, failure, fake_job):
    events = []
    class Session:
        def __init__(self, **_):
            self.handlers = {}; self.history = SimpleNamespace(items=[])
        def on(self, name):
            def decorator(f): self.handlers[name] = f; return f
            return decorator
        async def start(self, **_):
            events.append('start')
            if failure == 'start': raise RuntimeError('start failure')
        async def generate_reply(self, **_):
            if failure == 'reply': raise RuntimeError('reply failure')
        async def aclose(self):
            self.handlers['close'](SimpleNamespace(reason='closed'))
            await asyncio.sleep(0)
            events.append('root_span_ended')
    provider = MagicMock()
    provider.shutdown.side_effect = lambda: events.append('provider_shutdown')
    monkeypatch.setattr(agent, 'setup_langfuse', lambda *a, **kw: provider)
    monkeypatch.setattr(agent, 'flush_traces', lambda _: events.append('flush'))
    monkeypatch.setattr(agent, 'AgentSession', Session)
    monkeypatch.setattr(agent.openai.LLM, 'with_openrouter', lambda **_: object())
    register_rpc = MagicMock()
    monkeypatch.setattr(agent, 'register_approval_rpc', register_rpc)
    monkeypatch.setattr(agent.Settings, 'from_env', lambda: SimpleNamespace(openrouter_model='test', voice_enabled=False))
    callbacks = []
    ctx = SimpleNamespace(room=SimpleNamespace(name='room'), add_shutdown_callback=callbacks.append, is_fake_job=lambda: fake_job)
    async def scenario():
        if failure:
            with pytest.raises(RuntimeError): await agent.entrypoint(ctx)
        else:
            await agent.entrypoint(ctx)
        await callbacks[0]()
        await callbacks[0]()
    asyncio.run(scenario())
    assert events.count('flush') == 1
    assert events.index('root_span_ended') < events.index('flush') < events.index('provider_shutdown')

    assert register_rpc.call_count == (0 if fake_job or failure == 'start' else 1)
