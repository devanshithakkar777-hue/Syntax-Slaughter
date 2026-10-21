from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, auth, access
from ..database import get_db

router = APIRouter(prefix="/api/consent", tags=["consent"])

PRIVACY_TEXT = {
    "what_is_collected": (
        "Sukoon collects only what is needed to support the patient: profile basics, "
        "cognitive activity results, reminder responses, mood check-ins, and — only if "
        "explicitly authorized — approximate location and wearable device data."
    ),
    "why": (
        "This information lets Sukoon adapt activity difficulty, remind the patient about "
        "medicine/hydration/appointments, alert a caregiver if a reminder goes unanswered, "
        "and give an authorized doctor supportive (non-diagnostic) insight into trends."
    ),
    "who_can_access": (
        "The patient can see all of their own data. A linked caregiver can see what they "
        "are assigned to monitor. A doctor can see ONLY the specific data categories a "
        "caregiver or patient has explicitly authorized, for that one patient."
    ),
    "how_to_revoke": (
        "Any doctor authorization, or location/wearable tracking, can be revoked at any "
        "time from the Caregiver or Patient app. Revoking takes effect immediately."
    ),
    "disclaimers": [
        "Sukoon is a cognitive support and memory assistance platform. It does not diagnose or treat dementia.",
        "AI insights are intended to support caregivers and healthcare professionals and are not medical diagnoses.",
        "Location and wearable monitoring require user/caregiver authorization.",
        "Clinical decisions should be made by qualified healthcare professionals.",
    ],
}


@router.get("/privacy")
def privacy_policy():
    return PRIVACY_TEXT


@router.get("/{patient_id}")
def consent_state(patient_id: str, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if current.role == models.UserRole.caregiver:
        cg = access.caregiver_for_user(db, current)
        access.ensure_caregiver_owns_patient(db, cg, patient_id)
    elif current.role == models.UserRole.patient:
        if not current.patient_profile or current.patient_profile.id != patient_id:
            raise HTTPException(status_code=403, detail="Not your data")
    else:
        raise HTTPException(status_code=403, detail="Not permitted")

    rows = (
        db.query(models.ConsentRecord)
        .filter(models.ConsentRecord.patient_id == patient_id)
        .order_by(models.ConsentRecord.created_at.desc())
        .limit(50)
        .all()
    )
    return [
        {"id": r.id, "category": r.category, "granted": r.granted, "notes": r.notes,
         "created_at": r.created_at.isoformat()}
        for r in rows
    ]
