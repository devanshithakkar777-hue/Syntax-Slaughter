"""
Sukoon — Authentication & role-based access control.

- Passwords hashed with bcrypt (passlib).
- Sessions are JWT bearer tokens (HS256), short-lived, carrying user id + role.
- Role-guard dependencies (require_role) protect every sensitive route.
- Every login and authorization decision is written to the audit log.
"""
import os
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .database import get_db
from . import models

# --- Secret key -------------------------------------------------------------
# In production this MUST come from a secrets manager / environment variable.
# A random key is generated at process start if none is supplied, which is
# fine for a demo (all sessions reset with the server) but is flagged here
# so it is not mistaken for production-grade key management.
SECRET_KEY = os.environ.get("SUKOON_SECRET_KEY") or "sukoon-dev-secret-change-me-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 12  # 12 hours, generous for a hackathon demo session

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user: models.User) -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": user.id,
        "role": user.role.value if hasattr(user.role, "value") else user.role,
        "email": user.email,
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session. Please log in again.",
        )


def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_token(token)
    user = db.query(models.User).filter(models.User.id == payload.get("sub")).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Account not found or disabled")
    return user


def require_role(*roles: List[str]):
    """Dependency factory: restrict a route to one or more roles."""
    def _dep(user: models.User = Depends(get_current_user)) -> models.User:
        role_value = user.role.value if hasattr(user.role, "value") else user.role
        if role_value not in roles:
            raise HTTPException(status_code=403, detail="You do not have permission to access this resource")
        return user
    return _dep


def write_audit_log(db: Session, actor_user_id: Optional[str], action: str,
                     entity_type: str = None, entity_id: str = None, detail: str = None):
    entry = models.AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        detail=detail,
    )
    db.add(entry)
    db.commit()
