"""Local-only token endpoint for fronted-test; no model requests are made here."""

from __future__ import annotations

import json
import os
import re
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from livekit import api

from database.config import MemorySettings
from database.connection import DatabaseManager
from secretary.repository import SecretaryRepository


load_dotenv(Path(__file__).with_name(".env"), override=False)
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

# Vite proxies the request without rewriting its browser Origin header.
ALLOWED_ORIGINS = {"http://localhost:5173", "http://127.0.0.1:5173"}
USER_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

_SECRETARY_DB: DatabaseManager | None = None


def get_secretary_repository() -> SecretaryRepository:
    global _SECRETARY_DB
    if _SECRETARY_DB is None:
        _SECRETARY_DB = DatabaseManager(MemorySettings.from_env().database_url)
    return SecretaryRepository(_SECRETARY_DB)


@app.post("/api/secretary/verify")
async def verify_secretary_employee(request: Request, response: Response) -> dict[str, object]:
    """Verify fictional employee name and employee_id against PostgreSQL for TEST-Secretary mode."""
    if request.headers.get("origin") not in ALLOWED_ORIGINS:
        raise HTTPException(status_code=403, detail="Local frontend origin required")

    try:
        payload = json.loads(await request.body())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid JSON request body") from None

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON request body")

    employee_name = str(payload.get("employee_name") or "").strip()
    employee_id = str(payload.get("employee_id") or "").strip()
    if not employee_name or not employee_id:
        raise HTTPException(status_code=400, detail="氏名と社員IDの両方を入力してください。")

    try:
        repo = get_secretary_repository()
        employee = await repo.verify_employee(employee_id=employee_id, name=employee_name)
    except Exception:
        raise HTTPException(
            status_code=503, detail="社員データベースに接続できませんでした。"
        ) from None

    if employee is None:
        raise HTTPException(status_code=401, detail="氏名または社員IDが一致しません。")

    response.headers["Cache-Control"] = "no-store"
    return {
        "verified": True,
        "employee_id": employee.employee_id,
        "employee_name": employee.name,
        "department": employee.department,
    }


@app.post("/api/token")
async def create_token(request: Request, response: Response) -> dict[str, str]:
    """Issue a short-lived grant for a fresh private test room (voice-only or text-only)."""
    if request.headers.get("origin") not in ALLOWED_ORIGINS:
        raise HTTPException(status_code=403, detail="Local frontend origin required")

    mode = "voice"
    requested_user_id: str | None = None
    employee_name = ""
    employee_id = ""
    body = await request.body()
    if body:
        try:
            payload = json.loads(body)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid JSON request body") from None
        if not isinstance(payload, dict) or payload.get("mode", "voice") not in (
            "voice",
            "text",
            "secretary",
        ):
            raise HTTPException(
                status_code=400, detail="mode must be 'voice', 'text', or 'secretary'"
            )
        mode = payload.get("mode", "voice")
        employee_name = str(payload.get("employee_name") or "").strip()
        employee_id = str(payload.get("employee_id") or "").strip()
        if "user_id" in payload and payload["user_id"] is not None:
            raw_uid = payload["user_id"]
            if not isinstance(raw_uid, str) or not USER_ID_PATTERN.match(raw_uid.strip()):
                raise HTTPException(
                    status_code=400,
                    detail="user_id must be 1-64 chars of letters, digits, '.', '_', or '-'",
                )
            requested_user_id = raw_uid.strip()

    verified_employee = None
    if mode == "secretary":
        if not employee_name or not employee_id:
            raise HTTPException(status_code=400, detail="氏名と社員IDの両方を入力してください。")
        try:
            verified_employee = await get_secretary_repository().verify_employee(
                employee_id=employee_id,
                name=employee_name,
            )
        except Exception:
            raise HTTPException(
                status_code=503, detail="社員データベースに接続できませんでした。"
            ) from None
        if verified_employee is None:
            raise HTTPException(status_code=401, detail="氏名または社員IDが一致しません。")

    names = ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET")
    values = {name: os.getenv(name, "").strip() for name in names}
    if not all(values.values()):
        raise HTTPException(status_code=503, detail="LiveKit configuration is missing")
    if not values["LIVEKIT_URL"].startswith(("wss://", "ws://")):
        raise HTTPException(status_code=503, detail="LIVEKIT_URL must use ws:// or wss://")

    is_voice = mode in ("voice", "secretary")
    if mode == "secretary":
        room_prefix = "frontend-test-secretary-"
    elif mode == "voice":
        room_prefix = "frontend-test-"
    else:
        room_prefix = "frontend-test-text-"
    room = f"{room_prefix}{uuid4().hex}"
    if verified_employee is not None:
        identity = f"secretary-{verified_employee.employee_id}-{uuid4().hex[:8]}"
    else:
        identity = requested_user_id or f"browser-{uuid4().hex}"
    token_builder = (
        api.AccessToken(values["LIVEKIT_API_KEY"], values["LIVEKIT_API_SECRET"])
        .with_identity(identity)
        .with_ttl(timedelta(minutes=10))
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room,
                can_publish=is_voice,
                can_subscribe=True,
                can_publish_data=True,  # Approval RPC and text turns use the room data transport.
                can_publish_sources=["microphone"] if is_voice else [],
            )
        )
    )
    if verified_employee is not None:
        token_builder = token_builder.with_metadata(
            json.dumps(
                {
                    "secretary_verified": True,
                    "employee_id": verified_employee.employee_id,
                    "employee_name": verified_employee.name,
                },
                ensure_ascii=False,
            )
        )
    token = token_builder.to_jwt()
    response.headers["Cache-Control"] = "no-store"
    return {"server_url": values["LIVEKIT_URL"], "participant_token": token}
