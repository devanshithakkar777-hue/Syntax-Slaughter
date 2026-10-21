from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, auth, serializers, access
from ..database import get_db

router = APIRouter(prefix="/api/authorization", tags=["authorization"])

DEMO_DOCTOR_PASSWORD = "Doctor@123"  # used only when a family member invites a brand-new doctor in the demo


@router.post("")
def request_authorization(payload: schemas.DoctorAuthorizationCreate, current: models.User = Depends(auth.get_current_user),
                           db: Session = Depends(get_db)):
    """Doctor authorization is managed from the Family dashboard (or by the patient
    themselves) — the caregiver app only shows a read-only list, per the product
    decision to keep one clear place for granting/revoking clinical access."""
    fam = None
    if current.role == models.UserRole.family:
        fam = access.family_for_user(db, current)
        access.ensure_family_owns_patient(db, fam, payload.patient_id)
    elif current.role == models.UserRole.patient:
        if not current.patient_profile or current.patient_profile.id != payload.patient_id:
            raise HTTPException(status_code=403, detail="Not your data")
    else:
        raise HTTPException(status_code=403, detail="Only the patient or a linked family member can request doctor access")

    doctor_user = db.query(models.User).filter(models.User.email == payload.doctor_email.lower()).first()
    provisioned_password = None
    if doctor_user and doctor_user.role != models.UserRole.doctor:
        raise HTTPException(status_code=400, detail="That email is already registered under a different role")

    if not doctor_user:
        doctor_user = models.User(
            email=payload.doctor_email.lower(),
            password_hash=auth.hash_password(DEMO_DOCTOR_PASSWORD),
            role=models.UserRole.doctor,
            full_name=payload.doctor_name,
        )
        db.add(doctor_user)
        db.flush()
        doctor_profile = models.Doctor(user_id=doctor_user.id, hospital_or_clinic=payload.hospital_or_clinic)
        db.add(doctor_profile)
        db.flush()
        provisioned_password = DEMO_DOCTOR_PASSWORD
    else:
        doctor_profile = db.query(models.Doctor).filter(models.Doctor.user_id == doctor_user.id).first()
        if payload.hospital_or_clinic:
            doctor_profile.hospital_or_clinic = payload.hospital_or_clinic

    existing = (
        db.query(models.DoctorAuthorization)
        .filter(
            models.DoctorAuthorization.patient_id == payload.patient_id,
            models.DoctorAuthorization.doctor_id == doctor_profile.id,
            models.DoctorAuthorization.status.in_([models.AuthorizationStatus.pending, models.AuthorizationStatus.approved]),
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="An active or pending authorization already exists for this doctor")

    authz = models.DoctorAuthorization(
        patient_id=payload.patient_id, doctor_id=doctor_profile.id,
        requested_by_family_id=fam.id if fam else None,
        scope_cognitive_performance=payload.scope_cognitive_performance,
        scope_activity_history=payload.scope_activity_history,
        scope_reminder_adherence=payload.scope_reminder_adherence,
        scope_location=payload.scope_location,
        scope_wearable_data=payload.scope_wearable_data,
        scope_medical_records=payload.scope_medical_records,
    )
    db.add(authz)
    db.commit()
    db.refresh(authz)

    patient = access.get_patient_or_404(db, payload.patient_id)
    db.add(models.Notification(
        user_id=patient.user_id, title="Doctor access requested",
        body=f"{doctor_user.full_name} has been asked to be added as an authorized doctor. Review and approve if correct.",
        category="authorization",
    ))
    db.commit()
    auth.write_audit_log(db, current.id, "authorization.requested", "doctor_authorization", authz.id)

    out = serializers.doctor_authorization(authz, doctor_profile, patient)
    if provisioned_password:
        out["_demo_new_doctor_login"] = {"email": doctor_user.email, "password": provisioned_password}
    return out


@router.get("/patient/{patient_id}")
def list_for_patient(patient_id: str, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """Family and patient get the full management view; a caregiver keeps
    read-only visibility here (e.g. in an overview) even though the
    request/approve/reject/revoke actions now live only in the Family app."""
    if current.role == models.UserRole.family:
        fam = access.family_for_user(db, current)
        access.ensure_family_owns_patient(db, fam, patient_id)
    elif current.role == models.UserRole.caregiver:
        cg = access.caregiver_for_user(db, current)
        access.ensure_caregiver_owns_patient(db, cg, patient_id)
    elif current.role == models.UserRole.patient:
        if not current.patient_profile or current.patient_profile.id != patient_id:
            raise HTTPException(status_code=403, detail="Not your data")
    else:
        raise HTTPException(status_code=403, detail="Not permitted")

    rows = db.query(models.DoctorAuthorization).filter(models.DoctorAuthorization.patient_id == patient_id).order_by(models.DoctorAuthorization.requested_at.desc()).all()
    patient = access.get_patient_or_404(db, patient_id)
    return [serializers.doctor_authorization(r, db.query(models.Doctor).get(r.doctor_id), patient) for r in rows]


@router.post("/{authorization_id}/decide")
def decide(authorization_id: str, payload: schemas.AuthorizationDecision, current: models.User = Depends(auth.get_current_user),
           db: Session = Depends(get_db)):
    authz = db.query(models.DoctorAuthorization).filter(models.DoctorAuthorization.id == authorization_id).first()
    if not authz:
        raise HTTPException(status_code=404, detail="Not found")

    if current.role == models.UserRole.family:
        fam = access.family_for_user(db, current)
        access.ensure_family_owns_patient(db, fam, authz.patient_id)
    elif current.role == models.UserRole.patient:
        if not current.patient_profile or current.patient_profile.id != authz.patient_id:
            raise HTTPException(status_code=403, detail="Not your data")
    else:
        raise HTTPException(status_code=403, detail="Only the patient or a linked family member can decide on doctor access")

    if authz.status != models.AuthorizationStatus.pending:
        raise HTTPException(status_code=400, detail="This request has already been decided")

    authz.status = models.AuthorizationStatus.approved if payload.approve else models.AuthorizationStatus.rejected
    authz.decided_at = datetime.utcnow()
    db.add(models.ConsentRecord(patient_id=authz.patient_id, granted_by_user_id=current.id, category="doctor_access",
                                 granted=payload.approve, notes=f"authorization_id={authz.id}"))
    db.commit()
    auth.write_audit_log(db, current.id, f"authorization.{authz.status.value}", "doctor_authorization", authz.id)

    patient = access.get_patient_or_404(db, authz.patient_id)
    doctor = db.query(models.Doctor).filter(models.Doctor.id == authz.doctor_id).first()
    return serializers.doctor_authorization(authz, doctor, patient)


@router.post("/{authorization_id}/revoke")
def revoke(authorization_id: str, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    authz = db.query(models.DoctorAuthorization).filter(models.DoctorAuthorization.id == authorization_id).first()
    if not authz:
        raise HTTPException(status_code=404, detail="Not found")

    if current.role == models.UserRole.family:
        fam = access.family_for_user(db, current)
        access.ensure_family_owns_patient(db, fam, authz.patient_id)
    elif current.role == models.UserRole.patient:
        if not current.patient_profile or current.patient_profile.id != authz.patient_id:
            raise HTTPException(status_code=403, detail="Not your data")
    else:
        raise HTTPException(status_code=403, detail="Only the patient or a linked family member can revoke doctor access")

    authz.status = models.AuthorizationStatus.revoked
    authz.revoked_at = datetime.utcnow()
    db.add(models.ConsentRecord(patient_id=authz.patient_id, granted_by_user_id=current.id, category="doctor_access",
                                 granted=False, notes=f"revoked authorization_id={authz.id}"))
    db.commit()
    auth.write_audit_log(db, current.id, "authorization.revoked", "doctor_authorization", authz.id)

    patient = access.get_patient_or_404(db, authz.patient_id)
    doctor = db.query(models.Doctor).filter(models.Doctor.id == authz.doctor_id).first()
    return serializers.doctor_authorization(authz, doctor, patient)
