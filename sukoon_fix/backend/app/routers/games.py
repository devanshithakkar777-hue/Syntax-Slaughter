from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, auth, serializers, adaptive_engine
from ..database import get_db

router = APIRouter(prefix="/api/games", tags=["games"])


@router.get("/activities")
def list_activities(current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    rows = db.query(models.CognitiveActivity).all()
    return [
        {
            "code": a.code, "name_en": a.name_en, "name_as": a.name_as,
            "domain": a.domain, "description_en": a.description_en, "description_as": a.description_as,
        }
        for a in rows
    ]


@router.post("/sessions")
def submit_session(payload: schemas.GameSessionCreate, current: models.User = Depends(auth.get_current_user),
                    db: Session = Depends(get_db)):
    if current.role != models.UserRole.patient or not current.patient_profile:
        raise HTTPException(status_code=403, detail="Patient account required")
    patient = current.patient_profile

    activity = db.query(models.CognitiveActivity).filter(models.CognitiveActivity.code == payload.activity_code).first()
    if not activity:
        raise HTTPException(status_code=400, detail="Unknown activity_code")

    # idempotency: if this offline-generated id was already synced, return the existing record
    if payload.client_generated_id:
        existing_queue = db.query(models.SyncQueueItem).filter(
            models.SyncQueueItem.client_generated_id == payload.client_generated_id
        ).first()
        if existing_queue and existing_queue.status == models.SyncStatus.synced:
            existing_pr = db.query(models.PerformanceRecord).filter(
                models.PerformanceRecord.id == existing_queue.entity_type
            ).first()
            if existing_pr:
                return serializers.performance_record(existing_pr)

    session = models.GameSession(
        patient_id=patient.id,
        activity_code=payload.activity_code,
        difficulty=payload.difficulty,
        started_at=datetime.utcnow() - timedelta(seconds=30),
        completed_at=datetime.utcnow(),
    )
    db.add(session)
    db.flush()

    result = adaptive_engine.decide(patient.current_difficulty_level, payload.accuracy, payload.avg_response_time_ms)

    record = models.PerformanceRecord(
        session_id=session.id,
        patient_id=patient.id,
        activity_code=payload.activity_code,
        score=payload.score,
        accuracy=payload.accuracy,
        attempts=payload.attempts,
        correct_attempts=payload.correct_attempts,
        avg_response_time_ms=payload.avg_response_time_ms,
        difficulty=payload.difficulty,
        new_difficulty=result.new_difficulty,
        adaptive_direction=result.direction,
        adaptive_explanation_en=result.explanation_en,
        adaptive_explanation_as=result.explanation_as,
    )
    db.add(record)
    patient.current_difficulty_level = result.new_difficulty

    if payload.client_generated_id:
        db.add(models.SyncQueueItem(
            client_generated_id=payload.client_generated_id,
            patient_id=patient.id,
            entity_type="game_session",
            payload_json="{}",
            status=models.SyncStatus.synced,
            synced_at=datetime.utcnow(),
        ))

    db.commit()
    db.refresh(record)
    return serializers.performance_record(record)


@router.get("/performance/{patient_id}")
def performance_history(patient_id: str, days: int = 30, current: models.User = Depends(auth.get_current_user),
                         db: Session = Depends(get_db)):
    from .. import access
    if current.role == models.UserRole.patient:
        if not current.patient_profile or current.patient_profile.id != patient_id:
            raise HTTPException(status_code=403, detail="Not your data")
    elif current.role == models.UserRole.caregiver:
        cg = access.caregiver_for_user(db, current)
        access.ensure_caregiver_owns_patient(db, cg, patient_id)
    elif current.role == models.UserRole.doctor:
        doc = access.doctor_for_user(db, current)
        authz = access.ensure_doctor_authorized(db, doc, patient_id)
        if not authz.scope_cognitive_performance and not authz.scope_activity_history:
            raise HTTPException(status_code=403, detail="Access to cognitive performance not authorized")

    since = datetime.utcnow() - timedelta(days=days)
    rows = (
        db.query(models.PerformanceRecord)
        .filter(models.PerformanceRecord.patient_id == patient_id, models.PerformanceRecord.timestamp >= since)
        .order_by(models.PerformanceRecord.timestamp)
        .all()
    )
    return [serializers.performance_record(r) for r in rows]
