"""Shared access-control helpers: who may see/act on which patient's data."""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from . import models


def get_patient_or_404(db: Session, patient_id: str) -> models.Patient:
    p = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")
    return p


def caregiver_for_user(db: Session, user: models.User) -> models.Caregiver:
    cg = db.query(models.Caregiver).filter(models.Caregiver.user_id == user.id).first()
    if not cg:
        raise HTTPException(status_code=403, detail="No caregiver profile for this account")
    return cg


def doctor_for_user(db: Session, user: models.User) -> models.Doctor:
    doc = db.query(models.Doctor).filter(models.Doctor.user_id == user.id).first()
    if not doc:
        raise HTTPException(status_code=403, detail="No doctor profile for this account")
    return doc


def family_for_user(db: Session, user: models.User) -> models.FamilyMember:
    fam = db.query(models.FamilyMember).filter(models.FamilyMember.user_id == user.id).first()
    if not fam:
        raise HTTPException(status_code=403, detail="No family-dashboard profile for this account")
    return fam


def ensure_caregiver_owns_patient(db: Session, caregiver: models.Caregiver, patient_id: str):
    link = (
        db.query(models.PatientCaregiverRelationship)
        .filter(
            models.PatientCaregiverRelationship.caregiver_id == caregiver.id,
            models.PatientCaregiverRelationship.patient_id == patient_id,
        )
        .first()
    )
    if not link:
        raise HTTPException(status_code=403, detail="This patient is not assigned to your account")


def ensure_family_owns_patient(db: Session, family: models.FamilyMember, patient_id: str):
    link = (
        db.query(models.PatientFamilyRelationship)
        .filter(
            models.PatientFamilyRelationship.family_member_id == family.id,
            models.PatientFamilyRelationship.patient_id == patient_id,
        )
        .first()
    )
    if not link:
        raise HTTPException(status_code=403, detail="This patient is not linked to your family account")


def get_active_authorization(db: Session, doctor: models.Doctor, patient_id: str):
    return (
        db.query(models.DoctorAuthorization)
        .filter(
            models.DoctorAuthorization.doctor_id == doctor.id,
            models.DoctorAuthorization.patient_id == patient_id,
            models.DoctorAuthorization.status == models.AuthorizationStatus.approved,
        )
        .first()
    )


def ensure_doctor_authorized(db: Session, doctor: models.Doctor, patient_id: str) -> models.DoctorAuthorization:
    authz = get_active_authorization(db, doctor, patient_id)
    if not authz:
        raise HTTPException(
            status_code=403,
            detail="You do not have authorized access to this patient's data.",
        )
    return authz
