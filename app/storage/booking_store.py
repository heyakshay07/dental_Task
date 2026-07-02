from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from app.models import Booking, ConversationSession
from app.storage.database import SessionLocal
from app.storage.sql_models import BookingModel

def save_booking(session: ConversationSession, event: dict, sms_sid: Optional[str], start_time: datetime) -> Booking:
    booking = Booking(
        booking_id=str(uuid.uuid4()),
        call_id=session.call_id,
        clinic_id=session.clinic_id,
        patient_name=session.patient_name,
        service=session.service,
        start_time=event["start"],
        end_time=event["end"],
        calendar_event_id=event["event_id"],
        calendar_event_link=event.get("event_link"),
        caller_phone=session.caller_phone,
        sms_sid=sms_sid,
    )
    
    db = SessionLocal()
    try:
        model = BookingModel(
            booking_id=booking.booking_id,
            call_id=booking.call_id,
            clinic_id=booking.clinic_id,
            patient_name=booking.patient_name,
            service=booking.service,
            start_time=booking.start_time,
            end_time=booking.end_time,
            calendar_event_id=booking.calendar_event_id,
            calendar_event_link=booking.calendar_event_link,
            caller_phone=booking.caller_phone,
            sms_sid=booking.sms_sid,
            created_at=booking.created_at
        )
        db.add(model)
        db.commit()
    finally:
        db.close()
        
    return booking

def list_bookings(clinic_id: Optional[str] = None, limit: int = 200) -> list[Booking]:
    db = SessionLocal()
    try:
        query = db.query(BookingModel)
        if clinic_id:
            query = query.filter(BookingModel.clinic_id == clinic_id)
        models = query.order_by(BookingModel.created_at.desc()).limit(limit).all()
        
        bookings = []
        for model in models:
            booking = Booking(
                booking_id=model.booking_id,
                call_id=model.call_id,
                clinic_id=model.clinic_id,
                patient_name=model.patient_name,
                service=model.service,
                start_time=model.start_time,
                end_time=model.end_time,
                calendar_event_id=model.calendar_event_id,
                calendar_event_link=model.calendar_event_link,
                caller_phone=model.caller_phone,
                sms_sid=model.sms_sid,
                created_at=model.created_at
            )
            bookings.append(booking)
        return bookings
    finally:
        db.close()
