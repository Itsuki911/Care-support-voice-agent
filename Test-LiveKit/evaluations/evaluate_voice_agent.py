"""CLI for the provider-neutral voice-agent evaluator."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent
DEFAULT_REPORTS_DIR = REPO_ROOT / "export" / "evaluation_reports"
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from evaluations.voice_agent_evaluation import evaluate_file


def run_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate a voice-agent event dataset")
    parser.add_argument("--input", type=Path, required=True, help="voice-agent-evaluation-v1 JSON file")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--deepeval-judge", action="store_true", help="Run opt-in DeepEval LLM-as-a-judge metrics (requires judge API key).")
    parser.add_argument("--judge-model", default=None)
    args = parser.parse_args(argv)
    load_dotenv(BASE_DIR / ".env", override=False)
    judge_model = None
    if args.deepeval_judge:
        from evaluations.evaluate_secretary import build_judge_model
        _, judge_model = build_judge_model(args.judge_model)
    json_path, markdown_path, report = evaluate_file(args.input, args.output_dir, judge_model=judge_model)
    failed = sum(item["status"] == "FAIL" for item in report["metrics"])
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {markdown_path}")
    print(f"Metrics: {len(report['metrics'])}; failed gates: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(run_cli())
