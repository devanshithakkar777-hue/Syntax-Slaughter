"""
Sukoon — Offline Care Ledger event schemas.

Every event type the ledger accepts has a narrow, explicit payload schema
here. `ledger.validate_event` uses this registry to reject malformed or
unknown payloads *safely* (as a per-record outcome, never a crash / never a
500 that takes the rest of the batch down with it).

Wire-format note: the NDJSON line itself does NOT carry patient_id or
actor identity — those come from the URL path and the authenticated
session respectively, so a client can never assert "this event happened
as some other patient/user." The ledger row still *stores* patient_id and
actor_user_id/actor_role on every CareEvent, satisfying the full event
shape required by the architecture — they are just derived server-side
instead of trusted from the client, which is strictly safer.
"""
from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator, model_validator

CURRENT_SCHEMA_VERSION = 1

KNOWN_EVENT_TYPES = {
    "routine_edit",
    "cognitive_game_result",
    "mood_log",
    "reminder_scheduled",
    "reminder_notification_attempted",
    "reminder_provider_accepted",
    "reminder_user_acknowledged",
    "reminder_caregiver_escalated",
    "geofence_observation",
    "consent_change",
    "caregiver_action",
}

# Event types that are safety/medication critical — an unknown or malformed
# event carrying one of these types is always treated conservatively
# (rejected, never guessed-and-applied) even if future schema versions add
# more leniency elsewhere.
CRITICAL_EVENT_TYPES = {
    "reminder_scheduled",
    "reminder_notification_attempted",
    "reminder_provider_accepted",
    "reminder_user_acknowledged",
    "reminder_caregiver_escalated",
    "geofence_observation",
    "consent_change",
}


class CareEventEnvelope(BaseModel):
    """The outer shape every NDJSON line must match before we even look at
    the payload. Deliberately permissive on payload (validated separately
    per event_type) so one unknown future field never breaks ingestion."""
    event_id: str = Field(min_length=1, max_length=100)
    device_id: str = Field(min_length=1, max_length=100)
    device_sequence: int = Field(ge=0)
    event_type: str
    schema_version: int = Field(default=1, ge=1)
    observed_at: Optional[str] = None  # ISO 8601, device clock — untrusted
    consent_version: Optional[int] = Field(default=None, ge=0)
    payload: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Per-event-type payload schemas
# ---------------------------------------------------------------------------

class RoutineEditPayload(BaseModel):
    routine_key: str = Field(min_length=1, max_length=120)
    period: str = Field(pattern="^(morning|afternoon|evening|custom)$")
    title_en: str = Field(min_length=1, max_length=200)
    title_as: Optional[str] = None
    scheduled_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    active: bool = True


class CognitiveGameResultPayload(BaseModel):
    activity_code: str
    difficulty: int = Field(ge=1, le=5)
    score: int = Field(ge=0, le=100)
    accuracy: float = Field(ge=0.0, le=1.0)
    attempts: int = Field(ge=0, le=1000)
    correct_attempts: int = Field(ge=0, le=1000)
    avg_response_time_ms: int = Field(ge=0, le=600000)

    @field_validator("correct_attempts")
    @classmethod
    def correct_not_more_than_attempts(cls, v, info):
        attempts = info.data.get("attempts")
        if attempts is not None and v > attempts:
            raise ValueError("correct_attempts cannot exceed attempts")
        return v


class MoodLogPayload(BaseModel):
    mood: str = Field(pattern="^(good|okay|unsure|sad)$")
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class ReminderLifecyclePayload(BaseModel):
    """Shared shape for all five reminder-lifecycle event types."""
    reminder_occurrence_key: str = Field(min_length=1, max_length=160)
    note: Optional[str] = Field(default=None, max_length=300)


class GeofenceObservationPayload(BaseModel):
    observation_type: Literal["observed", "inferred_transition", "stale", "unknown"]
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    distance_from_safe_zone_m: Optional[float] = Field(default=None, ge=0)
    within_safe_zone: Optional[bool] = None

    @field_validator("within_safe_zone")
    @classmethod
    def unknown_cannot_claim_safety(cls, v, info):
        obs = info.data.get("observation_type")
        if obs in ("unknown", "stale") and v is not None:
            raise ValueError("an unknown/stale observation must not assert within_safe_zone")
        return v

    @model_validator(mode="after")
    def observed_requires_a_real_reading(self):
        if self.observation_type in ("observed", "inferred_transition"):
            if self.within_safe_zone is None or self.latitude is None or self.longitude is None:
                raise ValueError(
                    "an 'observed'/'inferred_transition' reading must include latitude, "
                    "longitude and within_safe_zone — partial data must be reported as 'stale' or 'unknown' instead"
                )
        return self


class ConsentChangePayload(BaseModel):
    category: str = Field(pattern="^(location|wearable|data_sharing)$")
    granted: bool
    notes: Optional[str] = Field(default=None, max_length=300)


class CaregiverActionPayload(BaseModel):
    action: str = Field(min_length=1, max_length=80)
    related_id: Optional[str] = Field(default=None, max_length=100)
    detail: Optional[str] = Field(default=None, max_length=300)


PAYLOAD_SCHEMAS = {
    "routine_edit": RoutineEditPayload,
    "cognitive_game_result": CognitiveGameResultPayload,
    "mood_log": MoodLogPayload,
    "reminder_scheduled": ReminderLifecyclePayload,
    "reminder_notification_attempted": ReminderLifecyclePayload,
    "reminder_provider_accepted": ReminderLifecyclePayload,
    "reminder_user_acknowledged": ReminderLifecyclePayload,
    "reminder_caregiver_escalated": ReminderLifecyclePayload,
    "geofence_observation": GeofenceObservationPayload,
    "consent_change": ConsentChangePayload,
    "caregiver_action": CaregiverActionPayload,
}
