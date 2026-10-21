"""Sukoon — Agentic AI Care Network (engine layer).

This is the compute layer behind Sukoon's "multi-agent" care architecture.
Five named, specialised agents each watch one slice of the patient's real
data (medicine sign-offs, hydration/meals, wearable+location, cognitive/
companion activity, and cross-cutting safety) and independently decide
whether to raise their status and hand off to the shared Escalation Agent,
which is the single place a family notification actually fires (see
notifications.notify_family). Nothing here calls an external LLM — every
agent is a transparent, explainable rule engine over the patient's own
logged data, which is what a safety-critical eldercare product should be at
prototype stage: reviewable and inspectable, not a black box. Everything
computed here is real (derived from the same rows the rest of the app
writes); only the underlying wearable/location readings are demo-simulated,
and that is flagged per-row via is_demo_data exactly like the rest of Sukoon.
"""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from . import models, llm_client


def _today(db: Session = None) -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


def _day_start():
    return datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)


# ---------------------------------------------------------------------------
# Individual agents
# ---------------------------------------------------------------------------

def _medication_agent(db: Session, patient_id: str, today: str) -> dict:
    rows = (
        db.query(models.ReminderResponse)
        .join(models.Reminder, models.ReminderResponse.reminder_id == models.Reminder.id)
        .filter(models.ReminderResponse.patient_id == patient_id, models.ReminderResponse.date == today,
                models.Reminder.kind == models.ReminderKind.medicine)
        .all()
    )
    total = len(rows)
    done = len([r for r in rows if r.status == models.ReminderStatus.completed and r.patient_confirmed and r.caregiver_confirmed])
    awaiting_cg = len([r for r in rows if r.patient_confirmed and not r.caregiver_confirmed])
    escalated = len([r for r in rows if r.caregiver_alert_sent])
    last = max(rows, key=lambda r: r.fired_at) if rows else None
    if escalated:
        status = "attention"
        summary = f"{escalated} dose(s) escalated to family today — caregiver did not confirm in time."
    elif awaiting_cg:
        status = "watching"
        summary = f"Patient confirmed {awaiting_cg} dose(s); awaiting independent caregiver sign-off."
    elif total and done == total:
        status = "active"
        summary = f"All {total} of today's doses dual-confirmed by patient + caregiver."
    elif total:
        status = "watching"
        summary = f"{done}/{total} doses dual-confirmed so far today."
    else:
        status = "idle"
        summary = "No medicine reminders scheduled today."
    return {
        "key": "medication", "name": "Medication Agent", "icon": "💊",
        "watches": "Dual sign-off medicine adherence",
        "status": status, "summary": summary,
        "last_action_at": last.fired_at.isoformat() if last else None,
        "is_demo_data": False,
    }


def _hydration_agent(db: Session, patient_id: str, today: str) -> dict:
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    target = patient.daily_water_target if patient else 8
    water = db.query(models.WaterIntake).filter(models.WaterIntake.patient_id == patient_id, models.WaterIntake.date == today).first()
    meal = db.query(models.MealIntake).filter(models.MealIntake.patient_id == patient_id, models.MealIntake.date == today).first()
    glasses = water.glasses_completed if water else 0
    meals_done = sum([bool(meal and meal.breakfast_done), bool(meal and meal.lunch_done), bool(meal and meal.dinner_done)])
    hour = datetime.utcnow().hour
    behind_water = hour >= 15 and glasses < max(2, target // 2)
    behind_meals = hour >= 14 and meals_done == 0
    if behind_water or behind_meals:
        status = "attention"
        summary = f"Only {glasses}/{target} glasses and {meals_done}/3 meals logged so far — below pace for this time of day."
    elif glasses >= target and meals_done == 3:
        status = "active"
        summary = f"Hydration and all 3 meals complete for today ({glasses}/{target} glasses)."
    else:
        status = "watching"
        summary = f"{glasses}/{target} glasses, {meals_done}/3 meals logged today."
    return {
        "key": "hydration", "name": "Hydration & Nutrition Agent", "icon": "💧",
        "watches": "Water + meal checklists",
        "status": status, "summary": summary,
        "last_action_at": (water.updated_at.isoformat() if water else (meal.updated_at.isoformat() if meal else None)),
        "is_demo_data": False,
    }


def _vitals_agent(db: Session, patient_id: str) -> dict:
    w = db.query(models.WearableData).filter(models.WearableData.patient_id == patient_id).order_by(models.WearableData.timestamp.desc()).first()
    loc = db.query(models.LocationData).filter(models.LocationData.patient_id == patient_id).order_by(models.LocationData.timestamp.desc()).first()
    flags = []
    status = "active"
    if w and w.heart_rate_bpm and (w.heart_rate_bpm > 110 or w.heart_rate_bpm < 45):
        flags.append(f"heart rate {w.heart_rate_bpm} bpm is outside the resting range")
        status = "attention"
    if loc and not loc.within_safe_zone:
        flags.append(f"currently {int(loc.distance_from_safe_zone_m)}m outside the safe zone")
        status = "attention"
    if not w and not loc:
        summary = "No SafeTag Tracker readings yet — pair the device to activate this agent."
        status = "idle"
    elif flags:
        summary = "SafeTag Tracker flagged: " + "; ".join(flags) + "."
    else:
        bits = []
        if w:
            bits.append(f"HR {w.heart_rate_bpm} bpm, {w.steps} steps, battery {w.battery_pct}%")
        if loc:
            bits.append("within safe zone" if loc.within_safe_zone else "outside safe zone")
        summary = "SafeTag Tracker nominal — " + ", ".join(bits) + "."
    return {
        "key": "vitals", "name": "Vitals & SafeTag Agent", "icon": "📍",
        "watches": "Wearable vitals + geofence via the SafeTag Tracker",
        "status": status, "summary": summary,
        "last_action_at": (w.timestamp.isoformat() if w else (loc.timestamp.isoformat() if loc else None)),
        "is_demo_data": True,
    }


def _companion_agent(db: Session, patient_id: str, today: str) -> dict:
    yday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    j_today = db.query(models.JournalEntry).filter(models.JournalEntry.patient_id == patient_id, models.JournalEntry.date == today).first()
    j_yday = db.query(models.JournalEntry).filter(models.JournalEntry.patient_id == patient_id, models.JournalEntry.date == yday).first()
    chats_today = db.query(models.CompanionChatMessage).filter(
        models.CompanionChatMessage.patient_id == patient_id,
        models.CompanionChatMessage.sender == "patient",
        models.CompanionChatMessage.created_at >= _day_start(),
    ).count()
    mood = db.query(models.MoodRecord).filter(models.MoodRecord.patient_id == patient_id, models.MoodRecord.date == today).first()
    status = "active"
    notes = []
    if j_yday is not None and j_yday.remembered is False:
        status = "attention"
        notes.append("did not recall yesterday on the journal recall check")
    if mood and mood.mood == "sad":
        status = "attention"
        notes.append("logged mood as low today")
    notes.append(f"{chats_today} companion chat message(s) today")
    notes.append("journal " + ("written" if j_today and j_today.text else "not yet written") + " today")
    summary = "; ".join(notes).capitalize() + "."
    return {
        "key": "companion", "name": "Cognitive & Companion Agent", "icon": "🧠",
        "watches": "Journal recall, mood check-ins, companion chat",
        "status": status, "summary": summary,
        "last_action_at": (j_today.updated_at.isoformat() if j_today else None),
        "is_demo_data": False,
    }


def _escalation_agent(db: Session, patient_id: str, today: str, other_agents: list) -> dict:
    open_alerts = db.query(models.SafetyAlert).filter(models.SafetyAlert.patient_id == patient_id, models.SafetyAlert.acknowledged == False).count()  # noqa: E712
    attention_count = len([a for a in other_agents if a["status"] == "attention"])
    if open_alerts or attention_count >= 2:
        status = "attention"
        summary = f"{open_alerts} open safety alert(s); coordinating {attention_count} agent(s) currently flagging concern."
    elif attention_count == 1:
        status = "watching"
        summary = "One agent is flagging a concern; monitoring before notifying family."
    else:
        status = "active"
        summary = "All agents nominal — no escalation needed right now."
    return {
        "key": "escalation", "name": "Safety & Escalation Agent", "icon": "🚨",
        "watches": "Cross-agent coordination + family notification decisions",
        "status": status, "summary": summary,
        "last_action_at": None,
        "is_demo_data": False,
    }


def compute_agent_statuses(db: Session, patient_id: str) -> list:
    today = _today()
    agents = [
        _medication_agent(db, patient_id, today),
        _hydration_agent(db, patient_id, today),
        _vitals_agent(db, patient_id),
        _companion_agent(db, patient_id, today),
    ]
    agents.append(_escalation_agent(db, patient_id, today, agents))
    return agents


# ---------------------------------------------------------------------------
# Risk score
# ---------------------------------------------------------------------------

def compute_risk_score(db: Session, patient_id: str) -> dict:
    today = _today()
    yday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    score = 0
    factors = []

    med_rows = (
        db.query(models.ReminderResponse)
        .join(models.Reminder, models.ReminderResponse.reminder_id == models.Reminder.id)
        .filter(models.ReminderResponse.patient_id == patient_id, models.ReminderResponse.date == today,
                models.Reminder.kind == models.ReminderKind.medicine)
        .all()
    )
    missed = len([r for r in med_rows if r.status == models.ReminderStatus.missed or r.caregiver_alert_sent])
    if missed:
        score += 25 * missed
        factors.append(f"{missed} medicine dose(s) missed or escalated today")

    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    target = patient.daily_water_target if patient else 8
    water = db.query(models.WaterIntake).filter(models.WaterIntake.patient_id == patient_id, models.WaterIntake.date == today).first()
    glasses = water.glasses_completed if water else 0
    hour = datetime.utcnow().hour
    if hour >= 16 and glasses < target * 0.5:
        score += 15
        factors.append("hydration behind pace for this time of day")

    meal = db.query(models.MealIntake).filter(models.MealIntake.patient_id == patient_id, models.MealIntake.date == today).first()
    if hour >= 15 and not (meal and meal.breakfast_done and meal.lunch_done):
        score += 10
        factors.append("meals behind pace for this time of day")

    mood = db.query(models.MoodRecord).filter(models.MoodRecord.patient_id == patient_id, models.MoodRecord.date == today).first()
    if mood and mood.mood == "sad":
        score += 15
        factors.append("mood logged as low today")

    j_yday = db.query(models.JournalEntry).filter(models.JournalEntry.patient_id == patient_id, models.JournalEntry.date == yday).first()
    if j_yday is not None and j_yday.remembered is False:
        score += 15
        factors.append("did not recall yesterday during the journal recall check")

    loc = db.query(models.LocationData).filter(models.LocationData.patient_id == patient_id).order_by(models.LocationData.timestamp.desc()).first()
    if loc and not loc.within_safe_zone:
        score += 20
        factors.append("outside the configured safe zone")

    open_alerts = db.query(models.SafetyAlert).filter(models.SafetyAlert.patient_id == patient_id, models.SafetyAlert.acknowledged == False).count()  # noqa: E712
    if open_alerts:
        score += 10 * open_alerts
        factors.append(f"{open_alerts} unacknowledged safety alert(s)")

    score = max(0, min(100, score))
    if score >= 61:
        band, label = "high", "Needs attention"
    elif score >= 31:
        band, label = "medium", "Monitor"
    else:
        band, label = "low", "Stable"
    if not factors:
        factors.append("No concerning signals detected across any agent today.")

    return {"score": score, "band": band, "label": label, "factors": factors}


# ---------------------------------------------------------------------------
# Escalation log (derived, not a new table)
# ---------------------------------------------------------------------------

def compute_escalation_log(db: Session, patient_id: str, limit: int = 15) -> list:
    events = []

    med_rows = (
        db.query(models.ReminderResponse)
        .join(models.Reminder, models.ReminderResponse.reminder_id == models.Reminder.id)
        .filter(models.ReminderResponse.patient_id == patient_id, models.ReminderResponse.caregiver_alert_sent == True)  # noqa: E712
        .all()
    )
    for r in med_rows:
        rem = db.query(models.Reminder).filter(models.Reminder.id == r.reminder_id).first()
        events.append({
            "agent": "Medication Agent", "icon": "💊",
            "reason": f"'{rem.title_en if rem else 'Medicine'}' not confirmed within the escalation window",
            "action": "Notified family", "at": (r.caregiver_alert_at or r.fired_at).isoformat(),
        })

    alerts = db.query(models.SafetyAlert).filter(models.SafetyAlert.patient_id == patient_id).order_by(models.SafetyAlert.created_at.desc()).limit(20).all()
    for a in alerts:
        events.append({
            "agent": "Safety & Escalation Agent", "icon": "🚨",
            "reason": a.message_en, "action": "Safety alert raised" + (" (acknowledged)" if a.acknowledged else ""),
            "at": a.created_at.isoformat(),
        })

    journals = db.query(models.JournalEntry).filter(models.JournalEntry.patient_id == patient_id, models.JournalEntry.remembered == False).order_by(models.JournalEntry.reviewed_at.desc()).limit(10).all()  # noqa: E712
    for j in journals:
        events.append({
            "agent": "Cognitive & Companion Agent", "icon": "🧠",
            "reason": f"Patient did not recall {j.date} during the next-day check",
            "action": "Notified family", "at": (j.reviewed_at or j.updated_at).isoformat(),
        })

    events.sort(key=lambda e: e["at"], reverse=True)
    return events[:limit]


# ---------------------------------------------------------------------------
# Unified cross-role care timeline
# ---------------------------------------------------------------------------

def compute_care_timeline(db: Session, patient_id: str, limit: int = 25) -> list:
    items = []

    resp = (
        db.query(models.ReminderResponse)
        .join(models.Reminder, models.ReminderResponse.reminder_id == models.Reminder.id)
        .filter(models.ReminderResponse.patient_id == patient_id, models.ReminderResponse.status == models.ReminderStatus.completed)
        .order_by(models.ReminderResponse.responded_at.desc())
        .limit(15)
        .all()
    )
    for r in resp:
        rem = db.query(models.Reminder).filter(models.Reminder.id == r.reminder_id).first()
        if not r.responded_at:
            continue
        items.append({"icon": "✅", "label": f"{rem.title_en if rem else r.reminder_id} completed", "at": r.responded_at.isoformat(), "source": "Medication/Hydration Agent"})

    moods = db.query(models.MoodRecord).filter(models.MoodRecord.patient_id == patient_id).order_by(models.MoodRecord.timestamp.desc()).limit(10).all()
    for m in moods:
        items.append({"icon": "🙂", "label": f"Mood check-in: {m.mood}", "at": m.timestamp.isoformat(), "source": "Companion Agent"})

    journals = db.query(models.JournalEntry).filter(models.JournalEntry.patient_id == patient_id).order_by(models.JournalEntry.created_at.desc()).limit(10).all()
    for j in journals:
        items.append({"icon": "📓", "label": f"Journal entry written for {j.date}", "at": j.created_at.isoformat(), "source": "Companion Agent"})

    games = db.query(models.GameSession).filter(models.GameSession.patient_id == patient_id, models.GameSession.completed_at.isnot(None)).order_by(models.GameSession.completed_at.desc()).limit(10).all()
    for g in games:
        items.append({"icon": "🎯", "label": f"Cognitive activity '{g.activity_code}' completed", "at": g.completed_at.isoformat(), "source": "Companion Agent"})

    locs = db.query(models.LocationData).filter(models.LocationData.patient_id == patient_id).order_by(models.LocationData.timestamp.desc()).limit(5).all()
    for l in locs:
        items.append({"icon": "📍", "label": "Within safe zone" if l.within_safe_zone else "Left safe zone", "at": l.timestamp.isoformat(), "source": "Vitals & SafeTag Agent"})

    items.sort(key=lambda e: e["at"], reverse=True)
    return items[:limit]


def build_overview(db: Session, patient_id: str) -> dict:
    agents = compute_agent_statuses(db, patient_id)
    return {
        "agents": agents,
        "risk": compute_risk_score(db, patient_id),
        "escalations": compute_escalation_log(db, patient_id),
        "timeline": compute_care_timeline(db, patient_id),
        "daily_briefing": compute_daily_briefing(db, patient_id),
        "cognitive_anomaly": compute_cognitive_anomaly(db, patient_id),
        "family_engagement": compute_family_engagement(db, patient_id),
        "adaptive_timing": compute_adaptive_timing(db, patient_id),
        "medication_safety": compute_medication_safety(db, patient_id),
        "clinical_brief": compute_clinical_brief(db, patient_id),
        "llm_enabled": llm_client.llm_enabled(),
    }


# ---------------------------------------------------------------------------
# 1. Clinical Insight Agent (doctor pre-visit briefing) -- LLM-ready
# ---------------------------------------------------------------------------

def compute_clinical_brief(db: Session, patient_id: str) -> dict:
    since30 = datetime.utcnow() - timedelta(days=30)
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    perf = db.query(models.PerformanceRecord).filter(models.PerformanceRecord.patient_id == patient_id, models.PerformanceRecord.timestamp >= since30).all()
    med_rows = (
        db.query(models.ReminderResponse)
        .join(models.Reminder, models.ReminderResponse.reminder_id == models.Reminder.id)
        .filter(models.ReminderResponse.patient_id == patient_id, models.ReminderResponse.fired_at >= since30,
                models.Reminder.kind == models.ReminderKind.medicine)
        .all()
    )
    moods = db.query(models.MoodRecord).filter(models.MoodRecord.patient_id == patient_id, models.MoodRecord.timestamp >= since30).all()
    escalations = len(compute_escalation_log(db, patient_id, limit=100))

    avg_score = round(sum(p.score for p in perf) / len(perf), 1) if perf else None
    med_total = len(med_rows)
    med_done = len([r for r in med_rows if r.status == models.ReminderStatus.completed])
    mood_counts = {}
    for m in moods:
        mood_counts[m.mood] = mood_counts.get(m.mood, 0) + 1
    top_mood = max(mood_counts, key=mood_counts.get) if mood_counts else None

    facts = {
        "patient_name": patient.user.full_name if patient and patient.user else "Patient",
        "age": patient.age if patient else None,
        "avg_cognitive_score_30d": avg_score,
        "sessions_30d": len(perf),
        "medicine_adherence": f"{med_done}/{med_total}" if med_total else "no medicine reminders in this period",
        "most_common_mood_30d": top_mood,
        "escalations_30d": escalations,
    }

    if llm_client.llm_enabled():
        prompt = "Patient data (last 30 days):\n" + "\n".join(f"- {k}: {v}" for k, v in facts.items())
        llm_text = llm_client.generate(llm_client.CLINICAL_BRIEF_SYSTEM_PROMPT, prompt, max_tokens=220)
        if llm_text:
            return {"text": llm_text, "source": "llm", "facts": facts}

    # Deterministic fallback (also the default when no LLM key is configured)
    bits = [f"{facts['patient_name']}" + (f" ({facts['age']}y)" if facts['age'] else "") + " — last 30 days:"]
    if avg_score is not None:
        bits.append(f"average cognitive activity score {avg_score}/100 across {len(perf)} session(s).")
    else:
        bits.append("no cognitive activity sessions logged.")
    bits.append(f"Medicine adherence {facts['medicine_adherence']}.")
    if top_mood:
        bits.append(f"Most frequently logged mood: {top_mood}.")
    if escalations:
        bits.append(f"{escalations} safety escalation(s) raised in this period.")
    else:
        bits.append("No safety escalations raised.")
    return {"text": " ".join(bits), "source": "rule_based", "facts": facts}


# ---------------------------------------------------------------------------
# 2. Daily Care Briefing
# ---------------------------------------------------------------------------

def compute_daily_briefing(db: Session, patient_id: str) -> dict:
    agents = compute_agent_statuses(db, patient_id)
    risk = compute_risk_score(db, patient_id)
    patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
    name = patient.user.full_name if patient and patient.user else "Patient"
    concerning = [a for a in agents if a["status"] == "attention"]
    if concerning:
        headline = f"{name}: {len(concerning)} area(s) need attention today — " + "; ".join(a["name"] for a in concerning) + "."
    else:
        headline = f"{name} is doing well today — every care agent reports normal status."
    return {"text": headline, "risk_score": risk["score"], "risk_band": risk["band"], "generated_at": datetime.utcnow().isoformat()}


# ---------------------------------------------------------------------------
# 3. "Ask Sukoon" natural-language query (rule-based intent matching)
# ---------------------------------------------------------------------------

def answer_query(db: Session, patient_id: str, text: str) -> str:
    t = (text or "").lower()
    today = _today()

    if any(k in t for k in ["medicine", "medication", "dose", "pill"]):
        rows = (
            db.query(models.ReminderResponse)
            .join(models.Reminder, models.ReminderResponse.reminder_id == models.Reminder.id)
            .filter(models.ReminderResponse.patient_id == patient_id, models.ReminderResponse.date == today,
                    models.Reminder.kind == models.ReminderKind.medicine)
            .all()
        )
        if not rows:
            return "No medicine reminders are scheduled for today."
        done = [r for r in rows if r.status == models.ReminderStatus.completed and r.patient_confirmed and r.caregiver_confirmed]
        return f"{len(done)} of {len(rows)} medicine dose(s) confirmed today (patient + caregiver dual sign-off)."

    if any(k in t for k in ["water", "hydrat", "drink"]):
        w = db.query(models.WaterIntake).filter(models.WaterIntake.patient_id == patient_id, models.WaterIntake.date == today).first()
        patient = db.query(models.Patient).filter(models.Patient.id == patient_id).first()
        target = patient.daily_water_target if patient else 8
        return f"{w.glasses_completed if w else 0} of {target} glasses of water logged today."

    if any(k in t for k in ["meal", "food", "eat", "breakfast", "lunch", "dinner"]):
        m = db.query(models.MealIntake).filter(models.MealIntake.patient_id == patient_id, models.MealIntake.date == today).first()
        if not m:
            return "No meals logged yet today."
        done = [n for n, v in [("breakfast", m.breakfast_done), ("lunch", m.lunch_done), ("dinner", m.dinner_done)] if v]
        return f"Meals logged today: {', '.join(done) if done else 'none yet'}."

    if any(k in t for k in ["mood", "feeling", "happy", "sad"]):
        mood = db.query(models.MoodRecord).filter(models.MoodRecord.patient_id == patient_id, models.MoodRecord.date == today).first()
        return f"Today's mood check-in: {mood.mood}." if mood else "No mood check-in logged yet today."

    if any(k in t for k in ["appointment", "doctor visit", "next visit"]):
        appt = (
            db.query(models.Appointment)
            .filter(models.Appointment.patient_id == patient_id, models.Appointment.date >= today)
            .order_by(models.Appointment.date.asc(), models.Appointment.time.asc())
            .first()
        )
        return (f"Next appointment: {appt.date} at {appt.time} with {appt.doctor_name}."
                if appt else "No upcoming appointments scheduled.")

    if any(k in t for k in ["safe zone", "location", "where is", "safetag"]):
        loc = db.query(models.LocationData).filter(models.LocationData.patient_id == patient_id).order_by(models.LocationData.timestamp.desc()).first()
        if not loc:
            return "No SafeTag Tracker location data yet."
        return ("Within the configured safe zone." if loc.within_safe_zone
                else f"Outside the safe zone — {int(loc.distance_from_safe_zone_m)}m away.") + " (Demo data)"

    if any(k in t for k in ["risk", "how is", "how's", "status", "overview"]):
        risk = compute_risk_score(db, patient_id)
        return f"Wellness risk score: {risk['score']}/100 ({risk['label']}). " + "; ".join(risk["factors"][:2]) + "."

    if any(k in t for k in ["journal", "remember", "recall"]):
        yday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
        j = db.query(models.JournalEntry).filter(models.JournalEntry.patient_id == patient_id, models.JournalEntry.date == yday).first()
        if not j:
            return "No journal entry was written yesterday."
        if j.remembered is None:
            return "Yesterday's journal entry hasn't been reviewed for recall yet."
        return "Patient recalled yesterday correctly." if j.remembered else "Patient did not recall yesterday during the recall check — family was notified."

    return ("I can answer questions about medicine, water, meals, mood, appointments, location/safe zone, "
            "journal recall, or overall risk status — try asking about one of those.")


# ---------------------------------------------------------------------------
# 4. Multi-patient triage (caregiver/doctor with several patients)
# ---------------------------------------------------------------------------

def compute_triage(db: Session, patients: list) -> list:
    """patients: list of (patient_id, full_name) tuples. Returns risk-sorted list."""
    out = []
    for pid, name in patients:
        risk = compute_risk_score(db, pid)
        open_esc = len(compute_escalation_log(db, pid, limit=5))
        out.append({"patient_id": pid, "name": name, "risk_score": risk["score"], "risk_band": risk["band"], "risk_label": risk["label"], "recent_escalations": open_esc})
    out.sort(key=lambda r: r["risk_score"], reverse=True)
    return out


# ---------------------------------------------------------------------------
# 5. Family Engagement Agent
# ---------------------------------------------------------------------------

def compute_family_engagement(db: Session, patient_id: str) -> list:
    links = db.query(models.PatientFamilyRelationship).filter(models.PatientFamilyRelationship.patient_id == patient_id).all()
    out = []
    now = datetime.utcnow()
    for link in links:
        fam = db.query(models.FamilyMember).filter(models.FamilyMember.id == link.family_member_id).first()
        if not fam or not fam.user:
            continue
        last_login = fam.user.last_login_at
        days_since = (now - last_login).days if last_login else None
        if days_since is None:
            status, note = "attention", "Has never signed in yet."
        elif days_since >= 5:
            status, note = "attention", f"Hasn't checked in for {days_since} day(s)."
        elif days_since >= 2:
            status, note = "watching", f"Last checked in {days_since} day(s) ago."
        else:
            status, note = "active", "Checked in recently."
        out.append({
            "name": fam.user.full_name, "relationship": fam.relationship_to_patient,
            "last_login_at": last_login.isoformat() if last_login else None,
            "days_since": days_since, "status": status, "note": note,
        })
    return out


# ---------------------------------------------------------------------------
# 6. Adaptive Reminder Timing Agent
# ---------------------------------------------------------------------------

def compute_adaptive_timing(db: Session, patient_id: str) -> list:
    since14 = datetime.utcnow() - timedelta(days=14)
    reminders = db.query(models.Reminder).filter(models.Reminder.patient_id == patient_id, models.Reminder.active == True).all()  # noqa: E712
    out = []
    for rem in reminders:
        rows = (
            db.query(models.ReminderResponse)
            .filter(models.ReminderResponse.reminder_id == rem.id, models.ReminderResponse.fired_at >= since14,
                    models.ReminderResponse.responded_at.isnot(None))
            .all()
        )
        if len(rows) < 2:
            continue
        latencies = [(r.responded_at - r.fired_at).total_seconds() / 60.0 for r in rows if r.responded_at and r.fired_at]
        if not latencies:
            continue
        avg_latency = sum(latencies) / len(latencies)
        if avg_latency > 20:
            out.append({
                "reminder_id": rem.id, "title": rem.title_en, "scheduled_time": rem.scheduled_time,
                "avg_response_minutes": round(avg_latency, 1),
                "suggestion": f"'{rem.title_en}' averages a {round(avg_latency)}-minute response over the last {len(rows)} occurrence(s) — consider moving it earlier or pairing it with a routine the patient already responds to quickly.",
            })
    return out


# ---------------------------------------------------------------------------
# 7. Medication Safety-Check Agent (reference-only, not clinical advice)
# ---------------------------------------------------------------------------

_KNOWN_INTERACTIONS = [
    (("warfarin",), ("aspirin", "ibuprofen"), "Combined use may increase bleeding risk — pharmacist/doctor review advised."),
    (("amlodipine",), ("simvastatin",), "May increase simvastatin levels — dose-limit caution is commonly advised."),
    (("metformin",), ("contrast dye", "iodinated contrast"), "Common precaution: hold metformin around contrast-imaging procedures."),
    (("ace inhibitor", "lisinopril", "enalapril"), ("potassium", "spironolactone"), "May raise potassium levels — periodic monitoring commonly advised."),
    (("donepezil",), ("anticholinergic",), "Anticholinergic drugs may counteract donepezil's intended effect."),
]


def compute_medication_safety(db: Session, patient_id: str) -> dict:
    """Extracts drug-name-ish keywords from prescriptions + medicine reminder
    titles and cross-checks against a small curated reference list. This is a
    demo reference check, not a substitute for pharmacist/clinical review."""
    names = set()
    records = db.query(models.MedicalRecord).filter(models.MedicalRecord.patient_id == patient_id).all()
    for r in records:
        if r.prescription:
            names.add(r.prescription.lower())
    reminders = db.query(models.Reminder).filter(models.Reminder.patient_id == patient_id, models.Reminder.kind == models.ReminderKind.medicine).all()
    for rem in reminders:
        names.add((rem.title_en or "").lower())
        if rem.detail:
            names.add(rem.detail.lower())

    blob = " ".join(names)
    flags = []
    for group_a, group_b, note in _KNOWN_INTERACTIONS:
        a_hit = any(a in blob for a in group_a)
        b_hit = any(b in blob for b in group_b)
        if a_hit and b_hit:
            flags.append({"drugs": list(group_a) + list(group_b), "note": note})

    return {"checked": True, "flags": flags, "disclaimer": "Reference check against a small curated list — not a substitute for pharmacist or clinical review."}


# ---------------------------------------------------------------------------
# 8. Cognitive trend anomaly detector
# ---------------------------------------------------------------------------

def compute_cognitive_anomaly(db: Session, patient_id: str) -> dict:
    since14 = datetime.utcnow() - timedelta(days=14)
    rows = (
        db.query(models.PerformanceRecord)
        .filter(models.PerformanceRecord.patient_id == patient_id, models.PerformanceRecord.timestamp >= since14)
        .order_by(models.PerformanceRecord.timestamp.asc())
        .all()
    )
    if len(rows) < 4:
        return {"flagged": False, "message": "Not enough recent sessions to detect a trend yet."}
    baseline = rows[:-2]
    recent = rows[-2:]
    baseline_avg = sum(r.score for r in baseline) / len(baseline)
    recent_avg = sum(r.score for r in recent) / len(recent)
    if baseline_avg <= 0:
        return {"flagged": False, "message": "Not enough baseline data yet."}
    drop_pct = round((baseline_avg - recent_avg) / baseline_avg * 100, 1)
    if drop_pct >= 20:
        return {"flagged": True, "drop_pct": drop_pct, "message": f"Cognitive score dropped {drop_pct}% in the last 2 sessions vs. the prior 14-day average ({round(baseline_avg)} → {round(recent_avg)}) — may be worth a doctor's review."}
    return {"flagged": False, "drop_pct": drop_pct, "message": "No significant change in cognitive performance trend."}
