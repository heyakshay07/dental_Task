from __future__ import annotations
from typing import Optional
from datetime import datetime

from app.models import ConversationSession, ConversationTurn, BookingStep
from app.storage.database import SessionLocal
from app.storage.sql_models import ConversationSessionModel

_cache: dict[str, ConversationSession] = {}

def get_session(call_id: str) -> Optional[ConversationSession]:
    if call_id in _cache:
        return _cache[call_id]

    db = SessionLocal()
    try:
        model = db.query(ConversationSessionModel).filter(ConversationSessionModel.call_id == call_id).first()
        if not model:
            return None
        
        session = ConversationSession(
            call_id=model.call_id,
            clinic_id=model.clinic_id,
            caller_phone=model.caller_phone,
            step=BookingStep(model.step),
            patient_name=model.patient_name,
            service=model.service,
            requested_datetime=model.requested_datetime,
            confirmed_datetime=model.confirmed_datetime,
            booking_id=model.booking_id,
            status=model.status,
            turns=[ConversationTurn(**turn) for turn in model.turns],
            created_at=model.created_at,
            updated_at=model.updated_at
        )
        _cache[call_id] = session
        return session
    finally:
        db.close()

def get_or_create_session(call_id: str, clinic_id: str = "default_clinic", caller_phone: Optional[str] = None) -> ConversationSession:
    existing = get_session(call_id)
    if existing:
        return existing

    session = ConversationSession(call_id=call_id, clinic_id=clinic_id, caller_phone=caller_phone)
    save_session(session)
    return session

def save_session(session: ConversationSession) -> None:
    session.updated_at = datetime.utcnow()
    _cache[session.call_id] = session

    db = SessionLocal()
    try:
        model = db.query(ConversationSessionModel).filter(ConversationSessionModel.call_id == session.call_id).first()
        if not model:
            model = ConversationSessionModel(call_id=session.call_id)
            db.add(model)
        
        model.clinic_id = session.clinic_id
        model.caller_phone = session.caller_phone
        model.step = session.step.value
        model.patient_name = session.patient_name
        model.service = session.service
        model.requested_datetime = session.requested_datetime
        model.confirmed_datetime = session.confirmed_datetime
        model.booking_id = session.booking_id
        model.status = session.status
        model.turns = [turn.model_dump(mode="json") for turn in session.turns]
        model.updated_at = session.updated_at
        
        db.commit()
    finally:
        db.close()

def list_sessions(clinic_id: Optional[str] = None, limit: int = 100) -> list[ConversationSession]:
    db = SessionLocal()
    try:
        query = db.query(ConversationSessionModel)
        if clinic_id:
            query = query.filter(ConversationSessionModel.clinic_id == clinic_id)
        models = query.order_by(ConversationSessionModel.updated_at.desc()).limit(limit).all()
        
        sessions = []
        for model in models:
            session = ConversationSession(
                call_id=model.call_id,
                clinic_id=model.clinic_id,
                caller_phone=model.caller_phone,
                step=BookingStep(model.step),
                patient_name=model.patient_name,
                service=model.service,
                requested_datetime=model.requested_datetime,
                confirmed_datetime=model.confirmed_datetime,
                booking_id=model.booking_id,
                status=model.status,
                turns=[ConversationTurn(**turn) for turn in model.turns],
                created_at=model.created_at,
                updated_at=model.updated_at
            )
            sessions.append(session)
        return sessions
    finally:
        db.close()
