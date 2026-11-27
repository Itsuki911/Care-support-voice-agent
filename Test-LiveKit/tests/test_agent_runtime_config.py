import json
from unittest.mock import Mock

import pytest

from agent_runtime_config import load_runtime_config
from agent import TerminalAssistant, _init_rag_runtime


def test_load_runtime_config_validates_and_preserves_values(tmp_path):
    path = tmp_path / 'settings.json'
    values = {'model': 'openai/gpt-6-luna', 'prompt': '日本語で応答する', 'disabled_tools': ['send_email'], 'rag': {'top_k': 3, 'chunk_size': 500, 'chunk_overlap': 50}, 'harness': {'memory_enabled': False, 'rag_enabled': True, 'memory_prompt_recent_limit': 4}}
    path.write_text(json.dumps(values), encoding='utf-8')
    assert load_runtime_config(path) == values
    values['rag']['chunk_overlap'] = 500
    path.write_text(json.dumps(values), encoding='utf-8')
    with pytest.raises(ValueError):
        load_runtime_config(path)


def test_disabled_tools_are_not_registered():
    assistant = TerminalAssistant(instructions='test', disabled_tools={'send_email'})
    assert {tool.id for tool in assistant.tools} == {'search_emails', 'read_email'}


def test_rag_overrides_are_applied_per_runtime(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql://localhost/example')
    monkeypatch.setenv('RAG_ENABLED', 'false')
    create = Mock(return_value=object())
    monkeypatch.setattr('agent.create_rag_runtime', create)
    assert _init_rag_runtime(enabled=True, settings_override={'top_k': 7, 'chunk_size': 600, 'chunk_overlap': 80}) is create.return_value
    settings = create.call_args.args[0]
    assert (settings.default_top_k, settings.chunk_size, settings.chunk_overlap) == (7, 600, 80)


def test_future_rag_settings_are_validated_but_not_applied(tmp_path, monkeypatch):
    path = tmp_path / 'settings.json'
    rag = {'embedding_model': 'test-embedding:latest', 'top_k': 4, 'metadata_filter': {'category': 'care'}, 'rerank_top_n': 3, 'max_iterations': 2, 'max_steps': 5, 'max_execution_time': 20, 'early_stopping_method': 'force'}
    path.write_text(json.dumps({'rag': rag}), encoding='utf-8')
    assert load_runtime_config(path)['rag'] == rag
    monkeypatch.setenv('DATABASE_URL', 'postgresql://localhost/example')
    create = Mock(return_value=object())
    monkeypatch.setattr('agent.create_rag_runtime', create)
    assert _init_rag_runtime(enabled=True, settings_override=rag) is create.return_value
    settings = create.call_args.args[0]
    assert settings.embedding_model == 'test-embedding:latest'
    assert settings.default_top_k == 4
    assert not hasattr(settings, 'rerank_top_n')
    rag['metadata_filter'] = ['invalid']
    path.write_text(json.dumps({'rag': rag}), encoding='utf-8')
    with pytest.raises(ValueError):
        load_runtime_config(path)


def test_rag_uses_separate_embedder_when_model_differs(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql://localhost/example')
    shared = Mock()
    shared.embedding_provider.model_name = 'memory-model'
    create = Mock(return_value=object())
    monkeypatch.setattr('agent.create_rag_runtime', create)
    _init_rag_runtime(enabled=True, memory_runtime=shared, settings_override={'embedding_model': 'rag-model'})
    assert create.call_args.kwargs['embedding_provider'] is None
    _init_rag_runtime(enabled=True, memory_runtime=shared, settings_override={'embedding_model': 'memory-model'})
    assert create.call_args.kwargs['embedding_provider'] is shared.embedding_provider


def test_llm_parameters_are_mapped_to_openrouter_request(monkeypatch):
    from agent import _create_openrouter_llm
    from types import SimpleNamespace

    opts = SimpleNamespace(extra_body={}, prompt_cache_breakpoints='auto')
    factory = Mock(return_value=SimpleNamespace(_opts=opts))
    monkeypatch.setattr('agent.openai.LLM.with_openrouter', factory)
    _create_openrouter_llm('anthropic/claude-haiku-5.5', 'v2', {
        'temperature': 0.3, 'reasoning_effort': 'high', 'max_tokens': 2048, 'prompt_caching': True,
    })
    assert factory.call_args.kwargs == {'model': 'anthropic/claude-haiku-5.5', 'temperature': 0.3, 'prompt_cache_key': 'care-support:v2'}
    assert opts.extra_body == {'reasoning': {'effort': 'high'}, 'max_tokens': 2048, 'cache_control': {'type': 'ephemeral'}}
    opts.extra_body = {}
    _create_openrouter_llm('openai/gpt-6-luna', 'v2', {'prompt_caching': False})
    assert factory.call_args.kwargs == {'model': 'openai/gpt-6-luna'}
    assert opts.prompt_cache_breakpoints is False
    assert opts.extra_body == {}


def test_invalid_llm_settings_rejected(tmp_path):
    path = tmp_path / 'settings.json'
    for llm in ({'temperature': 2.5}, {'max_tokens': 0}, {'reasoning_effort': 'unknown'}, {'prompt_caching': 'false'}):
        path.write_text(json.dumps({'llm': llm}), encoding='utf-8')
        with pytest.raises(ValueError):
            load_runtime_config(path)


def test_memory_extraction_frequency_is_validated(tmp_path):
    path = tmp_path / 'settings.json'
    path.write_text(json.dumps({'memory': {'extraction_frequency': 'every_response'}}), encoding='utf-8')
    assert load_runtime_config(path)['memory']['extraction_frequency'] == 'every_response'
    path.write_text(json.dumps({'memory': {'extraction_frequency': 'unexpected'}}), encoding='utf-8')
    with pytest.raises(ValueError):
        load_runtime_config(path)
