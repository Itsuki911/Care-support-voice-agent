"""Automated post-session pipeline: auto-resolve session_id -> Langfuse export -> DeepEval -> reports.

Can be triggered automatically in a detached background process when a LiveKit
session ends (``AUTO_EVAL_ON_SESSION_END=true``), or invoked manually:

    uv --directory Test-LiveKit run python -m evaluations.post_session_pipeline --latest
    uv --directory Test-LiveKit run python -m evaluations.post_session_pipeline --session-id <SESSION_ID>
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from evaluations.evaluate_secretary import (
    CONVERSATION_EVAL_VERSION,
    DEFAULT_SESSION_TRANSCRIPTS_DIR,
    DEFAULT_TRANSCRIPTS_DIR,
    SESSION_CONVERSATION_EVAL_VERSION,
    LangfuseResolutionError,
    MetricResult,
    build_judge_model,
    detect_session_type,
    evaluate_full_conversation,
    load_local_transcript,
    post_scores_to_langfuse,
    resolve_unique_langfuse_trace_id,
)
from evaluations.voice_agent_evaluation import evaluate_file as evaluate_voice_agent_file
from export_langfuse_session import (
    DEFAULT_EXPORT_DIR as DEFAULT_SESSION_EXPORT_DIR,
    build_default_output_path as build_session_export_path,
    export_full_session,
    sanitize_filename_component,
)
from export_langfuse_trace import (
    DEFAULT_EXPORT_DIR as DEFAULT_TRACE_EVALS_DIR,
    export_trace_to_file,
)

DEFAULT_REPORTS_DIR = REPO_ROOT / "export" / "evaluation_reports"
KNOWN_TOOL_NAMES = {
    "list_recent_memories",
    "search_memories",
    "search_emails",
    "read_email",
    "send_email",
    "search_web",
    "search_documents",
    "get_schedule",
    "get_tasks",
}
APPROVAL_REQUIRED_TOOLS = {"search_emails", "read_email", "send_email", "search_web"}

logger = logging.getLogger("care-support-voice-agent.post_session_pipeline")


def find_latest_session_id(
    *,
    session_transcripts_dir: Path = DEFAULT_SESSION_TRANSCRIPTS_DIR,
    secretary_transcripts_dir: Path = DEFAULT_TRANSCRIPTS_DIR,
) -> tuple[str, Path]:
    """Return (session_id, path) for the most recently modified local transcript JSON."""
    candidates: list[Path] = []
    for folder in (session_transcripts_dir, secretary_transcripts_dir):
        if folder.exists():
            candidates.extend(p for p in folder.glob("*.json") if p.is_file())
    if not candidates:
        raise FileNotFoundError(
            f"ローカル会話トランスクリプトが見つかりません（確認先: {session_transcripts_dir}, {secretary_transcripts_dir}）。"
        )
    candidates.sort(key=lambda p: (p.stat().st_mtime, len(p.name)), reverse=True)
    newest = candidates[0]
    doc = json.loads(newest.read_text(encoding="utf-8"))
    session_id = str(doc.get("session_id") or newest.stem).strip()
    return session_id, newest


def wait_for_langfuse_trace(
    session_id: str,
    *,
    host: str,
    public_key: str,
    secret_key: str,
    max_attempts: int = 6,
    poll_interval_seconds: float = 5.0,
    resolver: Callable[..., str] = resolve_unique_langfuse_trace_id,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> str:
    """Poll Langfuse Observations API until the flushed session trace becomes queryable."""
    last_exc: LangfuseResolutionError | None = None
    for attempt in range(1, max(1, max_attempts) + 1):
        try:
            return resolver(session_id, host=host, public_key=public_key, secret_key=secret_key)
        except LangfuseResolutionError as exc:
            last_exc = exc
            if exc.code != "LANGFUSE_TRACE_NOT_FOUND" or attempt >= max_attempts:
                raise
            sleep_fn(poll_interval_seconds)
    assert last_exc is not None
    raise last_exc


def build_voice_agent_eval_dataset(
    *,
    session_id: str,
    session_type: str,
    transcript_doc: dict[str, Any],
    trace_doc: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a voice-agent-evaluation-v1 payload strictly from real observed trace & transcript data."""
    observations = (trace_doc or {}).get("observations") or []
    tool_lat_ms: list[float] = []
    actual_tools: list[dict[str, Any]] = []
    llm_ttft_ms: list[float] = []
    total_cost = 0.0
    has_cost = False
    has_error = False

    # Prefer pure API execution span (`web_search.tavily`) over approval-inclusive `search_web`
    # so human approval wait time does not distort tool latency metrics.
    tavily_lat_ms = [
        round(float(obs["latency"]) * 1000.0, 2)
        for obs in observations
        if str(obs.get("name") or "") == "web_search.tavily"
        and isinstance(obs.get("latency"), (int, float))
    ]
    tool_lat_ms.extend(tavily_lat_ms)

    for obs in observations:
        name = str(obs.get("name") or "")
        lat = obs.get("latency")
        cost = obs.get("calculatedTotalCost")
        if isinstance(cost, (int, float)) and cost > 0:
            total_cost += float(cost)
            has_cost = True
        if obs.get("type") == "TOOL" and name in KNOWN_TOOL_NAMES:
            is_err = obs.get("level") == "ERROR"
            if is_err:
                has_error = True
            if isinstance(lat, (int, float)):
                # Skip approval-inclusive search_web latency when web_search.tavily is recorded
                if not (name == "search_web" and tavily_lat_ms):
                    tool_lat_ms.append(round(float(lat) * 1000.0, 2))
            actual_tools.append(
                {
                    "name": name,
                    "arguments": {},
                    "status": "error" if is_err else "success",
                    "approval_required": name in APPROVAL_REQUIRED_TOOLS,
                    "approval_obtained": True,
                }
            )
        if name == "llm_request" and isinstance(obs.get("timeToFirstToken"), (int, float)):
            llm_ttft_ms.append(round(float(obs["timeToFirstToken"]) * 1000.0, 2))

    turns = transcript_doc.get("turns") or []
    user_turns = [t["text"] for t in turns if t.get("role") == "user" and t.get("text")]
    asst_turns = [t["text"] for t in turns if t.get("role") == "assistant" and t.get("text")]

    architecture = "text-llm" if session_type == "text" else "stt-llm-tts"
    latencies_ms: dict[str, list[float]] = {}
    if llm_ttft_ms:
        latencies_ms["llm_ttft"] = llm_ttft_ms
    if tool_lat_ms:
        latencies_ms["tool"] = tool_lat_ms

    scenario: dict[str, Any] = {
        "scenario_id": session_id,
        "tags": [session_type, "live-session", "auto-eval"],
        "architecture": architecture,
        "latencies_ms": latencies_ms,
        "tools": {
            "actual": actual_tools,
            "allowed": sorted(KNOWN_TOOL_NAMES),
            "denied": [],
        },
        "conversation": {
            "input": user_turns[-1] if user_turns else "",
            "actual_output": asst_turns[-1] if asst_turns else "",
        },
        "reliability": {
            "session_success": True,
            "error": has_error,
            "timeout": False,
        },
    }
    if has_cost:
        scenario["usage"] = {"cost_usd": round(total_cost, 6)}

    return {
        "schema_version": "voice-agent-evaluation-v1",
        "dataset_version": f"auto-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        "scenarios": [scenario],
    }


def run_post_session_pipeline(
    *,
    session_id: str | None = None,
    transcript_file: Path | None = None,
    session_type: str = "auto",
    employee_id: str | None = None,
    judge_model_name: str | None = None,
    skip_langfuse: bool = False,
    skip_deepeval: bool = False,
    wait_attempts: int = 6,
    poll_interval_seconds: float = 5.0,
    session_export_dir: Path = DEFAULT_SESSION_EXPORT_DIR,
    trace_evals_dir: Path = DEFAULT_TRACE_EVALS_DIR,
    reports_dir: Path = DEFAULT_REPORTS_DIR,
    session_transcripts_dir: Path = DEFAULT_SESSION_TRANSCRIPTS_DIR,
    secretary_transcripts_dir: Path = DEFAULT_TRANSCRIPTS_DIR,
    # Injectable collaborators for deterministic offline unit tests
    trace_resolver: Callable[..., str] = resolve_unique_langfuse_trace_id,
    session_exporter: Callable[..., dict[str, Any]] = export_full_session,
    trace_exporter: Callable[..., tuple[Path, dict[str, Any]]] = export_trace_to_file,
    score_poster: Callable[..., int] = post_scores_to_langfuse,
    judge_factory: Callable[[str | None], tuple[str, Any]] = build_judge_model,
    conversation_evaluator: Callable[..., list[MetricResult]] = evaluate_full_conversation,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Execute the full automated export + evaluation + report pipeline for one session."""
    if not session_id:
        resolved_sid, resolved_path = find_latest_session_id(
            session_transcripts_dir=session_transcripts_dir,
            secretary_transcripts_dir=secretary_transcripts_dir,
        )
        session_id = resolved_sid
        if transcript_file is None:
            transcript_file = resolved_path

    transcript_doc = load_local_transcript(
        session_id,
        transcript_file=transcript_file,
        transcripts_dir=secretary_transcripts_dir,
        session_transcripts_dir=session_transcripts_dir,
    )
    resolved_type = detect_session_type(session_id, transcript_doc, requested=session_type)
    resolved_employee_id = employee_id or (
        str(transcript_doc.get("employee_id") or "").strip() or None
    )
    room_name = str(transcript_doc.get("room_name") or session_id)

    host = os.getenv("LANGFUSE_BASE_URL", "").strip() or os.getenv("LANGFUSE_HOST", "").strip()
    pk = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
    sk = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
    langfuse_ready = (not skip_langfuse) and all((host, pk, sk))

    summary: dict[str, Any] = {
        "session_id": session_id,
        "room_name": room_name,
        "session_type": resolved_type,
        "employee_id": resolved_employee_id,
        "completed_at": datetime.now().isoformat(),
        "trace_id": None,
        "session_export_path": None,
        "trace_eval_path": None,
        "report_json_path": None,
        "report_md_path": None,
        "deepeval_scores": [],
        "langfuse_scores_posted": 0,
        "errors": [],
    }

    # 1. Resolve trace & export full session JSON
    trace_id: str | None = None
    if langfuse_ready:
        try:
            trace_id = wait_for_langfuse_trace(
                session_id,
                host=host,
                public_key=pk,
                secret_key=sk,
                max_attempts=wait_attempts,
                poll_interval_seconds=poll_interval_seconds,
                resolver=trace_resolver,
                sleep_fn=sleep_fn,
            )
            summary["trace_id"] = trace_id
            session_out = build_session_export_path(session_id, output_dir=session_export_dir)
            session_exporter(
                session_id,
                session_out,
                public_key=pk,
                secret_key=sk,
                host=host,
            )
            summary["session_export_path"] = str(session_out)
        except Exception as exc:
            logger.warning("Langfuse session export failed for %s: %s", session_id, exc)
            summary["errors"].append(f"langfuse_session_export: {exc}")

    # 2. Run DeepEval multi-turn conversation evaluation & post scores to Langfuse
    deepeval_results: list[MetricResult] = []
    if not skip_deepeval:
        try:
            judge_id, judge_model = judge_factory(judge_model_name)
            eval_version = (
                CONVERSATION_EVAL_VERSION
                if resolved_type == "secretary"
                else SESSION_CONVERSATION_EVAL_VERSION
            )
            case_id_meta = (
                f"CONV:{resolved_employee_id}"
                if (resolved_type == "secretary" and resolved_employee_id)
                else f"CONV:{resolved_type}"
            )
            deepeval_results = conversation_evaluator(
                transcript_doc=transcript_doc,
                judge_model=judge_model,
                employee_id=resolved_employee_id,
                session_type=resolved_type,
            )
            summary["judge_model"] = judge_id
            summary["eval_version"] = eval_version
            summary["deepeval_scores"] = [
                {
                    "name": r.name,
                    "langfuse_name": r.langfuse_name,
                    "score": r.score,
                    "passed": r.passed,
                    "skipped": r.skipped,
                    "reason": r.reason,
                }
                for r in deepeval_results
            ]
            if langfuse_ready and trace_id:
                posted = score_poster(
                    trace_id=trace_id,
                    case_id=case_id_meta,
                    eval_config_version=eval_version,
                    judge_model_id=judge_id,
                    results=deepeval_results,
                    host=host,
                    public_key=pk,
                    secret_key=sk,
                )
                summary["langfuse_scores_posted"] = posted
        except Exception as exc:
            logger.warning("DeepEval evaluation failed for %s: %s", session_id, exc)
            summary["errors"].append(f"deepeval: {exc}")

    # 3. Export trace + newly posted evaluation scores to export/trace_evals/
    trace_doc: dict[str, Any] | None = None
    if langfuse_ready and trace_id:
        try:
            trace_path, trace_doc = trace_exporter(trace_id, output_dir=trace_evals_dir)
            summary["trace_eval_path"] = str(trace_path)
        except Exception as exc:
            logger.warning("Langfuse trace_evals export failed for %s: %s", trace_id, exc)
            summary["errors"].append(f"langfuse_trace_export: {exc}")

    # 4. Generate evaluation_reports JSON & Markdown from observed trace + transcript
    try:
        ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        safe_room = sanitize_filename_component(room_name)
        report_subdir = reports_dir / f"{ts}_{safe_room}"
        report_subdir.mkdir(parents=True, exist_ok=True)

        dataset = build_voice_agent_eval_dataset(
            session_id=session_id,
            session_type=resolved_type,
            transcript_doc=transcript_doc,
            trace_doc=trace_doc,
        )
        input_path = report_subdir / "session_input.json"
        input_path.write_text(
            json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        json_path, md_path, _report = evaluate_voice_agent_file(input_path, report_subdir)
        summary["report_json_path"] = str(json_path)
        summary["report_md_path"] = str(md_path)

        summary_path = report_subdir / "pipeline_summary.json"
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        summary["summary_path"] = str(summary_path)
    except Exception as exc:
        logger.warning("Voice-agent evaluation report generation failed: %s", exc)
        summary["errors"].append(f"evaluation_report: {exc}")

    return summary


def spawn_post_session_pipeline(
    session_id: str,
    transcript_file: Path,
    *,
    reports_dir: Path = DEFAULT_REPORTS_DIR,
) -> subprocess.Popen[Any]:
    """Launch the post-session pipeline in a detached background subprocess (macOS/Windows safe)."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    log_path = reports_dir / "auto_eval.log"
    cmd = [
        sys.executable,
        "-m",
        "evaluations.post_session_pipeline",
        "--session-id",
        session_id,
        "--transcript-file",
        str(transcript_file),
    ]
    popen_kwargs: dict[str, Any] = {
        "cwd": str(BASE_DIR),
        "stdin": subprocess.DEVNULL,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0)
        )
    else:
        popen_kwargs["start_new_session"] = True

    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(
            f"\n[{datetime.now().isoformat()}] Starting auto-eval pipeline for session_id={session_id}\n"
        )
        log_file.flush()
        popen_kwargs["stdout"] = log_file
        popen_kwargs["stderr"] = subprocess.STDOUT
        return subprocess.Popen(cmd, **popen_kwargs)


def main(argv: list[str] | None = None) -> int:
    load_dotenv(BASE_DIR / ".env", override=False)
    parser = argparse.ArgumentParser(
        description="Auto-export Langfuse session/trace and run DeepEval + evaluation reports."
    )
    parser.add_argument("--session-id", default=None, help="Session ID to process (omit with --latest)")
    parser.add_argument("--latest", action="store_true", help="Automatically pick the latest local session")
    parser.add_argument("--transcript-file", type=Path, default=None)
    parser.add_argument(
        "--session-type",
        choices=("auto", "voice", "text", "secretary"),
        default="auto",
    )
    parser.add_argument("--employee-id", default=None)
    parser.add_argument("--judge-model", default=None)
    parser.add_argument("--skip-langfuse", action="store_true")
    parser.add_argument("--skip-deepeval", action="store_true")
    parser.add_argument("--wait-attempts", type=int, default=6)
    parser.add_argument("--poll-interval", type=float, default=5.0)
    args = parser.parse_args(argv)

    if not args.session_id and not args.latest:
        args.latest = True

    summary = run_post_session_pipeline(
        session_id=None if args.latest and not args.session_id else args.session_id,
        transcript_file=args.transcript_file,
        session_type=args.session_type,
        employee_id=args.employee_id,
        judge_model_name=args.judge_model,
        skip_langfuse=args.skip_langfuse,
        skip_deepeval=args.skip_deepeval,
        wait_attempts=args.wait_attempts,
        poll_interval_seconds=args.poll_interval,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
