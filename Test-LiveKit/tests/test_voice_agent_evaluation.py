from __future__ import annotations

import json

from evaluations.voice_agent_evaluation import (
    SCHEMA_VERSION,
    edit_counts,
    evaluate_document,
    evaluate_file,
    markdown_report,
    normalize_text,
)


def by_name(report, name):
    return next(metric for metric in report["metrics"] if metric["metric"] == name)


def test_normalization_and_edit_counts_are_deterministic():
    assert normalize_text("ＡＢＣ １２") == "ABC12"
    assert edit_counts(list("abc"), list("adc")) == (1, 0, 0)
    assert edit_counts(list("ab"), list("abc")) == (0, 0, 1)
    assert edit_counts(list("abc"), list("ab")) == (0, 1, 0)


def test_evaluates_objective_metrics_and_preserves_na():
    document = {
        "schema_version": SCHEMA_VERSION,
        "dataset_version": "unit-v1",
        "scenarios": [{
            "scenario_id": "s1",
            "stt_samples": [{
                "reference_transcript": "予定は11時です",
                "recognized_transcript": "予定は12時です",
                "reference_tokens": ["予定", "は", "11時", "です"],
                "recognized_tokens": ["予定", "は", "12時", "です"],
                "expected_entities": [{"type": "time", "value": "11時", "critical": True}],
                "recognized_entities": [{"type": "time", "value": "12時"}],
            }],
            "latencies_ms": {"end_to_end": [100, 300]},
            "turn_samples": [{"eligible": True, "user_speech_end_ms": 100, "agent_first_audio_ms": 300, "response_deadline_ms": 500}],
            "task": {"eligible": True, "completed": True},
            "tools": {
                "expected": [{"name": "lookup", "arguments": {"id": "1"}}],
                "actual": [{"name": "lookup", "arguments": {"id": "1"}, "status": "success"}],
                "allowed": ["lookup"],
            },
            "reliability": {"session_success": True, "error": False, "timeout": False},
        }],
    }
    report = evaluate_document(document)
    assert by_name(report, "stt.cer.micro")["raw_value"] > 0
    assert by_name(report, "stt.wer.micro")["status"] == "FAIL"
    assert by_name(report, "stt.entity.critical_error_rate")["raw_value"] == 1.0
    assert by_name(report, "latency.end_to_end.p95")["raw_value"] == 290.0
    assert by_name(report, "tool.selection.f1")["status"] == "PASS"
    assert by_name(report, "deepeval.tool_permission")["status"] == "PASS"
    assert by_name(report, "tts.intelligibility.cer.micro")["status"] == "N/A"
    assert by_name(report, "deepeval.voice.speech_intelligibility")["status"] == "N/A"
    assert "| `stt.cer.micro` |" in markdown_report(report)


def test_detects_unapproved_and_false_success_tool_calls():
    report = evaluate_document({
        "schema_version": SCHEMA_VERSION,
        "scenarios": [{
            "scenario_id": "unsafe",
            "tools": {
                "expected": [],
                "actual": [{"name": "send_email", "arguments": {}, "status": "failed", "approval_required": True, "approval_obtained": False, "claimed_success": True}],
                "allowed": ["lookup"],
                "denied": ["send_email"],
            },
        }],
    })
    assert by_name(report, "safety.approval_violation_rate")["status"] == "FAIL"
    assert by_name(report, "safety.false_success_claim_rate")["status"] == "FAIL"
    assert by_name(report, "deepeval.tool_permission")["status"] == "FAIL"


def test_writes_json_and_markdown_reports(tmp_path):
    source = tmp_path / "cases.json"
    source.write_text(json.dumps({"schema_version": SCHEMA_VERSION, "scenarios": [{"scenario_id": "only", "task": {"eligible": True, "completed": True}}]}), encoding="utf-8")
    json_path, markdown_path, report = evaluate_file(source, tmp_path / "out")
    assert json.loads(json_path.read_text(encoding="utf-8"))["scenario_count"] == 1
    assert markdown_path.read_text(encoding="utf-8").startswith("# Voice Agent Evaluation Report")
    assert report["judge_enabled"] is False
