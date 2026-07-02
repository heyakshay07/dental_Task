"""
Data models.

Two families here:
1. VAPI wire format (loosely typed on purpose — VAPI's payloads carry a lot
   of fields we don't care about, so we only pull out what we need instead
   of failing validation on unknown fields).
2. Our own domain models (ConversationSession, Booking) that get persisted
   to Firestore.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# --------------------------------------------------------------------------
# VAPI wire format
# --------------------------------------------------------------------------

class VapiToolCall(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    name: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class VapiMessage(BaseModel):
    """The `message` object inside every VAPI server webhook POST body."""
    model_config = ConfigDict(extra="allow")
    type: str
    call: Optional[dict[str, Any]] = None
    toolCallList: Optional[list[VapiToolCall]] = None
    status: Optional[str] = None
    endedReason: Optional[str] = None
    artifact: Optional[dict[str, Any]] = None


class VapiWebhookPayload(BaseModel):
    model_config = ConfigDict(extra="allow")
    message: VapiMessage


# --------------------------------------------------------------------------
# Domain models
# --------------------------------------------------------------------------

class BookingStep(str, Enum):
    COLLECT_NAME = "collect_name"
    COLLECT_SERVICE = "collect_service"
    COLLECT_DATETIME = "collect_datetime"
    CONFIRM = "confirm"
    DONE = "done"


class ConversationTurn(BaseModel):
    role: str  # "assistant" | "user" | "system" | "tool"
    content: str
    tool_name: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ConversationSession(BaseModel):
    """One caller's progress through the booking flow. Keyed by VAPI call.id."""
    call_id: str
    clinic_id: str = "default_clinic"
    caller_phone: Optional[str] = None
    step: BookingStep = BookingStep.COLLECT_NAME
    patient_name: Optional[str] = None
    service: Optional[str] = None
    requested_datetime: Optional[str] = None  # ISO string, patient's stated preference
    confirmed_datetime: Optional[str] = None  # ISO string, actually booked slot
    booking_id: Optional[str] = None
    status: str = "in_progress"  # in_progress | booked | abandoned | failed
    turns: list[ConversationTurn] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Booking(BaseModel):
    booking_id: str
    call_id: str
    clinic_id: str = "default_clinic"
    patient_name: str
    service: str
    start_time: str  # ISO 8601
    end_time: str    # ISO 8601
    calendar_event_id: str
    calendar_event_link: Optional[str] = None
    caller_phone: Optional[str] = None
    sms_sid: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
