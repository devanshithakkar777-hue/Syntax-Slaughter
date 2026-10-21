"""Small hand-written serializers: SQLAlchemy model -> plain dict for JSON responses."""
from . import models


def _enum_val(v):
    return v.value if hasattr(v, "value") else v


def user_public(u: models.User) -> dict:
    return {
        "id": u.id,
        "email": u.email,
        "full_name": u.full_name,
        "role": _enum_val(u.role),
        "preferred_language": u.preferred_language,
        "is_demo": u.is_demo,
    }


def patient_summary(p: models.Patient) -> dict:
    return {
        "id": p.id,
        "user_id": p.user_id,
        "full_name": p.user.full_name if p.user else None,
        "age": p.age,
        "gender": p.gender,
        "condition_notes": p.condition_notes,
        "home_region": p.home_region,
        "current_difficulty_level": p.current_difficulty_level,
        "phone": p.phone,
    }


def performance_record(pr: models.PerformanceRecord) -> dict:
    return {
        "id": pr.id,
        "session_id": pr.session_id,
        "activity_code": pr.activity_code,
        "score": pr.score,
        "accuracy": pr.accuracy,
        "attempts": pr.attempts,
        "correct_attempts": pr.correct_attempts,
        "avg_response_time_ms": pr.avg_response_time_ms,
        "difficulty": pr.difficulty,
        "new_difficulty": pr.new_difficulty,
        "adaptive_direction": pr.adaptive_direction,
        "adaptive_explanation_en": pr.adaptive_explanation_en,
        "adaptive_explanation_as": pr.adaptive_explanation_as,
        "is_demo_data": pr.is_demo_data,
        "timestamp": pr.timestamp.isoformat() if pr.timestamp else None,
    }


def reminder(r: models.Reminder) -> dict:
    return {
        "id": r.id,
        "patient_id": r.patient_id,
        "kind": _enum_val(r.kind),
        "title_en": r.title_en,
        "title_as": r.title_as,
        "detail": r.detail,
        "scheduled_time": r.scheduled_time,
        "days_of_week": r.days_of_week,
        "escalation_minutes": r.escalation_minutes,
        "escalation_final_minutes": r.escalation_final_minutes,
        "active": r.active,
    }


def reminder_response(rr: models.ReminderResponse, parent: models.Reminder = None) -> dict:
    is_medicine = parent is not None and _enum_val(parent.kind) == "medicine"
    return {
        "id": rr.id,
        "reminder_id": rr.reminder_id,
        "patient_id": rr.patient_id,
        "date": rr.date,
        "fired_at": rr.fired_at.isoformat() if rr.fired_at else None,
        "status": _enum_val(rr.status),
        "responded_at": rr.responded_at.isoformat() if rr.responded_at else None,
        "gentle_followup_sent": rr.gentle_followup_sent,
        "caregiver_alert_sent": rr.caregiver_alert_sent,
        "is_demo_data": rr.is_demo_data,
        "title_en": parent.title_en if parent else None,
        "title_as": parent.title_as if parent else None,
        "detail": parent.detail if parent else None,
        "kind": _enum_val(parent.kind) if parent else None,
        "scheduled_time": parent.scheduled_time if parent else None,
        # Dual sign-off, medicine only -- other kinds leave these false/None
        # and the frontend just uses `status` as before.
        "requires_dual_confirmation": is_medicine,
        "patient_confirmed": rr.patient_confirmed,
        "patient_confirmed_at": rr.patient_confirmed_at.isoformat() if rr.patient_confirmed_at else None,
        "caregiver_confirmed": rr.caregiver_confirmed,
        "caregiver_confirmed_at": rr.caregiver_confirmed_at.isoformat() if rr.caregiver_confirmed_at else None,
    }


def routine(r: models.DailyRoutine, status_today: str = "pending") -> dict:
    return {
        "id": r.id,
        "patient_id": r.patient_id,
        "period": r.period,
        "title_en": r.title_en,
        "title_as": r.title_as,
        "scheduled_time": r.scheduled_time,
        "is_custom": r.is_custom,
        "status_today": status_today,
    }


def appointment(a: models.Appointment) -> dict:
    return {
        "id": a.id,
        "patient_id": a.patient_id,
        "doctor_name": a.doctor_name,
        "hospital_or_clinic": a.hospital_or_clinic,
        "date": a.date,
        "time": a.time,
        "location": a.location,
        "reminder_enabled": a.reminder_enabled,
        "notes": a.notes,
        # Free, no-signup video room (Jitsi Meet) so the family can join a
        # consultation remotely — same link for whoever opens it for this
        # appointment, generated deterministically from the appointment id.
        "virtual_meeting_url": f"https://meet.jit.si/Sukoon-Appt-{a.id}",
    }


def mood_record(m: models.MoodRecord) -> dict:
    return {
        "id": m.id,
        "patient_id": m.patient_id,
        "mood": m.mood,
        "date": m.date,
        "timestamp": m.timestamp.isoformat() if m.timestamp else None,
        "is_demo_data": m.is_demo_data,
    }


def wearable(w: models.WearableData) -> dict:
    return {
        "id": w.id,
        "patient_id": w.patient_id,
        "device_type": w.device_type,
        "heart_rate_bpm": w.heart_rate_bpm,
        "steps": w.steps,
        "activity_level": w.activity_level,
        "battery_pct": w.battery_pct,
        "is_demo_data": w.is_demo_data,
        "timestamp": w.timestamp.isoformat() if w.timestamp else None,
    }


def location(l: models.LocationData) -> dict:
    return {
        "id": l.id,
        "patient_id": l.patient_id,
        "latitude": l.latitude,
        "longitude": l.longitude,
        "distance_from_safe_zone_m": l.distance_from_safe_zone_m,
        "within_safe_zone": l.within_safe_zone,
        "is_demo_data": l.is_demo_data,
        "timestamp": l.timestamp.isoformat() if l.timestamp else None,
    }


def safe_zone(s: models.SafeZoneConfig) -> dict:
    return {
        "id": s.id,
        "patient_id": s.patient_id,
        "label": s.label,
        "center_lat": s.center_lat,
        "center_lng": s.center_lng,
        "radius_m": s.radius_m,
        "tracking_enabled": s.tracking_enabled,
        "consented": s.consented,
    }


def safety_alert(a: models.SafetyAlert) -> dict:
    return {
        "id": a.id,
        "patient_id": a.patient_id,
        "alert_type": a.alert_type,
        "severity": _enum_val(a.severity),
        "message_en": a.message_en,
        "message_as": a.message_as,
        "acknowledged": a.acknowledged,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def doctor_authorization(d: models.DoctorAuthorization, doctor: models.Doctor = None,
                          patient: models.Patient = None) -> dict:
    return {
        "id": d.id,
        "patient_id": d.patient_id,
        "doctor_id": d.doctor_id,
        "doctor_name": doctor.user.full_name if doctor and doctor.user else None,
        "hospital_or_clinic": doctor.hospital_or_clinic if doctor else None,
        "patient_name": patient.user.full_name if patient and patient.user else None,
        "status": _enum_val(d.status),
        "scope_cognitive_performance": d.scope_cognitive_performance,
        "scope_activity_history": d.scope_activity_history,
        "scope_reminder_adherence": d.scope_reminder_adherence,
        "scope_location": d.scope_location,
        "scope_wearable_data": d.scope_wearable_data,
        "scope_medical_records": d.scope_medical_records,
        "requested_by": "family" if d.requested_by_family_id else ("caregiver" if d.requested_by_caregiver_id else None),
        "requested_at": d.requested_at.isoformat() if d.requested_at else None,
        "decided_at": d.decided_at.isoformat() if d.decided_at else None,
        "revoked_at": d.revoked_at.isoformat() if d.revoked_at else None,
    }


def medical_record(m: models.MedicalRecord, doctor: models.Doctor = None) -> dict:
    return {
        "id": m.id,
        "appointment_id": m.appointment_id,
        "patient_id": m.patient_id,
        "doctor_id": m.doctor_id,
        "doctor_name": doctor.user.full_name if doctor and doctor.user else None,
        "hospital_or_clinic": doctor.hospital_or_clinic if doctor else None,
        "visit_date": m.visit_date,
        "chief_complaint": m.chief_complaint,
        "diagnosis": m.diagnosis,
        "prescription": m.prescription,
        "vitals_bp": m.vitals_bp,
        "vitals_pulse": m.vitals_pulse,
        "vitals_weight_kg": m.vitals_weight_kg,
        "follow_up_instructions": m.follow_up_instructions,
        "follow_up_date": m.follow_up_date,
        "is_demo_data": m.is_demo_data,
        "created_at": m.created_at.isoformat() if m.created_at else None,
        "updated_at": m.updated_at.isoformat() if m.updated_at else None,
    }


def patient_contact(c: models.PatientContact) -> dict:
    return {
        "id": c.id,
        "patient_id": c.patient_id,
        "name": c.name,
        "relationship_label": c.relationship_label,
        "contact_type": c.contact_type,
        "phone": c.phone,
        "photo_url": c.photo_url,
        "linked_family_member_id": c.linked_family_member_id,
        "linked_caregiver_id": c.linked_caregiver_id,
        "display_order": c.display_order,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def notification(n: models.Notification) -> dict:
    return {
        "id": n.id,
        "title": n.title,
        "body": n.body,
        "category": n.category,
        "read": n.read,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }
