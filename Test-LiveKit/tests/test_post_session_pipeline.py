"""Unit tests for the automated post-session export & evaluation pipeline."""

from __future__ import annotations

import json
from pathlib import Path

from evaluations.evaluate_secretary import LangfuseResolutionError, MetricResult
from evaluations.post_session_pipeline import (
    find_latest_session_id,
    run_post_session_pipeline,
    wait_for_langfuse_trace,
)


def test_find_latest_session_id_picks_newest_across_dirs(tmp_path: Path):
    sess_dir = tmp_path / "session_transcripts"
    sec_dir = tmp_path / "secretary_transcripts"
    sess_dir.mkdir()
    sec_dir.mkdir()

    older = sec_dir / "frontend-test-secretary-old.json"
    older.write_text(json.dumps({"session_id": "frontend-test-secretary-old", "turns": []}), encoding="utf-8")

    newer = sess_dir / "frontend-test-text-new.json"
    newer.write_text(json.dumps({"session_id": "frontend-test-text-new", "turns": []}), encoding="utf-8")
    # Ensure deterministic mtime ordering
    import os
    os.utime(older, (1000, 1000))
    os.utime(newer, (2000, 2000))

    sid, path = find_latest_session_id(
        session_transcripts_dir=sess_dir,
        secretary_transcripts_dir=sec_dir,
    )
    assert sid == "frontend-test-text-new"
    assert path == newer


def test_wait_for_langfuse_trace_retries_until_found():
    attempts = {"n": 0}

    def fake_resolver(session_id, **_):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise LangfuseResolutionError("LANGFUSE_TRACE_NOT_FOUND", "not ready yet")
        return "trace-ready-123"

    slept = []
    trace_id = wait_for_langfuse_trace(
        "sess-1",
        host="https://lf.example",
        public_key="pk",
        secret_key="sk",
        max_attempts=5,
        poll_interval_seconds=2.0,
        resolver=fake_resolver,
        sleep_fn=slept.append,
    )
    assert trace_id == "trace-ready-123"
    assert attempts["n"] == 3
    assert slept == [2.0, 2.0]


def test_run_post_session_pipeline_end_to_end_offline(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://lf.example")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")

    sess_dir = tmp_path / "session_transcripts"
    sec_dir = tmp_path / "secretary_transcripts"
    export_dir = tmp_path / "export"
    trace_dir = tmp_path / "trace_evals"
    reports_dir = tmp_path / "evaluation_reports"
    sess_dir.mkdir()
    sec_dir.mkdir()

    sid = "frontend-test-text-abc123-def456"
    tfile = sess_dir / f"{sid}.json"
    tfile.write_text(
        json.dumps(
            {
                "session_id": sid,
                "room_name": "frontend-test-text-abc123",
                "session_mode": "text",
                "turns": [
                    {"role": "user", "text": "こんにちは"},
                    {"role": "assistant", "text": "こんにちは！何かお手伝いできますか？"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    def fake_session_exporter(session_id, out_path: Path, **_):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps({"session_id": session_id, "traces": []}), encoding="utf-8")
        return {"session_id": session_id, "traces": []}

    def fake_trace_exporter(trace_id: str, *, output_dir: Path):
        output_dir.mkdir(parents=True, exist_ok=True)
        out = output_dir / f"trace_{trace_id}.json"
        doc = {
            "trace_id": trace_id,
            "observations": [
                {"name": "llm_request", "type": "GENERATION", "timeToFirstToken": 0.42},
                {"name": "search_web", "type": "TOOL", "latency": 1.2, "level": "DEFAULT"},
            ],
            "scores": [{"name": "text.conv.text_ux", "value": 1.0}],
        }
        out.write_text(json.dumps(doc), encoding="utf-8")
        return out, doc

    def fake_eval(**_):
        return [
            MetricResult(
                name="ConversationalGEval (TextUX)",
                langfuse_name="text.conv.text_ux",
                score=1.0,
                passed=True,
                reason="明瞭",
            )
        ]

    summary = run_post_session_pipeline(
        session_id=None,  # auto-pick latest!
        session_export_dir=export_dir,
        trace_evals_dir=trace_dir,
        reports_dir=reports_dir,
        session_transcripts_dir=sess_dir,
        secretary_transcripts_dir=sec_dir,
        trace_resolver=lambda *_, **__: "trace-xyz",
        session_exporter=fake_session_exporter,
        trace_exporter=fake_trace_exporter,
        score_poster=lambda **_: 1,
        judge_factory=lambda _: ("openai/gpt-6-luna", "dummy"),
        conversation_evaluator=fake_eval,
        sleep_fn=lambda _: None,
    )

    assert summary["errors"] == []
    assert summary["session_id"] == sid
    assert summary["session_type"] == "text"
    assert summary["trace_id"] == "trace-xyz"
    assert summary["langfuse_scores_posted"] == 1
    assert Path(summary["session_export_path"]).exists()
    assert Path(summary["trace_eval_path"]).exists()
    assert Path(summary["report_json_path"]).exists()
    assert Path(summary["report_md_path"]).exists()
    assert Path(summary["summary_path"]).exists()

    # Unannotated live session must mark tool.selection.f1 and tool.unnecessary_call_rate as N/A (not FAIL)
    report_data = json.loads(Path(summary["report_json_path"]).read_text(encoding="utf-8"))
    by_metric = {m["metric"]: m for m in report_data["metrics"]}
    assert by_metric["tool.selection.f1"]["status"] == "N/A"
    assert by_metric["tool.unnecessary_call_rate"]["status"] == "N/A"


def test_build_dataset_prefers_tavily_latency_over_approval_wait():
    from evaluations.post_session_pipeline import build_voice_agent_eval_dataset

    trace_doc = {
        "observations": [
            {"name": "search_web", "type": "TOOL", "latency": 18.95, "level": "DEFAULT"},
            {"name": "web_search.tavily", "type": "SPAN", "latency": 0.998, "level": "DEFAULT"},
        ]
    }
    dataset = build_voice_agent_eval_dataset(
        session_id="frontend-test-text-1",
        session_type="text",
        transcript_doc={"turns": [{"role": "user", "text": "q"}, {"role": "assistant", "text": "a"}]},
        trace_doc=trace_doc,
    )
    tool_lats = dataset["scenarios"][0]["latencies_ms"]["tool"]
    assert tool_lats == [998.0]


def test_trace_export_calculates_cost_with_cache_fallback_and_gpt6_luna():
    from types import SimpleNamespace
    from trace_export import enrich, load_prices

    class _FakeStatus:
        is_ok = True
        description = None

    span = SimpleNamespace(
        name="llm_request",
        context=SimpleNamespace(span_id=2, trace_id=1),
        parent=None,
        resource=None,
        attributes={
            "gen_ai.request.model": "openai/gpt-6-luna",
            "gen_ai.usage.input_tokens": 2000,
            "gen_ai.usage.output_tokens": 100,
            "gen_ai.usage.cache_write.input_tokens": 1500,
        },
        events=[],
        links=[],
        kind=None,
        status=_FakeStatus(),
        start_time=0,
        end_time=1,
        instrumentation_scope=None,
    )
    prices = {"openai/gpt-6-luna": {"input_per_million": 0.4, "output_per_million": 1.6}}
    enriched = enrich(span, prices)
    assert enriched.attributes["langfuse.observation.metadata.cost_source"] == "configured_rate_estimate_usd"
    cost_details = json.loads(enriched.attributes["langfuse.observation.cost_details"])
    assert cost_details["input"] > 0 and cost_details["output"] > 0 and cost_details["cache_creation_input_tokens"] > 0


def test_evaluate_full_conversation_passes_tool_results_as_context(monkeypatch):
    from evaluations.evaluate_secretary import evaluate_full_conversation

    seen_cases = []

    class FakeConvMetric:
        def __init__(self, **kwargs):
            self.score = 0.95
            self.reason = "ok"

        def measure(self, conv_case):
            seen_cases.append(conv_case)
            return self.score

        def is_successful(self):
            return True

    monkeypatch.setattr("deepeval.metrics.ConversationalGEval", FakeConvMetric)
    evaluate_full_conversation(
        transcript_doc={
            "session_mode": "text",
            "turns": [
                {"role": "user", "text": "最新のMacBookについて調べて"},
                {"role": "assistant", "text": "CNBCの記事によるとM5搭載モデルが発表されました。"},
            ],
            "tool_results": [
                {
                    "tool_name": "search_web",
                    "arguments": '{"query": "MacBook M5"}',
                    "output": '{"results": [{"url": "https://www.cnbc.com/...", "title": "Apple M5"}]}',
                    "is_error": False,
                }
            ],
        },
        judge_model="dummy",
        session_type="text",
    )
    assert seen_cases
    assert seen_cases[0].context is not None
    assert "search_web" in seen_cases[0].context[0]
    assert "cnbc.com" in seen_cases[0].context[0]
