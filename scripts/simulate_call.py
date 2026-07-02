"""
Simulates a full VAPI call by POSTing webhook payloads shaped exactly like
real VAPI server events, in order, against a running server. Useful for:
  - Local end-to-end testing before wiring up a real VAPI assistant
  - Recording the Loom demo against the live deployed URL

Usage:
    python scripts/simulate_call.py http://localhost:8000
    python scripts/simulate_call.py https://your-app.up.railway.app
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta

import requests

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
CALL_ID = f"sim-{uuid.uuid4().hex[:8]}"
CALLER_PHONE = "+12184177429"  # Twilio magic test number


def call_obj():
    return {"id": CALL_ID, "customer": {"number": CALLER_PHONE}}


def post_tool_call(name: str, parameters: dict, tool_call_id: str):
    payload = {
        "message": {
            "type": "tool-calls",
            "call": call_obj(),
            "toolCallList": [{"id": tool_call_id, "name": name, "parameters": parameters}],
        }
    }
    resp = requests.post(f"{BASE_URL}/webhook/vapi", json=payload, timeout=15)
    resp.raise_for_status()
    result = resp.json()["results"][0]["result"]
    print(f"  -> assistant says: {result}\n")
    return result


def main():
    print(f"Simulating call {CALL_ID} against {BASE_URL}\n")

    print("[1] Caller states their name")
    post_tool_call("providePatientName", {"name": "Akshay Patil"}, "tc-1")

    print("[2] Caller states the service")
    post_tool_call("selectService", {"service": "cleaning"}, "tc-2")

    print("[3] Caller states preferred date/time")
    preferred = (datetime.now() + timedelta(days=1)).replace(hour=14, minute=0, second=0, microsecond=0)
    post_tool_call("selectDateTime", {"preferredDateTime": preferred.isoformat()}, "tc-3")

    print("[4] Caller confirms")
    post_tool_call("confirmBooking", {"confirm": True}, "tc-4")

    print("[5] Send end-of-call-report")
    requests.post(f"{BASE_URL}/webhook/vapi", json={
        "message": {
            "type": "end-of-call-report",
            "call": call_obj(),
            "endedReason": "hangup",
            "artifact": {"transcript": "AI: Hi... User: ... [full transcript here]"},
        }
    }, timeout=15).raise_for_status()

    print(f"\nDone. Check GET {BASE_URL}/admin/sessions/{CALL_ID} and {BASE_URL}/admin/bookings")


if __name__ == "__main__":
    main()
