import random
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, auth, serializers, access, agentic_engine
from ..database import get_db
from ..reminders_engine import sync_reminders_for_patient
from ..notifications import notify_family
from ..media import validate_photo_data_url

router = APIRouter(prefix="/api/caregiver", tags=["caregiver"])


def _cg(db, user):
    return access.caregiver_for_user(db, user)


@router.get("/patients/{patient_id}/agentic")
def agentic_overview(patient_id: str, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """Sukoon's multi-agent care network: live status from 5 specialised agents,
    a computed wellness risk score, the escalation decision log, and a unified
    cross-role care timeline — all derived from the patient's real logged data."""
    cg = _cg(db, current)
    access.ensure_caregiver_owns_patient(db, cg, patient_id)
    return agentic_engine.build_overview(db, patient_id)


@router.post("/patients/{patient_id}/ask")
def ask_sukoon(patient_id: str, payload: schemas.AskSukoonQuery, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    cg = _cg(db, current)
    access.ensure_caregiver_owns_patient(db, cg, patient_id)
    return {"answer": agentic_engine.answer_query(db, patient_id, payload.text)}


@router.get("/triage")
def triage(current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """Risk-ranked list across every patient assigned to this caregiver —
    surfaces who needs attention first when managing more than one patient."""
    cg = _cg(db, current)
    links = db.query(models.PatientCaregiverRelationship).filter(models.PatientCaregiverRelationship.caregiver_id == cg.id).all()
    patients = []
    for link in links:
        p = db.query(models.Patient).filter(models.Patient.id == link.patient_id).first()
        if p and p.user:
            patients.append((p.id, p.user.full_name))
    return agentic_engine.compute_triage(db, patients)


@router.get("/patients")
def my_patients(current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    cg = _cg(db, current)
    links = db.query(models.PatientCaregiverRelationship).filter(models.PatientCaregiverRelationship.caregiver_id == cg.id).all()
    out = []
    today = datetime.utcnow().strftime("%Y-%m-%d")
    for link in links:
        p = db.query(models.Patient).filter(models.Patient.id == link.patient_id).first()
        if not p:
            continue
        sync_reminders_for_patient(db, p.id)
        mood_today = db.query(models.MoodRecord).filter(models.MoodRecord.patient_id == p.id, models.MoodRecord.date == today).first()
        open_alerts = db.query(models.SafetyAlert).filter(models.SafetyAlert.patient_id == p.id, models.SafetyAlert.acknowledged == False).count()  # noqa: E712
        routines = db.query(models.DailyRoutine).filter(models.DailyRoutine.patient_id == p.id, models.DailyRoutine.active == True).all()  # noqa: E712
        completed = 0
        for r in routines:
            c = db.query(models.RoutineCompletion).filter(models.RoutineCompletion.routine_id == r.id, models.RoutineCompletion.date == today).first()
            if c and c.status == "completed":
                completed += 1
        reminders_today = (
            db.query(models.ReminderResponse)
            .join(models.Reminder, models.ReminderResponse.reminder_id == models.Reminder.id)
            .filter(models.ReminderResponse.patient_id == p.id, models.ReminderResponse.date == today, models.Reminder.kind == models.ReminderKind.medicine)
            .all()
        )
        med_done = len([r for r in reminders_today if r.status == models.ReminderStatus.completed])
        hyd_rows = (
            db.query(models.ReminderResponse)
            .join(models.Reminder, models.ReminderResponse.reminder_id == models.Reminder.id)
            .filter(models.ReminderResponse.patient_id == p.id, models.ReminderResponse.date == today, models.Reminder.kind == models.ReminderKind.hydration)
            .all()
        )
        hyd_done = len([r for r in hyd_rows if r.status == models.ReminderStatus.completed])

        out.append({
            **serializers.patient_summary(p),
            "today_status": {
                "cognitive_activity_done": db.query(models.GameSession).filter(models.GameSession.patient_id == p.id, models.GameSession.started_at >= datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)).count() > 0,
                "medicine": f"{med_done}/{len(reminders_today)}" if reminders_today else "—",
                "hydration": f"{hyd_done}/{len(hyd_rows)}" if hyd_rows else "—",
                "routine_pct": round(100 * completed / len(routines)) if routines else 0,
                "mood": mood_today.mood if mood_today else None,
            },
            "open_alerts": open_alerts,
        })
    return out


@router.get("/patients/{patient_id}/dashboard")
def patient_dashboard(patient_id: str, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    cg = _cg(db, current)
    access.ensure_caregiver_owns_patient(db, cg, patient_id)
    sync_reminders_for_patient(db, patient_id)
    patient = access.get_patient_or_404(db, patient_id)

    since7 = datetime.utcnow() - timedelta(days=7)
    since30 = datetime.utcnow() - timedelta(days=30)
    perf30 = db.query(models.PerformanceRecord).filter(models.PerformanceRecord.patient_id == patient_id, models.PerformanceRecord.timestamp >= since30).order_by(models.PerformanceRecord.timestamp).all()

    mood_rows = db.query(models.MoodRecord).filter(models.MoodRecord.patient_id == patient_id, models.MoodRecord.timestamp >= since30).order_by(models.MoodRecord.timestamp).all()
    wearable_latest = db.query(models.WearableData).filter(models.WearableData.patient_id == patient_id).order_by(models.WearableData.timestamp.desc()).first()
    location_latest = db.query(models.LocationData).filter(models.LocationData.patient_id == patient_id).order_by(models.LocationData.timestamp.desc()).first()
    safe_zone = db.query(models.SafeZoneConfig).filter(models.SafeZoneConfig.patient_id == patient_id).first()
    alerts = db.query(models.SafetyAlert).filter(models.SafetyAlert.patient_id == patient_id).order_by(models.SafetyAlert.created_at.desc()).limit(20).all()
    doctors = db.query(models.DoctorAuthorization).filter(models.DoctorAuthorization.patient_id == patient_id).all()

    return {
        "patient": serializers.patient_summary(patient),
        "performance_30d": [serializers.performance_record(p) for p in perf30],
        "mood_30d": [serializers.mood_record(m) for m in mood_rows],
        "wearable_latest": serializers.wearable(wearable_latest) if wearable_latest else None,
        "location_latest": serializers.location(location_latest) if location_latest else None,
        "safe_zone": serializers.safe_zone(safe_zone) if safe_zone else None,
        "alerts": [serializers.safety_alert(a) for a in alerts],
        "doctor_authorizations": [serializers.doctor_authorization(d, db.query(models.Doctor).get(d.doctor_id), patient) for d in doctors],
    }


# ---- Reminders -----------------------------------------------------------

@router.post("/reminders")
def create_reminder(payload: schemas.ReminderCreate, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    cg = _cg(db, current)
    access.ensure_caregiver_owns_patient(db, cg, payload.patient_id)
    r = models.Reminder(
        patient_id=payload.patient_id, kind=payload.kind, title_en=payload.title_en, title_as=payload.title_as,
        detail=payload.detail, scheduled_time=payload.scheduled_time, days_of_week=payload.days_of_week or "MTWTFSS",
        escalation_minutes=payload.escalation_minutes, escalation_final_minutes=payload.escalation_final_minutes,
        created_by_caregiver_id=cg.id,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return serializers.reminder(r)


@router.get("/reminders/{patient_id}")
def list_reminders(patient_id: str, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    cg = _cg(db, current)
    access.ensure_caregiver_owns_patient(db, cg, patient_id)
    rows = db.query(models.Reminder).filter(models.Reminder.patient_id == patient_id).all()
    return [serializers.reminder(r) for r in rows]


@router.get("/reminders/{patient_id}/log")
def reminder_log(patient_id: str, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    cg = _cg(db, current)
    access.ensure_caregiver_owns_patient(db, cg, patient_id)
    sync_reminders_for_patient(db, patient_id)
    rows = (
        db.query(models.ReminderResponse, models.Reminder)
        .join(models.Reminder, models.ReminderResponse.reminder_id == models.Reminder.id)
        .filter(models.ReminderResponse.patient_id == patient_id)
        .order_by(models.ReminderResponse.fired_at.desc())
        .limit(50)
        .all()
    )
    return [serializers.reminder_response(rr, rem) for rr, rem in rows]


@router.get("/patients/{patient_id}/medicines/today")
def medicines_today(patient_id: str, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """Today's medicine checklist -- name, what it's for, and the dual
    patient+caregiver sign-off state. Mirrors the patient app's own medicine
    checklist so both sides see the exact same thing."""
    cg = _cg(db, current)
    access.ensure_caregiver_owns_patient(db, cg, patient_id)
    sync_reminders_for_patient(db, patient_id)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    rows = (
        db.query(models.ReminderResponse, models.Reminder)
        .join(models.Reminder, models.ReminderResponse.reminder_id == models.Reminder.id)
        .filter(
            models.ReminderResponse.patient_id == patient_id,
            models.ReminderResponse.date == today,
            models.Reminder.kind == models.ReminderKind.medicine,
        )
        .order_by(models.Reminder.scheduled_time)
        .all()
    )
    return [serializers.reminder_response(rr, rem) for rr, rem in rows]


@router.post("/reminders/{response_id}/confirm")
def confirm_medicine(response_id: str, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """Caregiver's independent sign-off that a medicine was actually taken.
    Completes the reminder only once the patient has also confirmed their side."""
    cg = _cg(db, current)
    rr = db.query(models.ReminderResponse).filter(models.ReminderResponse.id == response_id).first()
    if not rr:
        raise HTTPException(status_code=404, detail="Reminder not found")
    access.ensure_caregiver_owns_patient(db, cg, rr.patient_id)
    rem = db.query(models.Reminder).filter(models.Reminder.id == rr.reminder_id).first()
    if not rem or rem.kind != models.ReminderKind.medicine:
        raise HTTPException(status_code=400, detail="Only medicine reminders require caregiver confirmation")

    rr.caregiver_confirmed = True
    rr.caregiver_confirmed_at = datetime.utcnow()
    rr.caregiver_confirmed_by_id = cg.id
    if rr.patient_confirmed:
        rr.status = models.ReminderStatus.completed
        rr.responded_at = datetime.utcnow()
        db.commit()
        patient = access.get_patient_or_404(db, rr.patient_id)
        notify_family(
            db, rr.patient_id, title="Medicine taken",
            body=f"{rem.title_en} — confirmed taken by both {patient.user.full_name if patient.user else 'the patient'} and their caregiver.",
            category="medicine", important=False,
        )
    else:
        db.commit()
    return serializers.reminder_response(rr, rem)


@router.delete("/reminders/{reminder_id}")
def deactivate_reminder(reminder_id: str, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    cg = _cg(db, current)
    r = db.query(models.Reminder).filter(models.Reminder.id == reminder_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    access.ensure_caregiver_owns_patient(db, cg, r.patient_id)
    r.active = False
    db.commit()
    return {"ok": True}


# ---- Routines & appointments ---------------------------------------------

@router.post("/routines")
def create_routine(payload: schemas.RoutineCreate, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    cg = _cg(db, current)
    access.ensure_caregiver_owns_patient(db, cg, payload.patient_id)
    r = models.DailyRoutine(
        patient_id=payload.patient_id, period=payload.period, title_en=payload.title_en, title_as=payload.title_as,
        scheduled_time=payload.scheduled_time, is_custom=payload.is_custom, created_by_caregiver_id=cg.id,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return serializers.routine(r)


@router.get("/routines/{patient_id}")
def list_routines(patient_id: str, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    cg = _cg(db, current)
    access.ensure_caregiver_owns_patient(db, cg, patient_id)
    rows = db.query(models.DailyRoutine).filter(models.DailyRoutine.patient_id == patient_id, models.DailyRoutine.active == True).all()  # noqa: E712
    return [serializers.routine(r) for r in rows]


@router.post("/appointments")
def create_appointment(payload: schemas.AppointmentCreate, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    cg = _cg(db, current)
    access.ensure_caregiver_owns_patient(db, cg, payload.patient_id)
    a = models.Appointment(**payload.model_dump())
    db.add(a)
    db.commit()
    db.refresh(a)
    return serializers.appointment(a)


@router.get("/appointments/{patient_id}")
def list_appointments(patient_id: str, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    cg = _cg(db, current)
    access.ensure_caregiver_owns_patient(db, cg, patient_id)
    rows = db.query(models.Appointment).filter(models.Appointment.patient_id == patient_id).order_by(models.Appointment.date, models.Appointment.time).all()
    return [serializers.appointment(a) for a in rows]


# ---- Medical records (read-only hospital file) -----------------------------

@router.get("/medical-records/{patient_id}")
def medical_records(patient_id: str, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    cg = _cg(db, current)
    access.ensure_caregiver_owns_patient(db, cg, patient_id)
    rows = db.query(models.MedicalRecord).filter(models.MedicalRecord.patient_id == patient_id).order_by(models.MedicalRecord.visit_date.desc()).all()
    out = []
    for r in rows:
        doc = db.query(models.Doctor).filter(models.Doctor.id == r.doctor_id).first()
        out.append(serializers.medical_record(r, doc))
    return out


# ---- Alerts ---------------------------------------------------------------

@router.get("/alerts/{patient_id}")
def alerts(patient_id: str, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    cg = _cg(db, current)
    access.ensure_caregiver_owns_patient(db, cg, patient_id)
    sync_reminders_for_patient(db, patient_id)
    rows = db.query(models.SafetyAlert).filter(models.SafetyAlert.patient_id == patient_id).order_by(models.SafetyAlert.created_at.desc()).all()
    return [serializers.safety_alert(a) for a in rows]


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: str, payload: Optional[schemas.AlertAcknowledge] = None,
                       current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    cg = _cg(db, current)
    a = db.query(models.SafetyAlert).filter(models.SafetyAlert.id == alert_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Not found")
    access.ensure_caregiver_owns_patient(db, cg, a.patient_id)
    a.acknowledged = True
    a.acknowledged_at = datetime.utcnow()
    db.commit()

    note = (payload.note if payload else None) or "The alert has been taken care of. Patient is safe."
    caregiver_name = current.full_name
    notify_family(
        db, a.patient_id, title="Alert resolved — patient is safe",
        body=f"{caregiver_name}: {note}",
        category="safety", important=True,
    )
    return {"ok": True}


# ---- Safe zone / location --------------------------------------------------

@router.get("/location/{patient_id}")
def location_history(patient_id: str, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    cg = _cg(db, current)
    access.ensure_caregiver_owns_patient(db, cg, patient_id)
    rows = db.query(models.LocationData).filter(models.LocationData.patient_id == patient_id).order_by(models.LocationData.timestamp.desc()).limit(20).all()
    safe_zone = db.query(models.SafeZoneConfig).filter(models.SafeZoneConfig.patient_id == patient_id).first()
    return {"history": [serializers.location(r) for r in rows], "safe_zone": serializers.safe_zone(safe_zone) if safe_zone else None}


@router.post("/location/{patient_id}/safe-zone")
def set_safe_zone(patient_id: str, payload: schemas.SafeZoneUpdate, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    cg = _cg(db, current)
    access.ensure_caregiver_owns_patient(db, cg, patient_id)
    sz = db.query(models.SafeZoneConfig).filter(models.SafeZoneConfig.patient_id == patient_id).first()
    if not sz:
        sz = models.SafeZoneConfig(patient_id=patient_id)
        db.add(sz)
    sz.label = payload.label
    sz.center_lat = payload.center_lat
    sz.center_lng = payload.center_lng
    sz.radius_m = payload.radius_m
    sz.tracking_enabled = payload.tracking_enabled
    sz.consented = payload.consented
    sz.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(sz)
    if payload.consented:
        db.add(models.ConsentRecord(patient_id=patient_id, granted_by_user_id=current.id, category="location", granted=True))
        db.commit()
    auth.write_audit_log(db, current.id, "location.safe_zone_updated", "patient", patient_id)
    return serializers.safe_zone(sz)


@router.post("/location/{patient_id}/simulate-move")
def simulate_move(patient_id: str, payload: schemas.SimulateLocationMove, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """DEMO ONLY: simulates the patient's tracked device moving `distance_m` from the safe zone centre."""
    cg = _cg(db, current)
    access.ensure_caregiver_owns_patient(db, cg, patient_id)
    sz = db.query(models.SafeZoneConfig).filter(models.SafeZoneConfig.patient_id == patient_id).first()
    if not sz or not sz.tracking_enabled or not sz.consented:
        raise HTTPException(status_code=400, detail="Location tracking is not enabled/authorized for this patient")

    # crude offset: 0.000009 degrees latitude per metre (approx)
    deg_offset = payload.distance_m * 0.000009
    lat = sz.center_lat + deg_offset
    lng = sz.center_lng
    within = payload.distance_m <= sz.radius_m

    loc = models.LocationData(
        patient_id=patient_id, latitude=lat, longitude=lng,
        distance_from_safe_zone_m=payload.distance_m, within_safe_zone=within, is_demo_data=True,
    )
    db.add(loc)

    if not within:
        alert = models.SafetyAlert(
            patient_id=patient_id, alert_type="geofence", severity=models.AlertSeverity.warning,
            message_en=f"Patient may have moved outside the configured safe zone ({sz.label}, {sz.radius_m} m). Distance: {payload.distance_m:.0f} m.",
            message_as=f"ৰোগীগৰাকী নিৰাপদ অঞ্চলৰ বাহিৰলৈ গৈছে বুলি ধাৰণা কৰা হৈছে।",
            related_id=loc.id,
        )
        db.add(alert)
    db.commit()
    db.refresh(loc)

    if not within:
        # Leaving the safe zone is exactly the kind of update the "important
        # only" family preference is meant to still surface.
        notify_family(
            db, patient_id, title="Left safe zone",
            body=f"Patient may have moved outside {sz.label} — {payload.distance_m:.0f} m away.",
            category="safety", important=True,
        )
    return serializers.location(loc)


# ---- Wearable ---------------------------------------------------------------

@router.get("/wearable/{patient_id}")
def wearable_history(patient_id: str, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    cg = _cg(db, current)
    access.ensure_caregiver_owns_patient(db, cg, patient_id)
    rows = db.query(models.WearableData).filter(models.WearableData.patient_id == patient_id).order_by(models.WearableData.timestamp.desc()).limit(20).all()
    return [serializers.wearable(r) for r in rows]


@router.post("/wearable/{patient_id}/simulate-tick")
def simulate_wearable_tick(patient_id: str, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """DEMO ONLY: generates one plausible simulated wearable reading, clearly flagged as demo data."""
    cg = _cg(db, current)
    access.ensure_caregiver_owns_patient(db, cg, patient_id)
    w = models.WearableData(
        patient_id=patient_id, device_type="Smartwatch",
        heart_rate_bpm=random.randint(64, 96), steps=random.randint(500, 6500),
        activity_level=random.choice(["resting", "light", "active"]), battery_pct=random.randint(20, 100),
        is_demo_data=True,
    )
    db.add(w)
    db.commit()
    db.refresh(w)
    return serializers.wearable(w)


# ---- Patient contacts ("family tree" + call list) --------------------------
# Kept out of the patient app's own input surface by design (large-text,
# minimal-typing UI) — the caregiver or family dashboard manages this list,
# and the patient app only ever views/calls from it.

@router.get("/contacts/{patient_id}")
def list_contacts(patient_id: str, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    cg = _cg(db, current)
    access.ensure_caregiver_owns_patient(db, cg, patient_id)
    rows = db.query(models.PatientContact).filter(models.PatientContact.patient_id == patient_id).order_by(models.PatientContact.display_order, models.PatientContact.created_at).all()
    return [serializers.patient_contact(c) for c in rows]


@router.post("/contacts")
def create_contact(payload: schemas.PatientContactCreate, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    cg = _cg(db, current)
    access.ensure_caregiver_owns_patient(db, cg, payload.patient_id)
    photo = validate_photo_data_url(payload.photo_data_url)
    c = models.PatientContact(
        patient_id=payload.patient_id, name=payload.name, relationship_label=payload.relationship_label,
        contact_type=payload.contact_type, phone=payload.phone, photo_url=photo,
        linked_family_member_id=payload.linked_family_member_id, linked_caregiver_id=payload.linked_caregiver_id,
        display_order=payload.display_order,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return serializers.patient_contact(c)


@router.put("/contacts/{contact_id}")
def update_contact(contact_id: str, payload: schemas.PatientContactUpdate, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    cg = _cg(db, current)
    c = db.query(models.PatientContact).filter(models.PatientContact.id == contact_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Not found")
    access.ensure_caregiver_owns_patient(db, cg, c.patient_id)
    c.name = payload.name
    c.relationship_label = payload.relationship_label
    c.contact_type = payload.contact_type
    c.phone = payload.phone
    if payload.photo_data_url is not None:
        c.photo_url = validate_photo_data_url(payload.photo_data_url)
    c.display_order = payload.display_order
    db.commit()
    db.refresh(c)
    return serializers.patient_contact(c)


@router.delete("/contacts/{contact_id}")
def delete_contact(contact_id: str, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    cg = _cg(db, current)
    c = db.query(models.PatientContact).filter(models.PatientContact.id == contact_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Not found")
    access.ensure_caregiver_owns_patient(db, cg, c.patient_id)
    db.delete(c)
    db.commit()
    return {"ok": True}


@router.put("/patients/{patient_id}/phone")
def set_patient_phone(patient_id: str, payload: schemas.PatientPhoneUpdate, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """So the 'call the patient' button on the caregiver/family dashboards has a real number to dial."""
    cg = _cg(db, current)
    access.ensure_caregiver_owns_patient(db, cg, patient_id)
    patient = access.get_patient_or_404(db, patient_id)
    patient.phone = payload.phone
    db.commit()
    return serializers.patient_summary(patient)


# ---- Notifications ----------------------------------------------------------

@router.get("/notifications")
def notifications(current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    rows = db.query(models.Notification).filter(models.Notification.user_id == current.id).order_by(models.Notification.created_at.desc()).limit(30).all()
    return [serializers.notification(n) for n in rows]


@router.post("/notifications/{notification_id}/read")
def mark_read(notification_id: str, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    n = db.query(models.Notification).filter(models.Notification.id == notification_id, models.Notification.user_id == current.id).first()
    if not n:
        raise HTTPException(status_code=404, detail="Not found")
    n.read = True
    db.commit()
    return {"ok": True}
