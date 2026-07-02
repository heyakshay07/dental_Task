from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.storage.database import Base


class Clinic(Base):
    __tablename__ = "clinics"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)


class ConversationSessionModel(Base):
    __tablename__ = "conversation_sessions"

    call_id: Mapped[str] = mapped_column(String, primary_key=True)
    clinic_id: Mapped[str] = mapped_column(String, default="default_clinic")
    caller_phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    step: Mapped[str] = mapped_column(String, default="collect_name")
    patient_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    service: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    requested_datetime: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    confirmed_datetime: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    booking_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="in_progress")
    turns: Mapped[list[dict]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class BookingModel(Base):
    __tablename__ = "bookings"

    booking_id: Mapped[str] = mapped_column(String, primary_key=True)
    call_id: Mapped[str] = mapped_column(String, nullable=False)
    clinic_id: Mapped[str] = mapped_column(String, default="default_clinic")
    patient_name: Mapped[str] = mapped_column(String, nullable=False)
    service: Mapped[str] = mapped_column(String, nullable=False)
    start_time: Mapped[str] = mapped_column(String, nullable=False)
    end_time: Mapped[str] = mapped_column(String, nullable=False)
    calendar_event_id: Mapped[str] = mapped_column(String, nullable=False)
    calendar_event_link: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    caller_phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sms_sid: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
