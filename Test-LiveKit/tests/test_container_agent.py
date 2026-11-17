import base64
import json

import pytest

import container_agent


def test_materialize_optional_gmail_secrets_writes_ephemeral_files(monkeypatch, tmp_path):
    client = {"installed": {"client_id": "client"}}
    token = {"refresh_token": "refresh"}
    monkeypatch.setattr(container_agent, "SECRETS_DIR", tmp_path / "secrets")
    monkeypatch.setenv(
        "GMAIL_CLIENT_SECRET_JSON_B64",
        base64.b64encode(json.dumps(client).encode()).decode(),
    )
    monkeypatch.setenv(
        "GMAIL_TOKEN_JSON_B64",
        base64.b64encode(json.dumps(token).encode()).decode(),
    )

    container_agent.materialize_optional_gmail_secrets()

    client_path = tmp_path / "secrets" / "gmail-client.json"
    token_path = tmp_path / "secrets" / "gmail-token.json"
    assert json.loads(client_path.read_text()) == client
    assert json.loads(token_path.read_text()) == token
    assert container_agent.os.environ["GMAIL_CLIENT_SECRET_FILE"] == str(client_path)
    assert container_agent.os.environ["GMAIL_TOKEN_FILE"] == str(token_path)


def test_materialize_optional_gmail_secrets_rejects_invalid_json(monkeypatch, tmp_path):
    monkeypatch.setattr(container_agent, "SECRETS_DIR", tmp_path / "secrets")
    monkeypatch.setenv(
        "GMAIL_TOKEN_JSON_B64",
        base64.b64encode(b"not-json").decode(),
    )

    with pytest.raises(RuntimeError, match="GMAIL_TOKEN_JSON_B64"):
        container_agent.materialize_optional_gmail_secrets()
