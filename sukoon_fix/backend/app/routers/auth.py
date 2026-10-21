from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, auth, serializers
from ..database import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == payload.email.lower()).first()
    if not user or not auth.verify_password(payload.password, user.password_hash):
        # Deliberately generic message — do not reveal whether the email exists.
        auth.write_audit_log(db, None, "login.failed", detail=f"email={payload.email}")
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="This account has been disabled.")

    user.last_login_at = datetime.utcnow()
    db.commit()
    auth.write_audit_log(db, user.id, "login.success", "user", user.id)

    token = auth.create_access_token(user)
    profile_id = None
    if user.role == models.UserRole.patient and user.patient_profile:
        profile_id = user.patient_profile.id
    elif user.role == models.UserRole.caregiver and user.caregiver_profile:
        profile_id = user.caregiver_profile.id
    elif user.role == models.UserRole.doctor and user.doctor_profile:
        profile_id = user.doctor_profile.id
    elif user.role == models.UserRole.family and user.family_profile:
        profile_id = user.family_profile.id

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": serializers.user_public(user),
        "profile_id": profile_id,
    }


@router.get("/me")
def me(current: models.User = Depends(auth.get_current_user)):
    return serializers.user_public(current)


@router.patch("/language")
def set_language(payload: schemas.LanguageUpdate, current: models.User = Depends(auth.get_current_user),
                  db: Session = Depends(get_db)):
    current.preferred_language = payload.preferred_language
    db.commit()
    return serializers.user_public(current)


@router.post("/logout")
def logout(current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    # Stateless JWT: logout is enforced client-side by discarding the token.
    auth.write_audit_log(db, current.id, "logout", "user", current.id)
    return {"ok": True}
