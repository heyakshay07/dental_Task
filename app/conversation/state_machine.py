"""
The booking conversation flow, modeled as an explicit state machine:

    COLLECT_NAME -> COLLECT_SERVICE -> COLLECT_DATETIME -> CONFIRM -> DONE

Each step is only allowed to advance via ONE specific VAPI tool call. This
is the key design decision: instead of trying to parse free text ourselves,
we let the VAPI assistant's LLM do the extraction (via its own tool/function
schema) and our server just validates the extracted value, decides the next
question, and enforces that steps can't be skipped or replayed out of order
(e.g. a caller can't "confirm" a booking before a service was ever picked).

TOOL_STEP_MAP ties each VAPI function name to the step it's allowed to
advance. If a tool call for the wrong step arrives (assistant confused,
user changed their mind, etc.) we re-prompt for the current step instead of
silently accepting bad state.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from dateutil import parser as dateparser

from app.models import BookingStep, ConversationSession, ConversationTurn
from app.services import calendar_service, sms_service
from app.storage import session_store

CLINIC_SERVICES = {
    "cleaning": "Dental Cleaning",
    "checkup": "General Checkup",
    "filling": "Cavity Filling",
    "root canal": "Root Canal",
    "whitening": "Teeth Whitening",
    "extraction": "Tooth Extraction",
    "braces consultation": "Braces / Orthodontics Consultation",
}

TOOL_STEP_MAP = {
    "providePatientName": BookingStep.COLLECT_NAME,
    "selectService": BookingStep.COLLECT_SERVICE,
    "selectDateTime": BookingStep.COLLECT_DATETIME,
    "confirmBooking": BookingStep.CONFIRM,
}


@dataclass
class StepResult:
    """What we hand back to the webhook layer to relay to VAPI."""
    speak: str          # text the assistant should say next
    session: ConversationSession
    success: bool = True


def _match_service(raw: str) -> Optional[str]:
    raw_lower = raw.strip().lower()
    for key, label in CLINIC_SERVICES.items():
        if key in raw_lower or raw_lower in key:
            return label
    return None


def handle_tool_call(session: ConversationSession, tool_name: str,
                      parameters: dict[str, Any]) -> StepResult:
    """
    Main entry point. Dispatches to the handler for the session's CURRENT
    step, regardless of which tool VAPI thinks it's calling -- this is the
    guard against out-of-order / replayed tool calls.
    """
    session.turns.append(ConversationTurn(
        role="tool", content=str(parameters), tool_name=tool_name,
    ))

    expected_tool_step = TOOL_STEP_MAP.get(tool_name)
    if expected_tool_step is None:
        return StepResult(
            speak="Sorry, I didn't understand that. Could you repeat that?",
            session=session, success=False,
        )

    if session.step == BookingStep.DONE:
        return StepResult(
            speak="Your appointment is already booked. Is there anything else I can help with?",
            session=session,
        )

    if expected_tool_step != session.step:
        # Out-of-order call -- re-ask for whatever the current step needs.
        return StepResult(speak=_reprompt_for_step(session), session=session, success=False)

    handler = _STEP_HANDLERS[session.step]
    result = handler(session, parameters)
    session_store.save_session(result.session)
    return result


def _reprompt_for_step(session: ConversationSession) -> str:
    prompts = {
        BookingStep.COLLECT_NAME: "Could I get your full name, please?",
        BookingStep.COLLECT_SERVICE: (
            "Which service are you here for -- cleaning, checkup, filling, "
            "root canal, whitening, extraction, or a braces consultation?"
        ),
        BookingStep.COLLECT_DATETIME: "What day and time would you like to come in?",
        BookingStep.CONFIRM: "Shall I go ahead and confirm that appointment for you?",
    }
    return prompts.get(session.step, "Could you say that again?")


def _handle_name(session: ConversationSession, params: dict[str, Any]) -> StepResult:
    name = (params.get("name") or "").strip()
    if len(name) < 2:
        return StepResult(speak="Sorry, I didn't catch your name. Could you spell it out for me?",
                           session=session, success=False)
    session.patient_name = name
    session.step = BookingStep.COLLECT_SERVICE
    speak = (
        f"Thanks, {name.split()[0]}. Which service would you like to book -- "
        "cleaning, checkup, filling, root canal, whitening, extraction, "
        "or a braces consultation?"
    )
    session.turns.append(ConversationTurn(role="assistant", content=speak))
    return StepResult(speak=speak, session=session)


def _handle_service(session: ConversationSession, params: dict[str, Any]) -> StepResult:
    raw = (params.get("service") or "").strip()
    matched = _match_service(raw)
    if not matched:
        speak = (
            "I don't have that as one of our services. We offer cleaning, checkup, "
            "filling, root canal, whitening, extraction, or a braces consultation -- "
            "which would you like?"
        )
        return StepResult(speak=speak, session=session, success=False)

    session.service = matched
    session.step = BookingStep.COLLECT_DATETIME
    speak = f"Got it, {matched}. What day and time works best for you?"
    session.turns.append(ConversationTurn(role="assistant", content=speak))
    return StepResult(speak=speak, session=session)


def _handle_datetime(session: ConversationSession, params: dict[str, Any]) -> StepResult:
    raw = (params.get("preferredDateTime") or "").strip()
    try:
        # fuzzy=True lets us parse things like "next Tuesday at 3pm"
        parsed = dateparser.parse(raw, fuzzy=True, default=datetime.now())
    except (ValueError, OverflowError):
        parsed = None

    if not parsed:
        speak = "Sorry, I didn't catch a valid date and time. Could you tell me the day and time again?"
        return StepResult(speak=speak, session=session, success=False)

    session.requested_datetime = parsed.isoformat()

    slot = calendar_service.find_available_slot(parsed)
    if slot is None:
        speak = (
            "I'm not finding any open slots near that time in the next two weeks. "
            "Could you suggest another day?"
        )
        return StepResult(speak=speak, session=session, success=False)

    session.confirmed_datetime = slot.isoformat()
    session.step = BookingStep.CONFIRM

    friendly = slot.strftime("%A, %B %d at %I:%M %p")
    if slot.isoformat()[:16] == parsed.isoformat()[:16]:
        speak = f"{friendly} is available. Shall I confirm that appointment for {session.service}?"
    else:
        speak = (
            f"That exact time isn't available, but {friendly} is open. "
            f"Shall I book {session.service} for then?"
        )
    session.turns.append(ConversationTurn(role="assistant", content=speak))
    return StepResult(speak=speak, session=session)


def _handle_confirm(session: ConversationSession, params: dict[str, Any]) -> StepResult:
    confirmed = bool(params.get("confirm"))
    if not confirmed:
        session.step = BookingStep.COLLECT_DATETIME
        session.confirmed_datetime = None
        speak = "No problem. What other day or time would you like instead?"
        session.turns.append(ConversationTurn(role="assistant", content=speak))
        return StepResult(speak=speak, session=session)

    start = datetime.fromisoformat(session.confirmed_datetime)
    event = calendar_service.book_appointment(
        patient_name=session.patient_name,
        service=session.service,
        start_time=start,
        call_id=session.call_id,
    )

    sms_sid = None
    if session.caller_phone:
        sms_sid = sms_service.send_confirmation_sms(
            to_number=session.caller_phone,
            patient_name=session.patient_name,
            service=session.service,
            start_time=start,
        )

    session.booking_id = event["event_id"]
    session.status = "booked"
    session.step = BookingStep.DONE

    from app.storage import booking_store
    booking_store.save_booking(
        session=session, event=event, sms_sid=sms_sid, start_time=start,
    )

    friendly = start.strftime("%A, %B %d at %I:%M %p")
    speak = (
        f"You're all set, {session.patient_name.split()[0]}. Your {session.service} "
        f"appointment is confirmed for {friendly}"
        + (". A confirmation text is on its way." if sms_sid else ".")
    )
    session.turns.append(ConversationTurn(role="assistant", content=speak))
    return StepResult(speak=speak, session=session)


_STEP_HANDLERS = {
    BookingStep.COLLECT_NAME: _handle_name,
    BookingStep.COLLECT_SERVICE: _handle_service,
    BookingStep.COLLECT_DATETIME: _handle_datetime,
    BookingStep.CONFIRM: _handle_confirm,
}
