from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, auth, serializers, access, agentic_engine
from ..database import get_db
from ..notifications import notify_family

router = APIRouter(prefix="/api/doctor", tags=["doctor"])


@router.get("/patients/{patient_id}/agentic")
def agentic_overview(patient_id: str, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """Sukoon's multi-agent care network: live status from 5 specialised agents,
    a computed wellness risk score, the escalation decision log, and a unified
    cross-role care timeline — all derived from the patient's real logged data."""
    doc = access.doctor_for_user(db, current)
    access.ensure_doctor_authorized(db, doc, patient_id)
    return agentic_engine.build_overview(db, patient_id)


@router.post("/patients/{patient_id}/ask")
def ask_sukoon(patient_id: str, payload: schemas.AskSukoonQuery, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    doc = access.doctor_for_user(db, current)
    access.ensure_doctor_authorized(db, doc, patient_id)
    return {"answer": agentic_engine.answer_query(db, patient_id, payload.text)}


@router.get("/triage")
def triage(current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """Risk-ranked list across every authorized patient — surfaces who needs
    attention first when a doctor has more than one authorized patient."""
    doc = access.doctor_for_user(db, current)
    authorizations = (
        db.query(models.DoctorAuthorization)
        .filter(models.DoctorAuthorization.doctor_id == doc.id, models.DoctorAuthorization.status == models.AuthorizationStatus.approved)
        .all()
    )
    patients = []
    for authz in authorizations:
        p = db.query(models.Patient).filter(models.Patient.id == authz.patient_id).first()
        if p and p.user:
            patients.append((p.id, p.user.full_name))
    return agentic_engine.compute_triage(db, patients)


@router.get("/patients")
def authorized_patients(current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """Only patients with an approved DoctorAuthorization are ever visible here."""
    doc = access.doctor_for_user(db, current)
    authorizations = (
        db.query(models.DoctorAuthorization)
        .filter(models.DoctorAuthorization.doctor_id == doc.id, models.DoctorAuthorization.status == models.AuthorizationStatus.approved)
        .all()
    )
    out = []
    for authz in authorizations:
        p = db.query(models.Patient).filter(models.Patient.id == authz.patient_id).first()
        if not p:
            continue
        out.append({**serializers.patient_summary(p), "authorization": serializers.doctor_authorization(authz, doc, p)})
    return out


@router.get("/patients/{patient_id}/dashboard")
def patient_dashboard(patient_id: str, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    doc = access.doctor_for_user(db, current)
    authz = access.ensure_doctor_authorized(db, doc, patient_id)
    patient = access.get_patient_or_404(db, patient_id)
    auth.write_audit_log(db, current.id, "doctor.viewed_patient", "patient", patient_id)

    since30 = datetime.utcnow() - timedelta(days=30)
    result = {
        "patient": serializers.patient_summary(patient),
        "authorization": serializers.doctor_authorization(authz, doc, patient),
        "disclaimer": "Clinical decisions should not be based solely on Sukoon. This dashboard provides supportive information only.",
    }

    if authz.scope_cognitive_performance or authz.scope_activity_history:
        perf = db.query(models.PerformanceRecord).filter(models.PerformanceRecord.patient_id == patient_id, models.PerformanceRecord.timestamp >= since30).order_by(models.PerformanceRecord.timestamp).all()
        result["performance_30d"] = [serializers.performance_record(p) for p in perf]
    else:
        result["performance_30d"] = None

    if authz.scope_reminder_adherence:
        rows = (
            db.query(models.ReminderResponse, models.Reminder)
            .join(models.Reminder, models.ReminderResponse.reminder_id == models.Reminder.id)
            .filter(models.ReminderResponse.patient_id == patient_id)
            .order_by(models.ReminderResponse.fired_at.desc())
            .limit(30)
            .all()
        )
        result["reminder_adherence"] = [serializers.reminder_response(rr, rem) for rr, rem in rows]
    else:
        result["reminder_adherence"] = None

    if authz.scope_wearable_data:
        w = db.query(models.WearableData).filter(models.WearableData.patient_id == patient_id).order_by(models.WearableData.timestamp.desc()).limit(10).all()
        result["wearable_recent"] = [serializers.wearable(x) for x in w]
    else:
        result["wearable_recent"] = None

    if authz.scope_location:
        loc = db.query(models.LocationData).filter(models.LocationData.patient_id == patient_id).order_by(models.LocationData.timestamp.desc()).first()
        result["location_latest"] = serializers.location(loc) if loc else None
        sz = db.query(models.SafeZoneConfig).filter(models.SafeZoneConfig.patient_id == patient_id).first()
        result["safe_zone"] = serializers.safe_zone(sz) if sz else None
    else:
        result["location_latest"] = None
        result["safe_zone"] = None

    alerts = db.query(models.SafetyAlert).filter(models.SafetyAlert.patient_id == patient_id).order_by(models.SafetyAlert.created_at.desc()).limit(10).all()
    result["recent_alerts"] = [serializers.safety_alert(a) for a in alerts]

    return result


# ---- Hospital-file-style medical records ------------------------------------
# A "medical record" is one appointment's diagnosis/prescription/vitals/follow-up
# written by the doctor who saw the patient for that appointment — the same
# structure a real hospital file would use. Only the authorized doctor for a
# patient can write these; the patient, their caregiver (read-only) and any
# linked family member can read them, gated by the same scope_medical_records
# flag as everything else a doctor is granted.

@router.get("/patients/{patient_id}/appointments")
def patient_appointments(patient_id: str, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """Appointments for this patient, so the doctor can pick one to write/edit a
    hospital-file record against. Flags which appointments already have a record."""
    doc = access.doctor_for_user(db, current)
    access.ensure_doctor_authorized(db, doc, patient_id)
    appts = (
        db.query(models.Appointment)
        .filter(models.Appointment.patient_id == patient_id)
        .order_by(models.Appointment.date.desc(), models.Appointment.time.desc())
        .all()
    )
    out = []
    for a in appts:
        rec = db.query(models.MedicalRecord).filter(models.MedicalRecord.appointment_id == a.id).first()
        out.append({**serializers.appointment(a), "has_medical_record": rec is not None, "medical_record_id": rec.id if rec else None})
    return out


@router.get("/patients/{patient_id}/medical-records")
def list_medical_records(patient_id: str, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    doc = access.doctor_for_user(db, current)
    authz = access.ensure_doctor_authorized(db, doc, patient_id)
    if not authz.scope_medical_records:
        raise HTTPException(status_code=403, detail="You have not been granted access to this patient's medical records")
    rows = (
        db.query(models.MedicalRecord)
        .filter(models.MedicalRecord.patient_id == patient_id)
        .order_by(models.MedicalRecord.visit_date.desc())
        .all()
    )
    return [serializers.medical_record(r, doc) for r in rows]


@router.post("/medical-records")
def create_medical_record(payload: schemas.MedicalRecordCreate, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    doc = access.doctor_for_user(db, current)
    access.ensure_doctor_authorized(db, doc, payload.patient_id)

    appt = db.query(models.Appointment).filter(models.Appointment.id == payload.appointment_id, models.Appointment.patient_id == payload.patient_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found for this patient")

    existing = db.query(models.MedicalRecord).filter(models.MedicalRecord.appointment_id == payload.appointment_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="A medical record already exists for this appointment — edit it instead")

    rec = models.MedicalRecord(
        appointment_id=payload.appointment_id, patient_id=payload.patient_id, doctor_id=doc.id,
        visit_date=payload.visit_date, chief_complaint=payload.chief_complaint, diagnosis=payload.diagnosis,
        prescription=payload.prescription, vitals_bp=payload.vitals_bp, vitals_pulse=payload.vitals_pulse,
        vitals_weight_kg=payload.vitals_weight_kg, follow_up_instructions=payload.follow_up_instructions,
        follow_up_date=payload.follow_up_date,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    patient = access.get_patient_or_404(db, payload.patient_id)
    db.add(models.Notification(
        user_id=patient.user_id, title="New medical record added",
        body=f"Dr. {current.full_name} added a diagnosis/visit record for {payload.visit_date}.",
        category="medical_record",
    ))
    db.commit()
    auth.write_audit_log(db, current.id, "medical_record.created", "medical_record", rec.id)

    notify_family(
        db, payload.patient_id, title="New diagnosis from the doctor",
        body=f"Dr. {current.full_name} recorded a visit on {payload.visit_date}: {payload.diagnosis[:180]}",
        category="medical_record", important=True,
    )
    return serializers.medical_record(rec, doc)


@router.put("/medical-records/{record_id}")
def update_medical_record(record_id: str, payload: schemas.MedicalRecordUpdate, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    doc = access.doctor_for_user(db, current)
    rec = db.query(models.MedicalRecord).filter(models.MedicalRecord.id == record_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Not found")
    if rec.doctor_id != doc.id:
        raise HTTPException(status_code=403, detail="Only the doctor who wrote this record can edit it")
    access.ensure_doctor_authorized(db, doc, rec.patient_id)

    rec.chief_complaint = payload.chief_complaint
    rec.diagnosis = payload.diagnosis
    rec.prescription = payload.prescription
    rec.vitals_bp = payload.vitals_bp
    rec.vitals_pulse = payload.vitals_pulse
    rec.vitals_weight_kg = payload.vitals_weight_kg
    rec.follow_up_instructions = payload.follow_up_instructions
    rec.follow_up_date = payload.follow_up_date
    rec.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(rec)
    auth.write_audit_log(db, current.id, "medical_record.updated", "medical_record", rec.id)
    return serializers.medical_record(rec, doc)


@router.get("/medical-records/{record_id}")
def get_medical_record(record_id: str, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    doc = access.doctor_for_user(db, current)
    rec = db.query(models.MedicalRecord).filter(models.MedicalRecord.id == record_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Not found")
    access.ensure_doctor_authorized(db, doc, rec.patient_id)
    return serializers.medical_record(rec, doc)
