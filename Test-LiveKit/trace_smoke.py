"""Synthetic trace only: no LLM, microphone, Gmail or conversation content."""
from __future__ import annotations
import argparse
from importlib.metadata import version
from pathlib import Path
from uuid import uuid4
from dotenv import load_dotenv
from livekit.agents.telemetry import tracer
from observability import setup_langfuse, flush_traces
from prompt_config import load_prompt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export', action='store_true', help='send synthetic metadata to configured Langfuse')
    args = parser.parse_args()
    print('SDK versions:', ', '.join(f'{name}={version(name)}' for name in (
        'livekit-agents', 'livekit-plugins-openai', 'opentelemetry-sdk', 'opentelemetry-exporter-otlp-proto-http')))
    if not args.export:
        print('No external requests. Use --export to test synthetic ingestion.')
        return 0
    load_dotenv(Path(__file__).with_name('.env'), override=False)
    prompt = load_prompt()
    session_id = 'level0-smoke-' + uuid4().hex
    provider = setup_langfuse(session_id, prompt_version=prompt.version, prompt_hash=prompt.digest)
    if provider is None:
        print('Exporter unavailable: configure LANGFUSE_PUBLIC_KEY / SECRET_KEY / BASE_URL and enable tracing.')
        return 2
    try:
        with tracer.start_as_current_span('level0_smoke') as root:
            trace_id = f'{root.get_span_context().trace_id:032x}'
            with tracer.start_as_current_span('llm_request', attributes={
                'gen_ai.operation.name': 'chat', 'gen_ai.provider.name': 'synthetic',
                'gen_ai.request.model': 'level0-smoke-not-a-real-model',
                'gen_ai.usage.input_tokens': 10, 'gen_ai.usage.output_tokens': 5,
                'gen_ai.response.time_to_first_chunk': 0.01,
            }):
                pass
            with tracer.start_as_current_span('synthetic_tool', attributes={
                'langfuse.observation.type': 'tool', 'tool.state': 'not_executed',
            }):
                pass
        drained = flush_traces(provider)
        diagnostics = provider.export_diagnostics
        print(f'session_id={session_id}\ntrace_id={trace_id}')
        print(f'queue_drained={drained} accepted_spans={diagnostics.accepted} failed_spans={diagnostics.failed}')
        if not drained or diagnostics.failed or diagnostics.accepted < 3:
            print('OTLP acceptance not verified. Check region URL, project key pair, network and server logs.')
            return 1
        print('OTLP accepted. Verify this trace/session ID in Langfuse with environment/date filters cleared. Synthetic counts are not real usage or billing.')
        return 0
    finally:
        provider.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
