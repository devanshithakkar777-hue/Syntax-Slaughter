"""
Sukoon — Database models.

Covers every table named in the product spec (section 16):
Users, Patients, Caregivers, Doctors, PatientCaregiverRelationships,
DoctorAuthorizations, ConsentRecords, CognitiveActivities (activity type
catalog), GameSessions, PerformanceRecords, Reminders, ReminderResponses,
DailyRoutines, Appointments, MoodRecords, WearableData, LocationData,
SafetyAlerts, Notifications, SyncQueue, AuditLogs.

Every table uses a UUID primary key and created_at/updated_at timestamps.
"""
import uuid
import enum
from datetime import datetime

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, ForeignKey, Text, Enum,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base


def gen_id():
    return str(uuid.uuid4())


def now():
    return datetime.utcnow()


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class UserRole(str, enum.Enum):
    patient = "patient"
    caregiver = "caregiver"
    doctor = "doctor"
    family = "family"


class ReminderKind(str, enum.Enum):
    medicine = "medicine"
    hydration = "hydration"
    appointment = "appointment"
    routine = "routine"


class ReminderStatus(str, enum.Enum):
    pending = "pending"
    completed = "completed"
    missed = "missed"
    snoozed = "snoozed"
    escalated = "escalated"


class AuthorizationStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    revoked = "revoked"


class AlertSeverity(str, enum.Enum):
    info = "info"
    warning = "warning"
    critical = "critical"


class SyncStatus(str, enum.Enum):
    queued = "queued"
    synced = "synced"
    failed = "failed"


# ---------------------------------------------------------------------------
# Core identity
# ---------------------------------------------------------------------------

class User(Base):
    """Login identity shared by all roles (patients, caregivers, doctors)."""
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=gen_id)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(Enum(UserRole), nullable=False)
    full_name = Column(String, nullable=False)
    preferred_language = Column(String, default="en")  # 'en' or 'as' (Assamese)
    is_demo = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)
    last_login_at = Column(DateTime, nullable=True)

    patient_profile = relationship("Patient", back_populates="user", uselist=False)
    caregiver_profile = relationship("Caregiver", back_populates="user", uselist=False)
    doctor_profile = relationship("Doctor", back_populates="user", uselist=False)
    family_profile = relationship("FamilyMember", back_populates="user", uselist=False)


class Patient(Base):
    __tablename__ = "patients"

    id = Column(String, primary_key=True, default=gen_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, unique=True)
    age = Column(Integer, nullable=True)
    gender = Column(String, nullable=True)
    condition_notes = Column(Text, nullable=True)  # e.g. "Mild cognitive impairment"
    home_region = Column(String, default="Guwahati, Assam")
    current_difficulty_level = Column(Integer, default=2)  # 1-5
    phone = Column(String, nullable=True)  # lets caregiver/family "call the patient" (tel: link)
    daily_water_target = Column(Integer, default=8, nullable=False)  # glasses/day
    created_at = Column(DateTime, default=now)

    user = relationship("User", back_populates="patient_profile")


class Caregiver(Base):
    __tablename__ = "caregivers"

    id = Column(String, primary_key=True, default=gen_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, unique=True)
    relationship_to_patient = Column(String, default="Family caregiver")
    phone = Column(String, nullable=True)
    created_at = Column(DateTime, default=now)

    user = relationship("User", back_populates="caregiver_profile")


class Doctor(Base):
    __tablename__ = "doctors"

    id = Column(String, primary_key=True, default=gen_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, unique=True)
    hospital_or_clinic = Column(String, nullable=True)
    specialization = Column(String, default="Geriatric Medicine")
    registration_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=now)

    user = relationship("User", back_populates="doctor_profile")


class FamilyMember(Base):
    """A family-dashboard login: a broader household view than one caregiver's —
    sees the patient's, caregiver's, and doctor's data together, and is the
    only role (besides the patient) that can manage doctor authorizations."""
    __tablename__ = "family_members"

    id = Column(String, primary_key=True, default=gen_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, unique=True)
    relationship_to_patient = Column(String, default="Family member")
    phone = Column(String, nullable=True)
    # "all" = every update including small ones (missed water, mood check-in);
    # "important" = only safety-significant updates (left safe zone, alert
    # resolved, new diagnosis, help requests). Defaults to "important" so a
    # new family login isn't flooded on day one.
    notification_preference = Column(String, default="important")
    created_at = Column(DateTime, default=now)

    user = relationship("User", back_populates="family_profile")


class PatientCaregiverRelationship(Base):
    __tablename__ = "patient_caregiver_relationships"

    id = Column(String, primary_key=True, default=gen_id)
    patient_id = Column(String, ForeignKey("patients.id"), nullable=False)
    caregiver_id = Column(String, ForeignKey("caregivers.id"), nullable=False)
    is_primary = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)


class PatientFamilyRelationship(Base):
    __tablename__ = "patient_family_relationships"

    id = Column(String, primary_key=True, default=gen_id)
    patient_id = Column(String, ForeignKey("patients.id"), nullable=False)
    family_member_id = Column(String, ForeignKey("family_members.id"), nullable=False)
    created_at = Column(DateTime, default=now)


class PatientContact(Base):
    """One entry in the patient's 'family tree' / call list — a person the
    patient can see (name, relationship, photo) and call. May optionally be
    linked to a real Sukoon login (a FamilyMember or Caregiver account) so a
    patient-initiated call also raises an in-app notification for that
    person; a contact with no linked account (e.g. a nurse with no login)
    still works for photo recall and the tel: call button, just without the
    in-app notification. Managed by the caregiver or family dashboard —
    kept out of the patient app's own input surface by design."""
    __tablename__ = "patient_contacts"

    id = Column(String, primary_key=True, default=gen_id)
    patient_id = Column(String, ForeignKey("patients.id"), nullable=False)
    name = Column(String, nullable=False)
    relationship_label = Column(String, nullable=False)  # "Daughter", "Grandson", "Nurse", ...
    contact_type = Column(String, default="family")  # family | caregiver | nurse | other
    phone = Column(String, nullable=True)
    photo_url = Column(Text, nullable=True)  # data: URI (uploaded photo) — see routers/contacts.py
    linked_family_member_id = Column(String, ForeignKey("family_members.id"), nullable=True)
    linked_caregiver_id = Column(String, ForeignKey("caregivers.id"), nullable=True)
    display_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=now)


# ---------------------------------------------------------------------------
# Authorization & consent
# ---------------------------------------------------------------------------

class DoctorAuthorization(Base):
    """A request (from the family dashboard, or the patient themselves) granting
    a doctor scoped access to one patient. Caregivers can view these but not
    create/approve/revoke them — that authority lives with family + patient."""
    __tablename__ = "doctor_authorizations"

    id = Column(String, primary_key=True, default=gen_id)
    patient_id = Column(String, ForeignKey("patients.id"), nullable=False)
    doctor_id = Column(String, ForeignKey("doctors.id"), nullable=False)
    requested_by_caregiver_id = Column(String, ForeignKey("caregivers.id"), nullable=True)
    requested_by_family_id = Column(String, ForeignKey("family_members.id"), nullable=True)
    status = Column(Enum(AuthorizationStatus), default=AuthorizationStatus.pending)

    # granular scope switches
    scope_cognitive_performance = Column(Boolean, default=True)
    scope_activity_history = Column(Boolean, default=True)
    scope_reminder_adherence = Column(Boolean, default=True)
    scope_location = Column(Boolean, default=False)
    scope_wearable_data = Column(Boolean, default=True)
    scope_medical_records = Column(Boolean, default=True)

    requested_at = Column(DateTime, default=now)
    decided_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)


class ConsentRecord(Base):
    """Explicit consent grants for sensitive data categories (location, wearable, etc.)."""
    __tablename__ = "consent_records"

    id = Column(String, primary_key=True, default=gen_id)
    patient_id = Column(String, ForeignKey("patients.id"), nullable=False)
    granted_by_user_id = Column(String, ForeignKey("users.id"), nullable=False)
    category = Column(String, nullable=False)  # 'location', 'wearable', 'data_sharing'
    granted = Column(Boolean, default=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now)


# ---------------------------------------------------------------------------
# Cognitive activities / games
# ---------------------------------------------------------------------------

class CognitiveActivity(Base):
    """Catalog of activity types available in the app (seeded once)."""
    __tablename__ = "cognitive_activities"

    id = Column(String, primary_key=True, default=gen_id)
    code = Column(String, unique=True, nullable=False)  # memory_matching, pattern_recognition, ...
    name_en = Column(String, nullable=False)
    name_as = Column(String, nullable=False)
    domain = Column(String, nullable=False)  # memory, attention, recognition, engagement
    description_en = Column(Text, nullable=True)
    description_as = Column(Text, nullable=True)


class GameSession(Base):
    __tablename__ = "game_sessions"

    id = Column(String, primary_key=True, default=gen_id)
    patient_id = Column(String, ForeignKey("patients.id"), nullable=False)
    activity_code = Column(String, ForeignKey("cognitive_activities.code"), nullable=False)
    difficulty = Column(Integer, nullable=False)  # level at time of play, 1-5
    started_at = Column(DateTime, default=now)
    completed_at = Column(DateTime, nullable=True)
    is_demo_data = Column(Boolean, default=False)
    synced = Column(Boolean, default=True)


class PerformanceRecord(Base):
    """One scored result for a completed game session, plus adaptive-engine outcome."""
    __tablename__ = "performance_records"

    id = Column(String, primary_key=True, default=gen_id)
    session_id = Column(String, ForeignKey("game_sessions.id"), nullable=False)
    patient_id = Column(String, ForeignKey("patients.id"), nullable=False)
    activity_code = Column(String, nullable=False)

    score = Column(Integer, nullable=False)          # 0-100
    accuracy = Column(Float, nullable=False)          # 0.0-1.0
    attempts = Column(Integer, nullable=False)
    correct_attempts = Column(Integer, nullable=False)
    avg_response_time_ms = Column(Integer, nullable=False)
    difficulty = Column(Integer, nullable=False)

    # adaptive engine outcome
    new_difficulty = Column(Integer, nullable=False)
    adaptive_direction = Column(String, nullable=False)  # increased/maintained/reduced
    adaptive_explanation_en = Column(Text, nullable=False)
    adaptive_explanation_as = Column(Text, nullable=True)

    is_demo_data = Column(Boolean, default=False)
    timestamp = Column(DateTime, default=now)


# ---------------------------------------------------------------------------
# Routines, reminders, appointments
# ---------------------------------------------------------------------------

class DailyRoutine(Base):
    __tablename__ = "daily_routines"

    id = Column(String, primary_key=True, default=gen_id)
    patient_id = Column(String, ForeignKey("patients.id"), nullable=False)
    period = Column(String, nullable=False)  # morning / afternoon / evening / custom
    title_en = Column(String, nullable=False)
    title_as = Column(String, nullable=True)
    scheduled_time = Column(String, nullable=False)  # "HH:MM"
    is_custom = Column(Boolean, default=False)
    created_by_caregiver_id = Column(String, ForeignKey("caregivers.id"), nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)


class RoutineCompletion(Base):
    """Per-day completion state for a routine item."""
    __tablename__ = "routine_completions"

    id = Column(String, primary_key=True, default=gen_id)
    routine_id = Column(String, ForeignKey("daily_routines.id"), nullable=False)
    patient_id = Column(String, ForeignKey("patients.id"), nullable=False)
    date = Column(String, nullable=False)  # "YYYY-MM-DD"
    status = Column(String, default="pending")  # pending/completed
    completed_at = Column(DateTime, nullable=True)


class Reminder(Base):
    __tablename__ = "reminders"

    id = Column(String, primary_key=True, default=gen_id)
    patient_id = Column(String, ForeignKey("patients.id"), nullable=False)
    kind = Column(Enum(ReminderKind), nullable=False)
    title_en = Column(String, nullable=False)
    title_as = Column(String, nullable=True)
    detail = Column(String, nullable=True)  # e.g. medicine dosage, appointment location
    scheduled_time = Column(String, nullable=False)  # "HH:MM"
    days_of_week = Column(String, default="MTWTFSS")  # simple mask string
    escalation_minutes = Column(Integer, default=15)  # gentle follow-up after N minutes
    escalation_final_minutes = Column(Integer, default=30)  # caregiver alert after N minutes
    active = Column(Boolean, default=True)
    created_by_caregiver_id = Column(String, ForeignKey("caregivers.id"), nullable=True)
    created_at = Column(DateTime, default=now)


class ReminderResponse(Base):
    """One occurrence of a reminder firing on a given day, and how it was handled."""
    __tablename__ = "reminder_responses"

    id = Column(String, primary_key=True, default=gen_id)
    reminder_id = Column(String, ForeignKey("reminders.id"), nullable=False)
    patient_id = Column(String, ForeignKey("patients.id"), nullable=False)
    date = Column(String, nullable=False)  # "YYYY-MM-DD"
    fired_at = Column(DateTime, default=now)
    status = Column(Enum(ReminderStatus), default=ReminderStatus.pending)
    responded_at = Column(DateTime, nullable=True)
    gentle_followup_sent = Column(Boolean, default=False)
    gentle_followup_at = Column(DateTime, nullable=True)
    caregiver_alert_sent = Column(Boolean, default=False)
    caregiver_alert_at = Column(DateTime, nullable=True)
    is_demo_data = Column(Boolean, default=False)
    synced = Column(Boolean, default=True)
    # Medicine reminders require *both* sign-offs before they count as taken:
    # the patient confirms they took it, and the caregiver independently
    # confirms they saw it happen. Other reminder kinds (hydration, routine)
    # only ever use patient_confirmed (set alongside status=completed) and
    # ignore the caregiver_* pair entirely.
    patient_confirmed = Column(Boolean, default=False)
    patient_confirmed_at = Column(DateTime, nullable=True)
    caregiver_confirmed = Column(Boolean, default=False)
    caregiver_confirmed_at = Column(DateTime, nullable=True)
    caregiver_confirmed_by_id = Column(String, ForeignKey("caregivers.id"), nullable=True)


class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(String, primary_key=True, default=gen_id)
    patient_id = Column(String, ForeignKey("patients.id"), nullable=False)
    doctor_name = Column(String, nullable=False)
    hospital_or_clinic = Column(String, nullable=True)
    date = Column(String, nullable=False)  # "YYYY-MM-DD"
    time = Column(String, nullable=False)  # "HH:MM"
    location = Column(String, nullable=True)
    reminder_enabled = Column(Boolean, default=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now)


class MedicalRecord(Base):
    """A doctor's hospital-file-style record for one appointment: diagnosis,
    prescription, vitals and follow-up notes. Written only by the authorized
    doctor who saw the patient for that appointment; readable by patient,
    caregiver (view-only) and family per the same authorization scopes."""
    __tablename__ = "medical_records"

    id = Column(String, primary_key=True, default=gen_id)
    appointment_id = Column(String, ForeignKey("appointments.id"), nullable=False, unique=True)
    patient_id = Column(String, ForeignKey("patients.id"), nullable=False)
    doctor_id = Column(String, ForeignKey("doctors.id"), nullable=False)

    visit_date = Column(String, nullable=False)  # "YYYY-MM-DD"
    chief_complaint = Column(Text, nullable=True)
    diagnosis = Column(Text, nullable=False)
    prescription = Column(Text, nullable=True)  # free text: drug, dose, duration per line
    vitals_bp = Column(String, nullable=True)          # e.g. "138/86 mmHg"
    vitals_pulse = Column(String, nullable=True)        # e.g. "78 bpm"
    vitals_weight_kg = Column(Float, nullable=True)
    follow_up_instructions = Column(Text, nullable=True)
    follow_up_date = Column(String, nullable=True)  # "YYYY-MM-DD"

    is_demo_data = Column(Boolean, default=False)
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)


# ---------------------------------------------------------------------------
# Mood / wellbeing
# ---------------------------------------------------------------------------

class MoodRecord(Base):
    __tablename__ = "mood_records"

    id = Column(String, primary_key=True, default=gen_id)
    patient_id = Column(String, ForeignKey("patients.id"), nullable=False)
    mood = Column(String, nullable=False)  # good / okay / unsure / sad
    date = Column(String, nullable=False)  # "YYYY-MM-DD"
    timestamp = Column(DateTime, default=now)
    is_demo_data = Column(Boolean, default=False)
    synced = Column(Boolean, default=True)


class WaterIntake(Base):
    """One row per patient per day: a simple 'glasses drunk today' tally against
    Patient.daily_water_target. Deliberately not tied to specific times (unlike
    the hydration Reminder rows, which are a separate escalating-alert safety
    net) -- this is the patient's own simple self-tracked checklist."""
    __tablename__ = "water_intake"

    id = Column(String, primary_key=True, default=gen_id)
    patient_id = Column(String, ForeignKey("patients.id"), nullable=False)
    date = Column(String, nullable=False)  # "YYYY-MM-DD"
    glasses_completed = Column(Integer, default=0, nullable=False)
    updated_at = Column(DateTime, default=now, onupdate=now)


class MealIntake(Base):
    """One row per patient per day: a simple breakfast/lunch/dinner checklist,
    same spirit as WaterIntake -- 'Lunch - done, Dinner - pending'."""
    __tablename__ = "meal_intake"

    id = Column(String, primary_key=True, default=gen_id)
    patient_id = Column(String, ForeignKey("patients.id"), nullable=False)
    date = Column(String, nullable=False)  # "YYYY-MM-DD"
    breakfast_done = Column(Boolean, default=False)
    lunch_done = Column(Boolean, default=False)
    dinner_done = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=now, onupdate=now)


# ---------------------------------------------------------------------------
# Wearable + location (simulated)
# ---------------------------------------------------------------------------

class WearableData(Base):
    __tablename__ = "wearable_data"

    id = Column(String, primary_key=True, default=gen_id)
    patient_id = Column(String, ForeignKey("patients.id"), nullable=False)
    device_type = Column(String, default="Smartwatch")  # Smartwatch / Patch
    heart_rate_bpm = Column(Integer, nullable=True)
    steps = Column(Integer, nullable=True)
    activity_level = Column(String, nullable=True)  # resting/light/active
    battery_pct = Column(Integer, nullable=True)
    is_demo_data = Column(Boolean, default=True)
    timestamp = Column(DateTime, default=now)


class LocationData(Base):
    __tablename__ = "location_data"

    id = Column(String, primary_key=True, default=gen_id)
    patient_id = Column(String, ForeignKey("patients.id"), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    distance_from_safe_zone_m = Column(Float, nullable=False)
    within_safe_zone = Column(Boolean, default=True)
    is_demo_data = Column(Boolean, default=True)
    timestamp = Column(DateTime, default=now)


class SafeZoneConfig(Base):
    __tablename__ = "safe_zone_configs"

    id = Column(String, primary_key=True, default=gen_id)
    patient_id = Column(String, ForeignKey("patients.id"), nullable=False, unique=True)
    label = Column(String, default="Home")
    center_lat = Column(Float, nullable=False)
    center_lng = Column(Float, nullable=False)
    radius_m = Column(Integer, default=500)
    tracking_enabled = Column(Boolean, default=False)
    consented = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=now)


class SafetyAlert(Base):
    __tablename__ = "safety_alerts"

    id = Column(String, primary_key=True, default=gen_id)
    patient_id = Column(String, ForeignKey("patients.id"), nullable=False)
    alert_type = Column(String, nullable=False)  # 'geofence', 'reminder_nonresponse', 'wearable'
    severity = Column(Enum(AlertSeverity), default=AlertSeverity.warning)
    message_en = Column(Text, nullable=False)
    message_as = Column(Text, nullable=True)
    related_id = Column(String, nullable=True)  # reminder_response_id / location_data_id etc
    acknowledged = Column(Boolean, default=False)
    acknowledged_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=now)


# ---------------------------------------------------------------------------
# Notifications / sync / audit
# ---------------------------------------------------------------------------

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String, primary_key=True, default=gen_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=False)
    body = Column(Text, nullable=True)
    category = Column(String, default="general")  # reminder/alert/authorization/system
    read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=now)


class SyncQueueItem(Base):
    """Server-side mirror of a client offline-queue entry, for dedupe + audit."""
    __tablename__ = "sync_queue"

    id = Column(String, primary_key=True, default=gen_id)
    client_generated_id = Column(String, unique=True, nullable=False)  # idempotency key
    patient_id = Column(String, ForeignKey("patients.id"), nullable=False)
    entity_type = Column(String, nullable=False)  # game_session/mood/reminder_response
    payload_json = Column(Text, nullable=False)
    status = Column(Enum(SyncStatus), default=SyncStatus.queued)
    created_offline_at = Column(DateTime, nullable=True)
    synced_at = Column(DateTime, nullable=True)


class JournalEntry(Base):
    """One row per patient per day: a free-text (optionally voice-dictated)
    diary entry. The next day, the patient can read/hear it played back and
    mark whether they remembered the day -- a lightweight memory-recall
    check, not a clinical assessment."""
    __tablename__ = "journal_entries"

    id = Column(String, primary_key=True, default=gen_id)
    patient_id = Column(String, ForeignKey("patients.id"), nullable=False)
    date = Column(String, nullable=False)  # "YYYY-MM-DD"
    text = Column(Text, nullable=True)
    recorded_via_voice = Column(Boolean, default=False)
    remembered = Column(Boolean, nullable=True)  # null = not yet reviewed
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)


class CompanionChatMessage(Base):
    """History for the rule-based Companion Chat (not a real AI/LLM --
    scripted comfort responses). Kept simple: sender is 'patient' or 'bot'."""
    __tablename__ = "companion_chat_messages"

    id = Column(String, primary_key=True, default=gen_id)
    patient_id = Column(String, ForeignKey("patients.id"), nullable=False)
    sender = Column(String, nullable=False)  # "patient" | "bot"
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=now)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True, default=gen_id)
    actor_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    action = Column(String, nullable=False)  # e.g. "login", "authorization.approve"
    entity_type = Column(String, nullable=True)
    entity_id = Column(String, nullable=True)
    detail = Column(Text, nullable=True)
    ip_address = Column(String, nullable=True)
    created_at = Column(DateTime, default=now)


# ---------------------------------------------------------------------------
# Offline Care Ledger + Safety Reconciliation Engine
#
# Everything below is additive and self-contained: it introduces a new,
# append-only event ledger (CareEvent) as the audit source of truth for a
# bounded set of event categories (routine edits, the medication-reminder
# lifecycle, mood/cognitive-activity logs, geofence observations, consent
# changes, caregiver actions), plus small "derived projection" tables that
# are always fully rebuildable from the ledger alone (see ledger.py /
# reconciliation.py). None of the tables above are modified or depended on
# by this subsystem, so the already-working live app cannot be broken by it
# — this is a parallel, offline-sync-safe path, not a rewrite of the
# existing direct-write endpoints.
# ---------------------------------------------------------------------------

class CareEvent(Base):
    """Append-only ledger row. Never updated or deleted after insert — the
    *only* mutable bookkeeping fields are the ones recording how ingestion
    resolved this specific event (ingest_status/reconciliation_reason),
    which are written exactly once, at insert time, and never touched again.
    `server_sequence` (the DB's own autoincrement) is the single authoritative
    ordering key for replay — device_sequence and observed_at are untrusted
    client-reported metadata, kept for audit/gap-detection only."""
    __tablename__ = "care_events"

    server_sequence = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String, unique=True, nullable=False, index=True)  # client-generated UUID; idempotency key

    patient_id = Column(String, ForeignKey("patients.id"), nullable=False, index=True)
    device_id = Column(String, nullable=False)
    device_sequence = Column(Integer, nullable=False)

    event_type = Column(String, nullable=False)
    schema_version = Column(Integer, nullable=False, default=1)

    observed_at = Column(DateTime, nullable=True)   # device-claimed clock — untrusted
    received_at = Column(DateTime, default=now, nullable=False)  # server clock, at insert

    actor_user_id = Column(String, ForeignKey("users.id"), nullable=True)
    actor_role = Column(String, nullable=True)

    consent_version = Column(Integer, nullable=True)  # consent version the device believed was current

    payload_json = Column(Text, nullable=False)  # raw payload as submitted (even if later judged invalid)
    integrity_hash = Column(String, nullable=False)  # sha256 over event_id+patient_id+device_id+device_sequence+event_type+payload

    ingest_status = Column(String, nullable=False)  # accepted | duplicate | rejected | conflict_review
    reconciliation_reason = Column(Text, nullable=True)  # human-readable explanation of the outcome

    created_at = Column(DateTime, default=now)

    __table_args__ = (
        UniqueConstraint("device_id", "patient_id", "device_sequence", name="uq_care_event_device_seq"),
    )


class DeviceSyncCheckpoint(Base):
    """Per (patient, device) bookkeeping used purely for resumable sync and
    gap detection — never used to decide event ordering (server_sequence
    does that)."""
    __tablename__ = "device_sync_checkpoints"

    id = Column(String, primary_key=True, default=gen_id)
    patient_id = Column(String, ForeignKey("patients.id"), nullable=False)
    device_id = Column(String, nullable=False)
    max_device_sequence_seen = Column(Integer, default=0, nullable=False)
    contiguous_up_to = Column(Integer, default=0, nullable=False)  # highest N such that 1..N all seen, no gaps
    known_gaps_json = Column(Text, default="[]")  # JSON list of device_sequence ints seen-missing
    last_server_sequence = Column(Integer, default=0, nullable=False)
    updated_at = Column(DateTime, default=now, onupdate=now)

    __table_args__ = (
        UniqueConstraint("patient_id", "device_id", name="uq_device_checkpoint"),
    )


class RoutineLedgerState(Base):
    """Derived projection: the current state of one routine item, as
    reconciled from routine_edit ledger events. Fully rebuildable by replay."""
    __tablename__ = "routine_ledger_state"

    id = Column(String, primary_key=True, default=gen_id)
    patient_id = Column(String, ForeignKey("patients.id"), nullable=False)
    routine_key = Column(String, nullable=False)  # client-stable key so edits from different devices converge

    period = Column(String, nullable=True)
    title_en = Column(String, nullable=True)
    title_as = Column(String, nullable=True)
    scheduled_time = Column(String, nullable=True)
    active = Column(Boolean, default=True)

    last_event_id = Column(String, nullable=True)
    last_server_sequence = Column(Integer, nullable=True)
    conflict = Column(Boolean, default=False)
    conflict_reason = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=now, onupdate=now)

    __table_args__ = (
        UniqueConstraint("patient_id", "routine_key", name="uq_routine_ledger_key"),
    )


class ReminderLedgerState(Base):
    """Derived projection for the medication/reminder lifecycle. Delivery
    progress and the user's own acknowledgement are tracked as *separate*
    fields on purpose — a notification being sent is never conflated with
    the medicine actually being taken."""
    __tablename__ = "reminder_ledger_state"

    id = Column(String, primary_key=True, default=gen_id)
    patient_id = Column(String, ForeignKey("patients.id"), nullable=False)
    reminder_occurrence_key = Column(String, nullable=False)  # e.g. "<reminder_id>:<date>"

    delivery_state = Column(String, default="scheduled")  # scheduled|notification_attempted|provider_accepted
    user_acknowledged = Column(Boolean, default=False)
    user_acknowledged_at = Column(DateTime, nullable=True)
    caregiver_escalated = Column(Boolean, default=False)
    caregiver_escalated_at = Column(DateTime, nullable=True)

    sync_status = Column(String, default="pending")  # pending|synced|conflict|rejected|needs_review

    last_event_id = Column(String, nullable=True)
    last_server_sequence = Column(Integer, nullable=True)
    updated_at = Column(DateTime, default=now, onupdate=now)

    __table_args__ = (
        UniqueConstraint("patient_id", "reminder_occurrence_key", name="uq_reminder_ledger_key"),
    )


class ConsentLedgerState(Base):
    """Derived, versioned, per-category consent state. `version` increments
    on every accepted change and is the number compared against an incoming
    event's claimed consent_version to decide whether that event is stale."""
    __tablename__ = "consent_ledger_state"

    id = Column(String, primary_key=True, default=gen_id)
    patient_id = Column(String, ForeignKey("patients.id"), nullable=False)
    category = Column(String, nullable=False)  # location | wearable | data_sharing | ...
    granted = Column(Boolean, default=False)
    version = Column(Integer, default=0, nullable=False)

    last_event_id = Column(String, nullable=True)
    last_server_sequence = Column(Integer, nullable=True)
    updated_at = Column(DateTime, default=now, onupdate=now)

    __table_args__ = (
        UniqueConstraint("patient_id", "category", name="uq_consent_ledger_key"),
    )


class GeofenceLedgerState(Base):
    """Derived projection distinguishing a real observation from an inferred
    transition, a stale reading, or no signal at all. `within_safe_zone` is
    only ever set from an actual observation — it is never defaulted to a
    'safe' value when telemetry is missing."""
    __tablename__ = "geofence_ledger_state"

    id = Column(String, primary_key=True, default=gen_id)
    patient_id = Column(String, ForeignKey("patients.id"), nullable=False, unique=True)

    observation_type = Column(String, nullable=True)  # observed|inferred_transition|stale|unknown
    within_safe_zone = Column(Boolean, nullable=True)  # null = unknown
    distance_from_safe_zone_m = Column(Float, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    last_observed_at = Column(DateTime, nullable=True)  # device-claimed
    last_received_at = Column(DateTime, nullable=True)  # server clock
    last_event_id = Column(String, nullable=True)
    last_server_sequence = Column(Integer, nullable=True)
    updated_at = Column(DateTime, default=now, onupdate=now)
