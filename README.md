# Dental Appointment Booking Agent — Backend

Backend for a VAPI-powered voice AI receptionist for a dental clinic. Handles
inbound call webhooks, drives a multi-turn booking conversation, books real
Google Calendar events, sends Twilio SMS confirmations, and logs everything
to Firestore behind an admin REST API.

## Architecture

```
VAPI (voice) --POST--> /webhook/vapi --> state_machine --> calendar_service (Google Calendar)
                                      |                 \-> sms_service (Twilio)
                                      \-> session_store / booking_store (Firestore)

Admin/dashboard --GET--> /admin/bookings, /admin/sessions/{call_id}
```

- **`app/routers/webhook.py`** — the single VAPI server URL. Dispatches on
  `message.type`: `tool-calls` (drives the booking flow and must return a
  `results` array), `status-update`, `end-of-call-report`.
- **`app/conversation/state_machine.py`** — explicit state machine
  (`COLLECT_NAME -> COLLECT_SERVICE -> COLLECT_DATETIME -> CONFIRM -> DONE`).
  Each step only advances via one specific VAPI tool/function call, so an
  out-of-order or replayed tool call gets re-prompted instead of corrupting
  state. The LLM does natural-language extraction (via VAPI's function
  schema); the server only validates and decides what's said next.
- **`app/services/calendar_service.py`** — real Google Calendar API
  (freebusy check + event insert), no mocking.
- **`app/services/sms_service.py`** — real Twilio API call.
- **`app/storage/`** — Firestore-backed session + booking persistence, with
  a small in-process cache to avoid a Firestore round trip on every single
  webhook hit within one call.
- **`app/routers/admin.py`** — read-only REST API for bookings and
  per-caller conversation history, protected by a static API key header.

### Why Firestore-backed sessions, not in-memory

Railway/Render can restart or run multiple instances behind a load
balancer. An in-memory dict would lose a caller's progress on restart or go
inconsistent across instances. Firestore makes any instance able to handle
any webhook hit for a given `call.id`.

### Scaling to ~1,000 clinics (what I'd change with more time)

- `ConversationSession` and `Booking` already carry a `clinic_id` field.
  Today it defaults to `"default_clinic"`; in a real multi-tenant version,
  each clinic would have its own VAPI phone number / assistant, and the
  webhook would resolve `clinic_id` from `call.phoneNumberId` via a
  `clinics` Firestore collection (mapping phone number -> clinic config:
  calendar ID, Twilio sender, business hours, service list).
- The service list (`CLINIC_SERVICES`) and business hours
  (`BUSINESS_START_HOUR`/`BUSINESS_END_HOUR`) are hardcoded constants right
  now — these should move into the per-clinic config doc.
- The admin API's single static `ADMIN_API_KEY` should become per-clinic
  auth (JWT or OAuth), since right now one key can see every clinic's data.
- Firestore composite indexes would be needed on `(clinic_id, updated_at)`
  and `(clinic_id, created_at)` for the list queries to stay fast at scale
  (Firestore will prompt for these automatically the first time the query
  runs against real data).
- Google Calendar API has per-calendar quota limits; at real scale I'd put
  a queue (e.g. Cloud Tasks) in front of `book_appointment` rather than
  calling it synchronously inside the webhook handler.

## Setup

### 1. Clone and install

```bash
git clone <your-repo-url>
cd dental-booking-agent
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Google Cloud service account (Calendar + Firestore)

1. Create/select a GCP project.
2. Enable the **Google Calendar API** and **Cloud Firestore API**.
3. Create a Firestore database (Native mode) in the project.
4. Create a service account -> generate a JSON key -> download it.
5. Open Google Calendar in the browser, create (or use) a test calendar,
   and share it with the service account's `client_email` (found in the
   JSON key) with **"Make changes to events"** permission.
6. Copy that test calendar's ID (Calendar Settings -> "Integrate calendar"
   -> Calendar ID, looks like `xxxxx@group.calendar.google.com`).

### 3. Twilio test credentials

1. Sign up at twilio.com, grab your **Account SID** and **Auth Token**
   from the console.
2. Use a Twilio test/magic number as `TWILIO_FROM_NUMBER`
   (e.g. `+15005550006`) so you don't get charged while testing.

### 4. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:
- `GOOGLE_APPLICATION_CREDENTIALS=./service-account.json` and place the
  downloaded key file at that path (or set `GOOGLE_SERVICE_ACCOUNT_JSON` to
  the raw JSON contents instead — useful on Railway/Render where uploading
  a file isn't convenient; see `app/main.py`).
- `GOOGLE_CALENDAR_ID` — the test calendar ID from step 2.6.
- `FIRESTORE_PROJECT_ID` — your GCP project ID.
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`.
- `ADMIN_API_KEY` — any long random string; required in the
  `X-Admin-Api-Key` header for all `/admin/*` endpoints.

### 5. Run locally

```bash
uvicorn app.main:app --reload --port 8000
```

Visit `http://localhost:8000/health` -> `{"status": "healthy"}`.
Interactive API docs: `http://localhost:8000/docs`.

### 6. Run the test suite

```bash
pytest tests/ -v
```

These are pure unit tests against the state machine with the Calendar/SMS/
Firestore calls mocked out, so they run with zero external credentials.

### 7. Simulate a full call locally (no real VAPI account needed)

```bash
python scripts/simulate_call.py http://localhost:8000
```
```bash
 python scripts/simulate_call.py http://localhost:8000 
```

This POSTs a sequence of webhook payloads shaped exactly like real VAPI
events (`tool-calls` x4, then `end-of-call-report`), driving the state
machine through name -> service -> datetime -> confirm, actually booking a
real Google Calendar event and sending a real Twilio SMS. Then check:

```bash
curl -H "X-Admin-Api-Key: $ADMIN_API_KEY" http://localhost:8000/admin/bookings
curl -H "X-Admin-Api-Key: $ADMIN_API_KEY" http://localhost:8000/admin/sessions/<call_id>
```

## Deploying

### Railway

```bash
railway init
railway up
```

Then in the Railway dashboard, set all the env vars from `.env` (paste the
service account JSON directly into `GOOGLE_SERVICE_ACCOUNT_JSON` rather
than trying to upload a file). `railway.json` and `Procfile` are already
configured with the start command.

### Render

Push to GitHub, then "New Web Service" -> connect the repo -> Render will
pick up `render.yaml` automatically. Set the `sync: false` env vars in the
Render dashboard (secrets aren't committed to the repo).

## Wiring up a real VAPI assistant

1. Create an assistant in the VAPI dashboard (or via API) using
   `vapi_assistant_config.json` as a starting point — it defines the four
   tool/function schemas (`providePatientName`, `selectService`,
   `selectDateTime`, `confirmBooking`) that the state machine expects.
2. Set `serverUrl` to your deployed URL + `/webhook/vapi`.
3. Set `serverMessages` to include at least `tool-calls`, `status-update`,
   `end-of-call-report`.
4. (Optional) Set a server secret in the VAPI dashboard and set
   `VAPI_WEBHOOK_SECRET` in your env to match — the webhook checks the
   `x-vapi-secret` header if that's configured.
5. Attach a phone number to the assistant and call it.

## API Reference

| Endpoint | Method | Auth | Purpose |
|---|---|---|---|
| `/webhook/vapi` | POST | optional `x-vapi-secret` header | VAPI server URL — all call events |
| `/admin/bookings` | GET | `X-Admin-Api-Key` header | List all bookings |
| `/admin/sessions` | GET | `X-Admin-Api-Key` header | List all conversation sessions |
| `/admin/sessions/{call_id}` | GET | `X-Admin-Api-Key` header | Full conversation history for one caller |
| `/health` | GET | none | Liveness check |

## Known trade-offs (48-hour scope)

- Single hardcoded `CLINIC_SERVICES` list and business hours instead of
  per-clinic config — noted above as the first thing to generalize.
- No retry/backoff around the Google Calendar or Twilio calls; a failed
  calendar write inside `confirmBooking` currently surfaces as a 500
  rather than gracefully degrading. With more time I'd wrap both in retry
  logic and a fallback "we'll call you back to confirm" message.
- No idempotency key on calendar event creation — if VAPI retries a
  `tool-calls` webhook after a timeout, a duplicate event could theoretically
  be created. I'd add a deterministic idempotency check (e.g. search for an
  existing event with the same `call_id` in its description before
  inserting).
- Date/time parsing uses `dateutil`'s fuzzy parser rather than a dedicated
  NLP date parser — good enough for common phrasing but not exhaustive for
  every way a caller might say a date.
