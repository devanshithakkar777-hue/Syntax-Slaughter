"""
Sukoon — Safety Reconciliation Engine.

One function per event category, each implementing a documented,
deterministic conflict policy. Every function has the same contract:

    apply_<type>(db, patient_id, event: models.CareEvent) -> (outcome, reason)

`event` has already been persisted to the ledger (CareEvent) by the time
these run — these functions only update the small *derived projection*
tables, never the ledger itself, and never raise: any failure they can't
resolve is surfaced as a ("needs_review", reason) outcome rather than an
exception, so one odd record can never take the rest of a batch down.

Determinism is the whole point: calling these functions in
server_sequence order from a cold, empty projection table set (see
ledger.replay_patient) must always reproduce exactly the same end state
as the original incremental ingestion did. That's what makes replay a
real correctness guarantee rather than a demo animation.

CONFLICT-RESOLUTION POLICIES (documented per category, as required):

  routine_edit
    Last-write-wins by server_sequence (the one authoritative, server-
    assigned order — never by device clock). If the new edit's actor
    differs from the previous edit's actor and they landed within
    CONCURRENT_EDIT_WINDOW of each other, the edit is still applied (so
    the projection always reflects the latest known state) but flagged
    conflict=True / outcome "conflict_review" so a human can see two
    people edited the same routine around the same time.

  cognitive_game_result
    Append-only — every attempt is its own fact, there is nothing to
    merge or overwrite, so there is no conflict case. Always "accepted".

  medication reminder lifecycle (reminder_scheduled /
  reminder_notification_attempted / reminder_provider_accepted /
  reminder_user_acknowledged / reminder_caregiver_escalated)
    `delivery_state` only ever moves forward through
    scheduled -> notification_attempted -> provider_accepted; an event
    that would move it backward (e.g. a late-arriving "scheduled" after
    "provider_accepted" is already recorded) is still appended to the
    ledger for audit but does not downgrade the projection.
    `user_acknowledged` is a one-way flag completely separate from
    delivery — it is only ever set by an explicit
    reminder_user_acknowledged event, never inferred from a notification
    having been sent.
    `caregiver_escalated` is also one-way; a second escalation event for
    the same occurrence is detected and suppressed (outcome "duplicate")
    so reconnecting devices replaying a backlog can never create an
    alert storm.

  geofence_observation
    Append-only history (nothing to overwrite), but the *current-status*
    projection is staleness-aware: it is only as fresh as the latest
    observation's server receipt time, and missing/unknown telemetry is
    stored as exactly that — never silently treated as "safe".

  consent_change
    Versioned per (patient, category). A grant is only honoured if the
    event's claimed consent_version is >= the current authoritative
    version — an offline grant created before a later revocation can
    never resurrect access. A revoke always applies immediately
    regardless of version, because narrowing access is never the unsafe
    direction. Every accepted change bumps the authoritative version.

  caregiver_action
    Logged as-is (it's its own audit fact); best-effort side-effect
    (e.g. acknowledging an existing SafetyAlert) that never fails the
    event if the referenced entity doesn't exist.
"""
import json
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from . import models

CONCURRENT_EDIT_WINDOW = timedelta(minutes=5)
GEOFENCE_STALE_AFTER = timedelta(minutes=30)

_DELIVERY_RANK = {"scheduled": 0, "notification_attempted": 1, "provider_accepted": 2}


def _payload(event: models.CareEvent) -> dict:
    try:
        return json.loads(event.payload_json)
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# routine_edit
# ---------------------------------------------------------------------------

def apply_routine_edit(db: Session, patient_id: str, event: models.CareEvent):
    p = _payload(event)
    key = p.get("routine_key")
    if not key:
        return "rejected", "routine_edit payload missing routine_key"

    row = (
        db.query(models.RoutineLedgerState)
        .filter(models.RoutineLedgerState.patient_id == patient_id, models.RoutineLedgerState.routine_key == key)
        .first()
    )

    conflict = False
    reason = "routine created" if row is None else "routine updated (last-write-wins by server order)"

    if row is None:
        row = models.RoutineLedgerState(patient_id=patient_id, routine_key=key)
        db.add(row)
    elif row.last_event_id:
        # Compare against the *previous* event's own immutable, ledger-stored
        # received_at/actor — never the projection row's own updated_at
        # (which is a live wall-clock column and would make this
        # non-deterministic on replay, since replay runs at a different
        # wall-clock time than the original ingestion).
        prev = (
            db.query(models.CareEvent.actor_user_id, models.CareEvent.received_at)
            .filter(models.CareEvent.event_id == row.last_event_id)
            .first()
        )
        if prev and prev[0] and event.actor_user_id and prev[0] != event.actor_user_id and prev[1] and event.received_at:
            gap = abs(event.received_at - prev[1])
            if gap <= CONCURRENT_EDIT_WINDOW:
                conflict = True
                reason = (
                    f"concurrent edit: actor {event.actor_user_id} overwrote a change by {prev[0]} "
                    f"made {int(gap.total_seconds())}s earlier — applied by server order, flagged for review"
                )

    row.period = p.get("period", row.period)
    row.title_en = p.get("title_en", row.title_en)
    row.title_as = p.get("title_as", row.title_as)
    row.scheduled_time = p.get("scheduled_time", row.scheduled_time)
    row.active = p.get("active", row.active if row.active is not None else True)
    row.last_event_id = event.event_id
    row.last_server_sequence = event.server_sequence
    if conflict:
        row.conflict = True
        row.conflict_reason = reason

    return ("conflict_review" if conflict else "accepted"), reason


# ---------------------------------------------------------------------------
# cognitive_game_result / mood_log — pure audit facts, nothing to reconcile
# ---------------------------------------------------------------------------

def apply_cognitive_game_result(db: Session, patient_id: str, event: models.CareEvent):
    from . import adaptive_engine
    p = _payload(event)
    result = adaptive_engine.safe_decide(
        current_difficulty=p.get("difficulty", 2),
        accuracy=p.get("accuracy"),
        avg_response_time_ms=p.get("avg_response_time_ms"),
    )
    return "accepted", f"recorded; adaptive engine {result.direction} difficulty to {result.new_difficulty} ({result.explanation_en})"


def apply_mood_log(db: Session, patient_id: str, event: models.CareEvent):
    return "accepted", "mood entry recorded"


# ---------------------------------------------------------------------------
# medication reminder lifecycle
# ---------------------------------------------------------------------------

def _get_or_create_reminder_state(db: Session, patient_id: str, key: str) -> models.ReminderLedgerState:
    row = (
        db.query(models.ReminderLedgerState)
        .filter(models.ReminderLedgerState.patient_id == patient_id, models.ReminderLedgerState.reminder_occurrence_key == key)
        .first()
    )
    if row is None:
        row = models.ReminderLedgerState(patient_id=patient_id, reminder_occurrence_key=key)
        db.add(row)
        db.flush()
    return row


def _apply_delivery_progress(row: models.ReminderLedgerState, new_state: str, event: models.CareEvent):
    cur_rank = _DELIVERY_RANK.get(row.delivery_state, 0)
    new_rank = _DELIVERY_RANK.get(new_state, 0)
    if new_rank >= cur_rank:
        row.delivery_state = new_state
        row.last_event_id = event.event_id
        row.last_server_sequence = event.server_sequence
        row.sync_status = "synced"
        return "accepted", f"delivery state advanced to {new_state}"
    row.sync_status = row.sync_status or "synced"
    return "accepted", (
        f"recorded for audit; delivery state remains '{row.delivery_state}' "
        f"(already more advanced than late-arriving '{new_state}')"
    )


def apply_reminder_scheduled(db, patient_id, event):
    p = _payload(event)
    key = p.get("reminder_occurrence_key")
    if not key:
        return "rejected", "missing reminder_occurrence_key"
    row = _get_or_create_reminder_state(db, patient_id, key)
    return _apply_delivery_progress(row, "scheduled", event)


def apply_reminder_notification_attempted(db, patient_id, event):
    p = _payload(event)
    key = p.get("reminder_occurrence_key")
    if not key:
        return "rejected", "missing reminder_occurrence_key"
    row = _get_or_create_reminder_state(db, patient_id, key)
    return _apply_delivery_progress(row, "notification_attempted", event)


def apply_reminder_provider_accepted(db, patient_id, event):
    p = _payload(event)
    key = p.get("reminder_occurrence_key")
    if not key:
        return "rejected", "missing reminder_occurrence_key"
    row = _get_or_create_reminder_state(db, patient_id, key)
    return _apply_delivery_progress(row, "provider_accepted", event)


def apply_reminder_user_acknowledged(db, patient_id, event):
    p = _payload(event)
    key = p.get("reminder_occurrence_key")
    if not key:
        return "rejected", "missing reminder_occurrence_key"
    row = _get_or_create_reminder_state(db, patient_id, key)
    if row.user_acknowledged:
        return "duplicate", "already acknowledged — ignoring repeat acknowledgement"
    row.user_acknowledged = True
    row.user_acknowledged_at = event.observed_at or event.received_at
    row.last_event_id = event.event_id
    row.last_server_sequence = event.server_sequence
    row.sync_status = "synced"
    return "accepted", "medicine/reminder explicitly acknowledged by the user — never inferred from a notification alone"


def apply_reminder_caregiver_escalated(db, patient_id, event):
    p = _payload(event)
    key = p.get("reminder_occurrence_key")
    if not key:
        return "rejected", "missing reminder_occurrence_key"
    row = _get_or_create_reminder_state(db, patient_id, key)
    if row.caregiver_escalated:
        row.sync_status = "needs_review"
        return "duplicate", "already escalated — suppressing duplicate escalation to prevent an alert storm"
    row.caregiver_escalated = True
    row.caregiver_escalated_at = event.observed_at or event.received_at
    row.last_event_id = event.event_id
    row.last_server_sequence = event.server_sequence
    row.sync_status = "synced"
    # Best-effort real integration: surface it on the existing, already-live
    # Escalation Log / caregiver dashboard for this (synthetic) patient.
    try:
        db.add(models.SafetyAlert(
            patient_id=patient_id,
            alert_type="ledger_escalation",
            severity=models.AlertSeverity.warning,
            message_en=f"[Offline Care Ledger] Reminder occurrence '{key}' escalated after no acknowledgement.",
            related_id=key,
        ))
    except Exception:
        pass
    return "accepted", "caregiver escalation recorded (first for this occurrence)"


# ---------------------------------------------------------------------------
# geofence_observation
# ---------------------------------------------------------------------------

def apply_geofence_observation(db: Session, patient_id: str, event: models.CareEvent):
    p = _payload(event)
    row = db.query(models.GeofenceLedgerState).filter(models.GeofenceLedgerState.patient_id == patient_id).first()
    if row is None:
        row = models.GeofenceLedgerState(patient_id=patient_id)
        db.add(row)

    row.observation_type = p.get("observation_type")
    row.within_safe_zone = p.get("within_safe_zone")
    row.distance_from_safe_zone_m = p.get("distance_from_safe_zone_m")
    row.latitude = p.get("latitude")
    row.longitude = p.get("longitude")
    row.last_observed_at = event.observed_at
    row.last_received_at = event.received_at
    row.last_event_id = event.event_id
    row.last_server_sequence = event.server_sequence

    reason = f"geofence status set to '{row.observation_type}'"
    if row.observation_type in ("unknown", "stale"):
        reason += " — uncertainty recorded explicitly, not treated as safe"
    return "accepted", reason


def current_safety_signal(db: Session, patient_id: str, now: datetime = None) -> dict:
    """Read-only helper: the honest current geofence/safety signal, with
    staleness computed at read time (missing telemetry is never 'safe')."""
    now = now or datetime.utcnow()
    row = db.query(models.GeofenceLedgerState).filter(models.GeofenceLedgerState.patient_id == patient_id).first()
    if row is None or row.last_received_at is None:
        return {"status": "unknown", "within_safe_zone": None, "reason": "no location telemetry received yet"}
    if row.observation_type in ("unknown", "stale"):
        return {"status": row.observation_type, "within_safe_zone": None, "reason": f"device reported '{row.observation_type}'"}
    age = now - row.last_received_at
    if age > GEOFENCE_STALE_AFTER:
        return {
            "status": "stale", "within_safe_zone": None,
            "reason": f"last observation {int(age.total_seconds() // 60)} min ago, exceeds {int(GEOFENCE_STALE_AFTER.total_seconds() // 60)} min staleness threshold",
        }
    return {
        "status": row.observation_type,
        "within_safe_zone": row.within_safe_zone,
        "distance_from_safe_zone_m": row.distance_from_safe_zone_m,
        "reason": f"observed {int(age.total_seconds())}s ago",
    }


# ---------------------------------------------------------------------------
# consent_change
# ---------------------------------------------------------------------------

def apply_consent_change(db: Session, patient_id: str, event: models.CareEvent):
    p = _payload(event)
    category = p.get("category")
    granted = p.get("granted")
    if category is None or granted is None:
        return "rejected", "consent_change payload missing category/granted"

    row = (
        db.query(models.ConsentLedgerState)
        .filter(models.ConsentLedgerState.patient_id == patient_id, models.ConsentLedgerState.category == category)
        .first()
    )
    current_version = row.version if row else 0
    claimed_version = event.consent_version if event.consent_version is not None else 0

    if granted and claimed_version < current_version:
        return "rejected", (
            f"stale consent_version {claimed_version} < current {current_version} for '{category}' — "
            f"an offline grant cannot restore access over a newer decision (possibly a revocation)"
        )

    if row is None:
        row = models.ConsentLedgerState(patient_id=patient_id, category=category, granted=False, version=0)
        db.add(row)
        db.flush()

    row.granted = granted
    row.version = current_version + 1
    row.last_event_id = event.event_id
    row.last_server_sequence = event.server_sequence

    verb = "granted" if granted else "revoked"
    return "accepted", f"consent for '{category}' {verb}; version {current_version} -> {row.version}"


# ---------------------------------------------------------------------------
# caregiver_action
# ---------------------------------------------------------------------------

def apply_caregiver_action(db: Session, patient_id: str, event: models.CareEvent):
    p = _payload(event)
    action = p.get("action")
    if action == "alert_acknowledged" and p.get("related_id"):
        alert = db.query(models.SafetyAlert).filter(models.SafetyAlert.id == p["related_id"], models.SafetyAlert.patient_id == patient_id).first()
        if alert and not alert.acknowledged:
            alert.acknowledged = True
            alert.acknowledged_at = event.received_at
            return "accepted", f"alert {p['related_id']} acknowledged via caregiver_action"
    return "accepted", f"caregiver action '{action}' logged"


DISPATCH = {
    "routine_edit": apply_routine_edit,
    "cognitive_game_result": apply_cognitive_game_result,
    "mood_log": apply_mood_log,
    "reminder_scheduled": apply_reminder_scheduled,
    "reminder_notification_attempted": apply_reminder_notification_attempted,
    "reminder_provider_accepted": apply_reminder_provider_accepted,
    "reminder_user_acknowledged": apply_reminder_user_acknowledged,
    "reminder_caregiver_escalated": apply_reminder_caregiver_escalated,
    "geofence_observation": apply_geofence_observation,
    "consent_change": apply_consent_change,
    "caregiver_action": apply_caregiver_action,
}


def apply_event(db: Session, patient_id: str, event: models.CareEvent):
    """Dispatch to the per-type policy. Never raises — an internal error in
    a single event's reconciliation is caught and reported as needs_review
    rather than ever taking the request (or the rest of a batch) down."""
    fn = DISPATCH.get(event.event_type)
    if fn is None:
        return "rejected", f"unknown event_type '{event.event_type}'"
    try:
        return fn(db, patient_id, event)
    except Exception as e:
        return "needs_review", f"reconciliation error, needs human review: {e}"
