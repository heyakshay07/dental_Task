"""
VAPI webhook intake.

VAPI POSTs every server event to this single URL. All payloads share the
shape `{"message": {"type": "<type>", ...}}`. We only act on the handful of
types relevant to booking a dental appointment:

  - "tool-calls"        -> drive the booking state machine, MUST respond
                            with a `results` array (VAPI blocks on this).
  - "status-update"     -> track call lifecycle (ringing/in-progress/ended).
  - "end-of-call-report" -> finalize the session with the full transcript,
                            mark abandoned bookings.

Everything else is acknowledged with 200 and ignored -- VAPI does not
require (or wait on) a response for informational events, but replying 200
avoids it treating our endpoint as broken.
"""
from __future__ import annotations
import json
from fastapi import HTTPException

from fastapi import APIRouter, Header, HTTPException, Request

from app.config import get_settings
from app.conversation import state_machine
from app.models import ConversationTurn, VapiWebhookPayload
from app.storage import session_store

router = APIRouter()


def _verify_secret(x_vapi_secret: str | None) -> None:
    settings = get_settings()
    if settings.vapi_webhook_secret and x_vapi_secret != settings.vapi_webhook_secret:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")


@router.post("/webhook/vapi")
async def vapi_webhook(request: Request, x_vapi_secret: str | None = Header(default=None)):
    _verify_secret(x_vapi_secret)

    raw = await request.json()
    payload = VapiWebhookPayload.model_validate(raw)
    message = payload.message

    if message.type == "tool-calls":
        return _handle_tool_calls(message)

    if message.type == "status-update":
        return _handle_status_update(message)

    if message.type == "end-of-call-report":
        return _handle_end_of_call(message)

    # Informational event we don't act on (transcript, speech-update, etc.)
    return {"received": True}


def _call_id(message) -> str:
    call = message.call or {}
    call_id = call.get("id")
    if not call_id:
        raise HTTPException(status_code=400, detail="Missing call.id in webhook payload")
    return call_id


def _caller_phone(message) -> str | None:
    call = message.call or {}
    customer = call.get("customer") or {}
    return customer.get("number")


def _handle_tool_calls(message):
    call_id = _call_id(message)
    session = session_store.get_or_create_session(call_id, caller_phone=_caller_phone(message))

    if not message.toolCallList:
        return {"results": []}

    results = []
    for tool_call in message.toolCallList:
        step_result = state_machine.handle_tool_call(
            session=session, tool_name=tool_call.name, parameters=tool_call.parameters,
        )
        session = step_result.session  # carry forward mutations across multiple tool calls in one hit
        results.append({
            "toolCallId": tool_call.id,
            "result": step_result.speak,
        })

    return {"results": results}


def _handle_status_update(message):
    call_id = _call_id(message)
    session = session_store.get_or_create_session(call_id, caller_phone=_caller_phone(message))
    session.turns.append(ConversationTurn(role="system", content=f"status: {message.status}"))
    session_store.save_session(session)
    return {"received": True}


def _handle_end_of_call(message):
    call_id = _call_id(message)
    session = session_store.get_session(call_id)
    if session is None:
        return {"received": True}

    artifact = message.artifact or {}
    transcript = artifact.get("transcript")
    if transcript:
        session.turns.append(ConversationTurn(role="system", content=f"full_transcript: {transcript}"))

    if session.status == "in_progress":
        session.status = "abandoned"

    session.turns.append(ConversationTurn(
        role="system", content=f"call_ended: {message.endedReason or 'unknown'}",
    ))
    session_store.save_session(session)
    return {"received": True}
