"""Export a single Langfuse v4 trace (observations + evaluation scores) to export/trace_evals/.

Credentials and host are loaded from Test-LiveKit/.env (LANGFUSE_PUBLIC_KEY,
LANGFUSE_SECRET_KEY, LANGFUSE_BASE_URL / LANGFUSE_HOST).

Usage:
    uv --directory Test-LiveKit run python export_langfuse_trace.py <TRACE_ID>
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent
DEFAULT_EXPORT_DIR = REPO_ROOT / "export" / "trace_evals"
DEFAULT_TIMEOUT_SECONDS = 30
OBSERVATION_FIELDS = "core,basic,time,io,metadata,model,usage,prompt,metrics"


def sanitize_filename_component(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    cleaned = cleaned.strip("._")
    if not cleaned:
        raise ValueError("trace_id must contain at least one valid character")
    return cleaned


def _make_auth_header(public_key: str, secret_key: str) -> str:
    token = base64.b64encode(f"{public_key}:{secret_key}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def _default_get_json(
    url: str, headers: dict[str, str], timeout: int = DEFAULT_TIMEOUT_SECONDS
) -> dict[str, Any]:
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            pass
        detail = f" ({body})" if body else ""
        raise RuntimeError(f"Langfuse API returned HTTP {exc.code} for {url}{detail}") from None
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Failed to connect to Langfuse API: {exc.reason}") from None


def _observation_cost(obs: dict[str, Any]) -> float:
    for key in ("totalCost", "calculatedTotalCost"):
        val = obs.get(key)
        if isinstance(val, (int, float)):
            return float(val)
    return 0.0


def fetch_trace_export(
    trace_id: str,
    *,
    public_key: str,
    secret_key: str,
    host: str,
    get_json: Callable[[str, dict[str, str]], dict[str, Any]] | None = None,
    page_limit: int = 100,
    fields: str = OBSERVATION_FIELDS,
) -> dict[str, Any]:
    """Fetch all observations and scores for a Langfuse v4 trace_id."""
    if not trace_id or not trace_id.strip():
        raise ValueError("trace_id is required")

    base_url = host.strip().rstrip("/")
    if not base_url.startswith(("https://", "http://")):
        raise ValueError("Langfuse host must start with http:// or https://")

    headers = {
        "Authorization": _make_auth_header(public_key, secret_key),
        "Accept": "application/json",
    }
    fetcher = get_json or _default_get_json

    observations: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        params: dict[str, Any] = {
            "traceId": trace_id,
            "limit": page_limit,
            "fields": fields,
        }
        if cursor:
            params["cursor"] = cursor
        url = f"{base_url}/api/public/v2/observations?{urllib.parse.urlencode(params)}"
        payload = fetcher(url, headers)
        batch = payload.get("data") or []
        observations.extend(batch)
        next_cursor = (payload.get("meta") or {}).get("cursor")
        if not next_cursor or not batch:
            break
        cursor = str(next_cursor)

    # Fetch scores attached to this trace_id (v3 on Langfuse v4, fallback to v2).
    scores: list[dict[str, Any]] = []
    score_endpoints = ("/api/public/v3/scores", "/api/public/v2/scores")
    for endpoint in score_endpoints:
        try:
            score_cursor: str | None = None
            page = 1
            while True:
                params = {"traceId": trace_id, "limit": page_limit}
                if score_cursor:
                    params["cursor"] = score_cursor
                elif endpoint.endswith("/v2/scores"):
                    params["page"] = page
                url = f"{base_url}{endpoint}?{urllib.parse.urlencode(params)}"
                payload = fetcher(url, headers)
                batch = payload.get("data") or []
                scores.extend(batch)
                meta = payload.get("meta") or {}
                next_cursor = meta.get("cursor")
                total_pages = meta.get("totalPages")
                if next_cursor and batch:
                    score_cursor = str(next_cursor)
                    continue
                if not batch or (isinstance(total_pages, int) and page >= total_pages) or len(batch) < page_limit:
                    break
                page += 1
            break
        except RuntimeError as exc:
            if endpoint == score_endpoints[-1]:
                raise
            if "HTTP 404" not in str(exc) and "HTTP 410" not in str(exc):
                raise

    session_id = ""
    for obs in observations:
        sid = obs.get("sessionId")
        if isinstance(sid, str) and sid.strip():
            session_id = sid.strip()
            break
        meta = obs.get("metadata") or {}
        if isinstance(meta, dict):
            msid = meta.get("attributes.langfuse.session.id")
            if isinstance(msid, str) and msid.strip():
                session_id = msid.strip()
                break

    total_cost = round(sum(_observation_cost(obs) for obs in observations), 12)
    return {
        "trace_id": trace_id,
        "session_id": session_id,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "observation_count": len(observations),
        "score_count": len(scores),
        "total_cost": total_cost,
        "scores": scores,
        "observations": observations,
    }


def export_trace_to_file(
    trace_id: str,
    *,
    output_dir: Path = DEFAULT_EXPORT_DIR,
    env_path: Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    load_dotenv(env_path or (BASE_DIR / ".env"), override=False)
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
    secret_key = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
    host = (
        os.getenv("LANGFUSE_BASE_URL", "").strip()
        or os.getenv("LANGFUSE_HOST", "").strip()
    )
    if not all((public_key, secret_key, host)):
        raise RuntimeError(
            "LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_BASE_URL (or LANGFUSE_HOST) are required."
        )

    data = fetch_trace_export(
        trace_id,
        public_key=public_key,
        secret_key=secret_key,
        host=host,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    safe_id = sanitize_filename_component(trace_id)
    out_path = output_dir / f"{ts}_langfuse_trace_{safe_id}.json"
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path, data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export a Langfuse v4 trace (observations + scores) to export/trace_evals/."
    )
    parser.add_argument("trace_id", help="Langfuse trace_id to export")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_EXPORT_DIR,
        help=f"Output directory (default: {DEFAULT_EXPORT_DIR})",
    )
    args = parser.parse_args(argv)
    try:
        out_path, data = export_trace_to_file(args.trace_id, output_dir=args.output_dir)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        f"完了: trace_id={data['trace_id']}（observation={data['observation_count']}件, "
        f"score={data['score_count']}件）を {out_path} に保存しました。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
