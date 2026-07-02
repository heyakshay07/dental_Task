"""
Diagnostic: checks whether the service account can access the specific
calendar in GOOGLE_CALENDAR_ID, and what access role it has.
"""
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.config import get_settings

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def main():
    settings = get_settings()
    print(f"Using credentials file: {settings.google_application_credentials}")
    print(f"GOOGLE_CALENDAR_ID in .env: '{settings.google_calendar_id}'\n")

    creds = service_account.Credentials.from_service_account_file(
        settings.google_application_credentials, scopes=SCOPES,
    )
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)

    try:
        cal = service.calendars().get(calendarId=settings.google_calendar_id).execute()
        print("SUCCESS: Service account can access this calendar.")
        print(f"  Summary: {cal.get('summary')}")
        print(f"  Time zone: {cal.get('timeZone')}")
    except HttpError as e:
        print(f"FAILED: {e.status_code} {e.reason}")
        if e.status_code == 404:
            print("Calendar not found or not shared with this service account.")
        elif e.status_code == 403:
            print("Access forbidden - check sharing permissions.")
        return

    # Try to actually list a small window of events to confirm read access
    try:
        events = service.events().list(
            calendarId=settings.google_calendar_id, maxResults=1
        ).execute()
        print(f"\nEvent read access: OK ({len(events.get('items', []))} sample event(s) fetched)")
    except HttpError as e:
        print(f"\nEvent read access FAILED: {e.status_code} {e.reason}")

    # Try creating and immediately deleting a test event to confirm write access
    try:
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        test_event = {
            "summary": "Access check (safe to ignore/delete)",
            "start": {"dateTime": now.isoformat() + "Z"},
            "end": {"dateTime": (now + timedelta(minutes=5)).isoformat() + "Z"},
        }
        created = service.events().insert(
            calendarId=settings.google_calendar_id, body=test_event
        ).execute()
        service.events().delete(
            calendarId=settings.google_calendar_id, eventId=created["id"]
        ).execute()
        print("Write access: OK (test event created and deleted successfully)")
    except HttpError as e:
        print(f"Write access FAILED: {e.status_code} {e.reason}")


if __name__ == "__main__":
    main()