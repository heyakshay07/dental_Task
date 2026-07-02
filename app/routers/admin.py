"""
Admin REST API: view all bookings and per-caller conversation history.

Protected with a static bearer/API-key token. Supports both Authorization Bearer
and X-Admin-Api-Key headers, rendering as security schemes in OpenAPI docs.
"""
from __future__ import annotations

from typing import Optional

# pyrefly: ignore [missing-import]
from fastapi import APIRouter, Depends, HTTPException, Query, Security
# pyrefly: ignore [missing-import]
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings
from app.storage import booking_store, session_store

security_bearer = HTTPBearer(auto_error=False)
security_apikey = APIKeyHeader(name="X-Admin-Api-Key", auto_error=False)


def _require_admin(
    credentials: HTTPAuthorizationCredentials | None = Security(security_bearer),
    x_admin_api_key: str | None = Security(security_apikey),
) -> None:
    settings = get_settings()
    token = None
    if credentials and credentials.credentials:
        token = credentials.credentials
    elif x_admin_api_key:
        token = x_admin_api_key

    # Strip case-insensitive "Bearer " prefix if it was mistakenly included in the header/input value
    if token and token.lower().startswith("bearer "):
        token = token[7:].strip()

    if not token or token != settings.admin_api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing Authorization Bearer token or X-Admin-Api-Key header"
        )


router = APIRouter(prefix="/admin", dependencies=[Depends(_require_admin)])


@router.get("/bookings")
def get_bookings(
    clinic_id: Optional[str] = Query(default=None),
):
    bookings = booking_store.list_bookings(clinic_id=clinic_id)
    return {"count": len(bookings), "bookings": [b.model_dump(mode="json") for b in bookings]}


@router.get("/sessions")
def get_sessions(
    clinic_id: Optional[str] = Query(default=None),
):
    sessions = session_store.list_sessions(clinic_id=clinic_id)
    return {"count": len(sessions), "sessions": [s.model_dump(mode="json") for s in sessions]}


@router.get("/sessions/{call_id}")
def get_session_detail(call_id: str):
    session = session_store.get_session(call_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.model_dump(mode="json")

