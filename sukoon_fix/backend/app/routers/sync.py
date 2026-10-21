"""
Sukoon — Offline sync endpoint.

The patient app queues game sessions / mood check-ins / reminder responses in
browser localStorage while offline. When connectivity returns, it POSTs the
whole queue here in one batch. Each item carries a client-generated
idempotency key (`client_generated_id`) so a retried/duplicated batch never
creates duplicate records server-side.
"""
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, auth, adaptive_engine, serializers
from ..database import get_db

router = APIRouter(prefix="/api/sync", tags=["sync"])


@router.post("/batch")
def sync_batch(payload: schemas.SyncBatch, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if current.role != models.UserRole.patient or not current.patient_profile:
        raise HTTPException(status_code=403, detail="Patient account required")
    patient = current.patient_profile

    results = []
    for item in payload.items:
        existing = db.query(models.SyncQueueItem).filter(models.SyncQueueItem.client_generated_id == item.client_generated_id).first()
        if existing and existing.status == models.SyncStatus.synced:
            results.append({"client_generated_id": item.client_generated_id, "status": "already_synced"})
            continue

        queue_row = existing or models.SyncQueueItem(
            client_generated_id=item.client_generated_id,
            patient_id=patient.id,
            entity_type=item.entity_type,
            payload_json=json.dumps(item.payload),
            created_offline_at=_parse_dt(item.created_offline_at),
        )
        if not existing:
            db.add(queue_row)

        try:
            if item.entity_type == "mood":
                mood = item.payload.get("mood")
                date = item.payload.get("date") or datetime.utcnow().strftime("%Y-%m-%d")
                rec = models.MoodRecord(patient_id=patient.id, mood=mood, date=date, is_demo_data=False, synced=True)
                db.add(rec)
            elif item.entity_type == "game_session":
                p = item.payload
                activity = db.query(models.CognitiveActivity).filter(models.CognitiveActivity.code == p.get("activity_code")).first()
                if activity:
                    session = models.GameSession(patient_id=patient.id, activity_code=p.get("activity_code"),
                                                  difficulty=p.get("difficulty", patient.current_difficulty_level), synced=True)
                    db.add(session)
                    db.flush()
                    result = adaptive_engine.decide(patient.current_difficulty_level, p.get("accuracy", 0), p.get("avg_response_time_ms", 0))
                    record = models.PerformanceRecord(
                        session_id=session.id, patient_id=patient.id, activity_code=p.get("activity_code"),
                        score=p.get("score", 0), accuracy=p.get("accuracy", 0), attempts=p.get("attempts", 0),
                        correct_attempts=p.get("correct_attempts", 0), avg_response_time_ms=p.get("avg_response_time_ms", 0),
                        difficulty=p.get("difficulty", patient.current_difficulty_level),
                        new_difficulty=result.new_difficulty, adaptive_direction=result.direction,
                        adaptive_explanation_en=result.explanation_en, adaptive_explanation_as=result.explanation_as,
                    )
                    db.add(record)
                    patient.current_difficulty_level = result.new_difficulty
            elif item.entity_type == "reminder_response":
                rr_id = item.payload.get("response_id")
                status = item.payload.get("status")
                rr = db.query(models.ReminderResponse).filter(models.ReminderResponse.id == rr_id, models.ReminderResponse.patient_id == patient.id).first()
                if rr and status in ("completed", "snoozed"):
                    rr.status = models.ReminderStatus.completed if status == "completed" else models.ReminderStatus.snoozed
                    rr.responded_at = datetime.utcnow()
                    rr.synced = True
            elif item.entity_type == "routine_completion":
                routine_id = item.payload.get("routine_id")
                date = item.payload.get("date") or datetime.utcnow().strftime("%Y-%m-%d")
                existing_completion = db.query(models.RoutineCompletion).filter(
                    models.RoutineCompletion.routine_id == routine_id, models.RoutineCompletion.date == date
                ).first()
                if not existing_completion:
                    existing_completion = models.RoutineCompletion(routine_id=routine_id, patient_id=patient.id, date=date)
                    db.add(existing_completion)
                existing_completion.status = "completed"
                existing_completion.completed_at = datetime.utcnow()

            queue_row.status = models.SyncStatus.synced
            queue_row.synced_at = datetime.utcnow()
            db.commit()
            results.append({"client_generated_id": item.client_generated_id, "status": "synced"})
        except Exception as e:  # keep batch resilient — one bad item shouldn't fail the rest
            db.rollback()
            queue_row.status = models.SyncStatus.failed
            db.add(queue_row)
            db.commit()
            results.append({"client_generated_id": item.client_generated_id, "status": "failed", "error": str(e)})

    return {"results": results, "synced_count": len([r for r in results if r["status"] in ("synced", "already_synced")])}


def _parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None
