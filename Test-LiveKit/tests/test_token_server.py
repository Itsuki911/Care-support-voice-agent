import time

import jwt
import pytest
from fastapi.testclient import TestClient

from token_server import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("LIVEKIT_URL", "wss://example.livekit.cloud")
    monkeypatch.setenv("LIVEKIT_API_KEY", "test-key")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "test-secret-for-unit-tests-only-32-bytes")
    return TestClient(app)


def test_token_signature_grants_and_expiry(client):
    response = client.post("/api/token", headers={"Origin": "http://localhost:5173"})
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    data = response.json()
    assert set(data) == {"server_url", "participant_token"}
    assert data["server_url"] == "wss://example.livekit.cloud"
    claims = jwt.decode(
        data["participant_token"],
        "test-secret-for-unit-tests-only-32-bytes",
        algorithms=["HS256"],
        issuer="test-key",
    )
    assert claims["sub"].startswith("browser-")
    assert 590 <= claims["exp"] - time.time() <= 600
    grant = claims["video"]
    assert grant["roomJoin"] is True
    assert grant["room"].startswith("frontend-test-")
    assert grant["canPublishSources"] == ["microphone"]
    assert grant["canSubscribe"] is True
    assert grant["canPublishData"] is True  # Approval RPC; room admin stays disabled.
    assert not grant.get("roomAdmin", False)


def test_each_start_has_distinct_room_and_identity(client):
    def claims():
        data = client.post("/api/token", headers={"Origin": "http://localhost:5173"}).json()
        return jwt.decode(data["participant_token"], options={"verify_signature": False})

    first, second = claims(), claims()
    assert first["sub"] != second["sub"]
    assert first["video"]["room"] != second["video"]["room"]


@pytest.mark.parametrize("name", ["LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"])
def test_missing_configuration_is_rejected(client, monkeypatch, name):
    monkeypatch.delenv(name)
    response = client.post("/api/token", headers={"Origin": "http://localhost:5173"})
    assert response.status_code == 503
    assert "test-secret" not in response.text


@pytest.mark.parametrize("origin", ["https://example.com", "null", ""])
def test_foreign_or_missing_origin_is_rejected(client, origin):
    assert client.post("/api/token", headers={"Origin": origin}).status_code == 403


def test_invalid_livekit_url(client, monkeypatch):
    monkeypatch.setenv("LIVEKIT_URL", "https://example.com")
    assert client.post("/api/token", headers={"Origin": "http://localhost:5173"}).status_code == 503


def test_get_cannot_issue_token(client):
    assert client.get("/api/token").status_code == 405


def test_loopback_frontend_origin(client):
    assert client.post("/api/token", headers={"Origin": "http://127.0.0.1:5173"}).status_code == 200


def test_text_mode_token_disables_microphone_publish_and_uses_text_room_prefix(client):
    response = client.post(
        "/api/token",
        headers={"Origin": "http://localhost:5173"},
        json={"mode": "text"},
    )
    assert response.status_code == 200
    data = response.json()
    claims = jwt.decode(
        data["participant_token"],
        "test-secret-for-unit-tests-only-32-bytes",
        algorithms=["HS256"],
        issuer="test-key",
    )
    grant = claims["video"]
    assert grant["room"].startswith("frontend-test-text-")
    assert grant["canPublish"] is False
    assert grant.get("canPublishSources", []) == []
    assert grant["canPublishData"] is True
    assert grant["canSubscribe"] is True


def test_invalid_mode_is_rejected(client):
    response = client.post(
        "/api/token",
        headers={"Origin": "http://localhost:5173"},
        json={"mode": "hybrid"},
    )
    assert response.status_code == 400


def test_explicit_user_id_is_used_as_identity(client):
    response = client.post(
        "/api/token",
        headers={"Origin": "http://localhost:5173"},
        json={"mode": "text", "user_id": "care-user_01"},
    )
    assert response.status_code == 200
    claims = jwt.decode(
        response.json()["participant_token"],
        "test-secret-for-unit-tests-only-32-bytes",
        algorithms=["HS256"],
        issuer="test-key",
    )
    assert claims["sub"] == "care-user_01"


@pytest.mark.parametrize("bad_uid", ["", "   ", "user with spaces", "../bad"])
def test_invalid_user_id_is_rejected(client, bad_uid):
    response = client.post(
        "/api/token",
        headers={"Origin": "http://localhost:5173"},
        json={"mode": "voice", "user_id": bad_uid},
    )
    assert response.status_code == 400
