"""
Sukoon — Offline Care Ledger + Safety Reconciliation Engine, HTTP surface.

Authorization is enforced here, against live database relationships, on
every call — never inferred from anything the client claims, and never
left to the frontend alone to hide. The actor identity written onto every
ledger event is always the authenticated session's own id/role; the wire
format has no "acting_as" field, so one user can never submit an event as
someone else.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import models, auth, access, ledger
from ..database import get_db

router = APIRouter(prefix="/api/ledger", tags=["ledger"])


def _resolve_actor(db: Session, current: models.User, patient_id: str):
    """Returns (actor_user_id, actor_role) if `current` may act on this
    patient's ledger, else raises 403. Reuses the same ownership checks the
    rest of the app already relies on."""
    role = current.role.value if hasattr(current.role, "value") else current.role
    if role == "patient":
        if not current.patient_profile or current.patient_profile.id != patient_id:
            raise HTTPException(status_code=403, detail="Not your data")
    elif role == "caregiver":
        cg = access.caregiver_for_user(db, current)
        access.ensure_caregiver_owns_patient(db, cg, patient_id)
    elif role == "family":
        fam = access.family_for_user(db, current)
        access.ensure_family_owns_patient(db, fam, patient_id)
    elif role == "doctor":
        raise HTTPException(status_code=403, detail="Doctor accounts have read-only access to the care ledger")
    else:
        raise HTTPException(status_code=403, detail="Not permitted")
    return current.id, role


def _resolve_reader(db: Session, current: models.User, patient_id: str):
    """Looser check for read-only endpoints (export/status/replay-view):
    also allows an authorized doctor."""
    role = current.role.value if hasattr(current.role, "value") else current.role
    if role == "doctor":
        doc = access.doctor_for_user(db, current)
        access.ensure_doctor_authorized(db, doc, patient_id)
        return
    _resolve_actor(db, current, patient_id)


@router.post("/sync/{patient_id}")
async def sync_ledger(patient_id: str, request: Request,
                       current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """Accepts a chunk of NDJSON events (Content-Type: application/x-ndjson
    or just a raw body — the parser doesn't require the header). Safe to
    call repeatedly with overlapping/duplicate/out-of-order/malformed/
    interrupted content: every record is resolved independently and the
    response always reflects the true per-record and overall outcome."""
    access.get_patient_or_404(db, patient_id)
    actor_user_id, actor_role = _resolve_actor(db, current, patient_id)
    raw = await request.body()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty request body — expected NDJSON (one JSON object per line)")
    return ledger.ingest_ndjson_batch(db, patient_id, actor_user_id, actor_role, raw)


@router.get("/checkpoint/{patient_id}/{device_id}")
def get_checkpoint(patient_id: str, device_id: str,
                    current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """Lets a reconnecting device ask 'what have you already seen from me?'
    before resuming an upload, instead of resending everything."""
    access.get_patient_or_404(db, patient_id)
    _resolve_actor(db, current, patient_id)
    cp = ledger.get_checkpoint(db, patient_id, device_id)
    return cp or {"device_id": device_id, "max_device_sequence_seen": 0, "contiguous_up_to": 0, "gaps": [], "last_server_sequence": 0}


@router.get("/export/{patient_id}")
def export_ledger(patient_id: str,
                   current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """Streams the full, ordered audit bundle for one patient as NDJSON."""
    access.get_patient_or_404(db, patient_id)
    _resolve_reader(db, current, patient_id)
    return StreamingResponse(
        ledger.export_ndjson_lines(db, patient_id),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="sukoon_ledger_{patient_id}.ndjson"'},
    )


@router.post("/replay/{patient_id}")
def replay_ledger(patient_id: str,
                   current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """Wipes and deterministically rebuilds every derived projection for
    this patient from the ledger alone. Restricted to caregiver/patient/
    family (the same actors who can write) since it mutates projections —
    a doctor can read status/export but not trigger a rebuild."""
    access.get_patient_or_404(db, patient_id)
    _resolve_actor(db, current, patient_id)
    return ledger.replay_patient(db, patient_id)


@router.get("/status/{patient_id}")
def ledger_status(patient_id: str,
                   current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    access.get_patient_or_404(db, patient_id)
    _resolve_reader(db, current, patient_id)
    return ledger.patient_ledger_status(db, patient_id)
