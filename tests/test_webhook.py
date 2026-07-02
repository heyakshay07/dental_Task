"""
Unit tests for the VAPI webhook REST API endpoints.

These verify the x-vapi-secret header authentication/validation and different
webhook payload message types (tool-calls, status-update, end-of-call-report).
"""
from __future__ import annotations

# pyrefly: ignore [missing-import]
import pytest
# pyrefly: ignore [missing-import]
from fastapi.testclient import TestClient

from app.main import app
from app.config import get_settings
from app.models import ConversationSession
from app.conversation.state_machine import StepResult as StateMachineStepResult

client = TestClient(app)


@pytest.fixture(autouse=True)
def mock_webhook_dependencies(monkeypatch):
    # Mock storage operations to prevent actual Firestore hits
    saved_sessions = {}

    def mock_get_session(call_id: str):
        return saved_sessions.get(call_id)

    def mock_get_or_create_session(call_id: str, clinic_id: str = "default_clinic", caller_phone: str | None = None):
        if call_id not in saved_sessions:
            saved_sessions[call_id] = ConversationSession(
                call_id=call_id, clinic_id=clinic_id, caller_phone=caller_phone
            )
        return saved_sessions[call_id]

    def mock_save_session(session: ConversationSession):
        saved_sessions[session.call_id] = session

    monkeypatch.setattr("app.storage.session_store.get_session", mock_get_session)
    monkeypatch.setattr("app.storage.session_store.get_or_create_session", mock_get_or_create_session)
    monkeypatch.setattr("app.storage.session_store.save_session", mock_save_session)

    # Mock state_machine.handle_tool_call
    monkeypatch.setattr(
        "app.conversation.state_machine.handle_tool_call",
        lambda session, tool_name, parameters: StateMachineStepResult(
            speak=f"Mocked response for {tool_name}",
            session=session,
            success=True
        )
    )

    return saved_sessions


def test_webhook_no_secret_configured(monkeypatch):
    # When VAPI_WEBHOOK_SECRET is empty/unset, any webhook call should succeed
    settings = get_settings()
    monkeypatch.setattr(settings, "vapi_webhook_secret", "")

    payload = {
        "message": {
            "type": "status-update",
            "status": "ringing",
            "call": {"id": "call-no-secret"}
        }
    }

    # Request without x-vapi-secret header
    resp = client.post("/webhook/vapi", json=payload)
    assert resp.status_code == 200
    assert resp.json() == {"received": True}

    # Request with any x-vapi-secret header
    resp = client.post("/webhook/vapi", json=payload, headers={"x-vapi-secret": "random"})
    assert resp.status_code == 200


def test_webhook_with_secret_configured(monkeypatch):
    # Set a static webhook secret for testing
    settings = get_settings()
    monkeypatch.setattr(settings, "vapi_webhook_secret", "super-secret-token")

    payload = {
        "message": {
            "type": "status-update",
            "status": "ringing",
            "call": {"id": "call-with-secret"}
        }
    }

    # Request without x-vapi-secret header -> should fail with 401
    resp = client.post("/webhook/vapi", json=payload)
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid webhook secret"

    # Request with incorrect x-vapi-secret header -> should fail with 401
    resp = client.post("/webhook/vapi", json=payload, headers={"x-vapi-secret": "wrong-token"})
    assert resp.status_code == 401

    # Request with correct x-vapi-secret header -> should succeed with 200
    resp = client.post("/webhook/vapi", json=payload, headers={"x-vapi-secret": "super-secret-token"})
    assert resp.status_code == 200
    assert resp.json() == {"received": True}


def test_webhook_message_types(mock_webhook_dependencies):
    saved_sessions = mock_webhook_dependencies

    # 1. Test status-update
    payload_status = {
        "message": {
            "type": "status-update",
            "status": "in-progress",
            "call": {"id": "call-123", "customer": {"number": "+1234567890"}}
        }
    }
    resp = client.post("/webhook/vapi", json=payload_status)
    assert resp.status_code == 200
    assert "call-123" in saved_sessions
    assert saved_sessions["call-123"].caller_phone == "+1234567890"
    assert any("status: in-progress" in turn.content for turn in saved_sessions["call-123"].turns)

    # 2. Test tool-calls
    payload_tool = {
        "message": {
            "type": "tool-calls",
            "call": {"id": "call-123"},
            "toolCallList": [
                {"id": "tc-1", "name": "providePatientName", "parameters": {"name": "Alice"}}
            ]
        }
    }
    resp = client.post("/webhook/vapi", json=payload_tool)
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 1
    assert results[0]["toolCallId"] == "tc-1"
    assert results[0]["result"] == "Mocked response for providePatientName"

    # 3. Test end-of-call-report
    # Mark the session status as in_progress first
    saved_sessions["call-123"].status = "in_progress"
    payload_end = {
        "message": {
            "type": "end-of-call-report",
            "call": {"id": "call-123"},
            "endedReason": "customer-hung-up",
            "artifact": {
                "transcript": "Hello. I would like to book an appointment. Bye."
            }
        }
    }
    resp = client.post("/webhook/vapi", json=payload_end)
    assert resp.status_code == 200
    # The session status should be updated to abandoned (since it was in_progress and ended)
    assert saved_sessions["call-123"].status == "abandoned"
    assert any("full_transcript:" in turn.content for turn in saved_sessions["call-123"].turns)
    assert any("call_ended: customer-hung-up" in turn.content for turn in saved_sessions["call-123"].turns)

    # 4. Test unhandled / informational message
    payload_info = {
        "message": {
            "type": "speech-update",
            "call": {"id": "call-123"}
        }
    }
    resp = client.post("/webhook/vapi", json=payload_info)
    assert resp.status_code == 200
    assert resp.json() == {"received": True}
