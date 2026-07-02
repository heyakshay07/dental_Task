"""
Unit tests for the admin REST API endpoints.

These mock out the actual database (Firestore) list/get operations
and verify authentication and responses.
"""
from __future__ import annotations

# pyrefly: ignore [missing-import]
import pytest
# pyrefly: ignore [missing-import]
from fastapi.testclient import TestClient

from app.main import app
from app.config import get_settings
from app.models import Booking, ConversationSession

client = TestClient(app)


@pytest.fixture(autouse=True)
def mock_db_operations(monkeypatch):
    # Mock booking_store.list_bookings to return an empty list or mock list
    monkeypatch.setattr(
        "app.storage.booking_store.list_bookings",
        lambda clinic_id=None, limit=200: [
            Booking(
                booking_id="b-1",
                call_id="call-1",
                clinic_id="default_clinic",
                patient_name="John Doe",
                service="Dental Cleaning",
                start_time="2026-07-02T14:00:00",
                end_time="2026-07-02T14:30:00",
                calendar_event_id="evt_1",
                caller_phone="+12184177429",
            )
        ]
    )

    # Mock session_store.list_sessions
    monkeypatch.setattr(
        "app.storage.session_store.list_sessions",
        lambda clinic_id=None, limit=100: [
            ConversationSession(call_id="call-1", clinic_id="default_clinic")
        ]
    )

    # Mock session_store.get_session
    monkeypatch.setattr(
        "app.storage.session_store.get_session",
        lambda call_id: ConversationSession(call_id=call_id, clinic_id="default_clinic") if call_id == "call-1" else None
    )


def test_admin_routes_no_auth():
    # Attempting to fetch bookings without credentials should return 401
    resp = client.get("/admin/bookings")
    assert resp.status_code == 401
    assert "detail" in resp.json()

    # Attempting to fetch sessions without credentials should return 401
    resp = client.get("/admin/sessions")
    assert resp.status_code == 401


def test_admin_routes_invalid_auth():
    # Attempting to fetch with invalid Bearer token should return 401
    resp = client.get("/admin/bookings", headers={"Authorization": "Bearer invalid_secret"})
    assert resp.status_code == 401

    # Attempting to fetch with invalid X-Admin-Api-Key should return 401
    resp = client.get("/admin/bookings", headers={"X-Admin-Api-Key": "invalid_secret"})
    assert resp.status_code == 401


def test_admin_routes_authorized_bearer(monkeypatch):
    # Set a static admin key for testing
    settings = get_settings()
    monkeypatch.setattr(settings, "admin_api_key", "secret-test-token")

    # Fetch with valid Bearer token
    resp = client.get("/admin/bookings", headers={"Authorization": "Bearer secret-test-token"})
    assert resp.status_code == 200
    assert resp.json()["count"] == 1
    assert resp.json()["bookings"][0]["booking_id"] == "b-1"

    # Fetch sessions with valid Bearer token
    resp = client.get("/admin/sessions", headers={"Authorization": "Bearer secret-test-token"})
    assert resp.status_code == 200
    assert resp.json()["count"] == 1
    assert resp.json()["sessions"][0]["call_id"] == "call-1"

    # Fetch session detail with valid Bearer token
    resp = client.get("/admin/sessions/call-1", headers={"Authorization": "Bearer secret-test-token"})
    assert resp.status_code == 200
    assert resp.json()["call_id"] == "call-1"

    # Fetch non-existent session detail
    resp = client.get("/admin/sessions/call-none", headers={"Authorization": "Bearer secret-test-token"})
    assert resp.status_code == 404


def test_admin_routes_authorized_apikey(monkeypatch):
    # Set a static admin key for testing
    settings = get_settings()
    monkeypatch.setattr(settings, "admin_api_key", "secret-test-token")

    # Fetch with valid X-Admin-Api-Key header
    resp = client.get("/admin/bookings", headers={"X-Admin-Api-Key": "secret-test-token"})
    assert resp.status_code == 200
    assert resp.json()["count"] == 1
    assert resp.json()["bookings"][0]["booking_id"] == "b-1"

    # Fetch with leading 'Bearer ' in X-Admin-Api-Key (which can happen with UI autofill)
    resp = client.get("/admin/bookings", headers={"X-Admin-Api-Key": "Bearer secret-test-token"})
    assert resp.status_code == 200

    # Fetch with double 'Bearer Bearer ' in Authorization header
    resp = client.get("/admin/bookings", headers={"Authorization": "Bearer Bearer secret-test-token"})
    assert resp.status_code == 200
