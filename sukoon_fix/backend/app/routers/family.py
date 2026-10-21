"""Family dashboard — a broader household view than a single caregiver's.

A family member sees the patient's, caregiver's and doctor's data together
in one place, and is (along with the patient) the only role that can manage
doctor authorizations (see routers/authorization.py). Everything here is
read-only except doctor-authorization actions, which live in authorization.py
so there is exactly one place that logic is implemented.
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, auth, serializers, access, agentic_engine
from ..database import get_db
from ..reminders_engine import sync_reminders_for_patient
from ..media import validate_photo_data_url

router = APIRouter(prefix="/api/family", tags=["family"])


def _fam(db, user):
    return access.family_for_user(db, user)


@router.get("/patients/{patient_id}/agentic")
def agentic_overview(patient_id: str, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """Sukoon's multi-agent care network: live status from 5 specialised agents,
    a computed wellness risk score, the escalation decision log, and a unified
    cross-role care timeline — all derived from the patient's real logged data."""
    fam = _fam(db, current)
    access.ensure_family_owns_patient(db, fam, patient_id)
    return agentic_engine.build_overview(db, patient_id)


@router.post("/patients/{patient_id}/ask")
def ask_sukoon(patient_id: str, payload: schemas.AskSukoonQuery, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    fam = _fam(db, current)
    access.ensure_family_owns_patient(db, fam, patient_id)
    return {"answer": agentic_engine.answer_query(db, patient_id, payload.text)}


@router.get("/triage")
def triage(current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    fam = _fam(db, current)
    links = db.query(models.PatientFamilyRelationship).filter(models.PatientFamilyRelationship.family_member_id == fam.id).all()
    patients = []
    for link in links:
        p = db.query(models.Patient).filter(models.Patient.id == link.patient_id).first()
        if p and p.user:
            patients.append((p.id, p.user.full_name))
    return agentic_engine.compute_triage(db, patients)


@router.get("/patients")
def my_patients(current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    fam = _fam(db, current)
    links = db.query(models.PatientFamilyRelationship).filter(models.PatientFamilyRelationship.family_member_id == fam.id).all()
    out = []
    for link in links:
        p = db.query(models.Patient).filter(models.Patient.id == link.patient_id).first()
        if not p:
            continue
        open_alerts = db.query(models.SafetyAlert).filter(models.SafetyAlert.patient_id == p.id, models.SafetyAlert.acknowledged == False).count()  # noqa: E712
        out.append({**serializers.patient_summary(p), "open_alerts": open_alerts})
    return out


@router.get("/patients/{patient_id}/dashboard")
def family_dashboard(patient_id: str, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """Everything in one place: the patient's own profile, who their caregiver
    and authorized doctor(s) are, cognitive/mood trends, reminder adherence,
    wearable & location, appointments, hospital-file medical records, safety
    alerts and the current doctor-authorization list."""
    fam = _fam(db, current)
    access.ensure_family_owns_patient(db, fam, patient_id)
    sync_reminders_for_patient(db, patient_id)
    patient = access.get_patient_or_404(db, patient_id)

    since30 = datetime.utcnow() - timedelta(days=30)

    # Who is caring for this patient
    cg_links = db.query(models.PatientCaregiverRelationship).filter(models.PatientCaregiverRelationship.patient_id == patient_id).all()
    caregivers = []
    for link in cg_links:
        cg = db.query(models.Caregiver).filter(models.Caregiver.id == link.caregiver_id).first()
        if cg and cg.user:
            caregivers.append({"id": cg.id, "full_name": cg.user.full_name, "email": cg.user.email, "relationship_to_patient": cg.relationship_to_patient, "phone": cg.phone})

    doctor_authz = db.query(models.DoctorAuthorization).filter(models.DoctorAuthorization.patient_id == patient_id).order_by(models.DoctorAuthorization.requested_at.desc()).all()

    perf30 = db.query(models.PerformanceRecord).filter(models.PerformanceRecord.patient_id == patient_id, models.PerformanceRecord.timestamp >= since30).order_by(models.PerformanceRecord.timestamp).all()
    mood_rows = db.query(models.MoodRecord).filter(models.MoodRecord.patient_id == patient_id, models.MoodRecord.timestamp >= since30).order_by(models.MoodRecord.timestamp).all()

    reminder_rows = (
        db.query(models.ReminderResponse, models.Reminder)
        .join(models.Reminder, models.ReminderResponse.reminder_id == models.Reminder.id)
        .filter(models.ReminderResponse.patient_id == patient_id)
        .order_by(models.ReminderResponse.fired_at.desc())
        .limit(30)
        .all()
    )

    wearable_latest = db.query(models.WearableData).filter(models.WearableData.patient_id == patient_id).order_by(models.WearableData.timestamp.desc()).first()
    location_latest = db.query(models.LocationData).filter(models.LocationData.patient_id == patient_id).order_by(models.LocationData.timestamp.desc()).first()
    safe_zone = db.query(models.SafeZoneConfig).filter(models.SafeZoneConfig.patient_id == patient_id).first()

    appts = db.query(models.Appointment).filter(models.Appointment.patient_id == patient_id).order_by(models.Appointment.date.desc(), models.Appointment.time.desc()).all()
    medical_records = db.query(models.MedicalRecord).filter(models.MedicalRecord.patient_id == patient_id).order_by(models.MedicalRecord.visit_date.desc()).all()

    alerts = db.query(models.SafetyAlert).filter(models.SafetyAlert.patient_id == patient_id).order_by(models.SafetyAlert.created_at.desc()).limit(20).all()

    auth.write_audit_log(db, current.id, "family.viewed_patient", "patient", patient_id)

    return {
        "patient": serializers.patient_summary(patient),
        "caregivers": caregivers,
        "doctor_authorizations": [serializers.doctor_authorization(d, db.query(models.Doctor).get(d.doctor_id), patient) for d in doctor_authz],
        "performance_30d": [serializers.performance_record(p) for p in perf30],
        "mood_30d": [serializers.mood_record(m) for m in mood_rows],
        "reminder_adherence": [serializers.reminder_response(rr, rem) for rr, rem in reminder_rows],
        "wearable_latest": serializers.wearable(wearable_latest) if wearable_latest else None,
        "location_latest": serializers.location(location_latest) if location_latest else None,
        "safe_zone": serializers.safe_zone(safe_zone) if safe_zone else None,
        "appointments": [serializers.appointment(a) for a in appts],
        "medical_records": [serializers.medical_record(r, db.query(models.Doctor).get(r.doctor_id)) for r in medical_records],
        "alerts": [serializers.safety_alert(a) for a in alerts],
        "disclaimer": "Sukoon does not diagnose or treat dementia. AI-assisted insights are supportive signals only — clinical decisions should always be made by qualified healthcare professionals.",
    }


@router.get("/contacts/{patient_id}")
def list_contacts(patient_id: str, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    fam = _fam(db, current)
    access.ensure_family_owns_patient(db, fam, patient_id)
    rows = db.query(models.PatientContact).filter(models.PatientContact.patient_id == patient_id).order_by(models.PatientContact.display_order, models.PatientContact.created_at).all()
    return [serializers.patient_contact(c) for c in rows]


@router.post("/contacts")
def create_contact(payload: schemas.PatientContactCreate, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    fam = _fam(db, current)
    access.ensure_family_owns_patient(db, fam, payload.patient_id)
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
    fam = _fam(db, current)
    c = db.query(models.PatientContact).filter(models.PatientContact.id == contact_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Not found")
    access.ensure_family_owns_patient(db, fam, c.patient_id)
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
    fam = _fam(db, current)
    c = db.query(models.PatientContact).filter(models.PatientContact.id == contact_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Not found")
    access.ensure_family_owns_patient(db, fam, c.patient_id)
    db.delete(c)
    db.commit()
    return {"ok": True}


@router.put("/patients/{patient_id}/phone")
def set_patient_phone(patient_id: str, payload: schemas.PatientPhoneUpdate, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    fam = _fam(db, current)
    access.ensure_family_owns_patient(db, fam, patient_id)
    patient = access.get_patient_or_404(db, patient_id)
    patient.phone = payload.phone
    db.commit()
    return serializers.patient_summary(patient)


@router.get("/notifications")
def notifications(current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    rows = db.query(models.Notification).filter(models.Notification.user_id == current.id).order_by(models.Notification.created_at.desc()).limit(60).all()
    return [serializers.notification(n) for n in rows]


@router.get("/notification-preference")
def get_notification_preference(current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    fam = _fam(db, current)
    return {"notification_preference": fam.notification_preference or "important"}


@router.patch("/notification-preference")
def set_notification_preference(payload: schemas.FamilyNotificationPreferenceUpdate,
                                 current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    fam = _fam(db, current)
    fam.notification_preference = payload.notification_preference
    db.commit()
    return {"notification_preference": fam.notification_preference}


@router.post("/notifications/{notification_id}/read")
def mark_read(notification_id: str, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    n = db.query(models.Notification).filter(models.Notification.id == notification_id, models.Notification.user_id == current.id).first()
    if not n:
        raise HTTPException(status_code=404, detail="Not found")
    n.read = True
    db.commit()
    return {"ok": True}
