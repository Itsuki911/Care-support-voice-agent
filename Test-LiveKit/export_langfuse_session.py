"""Export full Langfuse v4 session traces and observations to a local JSON file.

Credentials and host are loaded from Test-LiveKit/.env (LANGFUSE_PUBLIC_KEY,
LANGFUSE_SECRET_KEY, LANGFUSE_BASE_URL / LANGFUSE_HOST).

Uses Langfuse Observations API v2 (`GET /api/public/v2/observations`), since
legacy v1 `/api/public/traces` returns HTTP 410 Gone on Langfuse v4.

Usage:
    cd Test-LiveKit
    uv run python export_langfuse_session.py <SESSION_ID>
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
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent
DEFAULT_EXPORT_DIR = REPO_ROOT / "export"
DEFAULT_TIMEOUT_SECONDS = 30
OBSERVATION_FIELDS = "core,basic,time,io,metadata,model,usage,prompt,metrics"


def sanitize_filename_component(value: str) -> str:
    """Keep filenames safe and confined to the export directory."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    cleaned = cleaned.strip("._")
    if not cleaned:
        raise ValueError("session_id must contain at least one valid character")
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


def fetch_session_export(
    session_id: str,
    *,
    public_key: str,
    secret_key: str,
    host: str,
    get_json: Callable[[str, dict[str, str]], dict[str, Any]] | None = None,
    page_limit: int = 100,
    fields: str = OBSERVATION_FIELDS,
) -> dict[str, Any]:
    """Fetch all observations for a Langfuse v4 session_id and group them by traceId."""
    if not session_id or not session_id.strip():
        raise ValueError("session_id is required")

    base_url = host.strip().rstrip("/")
    if not base_url.startswith(("https://", "http://")):
        raise ValueError("Langfuse host must start with http:// or https://")

    headers = {
        "Authorization": _make_auth_header(public_key, secret_key),
        "Accept": "application/json",
    }
    fetcher = get_json or _default_get_json

    all_observations: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        params: dict[str, Any] = {
            "sessionId": session_id,
            "limit": page_limit,
            "fields": fields,
        }
        if cursor:
            params["cursor"] = cursor
        url = f"{base_url}/api/public/v2/observations?{urllib.parse.urlencode(params)}"
        payload = fetcher(url, headers)
        batch = payload.get("data") or []
        all_observations.extend(batch)
        meta = payload.get("meta") or {}
        next_cursor = meta.get("cursor")
        if not next_cursor or not batch:
            break
        cursor = str(next_cursor)

    grouped: dict[str, list[dict[str, Any]]] = {}
    for obs in all_observations:
        trace_id = str(obs.get("traceId") or "unknown")
        grouped.setdefault(trace_id, []).append(obs)

    detailed_traces: list[dict[str, Any]] = []
    for trace_id, observations in grouped.items():
        observations.sort(key=lambda o: str(o.get("startTime") or ""))
        trace_cost = sum(_observation_cost(o) for o in observations)
        root_obs = next((o for o in observations if not o.get("parentObservationId")), None)
        detailed_traces.append(
            {
                "id": trace_id,
                "startTime": observations[0].get("startTime") if observations else None,
                "rootObservationId": root_obs.get("id") if root_obs else None,
                "rootObservationName": root_obs.get("name") if root_obs else None,
                "totalCost": trace_cost,
                "observationCount": len(observations),
                "observations": observations,
            }
        )

    detailed_traces.sort(key=lambda t: str(t.get("startTime") or ""))
    total_cost = sum(float(t.get("totalCost") or 0.0) for t in detailed_traces)

    return {
        "session_id": session_id,
        "trace_count": len(detailed_traces),
        "observation_count": len(all_observations),
        "total_cost": total_cost,
        "traces": detailed_traces,
    }


def export_full_session(
    session_id: str,
    output_path: Path,
    *,
    public_key: str,
    secret_key: str,
    host: str,
    get_json: Callable[[str, dict[str, str]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Fetch a Langfuse session and write it to output_path as UTF-8 JSON."""
    export_payload = fetch_session_export(
        session_id,
        public_key=public_key,
        secret_key=secret_key,
        host=host,
        get_json=get_json,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(export_payload, f, ensure_ascii=False, indent=2, default=str)
    return export_payload


def build_default_output_path(
    session_id: str,
    output_dir: Path = DEFAULT_EXPORT_DIR,
    *,
    now: datetime | None = None,
) -> Path:
    """Build a date-prefixed export filename like 2026-11-20_170500_langfuse_session_<id>.json."""
    safe_name = sanitize_filename_component(session_id)
    timestamp = (now or datetime.now()).strftime("%Y-%m-%d_%H%M%S")
    return output_dir / f"{timestamp}_langfuse_session_{safe_name}.json"


def main(argv: list[str] | None = None) -> int:
    load_dotenv(BASE_DIR / ".env", override=False)

    parser = argparse.ArgumentParser(
        description="Export full Langfuse v4 session traces and observations to export/*.json"
    )
    parser.add_argument("session_id", help="Target Langfuse session ID")
    parser.add_argument(
        "--host",
        default=None,
        help="Langfuse host URL (defaults to LANGFUSE_BASE_URL or LANGFUSE_HOST in .env)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_EXPORT_DIR,
        help=f"Directory to save JSON file (default: {DEFAULT_EXPORT_DIR})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Explicit output file path (overrides --output-dir)",
    )
    args = parser.parse_args(argv)

    public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
    secret_key = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
    host = (
        args.host
        or os.getenv("LANGFUSE_BASE_URL", "")
        or os.getenv("LANGFUSE_HOST", "")
    ).strip()

    missing = [
        name
        for name, val in (
            ("LANGFUSE_PUBLIC_KEY", public_key),
            ("LANGFUSE_SECRET_KEY", secret_key),
            ("LANGFUSE_BASE_URL", host),
        )
        if not val
    ]
    if missing:
        print(
            f"ERROR: Missing configuration: {', '.join(missing)}. Set them in Test-LiveKit/.env.",
            file=sys.stderr,
        )
        return 1

    output_path = args.output or build_default_output_path(
        args.session_id, args.output_dir
    )

    try:
        payload = export_full_session(
            args.session_id,
            output_path,
            public_key=public_key,
            secret_key=secret_key,
            host=host,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(
        f"完了: {payload['trace_count']} 件のトレース"
        f"（{payload['observation_count']} 件の observation）を {output_path} に保存しました。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
