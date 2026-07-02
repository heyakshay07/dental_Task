"""
Twilio SMS confirmation. Uses test credentials (Twilio's magic test numbers
work fine here without incurring real SMS charges during evaluation).
"""
from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from typing import Optional

from twilio.rest import Client

from app.config import get_settings


@lru_cache
def _client() -> Client:
    settings = get_settings()
    return Client(settings.twilio_account_sid, settings.twilio_auth_token)


def send_confirmation_sms(to_number: str, patient_name: str, service: str,
                           start_time: datetime) -> Optional[str]:
    settings = get_settings()
    friendly = start_time.strftime("%A, %B %d at %I:%M %p")
    body = (
        f"Hi {patient_name.split()[0]}, your {service} appointment is confirmed "
        f"for {friendly}. Reply to this number if you need to reschedule."
    )
    try:
        message = _client().messages.create(
            body=body, from_=settings.twilio_from_number, to=to_number,
        )
        return message.sid
    except Exception as exc:  # noqa: BLE001 - don't let SMS failure block the booking
        print(f"[sms_service] Failed to send SMS to {to_number}: {exc}")
        return None
