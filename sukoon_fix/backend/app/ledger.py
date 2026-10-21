"""
Sukoon — Offline Care Ledger: NDJSON ingestion, resumable sync checkpoints,
audit export, and deterministic replay.

See reconciliation.py for the per-event-type conflict policies this module
dispatches to, and models.py for the ledger schema itself. This module
owns everything about *how an event gets in* (parsing, idempotency,
ordering/gap bookkeeping) and *how the ledger proves itself* (export,
replay) — it never decides what an event *means*, that's reconciliation.py.
"""
import hashlib
import json
from datetime import datetime

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import models, reconciliation
from .ledger_schemas import (
    CareEventEnvelope, PAYLOAD_SCHEMAS, KNOWN_EVENT_TYPES, CURRENT_SCHEMA_VERSION,
)


def compute_integrity_hash(event_id, patient_id, device_id, device_sequence, event_type, payload: dict) -> str:
    canonical = json.dumps(
        {"event_id": event_id, "patient_id": patient_id, "device_id": device_id,
         "device_sequence": device_sequence, "event_type": event_type, "payload": payload},
        sort_keys=True, separators=(",", ":"), default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def parse_ndjson(raw: bytes):
    """Yields (line_no, parsed_dict_or_None, error_or_None) for every
    non-blank line. Never raises — a malformed line is reported per-line,
    never fatal to the rest of the batch."""
    text = raw.decode("utf-8", errors="replace")
    for i, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            yield i, None, f"malformed JSON on line {i}: {e}"
            continue
        if not isinstance(obj, dict):
            yield i, None, f"line {i} is valid JSON but not an object"
            continue
        yield i, obj, None


def _parse_observed_at(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Resumable-sync checkpoints (per patient+device)
# ---------------------------------------------------------------------------

def _update_checkpoint(db: Session, patient_id: str, device_id: str, device_sequence: int, server_sequence: int):
    cp = (
        db.query(models.DeviceSyncCheckpoint)
        .filter(models.DeviceSyncCheckpoint.patient_id == patient_id, models.DeviceSyncCheckpoint.device_id == device_id)
        .first()
    )
    if cp is None:
        cp = models.DeviceSyncCheckpoint(patient_id=patient_id, device_id=device_id)
        db.add(cp)
        db.flush()

    # known_gaps_json actually stores the set of device_sequence numbers seen
    # ABOVE contiguous_up_to that haven't been folded in yet (out-of-order
    # arrivals waiting for the numbers before them) -- true "gaps" (never
    # seen at all) are computed on read in _checkpoint_summary.
    seen_above = set(json.loads(cp.known_gaps_json or "[]"))
    if device_sequence > cp.contiguous_up_to:
        seen_above.add(device_sequence)
        nxt = cp.contiguous_up_to + 1
        while nxt in seen_above:
            seen_above.discard(nxt)
            cp.contiguous_up_to = nxt
            nxt += 1
    cp.max_device_sequence_seen = max(cp.max_device_sequence_seen, device_sequence)
    cp.known_gaps_json = json.dumps(sorted(seen_above))
    if server_sequence:
        cp.last_server_sequence = max(cp.last_server_sequence, server_sequence)
    db.commit()
    return cp


def _checkpoint_summary(cp: models.DeviceSyncCheckpoint):
    if cp is None:
        return None
    seen_above = set(json.loads(cp.known_gaps_json or "[]"))
    gaps = [n for n in range(cp.contiguous_up_to + 1, cp.max_device_sequence_seen + 1) if n not in seen_above]
    return {
        "device_id": cp.device_id,
        "max_device_sequence_seen": cp.max_device_sequence_seen,
        "contiguous_up_to": cp.contiguous_up_to,
        "gaps": gaps,
        "last_server_sequence": cp.last_server_sequence,
    }


def get_checkpoint(db: Session, patient_id: str, device_id: str):
    cp = (
        db.query(models.DeviceSyncCheckpoint)
        .filter(models.DeviceSyncCheckpoint.patient_id == patient_id, models.DeviceSyncCheckpoint.device_id == device_id)
        .first()
    )
    return _checkpoint_summary(cp)


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

def _store_rejected_stub(db: Session, patient_id, actor_user_id, actor_role, event_id, device_id, device_sequence, event_type, schema_version, payload, reason):
    """Persist a rejected event even when its envelope was malformed, as
    long as we have a usable event_id — so a retried identical bad line is
    recognized as a duplicate rather than re-rejected with fresh bookkeeping
    noise, and so the ledger genuinely never silently drops a submission."""
    device_id = device_id or "unknown-device"
    device_sequence = device_sequence if isinstance(device_sequence, int) else 0
    payload = payload if isinstance(payload, dict) else {}
    stub = models.CareEvent(
        event_id=event_id, patient_id=patient_id, device_id=device_id, device_sequence=device_sequence,
        event_type=event_type or "unknown", schema_version=schema_version or 0,
        observed_at=None, actor_user_id=actor_user_id, actor_role=actor_role, consent_version=None,
        payload_json=json.dumps(payload),
        integrity_hash=compute_integrity_hash(event_id, patient_id, device_id, device_sequence, event_type or "unknown", payload),
        ingest_status="rejected", reconciliation_reason=reason,
    )
    try:
        db.add(stub)
        db.commit()
        _update_checkpoint(db, patient_id, device_id, device_sequence, stub.server_sequence)
        return stub
    except IntegrityError:
        db.rollback()
        return db.query(models.CareEvent).filter(models.CareEvent.event_id == event_id).first()


def ingest_one(db: Session, patient_id: str, actor_user_id: str, actor_role: str, raw_obj: dict):
    """Ingests exactly one NDJSON-line object. Returns
    (outcome, reason, event_id, device_id, device_sequence). Never raises."""
    event_id = raw_obj.get("event_id") if isinstance(raw_obj, dict) else None
    device_id = raw_obj.get("device_id") if isinstance(raw_obj, dict) else None
    device_sequence = raw_obj.get("device_sequence") if isinstance(raw_obj, dict) else None

    # Idempotency check first, by event_id alone -- the cheapest, most
    # robust dedupe key, independent of anything else in the line.
    if event_id:
        existing = db.query(models.CareEvent).filter(models.CareEvent.event_id == event_id).first()
        if existing:
            return "duplicate", existing.reconciliation_reason or "duplicate of a previously-ingested event_id", event_id, existing.device_id, existing.device_sequence

    try:
        envelope = CareEventEnvelope.model_validate(raw_obj)
    except ValidationError as e:
        msg = e.errors()[0]["msg"] if e.errors() else str(e)
        reason = f"envelope validation failed: {msg}"
        if not event_id:
            return "rejected", reason + " (no event_id -- could not be recorded in the ledger)", None, device_id, device_sequence
        stub = _store_rejected_stub(db, patient_id, actor_user_id, actor_role, event_id, device_id, device_sequence,
                                     raw_obj.get("event_type"), raw_obj.get("schema_version"), raw_obj.get("payload"), reason)
        return "rejected", reason, event_id, stub.device_id if stub else device_id, stub.device_sequence if stub else device_sequence

    if envelope.event_type not in KNOWN_EVENT_TYPES:
        reason = f"unknown event_type '{envelope.event_type}' — handled safely as rejected, not guessed"
        stub = _store_rejected_stub(db, patient_id, actor_user_id, actor_role, envelope.event_id, envelope.device_id, envelope.device_sequence,
                                     envelope.event_type, envelope.schema_version, envelope.payload, reason)
        return "rejected", reason, envelope.event_id, envelope.device_id, envelope.device_sequence

    if envelope.schema_version != CURRENT_SCHEMA_VERSION:
        reason = f"unsupported schema_version {envelope.schema_version} for '{envelope.event_type}' (server supports {CURRENT_SCHEMA_VERSION})"
        stub = _store_rejected_stub(db, patient_id, actor_user_id, actor_role, envelope.event_id, envelope.device_id, envelope.device_sequence,
                                     envelope.event_type, envelope.schema_version, envelope.payload, reason)
        return "rejected", reason, envelope.event_id, envelope.device_id, envelope.device_sequence

    schema_cls = PAYLOAD_SCHEMAS[envelope.event_type]
    try:
        payload_model = schema_cls.model_validate(envelope.payload)
        payload_clean = payload_model.model_dump()
    except ValidationError as e:
        msg = e.errors()[0]["msg"] if e.errors() else str(e)
        reason = f"payload validation failed for '{envelope.event_type}': {msg}"
        stub = _store_rejected_stub(db, patient_id, actor_user_id, actor_role, envelope.event_id, envelope.device_id, envelope.device_sequence,
                                     envelope.event_type, envelope.schema_version, envelope.payload, reason)
        return "rejected", reason, envelope.event_id, envelope.device_id, envelope.device_sequence

    event = models.CareEvent(
        event_id=envelope.event_id, patient_id=patient_id, device_id=envelope.device_id,
        device_sequence=envelope.device_sequence, event_type=envelope.event_type,
        schema_version=envelope.schema_version, observed_at=_parse_observed_at(envelope.observed_at),
        actor_user_id=actor_user_id, actor_role=actor_role, consent_version=envelope.consent_version,
        payload_json=json.dumps(payload_clean),
        integrity_hash=compute_integrity_hash(envelope.event_id, patient_id, envelope.device_id, envelope.device_sequence, envelope.event_type, payload_clean),
        ingest_status="pending", reconciliation_reason=None,
    )
    db.add(event)
    try:
        db.flush()  # assigns server_sequence; also enforces the (device_id,patient_id,device_sequence) unique constraint
    except IntegrityError:
        db.rollback()
        existing = db.query(models.CareEvent).filter(models.CareEvent.event_id == envelope.event_id).first()
        if existing:
            return "duplicate", existing.reconciliation_reason or "duplicate", envelope.event_id, envelope.device_id, envelope.device_sequence
        return (
            "rejected",
            "device_id + device_sequence already used by a different event_id on this device (treated as a duplicate submission under a new id)",
            envelope.event_id, envelope.device_id, envelope.device_sequence,
        )

    outcome, reason = reconciliation.apply_event(db, patient_id, event)
    event.ingest_status = outcome
    event.reconciliation_reason = reason
    db.commit()
    _update_checkpoint(db, patient_id, envelope.device_id, envelope.device_sequence, event.server_sequence)
    return outcome, reason, envelope.event_id, envelope.device_id, envelope.device_sequence


def ingest_ndjson_batch(db: Session, patient_id: str, actor_user_id: str, actor_role: str, raw: bytes):
    results = []
    devices_touched = set()

    for line_no, obj, parse_error in parse_ndjson(raw):
        if parse_error:
            results.append({"line": line_no, "event_id": None, "device_id": None, "device_sequence": None,
                             "outcome": "rejected", "reason": parse_error})
            continue
        outcome, reason, event_id, device_id, device_sequence = ingest_one(db, patient_id, actor_user_id, actor_role, obj)
        if device_id:
            devices_touched.add(device_id)
        results.append({"line": line_no, "event_id": event_id, "device_id": device_id,
                         "device_sequence": device_sequence, "outcome": outcome, "reason": reason})

    checkpoints = [get_checkpoint(db, patient_id, d) for d in sorted(devices_touched)]
    any_bad = any(r["outcome"] in ("rejected", "conflict_review", "needs_review") for r in results)

    return {
        # Partial failure is never silently reported as full success.
        "status": "partial" if any_bad else ("complete" if results else "empty"),
        "received": len(results),
        "accepted": sum(1 for r in results if r["outcome"] == "accepted"),
        "duplicate": sum(1 for r in results if r["outcome"] == "duplicate"),
        "rejected": sum(1 for r in results if r["outcome"] == "rejected"),
        "conflict_or_review": sum(1 for r in results if r["outcome"] in ("conflict_review", "needs_review")),
        "results": results,
        "checkpoints": checkpoints,
    }


# ---------------------------------------------------------------------------
# Audit export
# ---------------------------------------------------------------------------

def export_ndjson_lines(db: Session, patient_id: str):
    """Streams the full, ordered ledger for one patient as NDJSON — the
    exportable audit bundle required by the spec. Includes rejected events
    too (a rejection is itself part of the honest audit history)."""
    events = (
        db.query(models.CareEvent)
        .filter(models.CareEvent.patient_id == patient_id)
        .order_by(models.CareEvent.server_sequence.asc())
        .all()
    )
    for e in events:
        line = {
            "server_sequence": e.server_sequence,
            "event_id": e.event_id,
            "patient_id": e.patient_id,
            "device_id": e.device_id,
            "device_sequence": e.device_sequence,
            "event_type": e.event_type,
            "schema_version": e.schema_version,
            "observed_at": e.observed_at.isoformat() if e.observed_at else None,
            "received_at": e.received_at.isoformat() if e.received_at else None,
            "actor_user_id": e.actor_user_id,
            "actor_role": e.actor_role,
            "consent_version": e.consent_version,
            "payload": json.loads(e.payload_json),
            "integrity_hash": e.integrity_hash,
            "ingest_status": e.ingest_status,
            "reconciliation_reason": e.reconciliation_reason,
        }
        yield json.dumps(line, sort_keys=True) + "\n"


# ---------------------------------------------------------------------------
# Deterministic replay
# ---------------------------------------------------------------------------

def replay_patient(db: Session, patient_id: str):
    """Rebuilds every ledger-derived projection for one patient FROM THE
    LEDGER ALONE, in server_sequence order — the one authoritative order.
    This is the correctness guarantee the whole subsystem rests on: if
    replay doesn't reproduce the same state incremental ingestion built,
    the design is wrong. Nothing outside the ledger-owned tables (listed
    below) is ever touched."""
    t0 = datetime.utcnow()

    db.query(models.ReminderLedgerState).filter(models.ReminderLedgerState.patient_id == patient_id).delete()
    db.query(models.RoutineLedgerState).filter(models.RoutineLedgerState.patient_id == patient_id).delete()
    db.query(models.ConsentLedgerState).filter(models.ConsentLedgerState.patient_id == patient_id).delete()
    db.query(models.GeofenceLedgerState).filter(models.GeofenceLedgerState.patient_id == patient_id).delete()
    db.query(models.SafetyAlert).filter(
        models.SafetyAlert.patient_id == patient_id, models.SafetyAlert.alert_type == "ledger_escalation"
    ).delete()
    db.commit()

    events = (
        db.query(models.CareEvent)
        .filter(models.CareEvent.patient_id == patient_id)
        .order_by(models.CareEvent.server_sequence.asc())
        .all()
    )

    outcomes = {}
    for event in events:
        if event.ingest_status == "rejected":
            # A rejected event never had an effect the first time, either —
            # replay must faithfully reproduce that, not retry it.
            outcomes["rejected"] = outcomes.get("rejected", 0) + 1
            continue
        outcome, _reason = reconciliation.apply_event(db, patient_id, event)
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
        db.flush()  # each projection upsert must be visible to the *next* event's lookup query
    db.commit()

    return {
        "patient_id": patient_id,
        "events_replayed": len(events),
        "outcomes": outcomes,
        "duration_ms": int((datetime.utcnow() - t0).total_seconds() * 1000),
    }


def patient_ledger_status(db: Session, patient_id: str):
    """Convenience read model: the current derived state across every
    category, for a status endpoint / future UI panel / the test harness's
    own assertions."""
    reminders = db.query(models.ReminderLedgerState).filter(models.ReminderLedgerState.patient_id == patient_id).all()
    routines = db.query(models.RoutineLedgerState).filter(models.RoutineLedgerState.patient_id == patient_id).all()
    consents = db.query(models.ConsentLedgerState).filter(models.ConsentLedgerState.patient_id == patient_id).all()
    geofence = reconciliation.current_safety_signal(db, patient_id)
    event_count = db.query(models.CareEvent).filter(models.CareEvent.patient_id == patient_id).count()

    return {
        "patient_id": patient_id,
        "ledger_event_count": event_count,
        "reminders": [
            {
                "reminder_occurrence_key": r.reminder_occurrence_key,
                "delivery_state": r.delivery_state,
                "user_acknowledged": r.user_acknowledged,
                "user_acknowledged_at": r.user_acknowledged_at.isoformat() if r.user_acknowledged_at else None,
                "caregiver_escalated": r.caregiver_escalated,
                "caregiver_escalated_at": r.caregiver_escalated_at.isoformat() if r.caregiver_escalated_at else None,
                "sync_status": r.sync_status,
            }
            for r in reminders
        ],
        "routines": [
            {
                "routine_key": r.routine_key, "period": r.period, "title_en": r.title_en,
                "scheduled_time": r.scheduled_time, "active": r.active,
                "conflict": r.conflict, "conflict_reason": r.conflict_reason,
            }
            for r in routines
        ],
        "consent": [
            {"category": c.category, "granted": c.granted, "version": c.version}
            for c in consents
        ],
        "geofence": geofence,
    }
