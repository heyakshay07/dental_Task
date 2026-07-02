"""
Real Google Calendar API integration (no mocking).

Auth: a service account JSON key (GOOGLE_APPLICATION_CREDENTIALS). Share the
test calendar with the service account's client_email, granting
"Make changes to events".

find_available_slot() uses the freebusy.query endpoint to check the
requested time, and if busy, walks forward in
APPOINTMENT_DURATION_MINUTES increments (within clinic business hours,
9am-5pm, next 14 days) until it finds an open slot.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from functools import lru_cache
from typing import Optional
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import build

from app.config import get_settings

SCOPES = ["https://www.googleapis.com/auth/calendar"]
BUSINESS_START_HOUR = 9
BUSINESS_END_HOUR = 17


@lru_cache
def _calendar_client():
    settings = get_settings()
    creds = service_account.Credentials.from_service_account_file(
        settings.google_application_credentials, scopes=SCOPES,
    )
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _tz() -> ZoneInfo:
    return ZoneInfo(get_settings().clinic_timezone)


def _localize(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=_tz())
    return dt


def _is_within_business_hours(dt: datetime) -> bool:
    return BUSINESS_START_HOUR <= dt.hour < BUSINESS_END_HOUR and dt.weekday() < 6  # Mon-Sat


def find_available_slot(preferred: datetime, max_days_ahead: int = 14) -> Optional[datetime]:
    """Return the nearest open slot at/after `preferred`, or None if nothing
    is found within the search window."""
    settings = get_settings()
    duration = timedelta(minutes=settings.appointment_duration_minutes)

    start_search = _localize(preferred)
    deadline = start_search + timedelta(days=max_days_ahead)

    # Query all busy periods in a single API call
    body = {
        "timeMin": start_search.isoformat(),
        "timeMax": deadline.isoformat(),
        "items": [{"id": settings.google_calendar_id}],
    }
    response = _calendar_client().freebusy().query(body=body).execute()
    busy_periods = response["calendars"][settings.google_calendar_id].get("busy", [])

    busy_ranges = []
    for period in busy_periods:
        b_start = datetime.fromisoformat(period["start"])
        b_end = datetime.fromisoformat(period["end"])
        busy_ranges.append((b_start, b_end))

    candidate = start_search
    if not _is_within_business_hours(candidate):
        candidate = candidate.replace(hour=BUSINESS_START_HOUR, minute=0, second=0, microsecond=0)
        if candidate < start_search:
            candidate += timedelta(days=1)

    while candidate < deadline:
        if _is_within_business_hours(candidate):
            cand_start = candidate
            cand_end = candidate + duration

            # Check overlap locally
            overlap = False
            for b_start, b_end in busy_ranges:
                if cand_start < b_end and b_start < cand_end:
                    overlap = True
                    break

            if not overlap:
                return candidate

        candidate += timedelta(minutes=settings.appointment_duration_minutes)
        if candidate.hour >= BUSINESS_END_HOUR:
            candidate = (candidate + timedelta(days=1)).replace(
                hour=BUSINESS_START_HOUR, minute=0, second=0, microsecond=0
            )

    return None


def book_appointment(patient_name: str, service: str, start_time: datetime, call_id: str) -> dict:
    settings = get_settings()
    duration = timedelta(minutes=settings.appointment_duration_minutes)
    start = _localize(start_time)
    end = start + duration

    event_body = {
        "summary": f"{service} - {patient_name}",
        "description": f"Booked via AI receptionist. VAPI call_id: {call_id}",
        "start": {"dateTime": start.isoformat(), "timeZone": settings.clinic_timezone},
        "end": {"dateTime": end.isoformat(), "timeZone": settings.clinic_timezone},
    }
    created = _calendar_client().events().insert(
        calendarId=settings.google_calendar_id, body=event_body,
    ).execute()

    return {
        "event_id": created["id"],
        "event_link": created.get("htmlLink"),
        "start": start.isoformat(),
        "end": end.isoformat(),
    }
