"""Container entrypoint that supervises a LiveKit agent and exposes /health.

Cloudflare Containers starts this program. It deliberately does not expose the
agent itself to the public Internet; its HTTP listener is reachable only via
the owning Cloudflare Worker/Durable Object.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import signal
import subprocess
import sys
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


PORT = int(os.getenv("PORT", "8080"))
SECRETS_DIR = Path("/tmp/livekit-agent-secrets")


def materialize_optional_gmail_secrets() -> None:
    """Decode optional Cloudflare secrets into short-lived files for Gmail SDK.

    The existing Gmail integration consumes file paths. In a container, the
    OAuth client and refresh-token JSON are supplied as base64-encoded secrets
    and written to the ephemeral filesystem at each startup.
    """
    secrets = {
        "GMAIL_CLIENT_SECRET_JSON_B64": ("GMAIL_CLIENT_SECRET_FILE", "gmail-client.json"),
        "GMAIL_TOKEN_JSON_B64": ("GMAIL_TOKEN_FILE", "gmail-token.json"),
    }
    for variable, (path_variable, filename) in secrets.items():
        encoded = os.getenv(variable, "").strip()
        if not encoded:
            continue
        try:
            decoded = base64.b64decode(encoded, validate=True)
            json.loads(decoded)
        except (ValueError, binascii.Error, json.JSONDecodeError) as exc:
            raise RuntimeError(f"{variable} must be base64-encoded JSON") from exc

        SECRETS_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = SECRETS_DIR / filename
        path.write_bytes(decoded)
        path.chmod(0o600)
        os.environ[path_variable] = str(path)


class HealthHandler(BaseHTTPRequestHandler):
    """Return process liveness only; never include runtime configuration."""

    agent_process: subprocess.Popen[bytes] | None = None

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        if self.path != "/health":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        alive = self.agent_process is not None and self.agent_process.poll() is None
        self.send_response(HTTPStatus.OK if alive else HTTPStatus.SERVICE_UNAVAILABLE)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b"ok" if alive else b"agent process is not running")

    def log_message(self, _format: str, *_args: object) -> None:
        """Keep health probe logs out of the container logs."""


def main() -> int:
    materialize_optional_gmail_secrets()
    process = subprocess.Popen([sys.executable, "agent.py", "start"])
    HealthHandler.agent_process = process
    server = ThreadingHTTPServer(("0.0.0.0", PORT), HealthHandler)

    def stop(_signal: int, _frame: object) -> None:
        server.shutdown()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        server.serve_forever()
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
        server.server_close()
    return process.returncode or 0


if __name__ == "__main__":
    raise SystemExit(main())
