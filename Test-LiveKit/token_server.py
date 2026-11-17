"""Local-only token endpoint for fronted-test; no model requests are made here."""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from livekit import api


load_dotenv(Path(__file__).with_name(".env"), override=False)
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

# Vite proxies the request without rewriting its browser Origin header.
ALLOWED_ORIGINS = {"http://localhost:5173", "http://127.0.0.1:5173"}


@app.post("/api/token")
def create_token(request: Request, response: Response) -> dict[str, str]:
    """Issue a short-lived, microphone-only grant for a fresh private test room."""
    if request.headers.get("origin") not in ALLOWED_ORIGINS:
        raise HTTPException(status_code=403, detail="Local frontend origin required")

    names = ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET")
    values = {name: os.getenv(name, "").strip() for name in names}
    if not all(values.values()):
        raise HTTPException(status_code=503, detail="LiveKit configuration is missing")
    if not values["LIVEKIT_URL"].startswith(("wss://", "ws://")):
        raise HTTPException(status_code=503, detail="LIVEKIT_URL must use ws:// or wss://")

    room = f"frontend-test-{uuid4().hex}"
    token = (
        api.AccessToken(values["LIVEKIT_API_KEY"], values["LIVEKIT_API_SECRET"])
        .with_identity(f"browser-{uuid4().hex}")
        .with_ttl(timedelta(minutes=10))
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=False,
                can_publish_sources=["microphone"],
            )
        )
        .to_jwt()
    )
    response.headers["Cache-Control"] = "no-store"
    return {"server_url": values["LIVEKIT_URL"], "participant_token": token}
