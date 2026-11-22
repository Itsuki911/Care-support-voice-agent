"""Provider-neutral, evidence-first evaluation for voice agents.

The runner deliberately keeps objective measurements deterministic.  DeepEval
standard metrics are used for tool-permission checks in every run and can be
opted into for LLM-as-a-judge conversation/RAG checks.  Missing observations
are reported as ``N/A`` rather than silently becoming a zero score.
"""

from __future__ import annotations

import json
import math
import statistics
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


SCHEMA_VERSION = "voice-agent-evaluation-v1"


@dataclass(frozen=True)
class MetricResult:
    metric: str
    raw_value: float | int | None
    normalized_score: float | None
    unit: str
    threshold: float | None
    status: str
    sample_count: int
    reason: str
    evidence: list[str]
    source: str
    configuration: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "raw_value": self.raw_value,
            "normalized_score": self.normalized_score,
            "unit": self.unit,
            "threshold": self.threshold,
            "status": self.status,
            "sample_count": self.sample_count,
            "reason": self.reason,
            "evidence": self.evidence,
            "source": self.source,
            "configuration": self.configuration,
        }


def _result(
    metric: str,
    raw_value: float | int | None,
    *,
    unit: str,
    threshold: float | None = None,
    lower_is_better: bool = False,
    sample_count: int = 0,
    reason: str,
    evidence: list[str] | None = None,
    source: str = "deterministic",
    configuration: dict[str, Any] | None = None,
) -> MetricResult:
    if raw_value is None:
        return MetricResult(metric, None, None, unit, threshold, "N/A", sample_count, reason,
                            evidence or [], source, configuration or {})
    # A normalized 0..1 score is meaningful for rates, not for milliseconds or
    # dollars.  Preserve those raw units and leave the derived score absent.
    score = (
        max(0.0, min(1.0, 1.0 - float(raw_value))) if lower_is_better else max(0.0, min(1.0, float(raw_value)))
    ) if unit == "ratio" else None
    if threshold is None:
        status = "PASS"
    elif lower_is_better:
        status = "PASS" if float(raw_value) <= threshold else "FAIL"
    else:
        status = "PASS" if float(raw_value) >= threshold else "FAIL"
    return MetricResult(metric, raw_value, score, unit, threshold, status, sample_count, reason,
                        evidence or [], source, configuration or {})


def normalize_text(value: str) -> str:
    """Fixed, conservative normalization for Japanese ASR comparison.

    NFKC and whitespace removal handle formatting noise only.  Digits,
    negations and proper nouns are intentionally not rewritten.
    """
    return "".join(unicodedata.normalize("NFKC", value).split())


def edit_counts(reference: list[str], hypothesis: list[str]) -> tuple[int, int, int]:
    """Return substitutions, deletions, and insertions via Levenshtein DP."""
    rows = len(reference) + 1
    cols = len(hypothesis) + 1
    table: list[list[tuple[int, int, int, int]]] = [[(0, 0, 0, 0)] * cols for _ in range(rows)]
    for i in range(1, rows):
        table[i][0] = (i, 0, i, 0)
    for j in range(1, cols):
        table[0][j] = (j, 0, 0, j)
    for i in range(1, rows):
        for j in range(1, cols):
            if reference[i - 1] == hypothesis[j - 1]:
                table[i][j] = table[i - 1][j - 1]
                continue
            candidates = [
                (table[i - 1][j - 1], "sub"),
                (table[i - 1][j], "del"),
                (table[i][j - 1], "ins"),
            ]
            previous, operation = min(candidates, key=lambda item: item[0][0])
            distance, substitutions, deletions, insertions = previous
            table[i][j] = (
                distance + 1,
                substitutions + (operation == "sub"),
                deletions + (operation == "del"),
                insertions + (operation == "ins"),
            )
    _, substitutions, deletions, insertions = table[-1][-1]
    return substitutions, deletions, insertions


def error_rate(reference: list[str], hypothesis: list[str]) -> tuple[float | None, tuple[int, int, int], int]:
    if not reference:
        return None, (0, 0, 0), 0
    substitutions, deletions, insertions = edit_counts(reference, hypothesis)
    return (substitutions + deletions + insertions) / len(reference), (substitutions, deletions, insertions), len(reference)


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile
    lower, upper = math.floor(position), math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _entity_key(entity: dict[str, Any]) -> tuple[str, str]:
    return str(entity.get("type", "")).strip(), normalize_text(str(entity.get("value", "")))


def _collect_samples(scenario: dict[str, Any], key: str) -> list[dict[str, Any]]:
    samples = scenario.get(key)
    if isinstance(samples, list):
        return [sample for sample in samples if isinstance(sample, dict)]
    return []


def _stt_metrics(scenarios: list[dict[str, Any]], *, key: str, prefix: str) -> list[MetricResult]:
    cer_rates: list[float] = []
    cer_errors = cer_ref_chars = 0
    wer_rates: list[float] = []
    wer_errors = wer_ref_words = 0
    expected_entities: set[tuple[str, str]] = set()
    actual_entities: set[tuple[str, str]] = set()
    critical_expected: set[tuple[str, str]] = set()
    scenario_ids: list[str] = []
    for scenario in scenarios:
        scenario_id = str(scenario.get("scenario_id", "unknown"))
        for sample in _collect_samples(scenario, key):
            reference = normalize_text(str(sample.get("reference_transcript", "")))
            recognized = normalize_text(str(sample.get("recognized_transcript", "")))
            if reference:
                rate, counts, denominator = error_rate(list(reference), list(recognized))
                assert rate is not None
                cer_rates.append(rate)
                cer_errors += sum(counts)
                cer_ref_chars += denominator
                scenario_ids.append(scenario_id)
            ref_tokens = sample.get("reference_tokens")
            got_tokens = sample.get("recognized_tokens")
            if isinstance(ref_tokens, list) and isinstance(got_tokens, list) and ref_tokens:
                rate, counts, denominator = error_rate([str(x) for x in ref_tokens], [str(x) for x in got_tokens])
                assert rate is not None
                wer_rates.append(rate)
                wer_errors += sum(counts)
                wer_ref_words += denominator
            for entity in sample.get("expected_entities") or []:
                if isinstance(entity, dict):
                    entity_key = _entity_key(entity)
                    expected_entities.add(entity_key)
                    if entity.get("critical"):
                        critical_expected.add(entity_key)
            for entity in sample.get("recognized_entities") or []:
                if isinstance(entity, dict):
                    actual_entities.add(_entity_key(entity))
    label = "STT" if prefix == "stt" else "independent STT for TTS audio"
    metrics = [
        _result(f"{prefix}.cer.micro", cer_errors / cer_ref_chars if cer_ref_chars else None, unit="ratio",
                threshold=0.05, lower_is_better=True, sample_count=len(cer_rates),
                reason=f"{label}; NFKC + whitespace-only normalization, character-level Levenshtein.",
                evidence=sorted(set(scenario_ids)), configuration={"normalization": "NFKC + remove whitespace"}),
        _result(f"{prefix}.cer.macro", statistics.fmean(cer_rates) if cer_rates else None, unit="ratio",
                threshold=0.05, lower_is_better=True, sample_count=len(cer_rates),
                reason="Mean per-utterance CER; prevents long utterances from dominating.", evidence=sorted(set(scenario_ids))),
        _result(f"{prefix}.wer.micro", wer_errors / wer_ref_words if wer_ref_words else None, unit="ratio",
                threshold=0.10, lower_is_better=True, sample_count=len(wer_rates),
                reason="Requires supplied, fixed token arrays; Japanese text is never tokenized implicitly.",
                evidence=sorted(set(scenario_ids)), configuration={"tokenizer": "dataset-supplied tokens"}),
        _result(f"{prefix}.wer.macro", statistics.fmean(wer_rates) if wer_rates else None, unit="ratio",
                threshold=0.10, lower_is_better=True, sample_count=len(wer_rates),
                reason="Mean per-utterance WER; N/A without dataset-supplied token arrays.", evidence=sorted(set(scenario_ids))),
    ]
    if expected_entities:
        matched = expected_entities & actual_entities
        precision = len(matched) / len(actual_entities) if actual_entities else 0.0
        recall = len(matched) / len(expected_entities)
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        critical_error = len(critical_expected - actual_entities) / len(critical_expected) if critical_expected else None
        metrics.extend([
            _result(f"{prefix}.entity.precision", precision, unit="ratio", threshold=0.98, sample_count=len(expected_entities),
                    reason="Exact type/value entity matching; semantic entity matching must be supplied separately.", evidence=sorted(set(scenario_ids))),
            _result(f"{prefix}.entity.recall", recall, unit="ratio", threshold=0.98, sample_count=len(expected_entities),
                    reason="Exact type/value entity matching.", evidence=sorted(set(scenario_ids))),
            _result(f"{prefix}.entity.f1", f1, unit="ratio", threshold=0.98, sample_count=len(expected_entities),
                    reason="Harmonic mean of exact entity precision and recall.", evidence=sorted(set(scenario_ids))),
            _result(f"{prefix}.entity.critical_error_rate", critical_error, unit="ratio", threshold=0.0, lower_is_better=True,
                    sample_count=len(critical_expected), reason="Missing critical entities only; N/A if no entity is marked critical.", evidence=sorted(set(scenario_ids))),
        ])
    else:
        metrics.append(_result(f"{prefix}.entity.f1", None, unit="ratio", reason="No expected/recognized entity annotations.", source="deterministic"))
    return metrics


def _latency_metrics(scenarios: list[dict[str, Any]]) -> list[MetricResult]:
    buckets: dict[str, list[float]] = {}
    evidence: dict[str, list[str]] = {}
    for scenario in scenarios:
        scenario_id = str(scenario.get("scenario_id", "unknown"))
        values = scenario.get("latencies_ms") or {}
        if not isinstance(values, dict):
            continue
        for name, raw in values.items():
            items = raw if isinstance(raw, list) else [raw]
            for value in items:
                if isinstance(value, (int, float)) and value >= 0:
                    buckets.setdefault(str(name), []).append(float(value))
                    evidence.setdefault(str(name), []).append(scenario_id)
    output: list[MetricResult] = []
    p95_thresholds: dict[str, float] = {
        "end_to_end": 1000.0,
        "stt": 350.0,
        "end_of_utterance": 300.0,
        "llm_ttft": 600.0,
        "tts_ttfa": 300.0,
        "tts_ttfb": 300.0,
        "tool": 500.0,
        "network": 200.0,
    }
    for name in ("end_to_end", "stt", "end_of_utterance", "llm_ttft", "tts_ttfa", "tts_ttfb", "tool", "network"):
        values = buckets.get(name, [])
        threshold = p95_thresholds.get(name)
        for statistic, raw in (("mean", statistics.fmean(values) if values else None), ("p50", _percentile(values, .50) if values else None),
                               ("p95", _percentile(values, .95) if values else None), ("p99", _percentile(values, .99) if values else None),
                               ("max", max(values) if values else None)):
            output.append(_result(f"latency.{name}.{statistic}", raw, unit="ms", threshold=threshold if statistic == "p95" else None,
                                  lower_is_better=True, sample_count=len(values),
                                  reason="Recorded monotonic-clock duration; component is N/A when not emitted by the provider.",
                                  evidence=sorted(set(evidence.get(name, []))), configuration={"percentile": "linear interpolation"}))
    return output


def _tool_metrics(scenarios: list[dict[str, Any]]) -> list[MetricResult]:
    expected: list[dict[str, Any]] = []
    actual: list[dict[str, Any]] = []
    allowed: set[str] = set()
    denied: set[str] = set()
    evidence: list[str] = []
    had_tool_data = False
    for scenario in scenarios:
        tools = scenario.get("tools")
        if not isinstance(tools, dict):
            continue
        had_tool_data = True
        evidence.append(str(scenario.get("scenario_id", "unknown")))
        expected.extend(call for call in tools.get("expected") or [] if isinstance(call, dict))
        actual.extend(call for call in tools.get("actual") or [] if isinstance(call, dict))
        allowed.update(str(value) for value in tools.get("allowed") or [])
        denied.update(str(value) for value in tools.get("denied") or [])
    if not had_tool_data:
        return [_result("tool.selection.f1", None, unit="ratio", reason="No tool trace supplied.")]
    expected_names = [str(call.get("name", "")) for call in expected]
    actual_names = [str(call.get("name", "")) for call in actual]
    matches = sum(min(expected_names.count(name), actual_names.count(name)) for name in set(expected_names))
    precision = matches / len(actual_names) if actual_names else (1.0 if not expected_names else 0.0)
    recall = matches / len(expected_names) if expected_names else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    expected_by_name: dict[str, list[dict[str, Any]]] = {}
    for call in expected:
        expected_by_name.setdefault(str(call.get("name", "")), []).append(call)
    argument_checks: list[bool] = []
    for call in actual:
        candidates = expected_by_name.get(str(call.get("name", "")), [])
        if candidates:
            wanted = candidates.pop(0).get("arguments", {})
            argument_checks.append(call.get("arguments", {}) == wanted)
    completed = [call for call in actual if "status" in call]
    successes = [call for call in completed if call.get("status") == "success"]
    unauthorized = [call for call in actual if (allowed and str(call.get("name", "")) not in allowed) or str(call.get("name", "")) in denied]
    approval_violations = [call for call in actual if call.get("approval_required") and not call.get("approval_obtained")]
    false_success = [call for call in actual if call.get("claimed_success") and call.get("status") not in {"success", "completed"}]
    return [
        _result("tool.selection.f1", f1, unit="ratio", threshold=1.0, sample_count=max(len(expected), len(actual)),
                reason="Multiset matching of expected and actual tool names.", evidence=sorted(set(evidence))),
        _result("tool.arguments.accuracy", sum(argument_checks) / len(argument_checks) if argument_checks else None, unit="ratio", threshold=1.0,
                sample_count=len(argument_checks), reason="Exact structured argument match on paired tool names; N/A when no paired calls.", evidence=sorted(set(evidence))),
        _result("tool.execution.success_rate", len(successes) / len(completed) if completed else None, unit="ratio", threshold=1.0,
                sample_count=len(completed), reason="Uses recorded tool terminal statuses only.", evidence=sorted(set(evidence))),
        _result("tool.unnecessary_call_rate", (len(actual) - matches) / len(actual) if actual else 0.0, unit="ratio", threshold=0.0, lower_is_better=True,
                sample_count=len(actual), reason="Actual calls not matched to an expected tool name.", evidence=sorted(set(evidence))),
        _result("safety.approval_violation_rate", len(approval_violations) / len(actual) if actual else 0.0, unit="ratio", threshold=0.0, lower_is_better=True,
                sample_count=len(actual), reason="Calls marked approval_required without approval_obtained are critical violations.", evidence=sorted(set(evidence))),
        _result("safety.false_success_claim_rate", len(false_success) / len(actual) if actual else 0.0, unit="ratio", threshold=0.0, lower_is_better=True,
                sample_count=len(actual), reason="Claims success although the recorded tool status is not successful.", evidence=sorted(set(evidence))),
        _deepeval_tool_permission(actual, sorted(allowed) if allowed else None, sorted(denied) if denied else None, evidence),
    ]


def _deepeval_tool_permission(actual: list[dict[str, Any]], allowed: list[str] | None, denied: list[str] | None, evidence: list[str]) -> MetricResult:
    if not allowed and not denied:
        return _result("deepeval.tool_permission", None, unit="ratio", reason="No allowlist or denylist supplied for this tool policy.", source="deepeval:ToolPermissionMetric")
    try:
        from deepeval.metrics import ToolPermissionMetric
        from deepeval.test_case import LLMTestCase, ToolCall
        calls = [ToolCall(name=str(call.get("name", "")), input_parameters=call.get("arguments") or {}) for call in actual]
        metric = ToolPermissionMetric(allowed_tools=allowed, denied_tools=denied, threshold=1.0)
        metric.measure(LLMTestCase(input="voice-agent tool trace", actual_output="recorded", tools_called=calls), _show_indicator=False)
        return _result("deepeval.tool_permission", float(metric.score), unit="ratio", threshold=1.0, sample_count=len(calls),
                       reason=str(metric.reason or "DeepEval deterministic tool permission check."), evidence=sorted(set(evidence)),
                       source="deepeval:ToolPermissionMetric")
    except Exception as exc:  # A missing optional package is not a zero score.
        return _result("deepeval.tool_permission", None, unit="ratio", reason=f"DeepEval could not run: {type(exc).__name__}: {exc}",
                       source="deepeval:ToolPermissionMetric")


def _task_reliability_metrics(scenarios: list[dict[str, Any]]) -> list[MetricResult]:
    eligible = completed = sessions = sessions_ok = errors = timeouts = recovered = recovery_attempts = 0
    costs: list[float] = []
    for scenario in scenarios:
        task = scenario.get("task") or {}
        if isinstance(task, dict) and task.get("eligible"):
            eligible += 1
            completed += bool(task.get("completed"))
        reliability = scenario.get("reliability") or {}
        if isinstance(reliability, dict):
            sessions += 1
            sessions_ok += bool(reliability.get("session_success"))
            errors += int(bool(reliability.get("error")))
            timeouts += int(bool(reliability.get("timeout")))
            recovery_attempts += int(bool(reliability.get("recovery_attempted")))
            recovered += int(bool(reliability.get("recovery_success")))
        usage = scenario.get("usage") or {}
        if isinstance(usage, dict) and isinstance(usage.get("cost_usd"), (int, float)):
            costs.append(float(usage["cost_usd"]))
    return [
        _result("task.completion_rate", completed / eligible if eligible else None, unit="ratio", threshold=1.0, sample_count=eligible,
                reason="Uses explicitly asserted expected final state; no textual inference.", evidence=[], configuration={"required": "task.eligible and task.completed"}),
        _result("reliability.session_success_rate", sessions_ok / sessions if sessions else None, unit="ratio", threshold=1.0, sample_count=sessions,
                reason="Recorded session terminal status.", evidence=[]),
        _result("reliability.error_rate", errors / sessions if sessions else None, unit="ratio", threshold=0.0, lower_is_better=True, sample_count=sessions,
                reason="Recorded error flags.", evidence=[]),
        _result("reliability.timeout_rate", timeouts / sessions if sessions else None, unit="ratio", threshold=0.0, lower_is_better=True, sample_count=sessions,
                reason="Recorded timeout flags.", evidence=[]),
        _result("reliability.recovery_success_rate", recovered / recovery_attempts if recovery_attempts else None, unit="ratio", threshold=1.0,
                sample_count=recovery_attempts, reason="Recorded recovery attempts and terminal results.", evidence=[]),
        _result("cost.per_session_usd", statistics.fmean(costs) if costs else None, unit="USD", threshold=0.05, lower_is_better=True, sample_count=len(costs),
                reason="Measured cost supplied by provider; no price estimation is performed here.", evidence=[]),
        _result("cost.per_successful_task_usd", sum(costs) / completed if costs and completed else None, unit="USD", threshold=0.02, lower_is_better=True, sample_count=completed,
                reason="Total supplied session cost divided by completed eligible tasks.", evidence=[]),
    ]


def _turn_metrics(scenarios: list[dict[str, Any]]) -> list[MetricResult]:
    early = false_end = false_interrupt = overlap = no_response = long_silence = timeout = deadline_turns = 0
    turns = interruptions = stopped = recovered = 0
    stop_latencies: list[float] = []
    for scenario in scenarios:
        for sample in _collect_samples(scenario, "turn_samples"):
            if not sample.get("eligible", True):
                continue
            turns += 1
            user_end = sample.get("user_speech_end_ms")
            agent_start = sample.get("agent_first_audio_ms")
            if isinstance(user_end, (int, float)) and isinstance(agent_start, (int, float)):
                early += int(agent_start < user_end and not sample.get("expected_barge_in", False))
                overlap += int(agent_start < user_end and not sample.get("expected_overlap", False) and not sample.get("expected_barge_in", False))
            false_end += int(bool(sample.get("false_end_of_turn")))
            false_interrupt += int(bool(sample.get("false_interruption")))
            deadline = sample.get("response_deadline_ms")
            if isinstance(deadline, (int, float)):
                deadline_turns += 1
                no_response += int(not isinstance(agent_start, (int, float)))
                timeout += int(isinstance(agent_start, (int, float)) and agent_start > deadline)
                long_silence += int(isinstance(agent_start, (int, float)) and agent_start - float(user_end or 0) > deadline)
            if sample.get("expected_barge_in"):
                interruptions += 1
                detected_at, stopped_at = sample.get("interruption_detected_ms"), sample.get("agent_stopped_ms")
                stopped += int(isinstance(detected_at, (int, float)))
                recovered += int(bool(sample.get("recovered_to_latest_request")))
                if isinstance(detected_at, (int, float)) and isinstance(stopped_at, (int, float)) and stopped_at >= detected_at:
                    stop_latencies.append(float(stopped_at - detected_at))
    return [
        _result("turn.early_response_rate", early / turns if turns else None, unit="ratio", threshold=0.0, lower_is_better=True, sample_count=turns, reason="Agent audio begins before the annotated user end, excluding expected barge-ins.", evidence=[]),
        _result("turn.false_end_of_turn_rate", false_end / turns if turns else None, unit="ratio", threshold=0.0, lower_is_better=True, sample_count=turns, reason="Requires explicit false_end_of_turn annotation.", evidence=[]),
        _result("turn.false_interruption_rate", false_interrupt / turns if turns else None, unit="ratio", threshold=0.0, lower_is_better=True, sample_count=turns, reason="Requires explicit false_interruption annotation.", evidence=[]),
        _result("turn.unwanted_overlap_rate", overlap / turns if turns else None, unit="ratio", threshold=0.0, lower_is_better=True, sample_count=turns, reason="Timestamped overlap not marked expected.", evidence=[]),
        _result("barge_in.detection_rate", stopped / interruptions if interruptions else None, unit="ratio", threshold=1.0, sample_count=interruptions, reason="Interruption event was detected.", evidence=[]),
        _result("barge_in.stop_latency.p95", _percentile(stop_latencies, .95) if stop_latencies else None, unit="ms", threshold=250.0, lower_is_better=True, sample_count=len(stop_latencies), reason="Interruption detection to agent audio stop.", evidence=[]),
        _result("barge_in.recovery_success_rate", recovered / interruptions if interruptions else None, unit="ratio", threshold=1.0, sample_count=interruptions, reason="Annotated processing of the latest interrupted request.", evidence=[]),
        _result("silence.no_response_rate", no_response / deadline_turns if deadline_turns else None, unit="ratio", threshold=0.0, lower_is_better=True, sample_count=deadline_turns, reason="No first agent audio timestamp for a deadline-bound turn.", evidence=[]),
        _result("silence.long_silence_rate", long_silence / deadline_turns if deadline_turns else None, unit="ratio", threshold=0.0, lower_is_better=True, sample_count=deadline_turns, reason="First agent audio exceeds scenario response deadline.", evidence=[]),
        _result("silence.timeout_rate", timeout / deadline_turns if deadline_turns else None, unit="ratio", threshold=0.0, lower_is_better=True, sample_count=deadline_turns, reason="First agent audio is after scenario response deadline.", evidence=[]),
    ]


def _deepeval_judge_metrics(scenarios: list[dict[str, Any]], judge_model: Any) -> list[MetricResult]:
    """Opt-in judge metrics. Failures are isolated and represented as N/A."""
    from deepeval.metrics import AnswerRelevancyMetric, ContextualRelevancyMetric, FaithfulnessMetric, TaskCompletionMetric
    from deepeval.test_case import LLMTestCase
    results: list[MetricResult] = []
    for scenario in scenarios:
        conversation = scenario.get("conversation") or {}
        if not isinstance(conversation, dict):
            continue
        input_text = conversation.get("input")
        output = conversation.get("actual_output")
        if not isinstance(input_text, str) or not isinstance(output, str):
            continue
        test_case = LLMTestCase(input=input_text, actual_output=output, expected_output=conversation.get("expected_output"), retrieval_context=conversation.get("retrieval_context"))
        specs: list[tuple[str, Any]] = [("deepeval.answer_relevancy", AnswerRelevancyMetric(model=judge_model, threshold=0.85, async_mode=False))]
        if conversation.get("expected_outcome"):
            specs.append(("deepeval.task_completion", TaskCompletionMetric(model=judge_model, task=str(conversation["expected_outcome"]), threshold=0.85, async_mode=False)))
        if conversation.get("retrieval_context"):
            specs.extend([
                ("deepeval.rag.faithfulness", FaithfulnessMetric(model=judge_model, threshold=0.85, async_mode=False)),
                ("deepeval.rag.contextual_relevancy", ContextualRelevancyMetric(model=judge_model, threshold=0.85, async_mode=False)),
            ])
        for name, metric in specs:
            try:
                metric.measure(test_case, _show_indicator=False)
                results.append(_result(name, float(metric.score), unit="ratio", threshold=0.85, sample_count=1,
                                       reason=str(metric.reason or "DeepEval judge result."), evidence=[str(scenario.get("scenario_id", "unknown"))],
                                       source=f"deepeval:{type(metric).__name__}", configuration={"judge_model": str(judge_model)}))
            except Exception as exc:
                results.append(_result(name, None, unit="ratio", reason=f"DeepEval judge failed: {type(exc).__name__}: {exc}",
                                       source=f"deepeval:{type(metric).__name__}"))
    return results


def _deepeval_voice_metrics(scenarios: list[dict[str, Any]], judge_model: Any | None) -> list[MetricResult]:
    """Run DeepEval's audio-native metrics only when actual audio is supplied.

    A transcript or a duration is not treated as audio evidence: every eligible
    item must provide a local path/URL in ``voice_turns[].audio_path``.
    """
    names = [
        ("deepeval.voice.speech_intelligibility", "SpeechIntelligibilityMetric"),
        ("deepeval.voice.naturalness", "VoiceNaturalnessMetric"),
        ("deepeval.voice.consistency", "VoiceConsistencyMetric"),
        ("deepeval.voice.audio_integrity", "AudioIntegrityMetric"),
        ("deepeval.voice.turn_taking_naturalness", "TurnTakingNaturalnessMetric"),
        ("deepeval.voice.agent_responsiveness", "AgentResponsivenessMetric"),
        ("deepeval.voice.audio_glitch", "AudioGlitchMetric"),
    ]
    raw_turns: list[tuple[dict[str, Any], str]] = []
    for scenario in scenarios:
        for turn in scenario.get("voice_turns") or []:
            if isinstance(turn, dict) and turn.get("audio_path"):
                raw_turns.append((turn, str(scenario.get("scenario_id", "unknown"))))
    if not raw_turns:
        return [
            _result(name, None, unit="ratio", reason="No decodable voice_turns[].audio_path was supplied; transcript-only data is not audio evidence.",
                    source=f"deepeval:{class_name}")
            for name, class_name in names
        ]
    try:
        from deepeval.metrics import (
            AgentResponsivenessMetric, AudioGlitchMetric, AudioIntegrityMetric,
            SpeechIntelligibilityMetric, TurnTakingNaturalnessMetric,
            VoiceConsistencyMetric, VoiceNaturalnessMetric,
        )
        from deepeval.test_case import Audio, ConversationalTestCase, Turn
        turns = []
        for turn, _ in raw_turns:
            audio = Audio(
                url=str(turn["audio_path"]),
                start_time=turn.get("start_time_seconds"),
                duration=turn.get("duration_seconds"),
            )
            turns.append(Turn(
                role=str(turn.get("role", "assistant")),
                content=str(turn.get("content", "")),
                audio=audio,
                interrupted=turn.get("interrupted"),
            ))
        voice_case = ConversationalTestCase(turns=turns, voice=True)
        specs: list[tuple[str, str, Any]] = [
            ("deepeval.voice.speech_intelligibility", "SpeechIntelligibilityMetric", SpeechIntelligibilityMetric()),
            ("deepeval.voice.naturalness", "VoiceNaturalnessMetric", VoiceNaturalnessMetric()),
            ("deepeval.voice.consistency", "VoiceConsistencyMetric", VoiceConsistencyMetric()),
            ("deepeval.voice.audio_integrity", "AudioIntegrityMetric", AudioIntegrityMetric()),
            ("deepeval.voice.turn_taking_naturalness", "TurnTakingNaturalnessMetric", TurnTakingNaturalnessMetric()),
            ("deepeval.voice.agent_responsiveness", "AgentResponsivenessMetric", AgentResponsivenessMetric()),
        ]
        if judge_model is not None:
            specs.append(("deepeval.voice.audio_glitch", "AudioGlitchMetric", AudioGlitchMetric(model=judge_model, async_mode=False)))
        else:
            specs.append(("deepeval.voice.audio_glitch", "AudioGlitchMetric", None))
        output: list[MetricResult] = []
        evidence = sorted({scenario_id for _, scenario_id in raw_turns})
        for name, class_name, metric in specs:
            if metric is None:
                output.append(_result(name, None, unit="ratio", reason="AudioGlitchMetric requires an explicitly configured DeepEval judge model.", source=f"deepeval:{class_name}"))
                continue
            try:
                metric.measure(voice_case, _show_indicator=False)
                raw_score = getattr(metric, "score", None)
                output.append(_result(name, float(raw_score) if raw_score is not None else None, unit="ratio", threshold=.5,
                                      sample_count=len(raw_turns), reason=str(getattr(metric, "reason", "") or "No eligible audio."),
                                      evidence=evidence, source=f"deepeval:{class_name}"))
            except Exception as exc:
                output.append(_result(name, None, unit="ratio", reason=f"DeepEval voice metric failed: {type(exc).__name__}: {exc}", source=f"deepeval:{class_name}"))
        return output
    except Exception as exc:
        return [
            _result(name, None, unit="ratio", reason=f"Voice inputs could not be prepared: {type(exc).__name__}: {exc}", source=f"deepeval:{class_name}")
            for name, class_name in names
        ]


def evaluate_document(document: dict[str, Any], *, judge_model: Any | None = None) -> dict[str, Any]:
    if document.get("schema_version") not in {None, SCHEMA_VERSION}:
        raise ValueError(f"Unsupported schema_version: {document.get('schema_version')}")
    scenarios = [item for item in document.get("scenarios") or [] if isinstance(item, dict)]
    if not scenarios:
        raise ValueError("At least one scenario is required.")
    results = [
        *_stt_metrics(scenarios, key="stt_samples", prefix="stt"),
        *_latency_metrics(scenarios),
        *_turn_metrics(scenarios),
        *_task_reliability_metrics(scenarios),
        *_tool_metrics(scenarios),
        *_stt_metrics(scenarios, key="tts_samples", prefix="tts.intelligibility"),
        *_deepeval_voice_metrics(scenarios, judge_model),
    ]
    if judge_model is not None:
        results.extend(_deepeval_judge_metrics(scenarios, judge_model))
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_version": document.get("dataset_version", "unspecified"),
        "scenario_count": len(scenarios),
        "judge_enabled": judge_model is not None,
        "metrics": [result.as_dict() for result in results],
    }


def markdown_report(report: dict[str, Any]) -> str:
    lines = ["# Voice Agent Evaluation Report", "", f"- Schema: `{report['schema_version']}`", f"- Dataset: `{report['dataset_version']}`", f"- Scenarios: `{report['scenario_count']}`", f"- DeepEval judge: `{'enabled' if report['judge_enabled'] else 'disabled'}`", "", "| Metric | Raw value | Score | Status | Samples | Reason |", "| --- | ---: | ---: | --- | ---: | --- |"]
    for item in report["metrics"]:
        raw = "N/A" if item["raw_value"] is None else f"{item['raw_value']:.4f} {item['unit']}"
        score = "N/A" if item["normalized_score"] is None else f"{item['normalized_score']:.4f}"
        reason = str(item["reason"]).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| `{item['metric']}` | {raw} | {score} | {item['status']} | {item['sample_count']} | {reason} |")
    return "\n".join(lines) + "\n"


def evaluate_file(input_path: Path, output_directory: Path, *, judge_model: Any | None = None) -> tuple[Path, Path, dict[str, Any]]:
    document = json.loads(input_path.read_text(encoding="utf-8"))
    report = evaluate_document(document, judge_model=judge_model)
    output_directory.mkdir(parents=True, exist_ok=True)
    json_path = output_directory / "voice_agent_evaluation_report.json"
    markdown_path = output_directory / "voice_agent_evaluation_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(markdown_report(report), encoding="utf-8")
    return json_path, markdown_path, report

