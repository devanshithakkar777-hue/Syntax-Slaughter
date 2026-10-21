"""
Sukoon — Reminder firing & non-response escalation.

Rather than requiring a real background worker/cron process (overkill for a
prototype and hard to demo reliably), escalation is evaluated *lazily*:
every time a patient or caregiver screen is loaded, `sync_reminders_for_patient`
walks each active reminder, ensures today's occurrence exists once it is due,
and escalates it through:

    pending -> (escalation_minutes elapsed, no response) -> gentle follow-up
            -> (escalation_final_minutes elapsed, no response) -> caregiver alert

This keeps behaviour correct regardless of polling cadence and needs no
extra infrastructure, while still faithfully implementing the escalation
workflow described in the spec.
"""
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from . import models
from .notifications import notify_family

# All Reminder.scheduled_time values (e.g. "08:00") are authored as IST wall-clock
# times (this is an India-focused demo), but the server stores/compares everything
# in UTC. Without this offset, a reminder set for 8am IST is only ever considered
# "due" at 8am UTC (1:30pm IST) -- so on a fresh day it can look like nothing is
# ever pending. We convert to IST only for the local wall-clock due-time check;
# everything actually stored (fired_at, the `date` bucket, etc.) stays in UTC so
# it lines up with the rest of the app, which is entirely UTC-based.
IST_OFFSET = timedelta(hours=5, minutes=30)


def _today_str(now: datetime) -> str:
    return now.strftime("%Y-%m-%d")


def _weekday_letter(now: datetime) -> str:
    # Monday=0 ... Sunday=6 -> M T W T F S S
    return "MTWTFSS"[now.weekday()]


def sync_reminders_for_patient(db: Session, patient_id: str, now: datetime = None):
    """Ensure today's reminder occurrences exist and escalate overdue ones.
    Returns list of newly created SafetyAlert objects (for real-time surfacing)."""
    now = now or datetime.utcnow()
    today = _today_str(now)
    weekday = _weekday_letter(now)
    new_alerts = []

    reminders = (
        db.query(models.Reminder)
        .filter(models.Reminder.patient_id == patient_id, models.Reminder.active == True)  # noqa: E712
        .all()
    )

    for rem in reminders:
        if weekday not in (rem.days_of_week or "MTWTFSS"):
            continue

        try:
            sched_h, sched_m = [int(x) for x in rem.scheduled_time.split(":")]
        except Exception:
            continue
        # scheduled_time is an IST wall-clock time -- do the "is it due" check in
        # IST, then convert back to UTC so everything we store/compare elsewhere
        # (fired_at, elapsed_minutes against `now`) stays in UTC.
        local_now = now + IST_OFFSET
        scheduled_local = local_now.replace(hour=sched_h, minute=sched_m, second=0, microsecond=0)
        scheduled_dt = scheduled_local - IST_OFFSET
        if now < scheduled_dt:
            continue  # not due yet today

        occurrence = (
            db.query(models.ReminderResponse)
            .filter(
                models.ReminderResponse.reminder_id == rem.id,
                models.ReminderResponse.date == today,
            )
            .first()
        )
        if occurrence is None:
            occurrence = models.ReminderResponse(
                reminder_id=rem.id,
                patient_id=patient_id,
                date=today,
                fired_at=scheduled_dt,
                status=models.ReminderStatus.pending,
            )
            db.add(occurrence)
            db.flush()

        if occurrence.status in (models.ReminderStatus.completed,):
            continue
        # Medicine reminders wait on two sign-offs (see routers/patient.py and
        # routers/caregiver.py), but once the patient themselves has confirmed
        # taking it, stop escalating -- an outstanding caregiver sign-off is a
        # bookkeeping step, not a "the patient may be in trouble" situation.
        if occurrence.patient_confirmed:
            continue

        elapsed_minutes = (now - scheduled_dt).total_seconds() / 60.0

        if not occurrence.gentle_followup_sent and elapsed_minutes >= rem.escalation_minutes:
            occurrence.gentle_followup_sent = True
            occurrence.gentle_followup_at = now

        if (
            not occurrence.caregiver_alert_sent
            and elapsed_minutes >= rem.escalation_final_minutes
        ):
            occurrence.caregiver_alert_sent = True
            occurrence.caregiver_alert_at = now
            occurrence.status = models.ReminderStatus.escalated

            label = rem.title_en
            alert = models.SafetyAlert(
                patient_id=patient_id,
                alert_type="reminder_nonresponse",
                severity=models.AlertSeverity.warning,
                message_en=f"Patient has not responded to the {rem.scheduled_time} {label} reminder.",
                message_as=f"ৰোগীয়ে {rem.scheduled_time} বজাৰ {rem.title_as or label} ৰিমাইণ্ডাৰত সঁহাৰি দিয়া নাই।",
                related_id=occurrence.id,
            )
            db.add(alert)
            new_alerts.append(alert)
            db.commit()
            # A missed reminder is a "little" update — only family members who
            # opted into every update see it; the safe-zone/alert-resolved/
            # diagnosis events elsewhere are marked important=True instead.
            notify_family(
                db, patient_id, title="Missed reminder",
                body=f"{label} at {rem.scheduled_time} was not responded to.",
                category="reminder", important=False,
            )
        elif occurrence.status == models.ReminderStatus.pending and elapsed_minutes < rem.escalation_final_minutes:
            pass  # still within grace window

    db.commit()
    return new_alerts
