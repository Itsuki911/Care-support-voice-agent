"""Manual CLI evaluation for TEST-Secretary mode using DeepEval and Langfuse Scores API."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import httpx
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CASES_PATH = Path(__file__).resolve().parent / "secretary_cases.json"
DEFAULT_TRANSCRIPTS_DIR = Path(__file__).resolve().parent / "transcripts"


class LangfuseResolutionError(Exception):
    """Raised when a Langfuse trace cannot be uniquely resolved or API fails."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class MetricResult:
    name: str
    langfuse_name: str
    score: float | None
    passed: bool | None
    reason: str
    skipped: bool = False


def load_case(case_id: str, cases_path: Path = DEFAULT_CASES_PATH) -> tuple[str, dict[str, Any]]:
    doc = json.loads(cases_path.read_text(encoding="utf-8"))
    eval_version = str(doc.get("eval_config_version") or "secretary-eval-v1")
    for case in doc.get("cases") or []:
        if case.get("case_id") == case_id:
            return eval_version, case
    raise ValueError(f"Unknown case_id: {case_id}")


def load_local_transcript(
    session_id: str,
    *,
    transcript_file: Path | None = None,
    transcripts_dir: Path = DEFAULT_TRANSCRIPTS_DIR,
) -> dict[str, Any]:
    path = transcript_file or (transcripts_dir / f"{session_id}.json")
    if not path.exists():
        raise FileNotFoundError(
            f"ローカルトランスクリプトが見つかりません: {path}（TEST-秘書モードの通話終了後に生成されます）"
        )
    doc = json.loads(path.read_text(encoding="utf-8"))
    turns = doc.get("turns") or []
    if not turns:
        raise ValueError(f"確定発話が空です: {path}")
    return doc


def build_judge_model(model_id: str | None = None) -> tuple[str, Any]:
    from deepeval.models import OpenAIModel

    resolved_model = (
        model_id
        or os.getenv("EVAL_JUDGE_MODEL", "").strip()
        or os.getenv("OPENROUTER_MODEL", "").strip()
        or "openai/gpt-6-luna"
    )
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    if openrouter_key:
        return resolved_model, OpenAIModel(
            model=resolved_model,
            api_key=openrouter_key,
            base_url="https://openrouter.ai/api/v1",
            temperature=0.0,
        )
    if openai_key:
        return resolved_model, OpenAIModel(
            model=resolved_model,
            api_key=openai_key,
            temperature=0.0,
        )
    raise RuntimeError("Judge 用の OPENROUTER_API_KEY または OPENAI_API_KEY が設定されていません。")


def evaluate_transcript(
    *,
    case: dict[str, Any],
    transcript_doc: dict[str, Any],
    judge_model: Any,
    threshold: float = 0.7,
) -> list[MetricResult]:
    from deepeval.metrics import ConversationalGEval, GEval
    from deepeval.test_case import (
        ConversationalTestCase,
        LLMTestCase,
        MultiTurnParams,
        SingleTurnParams,
        Turn,
    )

    turns_raw = transcript_doc.get("turns") or []
    user_turns = [t["text"] for t in turns_raw if t.get("role") == "user" and t.get("text")]
    asst_turns = [t["text"] for t in turns_raw if t.get("role") == "assistant" and t.get("text")]
    if not user_turns or not asst_turns:
        raise ValueError("評価に必要なユーザー発話およびAI回答が揃っていません。")

    actual_output = asst_turns[-1]
    input_text = user_turns[-1]

    geval = GEval(
        name="FinalAnswerAccuracy",
        evaluation_params=[
            SingleTurnParams.INPUT,
            SingleTurnParams.ACTUAL_OUTPUT,
            SingleTurnParams.EXPECTED_OUTPUT,
        ],
        criteria=(
            "最終回答（actual_output）がユーザーの質問（input）に対して正しく、"
            "期待される予定名・時刻・タスク名、または0件である旨を過不足なく伝えているか評価する。"
        ),
        model=judge_model,
        threshold=threshold,
        async_mode=False,
    )
    single_case = LLMTestCase(
        input=input_text,
        actual_output=actual_output,
        expected_output=case["expected_output"],
    )
    geval.measure(single_case)
    results = [
        MetricResult(
            name="GEval (FinalAnswerAccuracy)",
            langfuse_name="secretary.final_answer_accuracy",
            score=float(geval.score) if geval.score is not None else 0.0,
            passed=bool(geval.is_successful()),
            reason=str(geval.reason or ""),
        )
    ]

    if case.get("has_correction"):
        conv_geval = ConversationalGEval(
            name="CorrectionFollowup",
            evaluation_params=[MultiTurnParams.ROLE, MultiTurnParams.CONTENT],
            evaluation_steps=[
                "会話中のユーザー発話を確認し、途中の言い直し・訂正がある場合は最後の依頼を特定する。",
                "AIの最終回答が訂正前の古い依頼（例: 明日の予定）ではなく、訂正後の最後の依頼（例: 今日の締切）に沿って答えているか判定する。",
                "訂正前の依頼内容をそのまま案内していた場合は低スコア（不合格）とする。",
            ],
            model=judge_model,
            threshold=threshold,
            async_mode=False,
        )
        conv_turns = [
            Turn(role="user" if t["role"] == "user" else "assistant", content=t["text"])
            for t in turns_raw
            if t.get("text")
        ]
        conv_geval.measure(ConversationalTestCase(turns=conv_turns))
        results.append(
            MetricResult(
                name="ConversationalGEval (CorrectionFollowup)",
                langfuse_name="secretary.correction_followup",
                score=float(conv_geval.score) if conv_geval.score is not None else 0.0,
                passed=bool(conv_geval.is_successful()),
                reason=str(conv_geval.reason or ""),
            )
        )
    else:
        results.append(
            MetricResult(
                name="ConversationalGEval (CorrectionFollowup)",
                langfuse_name="secretary.correction_followup",
                score=None,
                passed=None,
                reason="訂正なしのケースのため対象外（SKIPPED）",
                skipped=True,
            )
        )

    return results


def _langfuse_auth_header(public_key: str, secret_key: str) -> str:
    token = base64.b64encode(f"{public_key}:{secret_key}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def resolve_unique_langfuse_trace_id(
    session_id: str,
    *,
    host: str,
    public_key: str,
    secret_key: str,
    http_client: httpx.Client | None = None,
) -> str:
    base_url = host.strip().rstrip("/")
    headers = {
        "Authorization": _langfuse_auth_header(public_key, secret_key),
        "Accept": "application/json",
    }
    url = f"{base_url}/api/public/v2/observations"
    params = {"sessionId": session_id, "limit": 100, "fields": "core"}
    try:
        if http_client is not None:
            resp = http_client.get(url, params=params, headers=headers)
        else:
            with httpx.Client(timeout=20.0) as client:
                resp = client.get(url, params=params, headers=headers)
    except httpx.HTTPError as exc:
        raise LangfuseResolutionError(
            "LANGFUSE_API_ERROR", f"Langfuse API への接続に失敗しました: {exc}"
        ) from None

    if resp.status_code >= 400:
        raise LangfuseResolutionError(
            "LANGFUSE_API_ERROR",
            f"Langfuse Observations API が HTTP {resp.status_code} を返しました。",
        )

    payload = resp.json()
    trace_ids = sorted(
        {
            str(obs.get("traceId"))
            for obs in (payload.get("data") or [])
            if obs.get("traceId")
        }
    )
    if len(trace_ids) == 0:
        raise LangfuseResolutionError(
            "LANGFUSE_TRACE_NOT_FOUND",
            f"session_id={session_id} に対応する Langfuse トレースが見つかりません。",
        )
    if len(trace_ids) > 1:
        raise LangfuseResolutionError(
            "LANGFUSE_TRACE_AMBIGUOUS",
            f"session_id={session_id} に対して複数（{len(trace_ids)}件）のトレースが存在し、一意に解決できません。",
        )
    return trace_ids[0]


def post_scores_to_langfuse(
    *,
    trace_id: str,
    case_id: str,
    eval_config_version: str,
    judge_model_id: str,
    results: list[MetricResult],
    host: str,
    public_key: str,
    secret_key: str,
    http_client: httpx.Client | None = None,
) -> int:
    base_url = host.strip().rstrip("/")
    headers = {
        "Authorization": _langfuse_auth_header(public_key, secret_key),
        "Content-Type": "application/json",
    }
    url = f"{base_url}/api/public/scores"
    posted = 0
    for r in results:
        if r.skipped or r.score is None:
            continue
        verdict = "PASS" if r.passed else "FAIL"
        # Strictly PII-free comment: never includes transcript, employee name, or schedule details.
        safe_comment = (
            f"[{verdict}] case={case_id} eval_version={eval_config_version} "
            f"judge={judge_model_id} score={r.score:.2f} (PII redacted; see local CLI output)"
        )
        body = {
            "traceId": trace_id,
            "name": r.langfuse_name,
            "value": round(r.score, 4),
            "dataType": "NUMERIC",
            "comment": safe_comment,
            "metadata": {
                "case_id": case_id,
                "eval_config_version": eval_config_version,
                "judge_model_id": judge_model_id,
                "passed": bool(r.passed),
            },
        }
        try:
            if http_client is not None:
                resp = http_client.post(url, json=body, headers=headers)
            else:
                with httpx.Client(timeout=20.0) as client:
                    resp = client.post(url, json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise LangfuseResolutionError(
                "LANGFUSE_API_ERROR", f"Langfuse Scores API 送信に失敗しました: {exc}"
            ) from None
        if resp.status_code >= 400:
            raise LangfuseResolutionError(
                "LANGFUSE_API_ERROR",
                f"Langfuse Scores API が HTTP {resp.status_code} を返しました。",
            )
        posted += 1
    return posted


def run_cli(argv: list[str] | None = None) -> int:
    load_dotenv(BASE_DIR / ".env", override=False)
    parser = argparse.ArgumentParser(description="Evaluate a TEST-Secretary call with DeepEval")
    parser.add_argument("--case-id", required=True, help="Case ID from secretary_cases.json")
    parser.add_argument("--session-id", required=True, help="Session ID / room name to evaluate")
    parser.add_argument("--transcript-file", type=Path, default=None)
    parser.add_argument("--judge-model", default=None)
    parser.add_argument("--skip-langfuse", action="store_true")
    args = parser.parse_args(argv)

    eval_version, case = load_case(args.case_id)
    transcript_doc = load_local_transcript(args.session_id, transcript_file=args.transcript_file)
    judge_model_id, judge_model = build_judge_model(args.judge_model)
    results = evaluate_transcript(
        case=case,
        transcript_doc=transcript_doc,
        judge_model=judge_model,
    )

    print(f"=== TEST-秘書モード 手動評価結果 ===")
    print(f"Case ID      : {args.case_id} ({case.get('description', '')})")
    print(f"Session ID   : {args.session_id}")
    print(f"Eval Version : {eval_version}")
    print(f"Judge Model  : {judge_model_id}")
    print("-" * 50)
    all_passed = True
    for r in results:
        if r.skipped:
            print(f"[SKIP] {r.name}: {r.reason}")
            continue
        verdict = "PASS" if r.passed else "FAIL"
        if not r.passed:
            all_passed = False
        print(f"[{verdict}] {r.name}: score={r.score:.3f}")
        print(f"  理由: {r.reason}")

    if not args.skip_langfuse:
        host = os.getenv("LANGFUSE_BASE_URL", "").strip() or os.getenv("LANGFUSE_HOST", "").strip()
        pk = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
        sk = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
        if not all((host, pk, sk)):
            print("[INFRA_ERROR: LANGFUSE_CONFIG_MISSING] Langfuse 接続情報が不足しているため登録をスキップしました。")
            return 2
        try:
            trace_id = resolve_unique_langfuse_trace_id(
                args.session_id, host=host, public_key=pk, secret_key=sk
            )
            posted = post_scores_to_langfuse(
                trace_id=trace_id,
                case_id=args.case_id,
                eval_config_version=eval_version,
                judge_model_id=judge_model_id,
                results=results,
                host=host,
                public_key=pk,
                secret_key=sk,
            )
            print(f"Langfuse スコア登録完了: trace_id={trace_id} ({posted}件)")
        except LangfuseResolutionError as exc:
            print(f"[INFRA_ERROR: {exc.code}] {exc}")
            return 2

    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(run_cli())
