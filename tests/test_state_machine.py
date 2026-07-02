"""
Unit tests for the conversation state machine.

These monkeypatch the calendar/sms/firestore-backed calls so the flow can
be tested with zero external credentials (useful for CI). Run with:

    pytest tests/ -v
"""
from datetime import datetime, timedelta

import pytest

from app.conversation import state_machine
from app.models import BookingStep, ConversationSession


@pytest.fixture(autouse=True)
def patch_external(monkeypatch):
    # Calendar: always report the requested slot as free
    monkeypatch.setattr(
        state_machine.calendar_service, "find_available_slot",
        lambda preferred, max_days_ahead=14: preferred,
    )
    monkeypatch.setattr(
        state_machine.calendar_service, "book_appointment",
        lambda **kwargs: {
            "event_id": "evt_123", "event_link": "https://calendar.google.com/evt_123",
            "start": kwargs["start_time"].isoformat(),
            "end": (kwargs["start_time"] + timedelta(minutes=30)).isoformat(),
        },
    )
    # SMS: no-op
    monkeypatch.setattr(state_machine.sms_service, "send_confirmation_sms", lambda **kwargs: "SMxxxx")
    # Firestore-backed stores: no-op
    monkeypatch.setattr("app.storage.session_store.save_session", lambda session: None)
    monkeypatch.setattr("app.storage.booking_store.save_booking", lambda **kwargs: None)


def fresh_session() -> ConversationSession:
    return ConversationSession(call_id="test-call-1")


def test_happy_path_full_booking_flow():
    session = fresh_session()

    r1 = state_machine.handle_tool_call(session, "providePatientName", {"name": "Akshay Patil"})
    assert r1.success
    assert session.step == BookingStep.COLLECT_SERVICE

    r2 = state_machine.handle_tool_call(session, "selectService", {"service": "cleaning"})
    assert r2.success
    assert session.service == "Dental Cleaning"
    assert session.step == BookingStep.COLLECT_DATETIME

    tomorrow_2pm = (datetime.now() + timedelta(days=1)).replace(
        hour=14, minute=0, second=0, microsecond=0
    )
    r3 = state_machine.handle_tool_call(
        session, "selectDateTime", {"preferredDateTime": tomorrow_2pm.isoformat()}
    )
    assert r3.success
    assert session.step == BookingStep.CONFIRM

    r4 = state_machine.handle_tool_call(session, "confirmBooking", {"confirm": True})
    assert r4.success
    assert session.step == BookingStep.DONE
    assert session.status == "booked"
    assert session.booking_id == "evt_123"


def test_out_of_order_tool_call_is_rejected():
    session = fresh_session()
    # Try to confirm before name/service/datetime are collected
    result = state_machine.handle_tool_call(session, "confirmBooking", {"confirm": True})
    assert not result.success
    assert session.step == BookingStep.COLLECT_NAME  # unchanged


def test_invalid_service_reprompts_without_advancing():
    session = fresh_session()
    state_machine.handle_tool_call(session, "providePatientName", {"name": "Akshay Patil"})
    result = state_machine.handle_tool_call(session, "selectService", {"service": "surgery on the moon"})
    assert not result.success
    assert session.step == BookingStep.COLLECT_SERVICE


def test_declining_confirmation_returns_to_datetime_step():
    session = fresh_session()
    state_machine.handle_tool_call(session, "providePatientName", {"name": "Akshay Patil"})
    state_machine.handle_tool_call(session, "selectService", {"service": "checkup"})
    tomorrow = (datetime.now() + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
    state_machine.handle_tool_call(session, "selectDateTime", {"preferredDateTime": tomorrow.isoformat()})

    result = state_machine.handle_tool_call(session, "confirmBooking", {"confirm": False})
    assert session.step == BookingStep.COLLECT_DATETIME
    assert session.confirmed_datetime is None
