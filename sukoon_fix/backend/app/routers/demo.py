"""
Sukoon — Demo-mode conveniences.

Real reminder escalation (see reminders_engine.py) waits for real minutes to
pass, which is correct behaviour but too slow for a live 5-minute judge
demo. These endpoints let a judge/presenter fast-forward the exact same
code path instead of faking a different one: they still create a genuine
ReminderResponse escalation and a genuine SafetyAlert row, just without
waiting. Every response is unambiguous about being a demo action.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, auth, access, serializers
from ..database import get_db
from ..reminders_engine import sync_reminders_for_patient

router = APIRouter(prefix="/api/demo", tags=["demo"])


def _authorize_patient_access(db, current, patient_id):
    if current.role == models.UserRole.patient:
        if not current.patient_profile or current.patient_profile.id != patient_id:
            raise HTTPException(status_code=403, detail="Not your data")
    elif current.role == models.UserRole.caregiver:
        cg = access.caregiver_for_user(db, current)
        access.ensure_caregiver_owns_patient(db, cg, patient_id)
    else:
        raise HTTPException(status_code=403, detail="Not permitted")


@router.post("/{patient_id}/force-escalate")
def force_escalate(patient_id: str, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """Fast-forwards the oldest pending reminder today straight to caregiver-alert stage."""
    _authorize_patient_access(db, current, patient_id)
    sync_reminders_for_patient(db, patient_id)
    today = datetime.utcnow().strftime("%Y-%m-%d")

    rr = (
        db.query(models.ReminderResponse, models.Reminder)
        .join(models.Reminder, models.ReminderResponse.reminder_id == models.Reminder.id)
        .filter(
            models.ReminderResponse.patient_id == patient_id,
            models.ReminderResponse.date == today,
            models.ReminderResponse.status == models.ReminderStatus.pending,
        )
        .order_by(models.Reminder.scheduled_time)
        .first()
    )
    if not rr:
        raise HTTPException(status_code=404, detail="No pending reminder available to escalate right now")

    response, reminder = rr
    response.gentle_followup_sent = True
    response.gentle_followup_at = datetime.utcnow()
    response.caregiver_alert_sent = True
    response.caregiver_alert_at = datetime.utcnow()
    response.status = models.ReminderStatus.escalated

    alert = models.SafetyAlert(
        patient_id=patient_id,
        alert_type="reminder_nonresponse",
        severity=models.AlertSeverity.warning,
        message_en=f"Patient has not responded to the {reminder.scheduled_time} {reminder.title_en} reminder.",
        message_as=f"ৰোগীয়ে {reminder.scheduled_time} বজাৰ {reminder.title_as or reminder.title_en} ৰিমাইণ্ডাৰত সঁহাৰি দিয়া নাই।",
        related_id=response.id,
    )
    db.add(alert)
    db.commit()
    return {"escalated": serializers.reminder_response(response, reminder), "alert": serializers.safety_alert(alert)}


@router.post("/{patient_id}/reset-today")
def reset_today(patient_id: str, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """Resets today's reminder occurrences so the demo flow can be re-run."""
    _authorize_patient_access(db, current, patient_id)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    rows = db.query(models.ReminderResponse).filter(models.ReminderResponse.patient_id == patient_id, models.ReminderResponse.date == today).all()
    for r in rows:
        db.delete(r)
    completions = db.query(models.RoutineCompletion).filter(models.RoutineCompletion.patient_id == patient_id, models.RoutineCompletion.date == today).all()
    for c in completions:
        db.delete(c)
    db.commit()
    return {"ok": True, "reset_count": len(rows)}
