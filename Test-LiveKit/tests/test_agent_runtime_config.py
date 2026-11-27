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
