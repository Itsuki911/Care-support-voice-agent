"""Per-session settings saved by the local Agent settings screen."""
from __future__ import annotations

import json
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent / '.agent-runtime-config.json'
MODELS = frozenset({'anthropic/claude-haiku-5.5', 'openai/gpt-6-luna', 'deepseek/deepseek-v4.1-flash-1017', 'qwen/qwen3.8-flash'})
TOOLS = frozenset({'search_emails', 'read_email', 'send_email', 'search_memories', 'list_recent_memories', 'save_memory', 'search_documents', 'search_web', 'get_schedule', 'get_tasks'})


def load_runtime_config(path: Path = CONFIG_PATH) -> dict:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {}
    if not isinstance(data, dict):
        raise ValueError('Invalid agent settings')
    model = data.get('model')
    if model is not None and model not in MODELS:
        raise ValueError('Invalid model')
    llm = data.get('llm', {})
    if not isinstance(llm, dict) or set(llm) - {'temperature', 'reasoning_effort', 'max_tokens', 'prompt_caching'}:
        raise ValueError('Invalid LLM settings')
    temperature = llm.get('temperature')
    if temperature is not None and (isinstance(temperature, bool) or not isinstance(temperature, (int, float)) or not 0 <= temperature <= 2):
        raise ValueError('Invalid temperature')
    max_tokens = llm.get('max_tokens')
    if max_tokens is not None and (isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or not 1 <= max_tokens <= 32768):
        raise ValueError('Invalid max_tokens')
    if llm.get('reasoning_effort', 'auto') not in {'auto', 'none', 'minimal', 'low', 'medium', 'high', 'xhigh'}:
        raise ValueError('Invalid reasoning_effort')
    if not isinstance(llm.get('prompt_caching', True), bool):
        raise ValueError('Invalid prompt_caching')
    prompt = data.get('prompt')
    if prompt is not None and (not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 100000):
        raise ValueError('Invalid prompt')
    tools = data.get('disabled_tools', [])
    if not isinstance(tools, list) or any(item not in TOOLS for item in tools):
        raise ValueError('Invalid tools')
    rag = data.get('rag', {})
    if not isinstance(rag, dict) or set(rag) - {'top_k', 'similarity_threshold', 'chunk_size', 'chunk_overlap', 'embedding_model', 'metadata_filter', 'rerank_top_n', 'max_iterations', 'max_steps', 'max_execution_time', 'early_stopping_method'}:
        raise ValueError('Invalid RAG settings')
    for key, low, high, kind in [('top_k', 1, 50, int), ('similarity_threshold', 0, 1, (int, float)), ('chunk_size', 100, 4000, int), ('chunk_overlap', 0, 2000, int)]:
        if key in rag and (isinstance(rag[key], bool) or not isinstance(rag[key], kind) or not low <= rag[key] <= high):
            raise ValueError('Invalid RAG setting: ' + key)
    import re
    embedding_model = rag.get('embedding_model')
    if embedding_model is not None and (not isinstance(embedding_model, str) or len(embedding_model) > 150 or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._:/-]*', embedding_model)):
        raise ValueError('Invalid embedding model')
    metadata_filter = rag.get('metadata_filter')
    if metadata_filter is not None and not isinstance(metadata_filter, dict):
        raise ValueError('Invalid metadata filter')
    for key, maximum in [('rerank_top_n', 1000), ('max_iterations', 1000), ('max_steps', 1000), ('max_execution_time', 86400)]:
        value = rag.get(key)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum):
            raise ValueError('Invalid RAG setting: ' + key)
    if rag.get('early_stopping_method') not in (None, 'force', 'generate'):
        raise ValueError('Invalid early stopping method')
    if rag.get('chunk_overlap', 0) >= rag.get('chunk_size', 450):
        raise ValueError('Chunk overlap must be smaller than chunk size')
    memory = data.get('memory', {})
    if not isinstance(memory, dict) or set(memory) - {'extraction_frequency'}:
        raise ValueError('Invalid memory settings')
    if memory.get('extraction_frequency', 'session_end') not in ('session_end', 'every_response'):
        raise ValueError('Invalid extraction_frequency')
    harness = data.get('harness', {})
    if not isinstance(harness, dict) or set(harness) - {'memory_enabled', 'rag_enabled', 'memory_prompt_recent_limit', 'stt_model', 'tts_model', 'tts_voice'}:
        raise ValueError('Invalid harness settings')
    for key in ('memory_enabled', 'rag_enabled'):
        if key in harness and not isinstance(harness[key], bool):
            raise ValueError('Invalid harness setting')
    speech = [harness.get(key) for key in ('stt_model', 'tts_model', 'tts_voice')]
    if any(not isinstance(v, str) or len(v) > 150 for v in speech if v is not None):
        raise ValueError('Invalid speech settings')
    if any(speech) and not all(speech):
        raise ValueError('Speech model and voice must be configured together')
    limit = harness.get('memory_prompt_recent_limit', 5)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 5:
        raise ValueError('Invalid memory prompt limit')
    return data
