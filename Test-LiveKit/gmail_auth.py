"""Run on your own PC after obtaining a Desktop OAuth client JSON from Google."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

from gmail_tools import BASE_DIR, SCOPES, configured_path


def save_token(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".gmail-token-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(value)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> int:
    load_dotenv(BASE_DIR / ".env", override=False)
    source = configured_path("GMAIL_CLIENT_SECRET_FILE", ".secrets/gmail-client.json")
    target = configured_path("GMAIL_TOKEN_FILE", ".secrets/gmail-token.json")
    try:
        flow = InstalledAppFlow.from_client_secrets_file(str(source), SCOPES)
        credentials = flow.run_local_server(host="localhost", port=0, access_type="offline", prompt="consent", timeout_seconds=180)
        save_token(target, credentials.to_json())
    except Exception:
        print("Gmail認証に失敗しました。OAuthクライアントJSON・同意画面・保存先を確認してください。")
        return 1
    print("Gmail認証情報を保存しました。agentを起動できます。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
