"""
Sukoon — Pydantic request schemas (input validation).

Output serialization is done with small hand-written `to_dict()` helpers in
each router (kept simple deliberately — this is a prototype, not a public
SDK). Every input schema below is what stands between a raw HTTP body and
the database, so this is where input validation for the app lives.
"""
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class GameSessionCreate(BaseModel):
    activity_code: str
    difficulty: int = Field(ge=1, le=5)
    score: int = Field(ge=0, le=100)
    accuracy: float = Field(ge=0.0, le=1.0)
    attempts: int = Field(ge=0, le=1000)
    correct_attempts: int = Field(ge=0, le=1000)
    avg_response_time_ms: int = Field(ge=0, le=600000)
    client_generated_id: Optional[str] = None
    created_offline_at: Optional[str] = None

    @field_validator("correct_attempts")
    @classmethod
    def correct_not_more_than_attempts(cls, v, info):
        attempts = info.data.get("attempts")
        if attempts is not None and v > attempts:
            raise ValueError("correct_attempts cannot exceed attempts")
        return v


class MoodCreate(BaseModel):
    mood: str = Field(pattern="^(good|okay|unsure|sad)$")
    client_generated_id: Optional[str] = None
    created_offline_at: Optional[str] = None


class ReminderCreate(BaseModel):
    patient_id: str
    kind: str = Field(pattern="^(medicine|hydration|appointment|routine)$")
    title_en: str = Field(min_length=1, max_length=200)
    title_as: Optional[str] = None
    detail: Optional[str] = Field(default=None, max_length=500)
    scheduled_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    days_of_week: Optional[str] = "MTWTFSS"
    escalation_minutes: int = Field(default=15, ge=1, le=180)
    escalation_final_minutes: int = Field(default=30, ge=2, le=360)


class ReminderRespond(BaseModel):
    status: str = Field(pattern="^(completed|snoozed)$")


class RoutineCreate(BaseModel):
    patient_id: str
    period: str = Field(pattern="^(morning|afternoon|evening|custom)$")
    title_en: str = Field(min_length=1, max_length=200)
    title_as: Optional[str] = None
    scheduled_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    is_custom: bool = False


class AppointmentCreate(BaseModel):
    patient_id: str
    doctor_name: str = Field(min_length=1, max_length=200)
    hospital_or_clinic: Optional[str] = None
    date: str
    time: str
    location: Optional[str] = None
    notes: Optional[str] = None


class DoctorAuthorizationCreate(BaseModel):
    patient_id: str
    doctor_name: str = Field(min_length=1, max_length=200)
    hospital_or_clinic: Optional[str] = None
    doctor_email: EmailStr
    scope_cognitive_performance: bool = True
    scope_activity_history: bool = True
    scope_reminder_adherence: bool = True
    scope_location: bool = False
    scope_wearable_data: bool = True
    scope_medical_records: bool = True


class AuthorizationDecision(BaseModel):
    approve: bool


class MedicalRecordCreate(BaseModel):
    appointment_id: str
    patient_id: str
    visit_date: str
    chief_complaint: Optional[str] = Field(default=None, max_length=1000)
    diagnosis: str = Field(min_length=1, max_length=2000)
    prescription: Optional[str] = Field(default=None, max_length=2000)
    vitals_bp: Optional[str] = Field(default=None, max_length=20)
    vitals_pulse: Optional[str] = Field(default=None, max_length=20)
    vitals_weight_kg: Optional[float] = Field(default=None, ge=0, le=400)
    follow_up_instructions: Optional[str] = Field(default=None, max_length=1000)
    follow_up_date: Optional[str] = None


class MedicalRecordUpdate(BaseModel):
    chief_complaint: Optional[str] = Field(default=None, max_length=1000)
    diagnosis: str = Field(min_length=1, max_length=2000)
    prescription: Optional[str] = Field(default=None, max_length=2000)
    vitals_bp: Optional[str] = Field(default=None, max_length=20)
    vitals_pulse: Optional[str] = Field(default=None, max_length=20)
    vitals_weight_kg: Optional[float] = Field(default=None, ge=0, le=400)
    follow_up_instructions: Optional[str] = Field(default=None, max_length=1000)
    follow_up_date: Optional[str] = None


class FamilyLinkPatientCreate(BaseModel):
    patient_id: str
    relationship_to_patient: Optional[str] = Field(default="Family member", max_length=100)


class AlertAcknowledge(BaseModel):
    note: Optional[str] = Field(default=None, max_length=300)


class FamilyNotificationPreferenceUpdate(BaseModel):
    notification_preference: str = Field(pattern="^(all|important)$")


class PatientContactCreate(BaseModel):
    patient_id: str
    name: str = Field(min_length=1, max_length=120)
    relationship_label: str = Field(min_length=1, max_length=60)
    contact_type: str = Field(default="family", pattern="^(family|caregiver|nurse|other)$")
    phone: Optional[str] = Field(default=None, max_length=30)
    photo_data_url: Optional[str] = None  # "data:image/...;base64,...." — see routers/contacts.py for the size cap
    linked_family_member_id: Optional[str] = None
    linked_caregiver_id: Optional[str] = None
    display_order: int = 0


class PatientContactUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    relationship_label: str = Field(min_length=1, max_length=60)
    contact_type: str = Field(default="family", pattern="^(family|caregiver|nurse|other)$")
    phone: Optional[str] = Field(default=None, max_length=30)
    photo_data_url: Optional[str] = None
    display_order: int = 0


class PatientContactCall(BaseModel):
    reason: Optional[str] = Field(default="upset", max_length=120)


class PatientPhoneUpdate(BaseModel):
    phone: Optional[str] = Field(default=None, max_length=30)


class SafeZoneUpdate(BaseModel):
    label: str = "Home"
    center_lat: float
    center_lng: float
    radius_m: int = Field(default=500, ge=50, le=20000)
    tracking_enabled: bool
    consented: bool


class SimulateLocationMove(BaseModel):
    distance_m: float = Field(ge=0, le=50000)


class JournalEntryUpdate(BaseModel):
    text: str = Field(default="", max_length=8000)
    recorded_via_voice: bool = False


class JournalRecall(BaseModel):
    remembered: bool


class AskSukoonQuery(BaseModel):
    text: str = Field(min_length=1, max_length=300)


class CompanionChatSend(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


class SyncItem(BaseModel):
    client_generated_id: str
    entity_type: str = Field(pattern="^(game_session|mood|reminder_response|routine_completion)$")
    payload: dict
    created_offline_at: Optional[str] = None


class SyncBatch(BaseModel):
    items: list[SyncItem]


class LanguageUpdate(BaseModel):
    preferred_language: str = Field(pattern="^(en|as)$")
