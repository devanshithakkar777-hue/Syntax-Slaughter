import random
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, auth, serializers, access, llm_client
from ..database import get_db
from ..reminders_engine import sync_reminders_for_patient
from ..notifications import notify_family

router = APIRouter(prefix="/api/patient", tags=["patient"])


def _own_patient(db: Session, user: models.User) -> models.Patient:
    if user.role != models.UserRole.patient or not user.patient_profile:
        raise HTTPException(status_code=403, detail="Patient account required")
    return user.patient_profile


def _get_or_create_water_intake(db: Session, patient_id: str, today: str) -> models.WaterIntake:
    row = (
        db.query(models.WaterIntake)
        .filter(models.WaterIntake.patient_id == patient_id, models.WaterIntake.date == today)
        .first()
    )
    if not row:
        row = models.WaterIntake(patient_id=patient_id, date=today, glasses_completed=0)
        db.add(row)
        db.flush()
    return row


def _water_intake_payload(row: models.WaterIntake, target: int) -> dict:
    completed = min(row.glasses_completed, target)
    return {
        "date": row.date,
        "target": target,
        "completed": completed,
        # per-glass checklist state for the UI: "Glass 1 - done", "Glass 2 - pending"...
        "glasses": [{"number": i + 1, "done": i < completed} for i in range(target)],
    }


MEAL_KEYS = ["breakfast", "lunch", "dinner"]
MEAL_LABELS = {
    "breakfast": {"en": "Breakfast", "as": "ৰাতিপুৱাৰ আহাৰ"},
    "lunch": {"en": "Lunch", "as": "দুপৰীয়াৰ আহাৰ"},
    "dinner": {"en": "Dinner", "as": "নৈশ আহাৰ"},
}


def _get_or_create_meal_intake(db: Session, patient_id: str, today: str) -> models.MealIntake:
    row = (
        db.query(models.MealIntake)
        .filter(models.MealIntake.patient_id == patient_id, models.MealIntake.date == today)
        .first()
    )
    if not row:
        row = models.MealIntake(patient_id=patient_id, date=today)
        db.add(row)
        db.flush()
    return row


def _meal_intake_payload(row: models.MealIntake) -> dict:
    return {
        "date": row.date,
        "meals": [
            {
                "key": k,
                "label_en": MEAL_LABELS[k]["en"],
                "label_as": MEAL_LABELS[k]["as"],
                "done": getattr(row, f"{k}_done"),
            }
            for k in MEAL_KEYS
        ],
    }


@router.get("/home")
def home(current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    patient = _own_patient(db, current)
    now = datetime.utcnow()
    today = now.strftime("%Y-%m-%d")

    sync_reminders_for_patient(db, patient.id, now)

    routines = (
        db.query(models.DailyRoutine)
        .filter(models.DailyRoutine.patient_id == patient.id, models.DailyRoutine.active == True)  # noqa: E712
        .order_by(models.DailyRoutine.scheduled_time)
        .all()
    )
    routine_list = []
    completed_count = 0
    for r in routines:
        completion = (
            db.query(models.RoutineCompletion)
            .filter(models.RoutineCompletion.routine_id == r.id, models.RoutineCompletion.date == today)
            .first()
        )
        status_today = completion.status if completion else "pending"
        if status_today == "completed":
            completed_count += 1
        routine_list.append(serializers.routine(r, status_today))

    reminders_today = (
        db.query(models.ReminderResponse, models.Reminder)
        .join(models.Reminder, models.ReminderResponse.reminder_id == models.Reminder.id)
        .filter(models.ReminderResponse.patient_id == patient.id, models.ReminderResponse.date == today)
        .order_by(models.Reminder.scheduled_time)
        .all()
    )
    reminders_serialized = [serializers.reminder_response(rr, rem) for rr, rem in reminders_today]
    next_medicine = next(
        (
            r for r in reminders_serialized
            if r["kind"] == "medicine" and r["status"] in ("pending", "escalated") and not r["patient_confirmed"]
        ),
        None,
    )
    water_row = _get_or_create_water_intake(db, patient.id, today)
    water_target = patient.daily_water_target or 8
    hydration_progress = _water_intake_payload(water_row, water_target)
    meal_row = _get_or_create_meal_intake(db, patient.id, today)
    meals_progress = _meal_intake_payload(meal_row)
    db.commit()

    next_appointment = (
        db.query(models.Appointment)
        .filter(models.Appointment.patient_id == patient.id, models.Appointment.date >= today)
        .order_by(models.Appointment.date, models.Appointment.time)
        .first()
    )

    mood_today = (
        db.query(models.MoodRecord)
        .filter(models.MoodRecord.patient_id == patient.id, models.MoodRecord.date == today)
        .first()
    )

    sessions_today = (
        db.query(models.GameSession)
        .filter(models.GameSession.patient_id == patient.id, models.GameSession.started_at >= now.replace(hour=0, minute=0, second=0, microsecond=0))
        .count()
    )

    return {
        "patient": serializers.patient_summary(patient),
        "greeting_name": patient.user.full_name.split(" ")[0] if patient.user else "",
        "today_routine": routine_list,
        "routine_progress": {"completed": completed_count, "total": len(routine_list)},
        "reminders_today": reminders_serialized,
        "next_medicine": next_medicine,
        "hydration_progress": {
            "completed": hydration_progress["completed"],
            "total": hydration_progress["target"],
        },
        "water_intake": hydration_progress,
        "meals_today": meals_progress,
        "next_appointment": serializers.appointment(next_appointment) if next_appointment else None,
        "mood_today": serializers.mood_record(mood_today) if mood_today else None,
        "cognitive_activity_done_today": sessions_today > 0,
        "current_difficulty_level": patient.current_difficulty_level,
    }


@router.post("/routine/{routine_id}/complete")
def complete_routine(routine_id: str, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    patient = _own_patient(db, current)
    r = db.query(models.DailyRoutine).filter(models.DailyRoutine.id == routine_id, models.DailyRoutine.patient_id == patient.id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Routine item not found")
    today = datetime.utcnow().strftime("%Y-%m-%d")
    completion = (
        db.query(models.RoutineCompletion)
        .filter(models.RoutineCompletion.routine_id == routine_id, models.RoutineCompletion.date == today)
        .first()
    )
    if not completion:
        completion = models.RoutineCompletion(routine_id=routine_id, patient_id=patient.id, date=today)
        db.add(completion)
    completion.status = "completed"
    completion.completed_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


@router.get("/water-intake")
def get_water_intake(current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """Today's hydration checklist: a simple 'glasses drunk today' tally against
    the patient's daily target -- e.g. 'Glass 1 - done, Glass 2 - pending'."""
    patient = _own_patient(db, current)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    row = _get_or_create_water_intake(db, patient.id, today)
    db.commit()
    return _water_intake_payload(row, patient.daily_water_target or 8)


@router.post("/water-intake/log")
def log_water_intake(current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """Marks the next glass as done (i.e. 'Glass N - done')."""
    patient = _own_patient(db, current)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    target = patient.daily_water_target or 8
    row = _get_or_create_water_intake(db, patient.id, today)
    was_complete = row.glasses_completed >= target
    if row.glasses_completed < target:
        row.glasses_completed += 1
    db.commit()
    if not was_complete and row.glasses_completed >= target:
        notify_family(
            db, patient.id, title="Hydration goal reached",
            body=f"{patient.user.full_name if patient.user else 'Patient'} finished all {target} glasses of water today.",
            category="update", important=False,
        )
    return _water_intake_payload(row, target)


@router.post("/water-intake/unlog")
def unlog_water_intake(current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """Undo the most recently logged glass (misclick correction)."""
    patient = _own_patient(db, current)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    target = patient.daily_water_target or 8
    row = _get_or_create_water_intake(db, patient.id, today)
    if row.glasses_completed > 0:
        row.glasses_completed -= 1
    db.commit()
    return _water_intake_payload(row, target)


@router.get("/meals")
def get_meals(current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """Today's food checklist: 'Breakfast - done, Lunch - pending, Dinner - pending'."""
    patient = _own_patient(db, current)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    row = _get_or_create_meal_intake(db, patient.id, today)
    db.commit()
    return _meal_intake_payload(row)


@router.post("/meals/{meal_key}/toggle")
def toggle_meal(meal_key: str, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if meal_key not in MEAL_KEYS:
        raise HTTPException(status_code=404, detail="Unknown meal")
    patient = _own_patient(db, current)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    row = _get_or_create_meal_intake(db, patient.id, today)
    field = f"{meal_key}_done"
    setattr(row, field, not getattr(row, field))
    db.commit()
    if row.breakfast_done and row.lunch_done and row.dinner_done:
        notify_family(
            db, patient.id, title="All meals logged today",
            body=f"{patient.user.full_name if patient.user else 'Patient'} has logged breakfast, lunch and dinner today.",
            category="update", important=False,
        )
    return _meal_intake_payload(row)


def _journal_payload(row: Optional[models.JournalEntry], date: str) -> dict:
    if not row:
        return {"date": date, "text": "", "recorded_via_voice": False, "remembered": None, "has_entry": False}
    return {
        "date": row.date,
        "text": row.text or "",
        "recorded_via_voice": bool(row.recorded_via_voice),
        "remembered": row.remembered,
        "has_entry": bool(row.text and row.text.strip()),
    }


@router.get("/journal/today")
def journal_today(current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    patient = _own_patient(db, current)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    row = db.query(models.JournalEntry).filter(
        models.JournalEntry.patient_id == patient.id, models.JournalEntry.date == today
    ).first()
    return _journal_payload(row, today)


@router.put("/journal/today")
def journal_update_today(payload: schemas.JournalEntryUpdate, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    patient = _own_patient(db, current)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    row = db.query(models.JournalEntry).filter(
        models.JournalEntry.patient_id == patient.id, models.JournalEntry.date == today
    ).first()
    if not row:
        row = models.JournalEntry(patient_id=patient.id, date=today)
        db.add(row)
    row.text = payload.text
    row.recorded_via_voice = payload.recorded_via_voice
    db.commit()
    db.refresh(row)
    return _journal_payload(row, today)


@router.get("/journal/yesterday")
def journal_yesterday(current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    patient = _own_patient(db, current)
    yday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    row = db.query(models.JournalEntry).filter(
        models.JournalEntry.patient_id == patient.id, models.JournalEntry.date == yday
    ).first()
    return _journal_payload(row, yday)


@router.post("/journal/yesterday/recall")
def journal_recall_yesterday(payload: schemas.JournalRecall, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    patient = _own_patient(db, current)
    yday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    row = db.query(models.JournalEntry).filter(
        models.JournalEntry.patient_id == patient.id, models.JournalEntry.date == yday
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="No journal entry for yesterday")
    row.remembered = payload.remembered
    row.reviewed_at = datetime.utcnow()
    db.commit()
    if payload.remembered is False:
        notify_family(
            db, patient.id, title="Memory check-in flagged",
            body=f"{patient.user.full_name if patient.user else 'Patient'} did not recall yesterday's journal entry when reviewing it today.",
            category="update", important=False,
        )
    db.refresh(row)
    return _journal_payload(row, yday)


# --- Companion Chat: lightweight rule-based comfort chat. NOT a real AI/LLM --
# scripted keyword -> canned response, purely to give the patient someone to
# "talk to" when lonely, and to gently redirect to the real Call-for-Comfort
# family feature or a distracting activity when appropriate.
_COMPANION_RULES = [
    (("lonely", "alone", "no one", "nobody"),
     ["I'm sorry you're feeling lonely. I'm here with you. Would you like to call someone in your family? Tap the Family tab and choose a photo — they'll be told right away.",
      "Feeling alone is hard. You're not alone right now — I'm right here. Would talking to a family member help? You can reach them from the Family tab."]),
    (("sad", "upset", "cry", "unhappy", "depressed", "down"),
     ["I'm sorry you're feeling this way. It's okay to feel sad sometimes. Would you like to call a loved one, or shall we try a calming activity together?",
      "That sounds tough. You matter, and your feelings are valid. Would you like me to help you reach your family for a chat?"]),
    (("pain", "hurt", "sick", "unwell", "dizzy", "fall", "fell"),
     ["That sounds concerning. Please use the red Help button so your caregiver is notified right away — I want to make sure you're safe.",
      "I'm not able to help with medical concerns myself. Please press the Help button now so your caregiver knows."]),
    (("bored", "boring", "nothing to do"),
     ["How about a memory game to pass the time? Head to the Cognitive Activities from your home screen — I think you'll enjoy it.",
      "Let's find something fun! There are some simple games in your Activities section."]),
    (("hello", "hi", "hey", "namaste"),
     ["Hello! It's good to hear from you. How are you feeling today?",
      "Hi there! I'm glad you stopped by to chat. How is your day going?"]),
    (("thank", "thanks"),
     ["You're very welcome. I'm always here if you want to talk.",
      "Anytime! Take care of yourself today."]),
    (("miss", "family", "son", "daughter", "husband", "wife", "children"),
     ["It's natural to miss the people you love. Would you like to call them right now? Tap the Family tab and choose their photo.",
      "Thinking of family is a beautiful thing. You can reach out to them anytime from the Family tab."]),
]
_COMPANION_DEFAULT = [
    "I'm here to listen. Tell me more about how you're feeling.",
    "Thank you for sharing that with me. Would you like to talk more, or perhaps call a family member?",
    "I understand. I'm right here with you.",
]


def _companion_reply(text: str, history: list = None) -> str:
    """Safety-critical keyword rules (loneliness, pain/fall, etc.) always win,
    regardless of whether an LLM is configured -- a real model is only ever
    allowed to generate the *soft* conversational fallback reply, never a
    safety-relevant one. See llm_client.py for why."""
    t = (text or "").lower()
    for keywords, replies in _COMPANION_RULES:
        if any(k in t for k in keywords):
            return random.choice(replies)

    if llm_client.llm_enabled():
        convo = ""
        if history:
            convo = "\n".join(f"{'Patient' if m['sender'] == 'patient' else 'You'}: {m['text']}" for m in history[-6:])
        prompt = (f"{convo}\nPatient: {text}\nYou:" if convo else f"Patient: {text}\nYou:")
        llm_reply = llm_client.generate(llm_client.COMPANION_SYSTEM_PROMPT, prompt, max_tokens=150)
        if llm_reply:
            return llm_reply

    return random.choice(_COMPANION_DEFAULT)


@router.get("/companion/history")
def companion_history(current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    patient = _own_patient(db, current)
    rows = (
        db.query(models.CompanionChatMessage)
        .filter(models.CompanionChatMessage.patient_id == patient.id)
        .order_by(models.CompanionChatMessage.created_at.asc())
        .limit(100)
        .all()
    )
    if not rows:
        return {"messages": []}
    return {"messages": [{"sender": r.sender, "text": r.text} for r in rows]}


@router.post("/companion/send")
def companion_send(payload: schemas.CompanionChatSend, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    patient = _own_patient(db, current)
    prior = (
        db.query(models.CompanionChatMessage)
        .filter(models.CompanionChatMessage.patient_id == patient.id)
        .order_by(models.CompanionChatMessage.created_at.desc())
        .limit(6)
        .all()
    )
    history = [{"sender": m.sender, "text": m.text} for m in reversed(prior)]
    user_msg = models.CompanionChatMessage(patient_id=patient.id, sender="patient", text=payload.text)
    db.add(user_msg)
    reply_text = _companion_reply(payload.text, history)
    bot_msg = models.CompanionChatMessage(patient_id=patient.id, sender="bot", text=reply_text)
    db.add(bot_msg)
    db.commit()
    return {"sender": "bot", "text": reply_text}


@router.get("/reminders/today")
def reminders_today(current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    patient = _own_patient(db, current)
    sync_reminders_for_patient(db, patient.id)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    rows = (
        db.query(models.ReminderResponse, models.Reminder)
        .join(models.Reminder, models.ReminderResponse.reminder_id == models.Reminder.id)
        .filter(models.ReminderResponse.patient_id == patient.id, models.ReminderResponse.date == today)
        .order_by(models.Reminder.scheduled_time)
        .all()
    )
    return [serializers.reminder_response(rr, rem) for rr, rem in rows]


@router.post("/reminders/{response_id}/respond")
def respond_reminder(response_id: str, payload: schemas.ReminderRespond,
                      current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    patient = _own_patient(db, current)
    rr = db.query(models.ReminderResponse).filter(
        models.ReminderResponse.id == response_id, models.ReminderResponse.patient_id == patient.id
    ).first()
    if not rr:
        raise HTTPException(status_code=404, detail="Reminder not found")
    rem = db.query(models.Reminder).filter(models.Reminder.id == rr.reminder_id).first()

    if payload.status != "completed":
        rr.status = models.ReminderStatus.snoozed
        rr.responded_at = datetime.utcnow()
        db.commit()
        return serializers.reminder_response(rr, rem)

    if rem and rem.kind == models.ReminderKind.medicine:
        # Dual sign-off: the patient confirming only finishes the job if the
        # caregiver already confirmed their side too (or vice versa, see
        # caregiver.py's confirm_medicine).
        rr.patient_confirmed = True
        rr.patient_confirmed_at = datetime.utcnow()
        if rr.caregiver_confirmed:
            rr.status = models.ReminderStatus.completed
            rr.responded_at = datetime.utcnow()
            db.commit()
            notify_family(
                db, patient.id, title="Medicine taken",
                body=f"{rem.title_en} — confirmed taken by both {patient.user.full_name if patient.user else 'the patient'} and their caregiver.",
                category="medicine", important=False,
            )
        else:
            db.commit()
    else:
        rr.status = models.ReminderStatus.completed
        rr.patient_confirmed = True
        rr.patient_confirmed_at = datetime.utcnow()
        rr.responded_at = datetime.utcnow()
        db.commit()
    return serializers.reminder_response(rr, rem)


@router.get("/appointments")
def appointments(current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    patient = _own_patient(db, current)
    rows = (
        db.query(models.Appointment)
        .filter(models.Appointment.patient_id == patient.id)
        .order_by(models.Appointment.date, models.Appointment.time)
        .all()
    )
    return [serializers.appointment(a) for a in rows]


@router.get("/medical-records")
def medical_records(current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    patient = _own_patient(db, current)
    rows = db.query(models.MedicalRecord).filter(models.MedicalRecord.patient_id == patient.id).order_by(models.MedicalRecord.visit_date.desc()).all()
    out = []
    for r in rows:
        doc = db.query(models.Doctor).filter(models.Doctor.id == r.doctor_id).first()
        out.append(serializers.medical_record(r, doc))
    return out


@router.post("/mood")
def submit_mood(payload: schemas.MoodCreate, current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    patient = _own_patient(db, current)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    existing = (
        db.query(models.MoodRecord)
        .filter(models.MoodRecord.patient_id == patient.id, models.MoodRecord.date == today)
        .first()
    )
    if existing:
        existing.mood = payload.mood
        existing.timestamp = datetime.utcnow()
        db.commit()
        return serializers.mood_record(existing)
    rec = models.MoodRecord(patient_id=patient.id, mood=payload.mood, date=today)
    db.add(rec)
    db.commit()
    notify_family(
        db, patient.id, title="Mood check-in",
        body=f"{patient.user.full_name if patient.user else 'Patient'} checked in feeling: {payload.mood}.",
        category="mood", important=False,
    )
    return serializers.mood_record(rec)


@router.get("/contacts")
def contacts(current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """The patient's own family tree / call list — read-only here by design;
    a caregiver or family member manages who's on it."""
    patient = _own_patient(db, current)
    rows = (
        db.query(models.PatientContact)
        .filter(models.PatientContact.patient_id == patient.id)
        .order_by(models.PatientContact.display_order, models.PatientContact.created_at)
        .all()
    )
    return [serializers.patient_contact(c) for c in rows]


@router.post("/contacts/{contact_id}/call")
def call_contact(contact_id: str, payload: Optional[schemas.PatientContactCall] = None,
                  current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """Records that the patient is calling this contact (the actual dialing
    happens client-side via a tel: link) and lets the people who can help
    know right away, even if they miss the call itself."""
    patient = _own_patient(db, current)
    c = db.query(models.PatientContact).filter(models.PatientContact.id == contact_id, models.PatientContact.patient_id == patient.id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contact not found")

    reason = (payload.reason if payload else None) or "upset"
    patient_name = patient.user.full_name if patient.user else "The patient"

    alert = models.SafetyAlert(
        patient_id=patient.id, alert_type="patient_initiated_call", severity=models.AlertSeverity.warning,
        message_en=f"{patient_name} called {c.name} ({c.relationship_label}) — feeling {reason}.",
        message_as=f"{patient_name}ৰ মন খাৰাপ হোৱাত {c.name}লৈ কল কৰিছে।",
        related_id=c.id,
    )
    db.add(alert)

    notified_user_id = None
    if c.linked_family_member_id:
        fam = db.query(models.FamilyMember).filter(models.FamilyMember.id == c.linked_family_member_id).first()
        if fam:
            notified_user_id = fam.user_id
    elif c.linked_caregiver_id:
        cg = db.query(models.Caregiver).filter(models.Caregiver.id == c.linked_caregiver_id).first()
        if cg:
            notified_user_id = cg.user_id

    if notified_user_id:
        db.add(models.Notification(
            user_id=notified_user_id, title=f"{patient_name} is calling you",
            body=f"They said they're feeling {reason} and are trying to reach you now at their number.",
            category="call",
        ))
    db.commit()
    auth.write_audit_log(db, current.id, "patient.called_contact", "patient_contact", c.id)

    # Anyone who called this contact directly already knows — but the wider
    # family (per their "important updates" preference) should too, in case
    # the specific person they called doesn't pick up.
    notify_family(
        db, patient.id, title="Patient reached out for comfort",
        body=f"{patient_name} called {c.name} ({c.relationship_label}) because they were feeling {reason}.",
        category="alert", important=True,
    )
    return {"ok": True, "phone": c.phone, "name": c.name}


@router.post("/help")
def trigger_help(current: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """Patient-triggered emergency/help action -> notifies all linked caregivers."""
    patient = _own_patient(db, current)
    links = db.query(models.PatientCaregiverRelationship).filter(models.PatientCaregiverRelationship.patient_id == patient.id).all()
    alert = models.SafetyAlert(
        patient_id=patient.id,
        alert_type="help_request",
        severity=models.AlertSeverity.critical,
        message_en=f"{patient.user.full_name} pressed the Help button and may need assistance.",
        message_as=f"{patient.user.full_name}ৰ সহায়ৰ প্ৰয়োজন হ'ব পাৰে।",
    )
    db.add(alert)
    for link in links:
        cg = db.query(models.Caregiver).filter(models.Caregiver.id == link.caregiver_id).first()
        if cg:
            db.add(models.Notification(
                user_id=cg.user_id,
                title="Help requested",
                body=f"{patient.user.full_name} pressed the Help button.",
                category="alert",
            ))
    db.commit()
    auth.write_audit_log(db, current.id, "patient.help_triggered", "patient", patient.id)
    notify_family(
        db, patient.id, title="Help requested",
        body=f"{patient.user.full_name if patient.user else 'Patient'} pressed the Help button and may need assistance.",
        category="alert", important=True,
    )
    return {"ok": True, "message": "Your caregiver has been notified."}
