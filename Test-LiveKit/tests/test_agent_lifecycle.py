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


def test_text_and_voice_sessions_are_strictly_separated(monkeypatch):
    created_sessions = []
    replies = []

    class Session:
        def __init__(self, **opts):
            self.opts = opts
            self.handlers = {}
            self.history = SimpleNamespace(items=[])
            self.start_kwargs = None
            created_sessions.append(self)

        def on(self, name):
            def decorator(f):
                self.handlers[name] = f
                return f
            return decorator

        async def start(self, **kwargs):
            self.start_kwargs = kwargs

        async def generate_reply(self, **kwargs):
            replies.append(kwargs)

        async def interrupt(self):
            pass

        async def aclose(self):
            if 'close' in self.handlers:
                self.handlers['close'](SimpleNamespace(reason='closed'))

    monkeypatch.setattr(agent, 'setup_langfuse', lambda *a, **kw: None)
    monkeypatch.setattr(agent, 'AgentSession', Session)
    monkeypatch.setattr(agent.openai.LLM, 'with_openrouter', lambda **_: 'llm')
    monkeypatch.setattr(agent.inference, 'STT', lambda m: f'stt:{m}')
    monkeypatch.setattr(agent.inference, 'TTS', lambda m, voice=None: f'tts:{m}:{voice}')
    monkeypatch.setattr(agent.inference, 'VAD', lambda: 'vad')
    monkeypatch.setattr(agent, 'register_approval_rpc', lambda *_: None)
    monkeypatch.setattr(
        agent.Settings,
        'from_env',
        lambda: SimpleNamespace(
            openrouter_model='test-model',
            voice_enabled=True,
            stt_model='deepgram/nova-3',
            tts_model='cartesia/sonic-3',
            tts_voice='voice-1',
        ),
    )

    class FakeRoom:
        def __init__(self, name):
            self.name = name
            self.events = {}

        def on(self, name, cb=None):
            if cb is not None:
                self.events[name] = cb
                return cb
            def decorator(f):
                self.events[name] = f
                return f
            return decorator

    async def scenario():
        # 1. Text-only session: no STT/TTS/VAD configured, audio I/O disabled, user_text_input accepted
        text_room = FakeRoom('frontend-test-text-abc123')
        text_callbacks = []
        text_ctx = SimpleNamespace(
            room=text_room,
            add_shutdown_callback=text_callbacks.append,
            is_fake_job=lambda: False,
        )
        await agent.entrypoint(text_ctx)
        text_session = created_sessions[-1]
        assert 'stt' not in text_session.opts
        assert 'tts' not in text_session.opts
        assert 'vad' not in text_session.opts
        assert text_session.start_kwargs['room_options'].audio_input is False
        assert text_session.start_kwargs['room_options'].audio_output is False

        text_room.events['data_received'](
            SimpleNamespace(data=b'{"type":"user_text_input","text":"Hello text mode"}')
        )
        await asyncio.sleep(0.01)
        assert any(r.get('user_input') == 'Hello text mode' and r.get('input_modality') == 'text' for r in replies)
        await text_callbacks[0]()

        # 2. Voice-only session: STT/TTS/VAD configured, user_text_input rejected
        replies.clear()
        voice_room = FakeRoom('frontend-test-def456')
        voice_callbacks = []
        voice_ctx = SimpleNamespace(
            room=voice_room,
            add_shutdown_callback=voice_callbacks.append,
            is_fake_job=lambda: False,
        )
        await agent.entrypoint(voice_ctx)
        voice_session = created_sessions[-1]
        assert voice_session.opts['stt'] == 'stt:deepgram/nova-3'
        assert voice_session.opts['tts'] == 'tts:cartesia/sonic-3:voice-1'
        assert voice_session.opts['vad'] == 'vad'

        voice_room.events['data_received'](
            SimpleNamespace(data=b'{"type":"user_text_input","text":"Should be ignored"}')
        )
        await asyncio.sleep(0.01)
        assert not any(r.get('user_input') == 'Should be ignored' for r in replies)
        await voice_callbacks[0]()

    asyncio.run(scenario())


def test_anthropic_model_enables_openrouter_cache_control():
    from livekit.plugins import openai

    llm_instance = openai.LLM.with_openrouter(
        model="anthropic/claude-haiku-5.5",
        api_key="test-key",
        prompt_cache_key="care-support:v2",
    )
    extra_body = llm_instance._opts.extra_body
    assert isinstance(extra_body, dict)
    extra_body.setdefault("cache_control", {"type": "ephemeral"})
    assert llm_instance._opts.extra_body["cache_control"] == {"type": "ephemeral"}
