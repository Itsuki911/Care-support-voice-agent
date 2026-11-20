import json

import pytest

import export_langfuse_session as exporter


def test_export_full_session_cursor_pagination_groups_and_sorts(tmp_path):
    calls = []

    def fake_get(url: str, headers: dict[str, str]):
        calls.append((url, headers["Authorization"]))
        if "cursor=" not in url:
            return {
                "data": [
                    {
                        "id": "obs-b",
                        "traceId": "trace-1",
                        "parentObservationId": "obs-root",
                        "name": "llm_request",
                        "startTime": "2026-11-20T07:01:05Z",
                        "totalCost": 0.0015,
                    },
                    {
                        "id": "obs-2",
                        "traceId": "trace-2",
                        "parentObservationId": None,
                        "name": "agent_session",
                        "startTime": "2026-11-20T07:02:00Z",
                        "totalCost": 0.0025,
                    },
                ],
                "meta": {"cursor": "next-page-token"},
            }
        return {
            "data": [
                {
                    "id": "obs-root",
                    "traceId": "trace-1",
                    "parentObservationId": None,
                    "name": "agent_session",
                    "startTime": "2026-11-20T07:01:00Z",
                    "totalCost": 0.0,
                }
            ],
            "meta": {"cursor": None},
        }

    output_file = tmp_path / "export" / "langfuse_session_sess-123.json"
    result = exporter.export_full_session(
        "sess-123",
        output_file,
        public_key="pk-test",
        secret_key="sk-test",
        host="https://jp.cloud.langfuse.com/",
        get_json=fake_get,
    )

    assert len(calls) == 2
    assert "/api/public/v2/observations?" in calls[0][0]
    assert "cursor=next-page-token" in calls[1][0]
    assert calls[0][1].startswith("Basic ")

    assert result["session_id"] == "sess-123"
    assert result["trace_count"] == 2
    assert result["observation_count"] == 3
    assert result["total_cost"] == pytest.approx(0.004)
    assert [t["id"] for t in result["traces"]] == ["trace-1", "trace-2"]
    assert result["traces"][0]["rootObservationName"] == "agent_session"
    assert [o["id"] for o in result["traces"][0]["observations"]] == ["obs-root", "obs-b"]

    saved = json.loads(output_file.read_text(encoding="utf-8"))
    assert saved == result


def test_sanitize_filename_component_prevents_traversal():
    assert exporter.sanitize_filename_component("../frontend-test/abc") == "frontend-test_abc"
    with pytest.raises(ValueError):
        exporter.sanitize_filename_component("...")


def test_build_default_output_path_prefixes_date(tmp_path):
    from datetime import datetime

    fixed = datetime(2026, 11, 20, 17, 5, 30)
    path = exporter.build_default_output_path("sess-abc", tmp_path, now=fixed)
    assert path == tmp_path / "2026-11-20_170530_langfuse_session_sess-abc.json"


def test_main_reports_missing_credentials(monkeypatch, capsys):
    monkeypatch.setattr(exporter, "load_dotenv", lambda *a, **kw: False)
    for var in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL", "LANGFUSE_HOST"):
        monkeypatch.delenv(var, raising=False)

    code = exporter.main(["sess-missing"])
    assert code == 1
    assert "LANGFUSE_PUBLIC_KEY" in capsys.readouterr().err
