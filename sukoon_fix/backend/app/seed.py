"""
Sukoon — Demo data seeding.

Creates three demo login accounts (patient / caregiver / doctor) plus two
weeks of realistic, clearly-flagged demo history so a judge can open any
dashboard and immediately see trends, not an empty app. Safe to re-run:
it wipes and recreates the sukoon.db file first.

Run:  python -m app.seed
"""
import os
import random
from datetime import datetime, timedelta

from .database import Base, engine, SessionLocal
from . import models, auth

random.seed(42)

DEMO_PASSWORD_PATIENT = "Patient@123"
DEMO_PASSWORD_CAREGIVER = "Caregiver@123"
DEMO_PASSWORD_DOCTOR = "Doctor@123"
DEMO_PASSWORD_FAMILY = "Family@123"

ACTIVITIES = [
    dict(code="memory_matching", name_en="Memory Matching", name_as="স্মৃতি মিলোৱা", domain="memory",
         description_en="Shown a few familiar objects, then asked to recall which were shown.",
         description_as="কেইটামান পৰিচিত বস্তু দেখুওৱাৰ পিছত সেইবোৰ মনত ৰখা।"),
    dict(code="pattern_recognition", name_en="Pattern Recognition", name_as="আকৃতি চিনাক্তকৰণ", domain="attention",
         description_en="Shown a short sequence and asked to pick what comes next.",
         description_as="এটা সৰু ক্ৰম দেখুওৱাৰ পিছত পৰৱৰ্তী বস্তুটো বাছি উলিওৱা।"),
    dict(code="object_recognition", name_en="Object Recognition", name_as="বস্তু চিনাক্তকৰণ", domain="recognition",
         description_en="Simple recognition questions about familiar everyday objects.",
         description_as="পৰিচিত দৈনন্দিন বস্তুৰ বিষয়ে সহজ প্ৰশ্ন।"),
    dict(code="routine_recall", name_en="Daily Routine Recall", name_as="দৈনন্দিন কাৰ্যসূচী স্মৰণ", domain="engagement",
         description_en="Simple multiple-choice questions about the patient's own configured routine.",
         description_as="ৰোগীৰ নিজৰ দৈনন্দিন কাৰ্যসূচীৰ বিষয়ে সহজ প্ৰশ্ন।"),
]

GUWAHATI_LAT, GUWAHATI_LNG = 26.1445, 91.7362


def wipe_db():
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sukoon.db")
    if os.path.exists(db_path):
        os.remove(db_path)
    Base.metadata.create_all(bind=engine)


def run():
    wipe_db()
    db = SessionLocal()
    try:
        # --- Activity catalog ------------------------------------------------
        for a in ACTIVITIES:
            db.add(models.CognitiveActivity(**a))
        db.commit()

        # --- Users -------------------------------------------------------------
        patient_user = models.User(
            email="patient@sukoon.demo", password_hash=auth.hash_password(DEMO_PASSWORD_PATIENT),
            role=models.UserRole.patient, full_name="Renu Bora", preferred_language="en", is_demo=True,
        )
        caregiver_user = models.User(
            email="caregiver@sukoon.demo", password_hash=auth.hash_password(DEMO_PASSWORD_CAREGIVER),
            role=models.UserRole.caregiver, full_name="Priya Bora", preferred_language="en", is_demo=True,
        )
        doctor_user = models.User(
            email="doctor@sukoon.demo", password_hash=auth.hash_password(DEMO_PASSWORD_DOCTOR),
            role=models.UserRole.doctor, full_name="Dr. Anjali Sharma", preferred_language="en", is_demo=True,
        )
        family_user = models.User(
            email="family@sukoon.demo", password_hash=auth.hash_password(DEMO_PASSWORD_FAMILY),
            role=models.UserRole.family, full_name="Rajiv Bora", preferred_language="en", is_demo=True,
        )
        db.add_all([patient_user, caregiver_user, doctor_user, family_user])
        db.flush()

        patient = models.Patient(
            user_id=patient_user.id, age=72, gender="Female",
            condition_notes="Mild cognitive impairment (demo profile) — for prototype demonstration only.",
            home_region="Guwahati, Assam", current_difficulty_level=2, phone="+91 98640 22222",
        )
        caregiver = models.Caregiver(user_id=caregiver_user.id, relationship_to_patient="Daughter", phone="+91 98640 00000")
        doctor = models.Doctor(user_id=doctor_user.id, hospital_or_clinic="Guwahati Medical College Hospital",
                                specialization="Geriatric Medicine", registration_id="AMC/GMC/2014/00321")
        family = models.FamilyMember(user_id=family_user.id, relationship_to_patient="Son", phone="+91 98640 11111",
                                      notification_preference="all")
        db.add_all([patient, caregiver, doctor, family])
        db.flush()

        db.add(models.PatientCaregiverRelationship(patient_id=patient.id, caregiver_id=caregiver.id, is_primary=True))
        db.add(models.PatientFamilyRelationship(patient_id=patient.id, family_member_id=family.id))

        # --- Doctor authorization (pre-approved so the Doctor login has data on
        #     first look; the family dashboard can still demo requesting a
        #     *second* doctor live) --------------------------------------------
        authz = models.DoctorAuthorization(
            patient_id=patient.id, doctor_id=doctor.id, requested_by_family_id=family.id,
            status=models.AuthorizationStatus.approved,
            scope_cognitive_performance=True, scope_activity_history=True, scope_reminder_adherence=True,
            scope_location=False, scope_wearable_data=True, scope_medical_records=True,
            requested_at=datetime.utcnow() - timedelta(days=10), decided_at=datetime.utcnow() - timedelta(days=10),
        )
        db.add(authz)
        db.add(models.ConsentRecord(patient_id=patient.id, granted_by_user_id=family_user.id,
                                     category="doctor_access", granted=True, notes="Demo seed: pre-approved"))

        # --- Daily routine (culturally grounded for Assam/NER) ----------------
        routines = [
            dict(period="morning", title_en="Morning tea and jolpan (breakfast)", title_as="ৰাতিপুৱাৰ চাহ আৰু জলপান", scheduled_time="07:30"),
            dict(period="morning", title_en="Cognitive activity time", title_as="জ্ঞানমূলক কাৰ্যকলাপৰ সময়", scheduled_time="09:30"),
            dict(period="afternoon", title_en="Lunch and rest", title_as="দুপৰীয়াৰ আহাৰ আৰু জিৰণি", scheduled_time="13:00"),
            dict(period="afternoon", title_en="Tea with neighbours", title_as="চুবুৰীয়াৰ সৈতে চাহ", scheduled_time="16:00", is_custom=True),
            dict(period="evening", title_en="Naam-prasanga (evening prayer)", title_as="সন্ধিয়া নাম-প্ৰসংগ", scheduled_time="18:30"),
            dict(period="evening", title_en="Dinner", title_as="নৈশ আহাৰ", scheduled_time="20:00"),
        ]
        for r in routines:
            db.add(models.DailyRoutine(patient_id=patient.id, created_by_caregiver_id=caregiver.id, **r))

        # --- Reminders ----------------------------------------------------------
        reminders = [
            models.Reminder(patient_id=patient.id, kind=models.ReminderKind.medicine,
                             title_en="Blood pressure tablet (Amlodipine 5mg)", title_as="ৰক্তচাপৰ বৰি (Amlodipine 5mg)",
                             detail="1 tablet after breakfast", scheduled_time="08:00",
                             escalation_minutes=15, escalation_final_minutes=30, created_by_caregiver_id=caregiver.id),
            models.Reminder(patient_id=patient.id, kind=models.ReminderKind.medicine,
                             title_en="Blood pressure tablet (Amlodipine 5mg)", title_as="ৰক্তচাপৰ বৰি (Amlodipine 5mg)",
                             detail="1 tablet after dinner", scheduled_time="20:00",
                             escalation_minutes=15, escalation_final_minutes=30, created_by_caregiver_id=caregiver.id),
            models.Reminder(patient_id=patient.id, kind=models.ReminderKind.hydration,
                             title_en="Drink a glass of water", title_as="এগ্লাছ পানী খাওক",
                             scheduled_time="10:00", escalation_minutes=20, escalation_final_minutes=45, created_by_caregiver_id=caregiver.id),
            models.Reminder(patient_id=patient.id, kind=models.ReminderKind.hydration,
                             title_en="Drink a glass of water", title_as="এগ্লাছ পানী খাওক",
                             scheduled_time="13:30", escalation_minutes=20, escalation_final_minutes=45, created_by_caregiver_id=caregiver.id),
            models.Reminder(patient_id=patient.id, kind=models.ReminderKind.hydration,
                             title_en="Drink a glass of water", title_as="এগ্লাছ পানী খাওক",
                             scheduled_time="17:00", escalation_minutes=20, escalation_final_minutes=45, created_by_caregiver_id=caregiver.id),
        ]
        db.add_all(reminders)

        # --- Appointments: one upcoming, plus past visits with hospital-file
        #     medical records so the Doctor/Family/Caregiver/Patient dashboards
        #     all have real diagnosis history to show, not an empty state. ------
        next_appt_date = (datetime.utcnow() + timedelta(days=6)).strftime("%Y-%m-%d")
        upcoming_appt = models.Appointment(
            patient_id=patient.id, doctor_name="Dr. Anjali Sharma",
            hospital_or_clinic="Guwahati Medical College Hospital", date=next_appt_date, time="11:00",
            location="OPD Block C, Room 214", notes="Routine geriatric follow-up",
        )
        db.add(upcoming_appt)

        past_visits = [
            dict(
                days_ago=95, time="10:30",
                chief_complaint="Occasional forgetfulness, difficulty recalling recent conversations; reported by daughter.",
                diagnosis="Mild Cognitive Impairment (MCI), likely age-associated. No acute neurological deficit on exam. "
                          "Clinical correlation and periodic review advised — not a confirmed dementia diagnosis at this stage.",
                prescription="Tab. Donepezil 5mg — once daily, night — 90 days\nTab. Vitamin B-Complex — once daily — 90 days",
                bp="138/86 mmHg", pulse="78 bpm", weight=58.4,
                follow_up="Repeat MMSE cognitive screening; monitor for progression.", follow_up_days_after=60,
            ),
            dict(
                days_ago=35, time="11:15",
                chief_complaint="Follow-up visit. Caregiver reports improved routine adherence, occasional evening confusion.",
                diagnosis="Mild Cognitive Impairment — stable to mildly improved on cognitive activity tracking since last visit. "
                          "Evening disorientation ('sundowning' pattern) noted — supportive, non-pharmacological measures advised first.",
                prescription="Continue Tab. Donepezil 5mg — once daily, night — 90 days\nContinue Vitamin B-Complex — once daily — 90 days",
                bp="132/84 mmHg", pulse="74 bpm", weight=58.9,
                follow_up="Maintain consistent evening routine and lighting; review again in 8 weeks.", follow_up_days_after=56,
            ),
        ]
        for v in past_visits:
            visit_dt = datetime.utcnow() - timedelta(days=v["days_ago"])
            appt = models.Appointment(
                patient_id=patient.id, doctor_name="Dr. Anjali Sharma",
                hospital_or_clinic="Guwahati Medical College Hospital",
                date=visit_dt.strftime("%Y-%m-%d"), time=v["time"],
                location="OPD Block C, Room 214", notes="Geriatric medicine follow-up",
            )
            db.add(appt)
            db.flush()
            follow_up_date = (visit_dt + timedelta(days=v["follow_up_days_after"])).strftime("%Y-%m-%d")
            db.add(models.MedicalRecord(
                appointment_id=appt.id, patient_id=patient.id, doctor_id=doctor.id,
                visit_date=visit_dt.strftime("%Y-%m-%d"), chief_complaint=v["chief_complaint"], diagnosis=v["diagnosis"],
                prescription=v["prescription"], vitals_bp=v["bp"], vitals_pulse=v["pulse"], vitals_weight_kg=v["weight"],
                follow_up_instructions=v["follow_up"], follow_up_date=follow_up_date,
                is_demo_data=True, created_at=visit_dt, updated_at=visit_dt,
            ))

        # --- Safe zone + location (demo, opted in) --------------------------------
        db.add(models.SafeZoneConfig(
            patient_id=patient.id, label="Home", center_lat=GUWAHATI_LAT, center_lng=GUWAHATI_LNG,
            radius_m=500, tracking_enabled=True, consented=True,
        ))
        db.add(models.LocationData(patient_id=patient.id, latitude=GUWAHATI_LAT, longitude=GUWAHATI_LNG,
                                    distance_from_safe_zone_m=40, within_safe_zone=True, is_demo_data=True))
        db.add(models.ConsentRecord(patient_id=patient.id, granted_by_user_id=caregiver_user.id,
                                     category="location", granted=True, notes="Demo seed"))

        # --- Family tree / call list -----------------------------------------
        # Shown on the patient's own dashboard as a memory aid (name + relationship
        # + photo), and doubles as the "call someone if upset" contact list.
        # Linked contacts (family/caregiver) also raise an in-app notification
        # when the patient calls them; the nurse here has no Sukoon login, so
        # calling her only dials the number (still a real, working tel: call).
        db.add_all([
            models.PatientContact(
                patient_id=patient.id, name="Rajiv Bora", relationship_label="Son",
                contact_type="family", phone=family.phone, linked_family_member_id=family.id, display_order=1,
            ),
            models.PatientContact(
                patient_id=patient.id, name="Priya Bora", relationship_label="Daughter (Caregiver)",
                contact_type="caregiver", phone=caregiver.phone, linked_caregiver_id=caregiver.id, display_order=2,
            ),
            models.PatientContact(
                patient_id=patient.id, name="Nurse Ritu Das", relationship_label="Visiting Nurse",
                contact_type="nurse", phone="+91 98640 33333", display_order=3,
            ),
            models.PatientContact(
                patient_id=patient.id, name="Ankita Bora", relationship_label="Granddaughter",
                contact_type="other", phone="+91 98640 44444", display_order=4,
            ),
        ])

        db.flush()

        # --- 14 days of history: game sessions, mood, wearable, reminder log -----
        now = datetime.utcnow()
        difficulty = 1
        for day_offset in range(14, 0, -1):
            day = now - timedelta(days=day_offset)
            day_str = day.strftime("%Y-%m-%d")

            # 1-2 cognitive sessions/day, memory improving, attention inconsistent
            for activity in random.sample(ACTIVITIES, k=random.choice([1, 2])):
                if activity["domain"] == "memory":
                    accuracy = min(0.98, 0.55 + day_offset * -0.01 + random.uniform(0, 0.15) + (14 - day_offset) * 0.02)
                    accuracy = max(0.4, min(0.98, 0.5 + (14 - day_offset) * 0.03 + random.uniform(-0.05, 0.08)))
                    response_ms = random.randint(3000, 6000)
                elif activity["domain"] == "attention":
                    accuracy = random.choice([0.45, 0.55, 0.9, 0.65, 0.8, 0.5])  # inconsistent, on purpose
                    response_ms = random.randint(4000, 11000)
                else:
                    accuracy = random.uniform(0.6, 0.95)
                    response_ms = random.randint(3500, 8000)

                attempts = random.randint(6, 10)
                correct = max(0, min(attempts, round(attempts * accuracy)))
                score = round(accuracy * 100)

                from .adaptive_engine import decide
                result = decide(difficulty, accuracy, response_ms)
                difficulty = result.new_difficulty

                session = models.GameSession(patient_id=patient.id, activity_code=activity["code"],
                                              difficulty=result.new_difficulty, started_at=day, completed_at=day,
                                              is_demo_data=True)
                db.add(session)
                db.flush()
                db.add(models.PerformanceRecord(
                    session_id=session.id, patient_id=patient.id, activity_code=activity["code"],
                    score=score, accuracy=round(accuracy, 2), attempts=attempts, correct_attempts=correct,
                    avg_response_time_ms=response_ms, difficulty=difficulty, new_difficulty=result.new_difficulty,
                    adaptive_direction=result.direction, adaptive_explanation_en=result.explanation_en,
                    adaptive_explanation_as=result.explanation_as, is_demo_data=True, timestamp=day,
                ))

            # mood
            mood = random.choices(["good", "okay", "unsure", "sad"], weights=[5, 4, 2, 1])[0]
            db.add(models.MoodRecord(patient_id=patient.id, mood=mood, date=day_str, timestamp=day, is_demo_data=True))

            # wearable (2-3 ticks/day)
            for _ in range(random.randint(2, 3)):
                db.add(models.WearableData(
                    patient_id=patient.id, device_type="Smartwatch",
                    heart_rate_bpm=random.randint(66, 92), steps=random.randint(800, 5200),
                    activity_level=random.choice(["resting", "light", "active"]), battery_pct=random.randint(30, 100),
                    is_demo_data=True, timestamp=day,
                ))

            # reminder responses (mostly completed; one realistic missed+escalated episode)
            for rem in reminders:
                status = models.ReminderStatus.completed
                escalated = False
                if day_offset == 5 and rem.title_en.startswith("Blood pressure") and rem.scheduled_time == "20:00":
                    status = models.ReminderStatus.escalated
                    escalated = True
                elif random.random() < 0.06:
                    status = models.ReminderStatus.missed

                rr = models.ReminderResponse(
                    reminder_id=rem.id, patient_id=patient.id, date=day_str, fired_at=day, status=status,
                    responded_at=None if status in (models.ReminderStatus.missed, models.ReminderStatus.escalated) else day,
                    gentle_followup_sent=escalated, gentle_followup_at=day if escalated else None,
                    caregiver_alert_sent=escalated, caregiver_alert_at=day if escalated else None,
                    is_demo_data=True,
                )
                db.add(rr)
                if escalated:
                    db.add(models.SafetyAlert(
                        patient_id=patient.id, alert_type="reminder_nonresponse", severity=models.AlertSeverity.warning,
                        message_en=f"Patient did not respond to the {rem.scheduled_time} {rem.title_en} reminder.",
                        message_as=f"ৰোগীয়ে {rem.scheduled_time} বজাৰ ৰিমাইণ্ডাৰত সঁহাৰি দিয়া নাই।",
                        acknowledged=True, acknowledged_at=day + timedelta(hours=1), created_at=day,
                    ))

        patient.current_difficulty_level = difficulty

        db.add(models.Notification(user_id=caregiver_user.id, title="Welcome to Sukoon",
                                    body="Renu Bora's caregiver dashboard is ready.", category="system", read=True))
        db.add(models.Notification(user_id=patient_user.id, title="Welcome to Sukoon",
                                    body="Good morning, Renu! Your day is ready.", category="system", read=True))

        # A couple of pre-seeded updates so the Family dashboard's "Updates" tab
        # isn't empty on first login — one "little" update and one "important"
        # one, so the all-vs-important preference is visibly demonstrable.
        db.add(models.Notification(
            user_id=family_user.id, title="Mood check-in", category="mood", read=False,
            body="Renu Bora checked in feeling: good.", created_at=now - timedelta(hours=6),
        ))
        db.add(models.Notification(
            user_id=family_user.id, title="Alert resolved — patient is safe", category="safety", read=False,
            body="Priya Bora: Checked on Renu after the missed reminder — she'd simply stepped out to the garden. All good.",
            created_at=now - timedelta(days=5, hours=-1),
        ))

        # --- Second doctor patient (demonstrates the doctor dashboard handles
        #     multiple authorized patients, each independently scoped) ----------
        patient2_user = models.User(
            email="patient2@sukoon.demo", password_hash=auth.hash_password(DEMO_PASSWORD_PATIENT),
            role=models.UserRole.patient, full_name="Nabin Das", preferred_language="en", is_demo=True,
        )
        db.add(patient2_user)
        db.flush()
        patient2 = models.Patient(
            user_id=patient2_user.id, age=68, gender="Male",
            condition_notes="Mild memory lapses under investigation (demo profile).",
            home_region="Jorhat, Assam", current_difficulty_level=2, phone="+91 98640 55555",
        )
        db.add(patient2)
        db.flush()
        db.add(models.DoctorAuthorization(
            patient_id=patient2.id, doctor_id=doctor.id, status=models.AuthorizationStatus.approved,
            scope_cognitive_performance=True, scope_activity_history=True, scope_reminder_adherence=True,
            scope_location=False, scope_wearable_data=False, scope_medical_records=True,
            requested_at=now - timedelta(days=4), decided_at=now - timedelta(days=4),
        ))
        appt2 = models.Appointment(
            patient_id=patient2.id, doctor_name="Dr. Anjali Sharma",
            hospital_or_clinic="Guwahati Medical College Hospital",
            date=(now - timedelta(days=10)).strftime("%Y-%m-%d"), time="09:45",
            location="OPD Block C, Room 214", notes="Initial consultation",
        )
        db.add(appt2)
        db.flush()
        db.add(models.MedicalRecord(
            appointment_id=appt2.id, patient_id=patient2.id, doctor_id=doctor.id,
            visit_date=appt2.date, chief_complaint="Occasional word-finding difficulty, noticed by family over 2 months.",
            diagnosis="Subjective cognitive concern — formal neuropsychological testing recommended before any diagnosis.",
            prescription=None, vitals_bp="128/82 mmHg", vitals_pulse="72 bpm", vitals_weight_kg=71.2,
            follow_up_instructions="Schedule neuropsychological assessment; review in 6 weeks.",
            follow_up_date=(now + timedelta(days=32)).strftime("%Y-%m-%d"),
            is_demo_data=True, created_at=appt2.date and now - timedelta(days=10), updated_at=now - timedelta(days=10),
        ))
        for i in range(3):
            day = now - timedelta(days=2 * i + 1)
            activity = ACTIVITIES[i % len(ACTIVITIES)]
            accuracy = random.uniform(0.55, 0.85)
            attempts = random.randint(6, 9)
            correct = round(attempts * accuracy)
            session2 = models.GameSession(patient_id=patient2.id, activity_code=activity["code"], difficulty=2,
                                           started_at=day, completed_at=day, is_demo_data=True)
            db.add(session2)
            db.flush()
            from .adaptive_engine import decide as decide2
            r2 = decide2(2, accuracy, 5200)
            db.add(models.PerformanceRecord(
                session_id=session2.id, patient_id=patient2.id, activity_code=activity["code"],
                score=round(accuracy * 100), accuracy=round(accuracy, 2), attempts=attempts, correct_attempts=correct,
                avg_response_time_ms=5200, difficulty=2, new_difficulty=r2.new_difficulty,
                adaptive_direction=r2.direction, adaptive_explanation_en=r2.explanation_en,
                adaptive_explanation_as=r2.explanation_as, is_demo_data=True, timestamp=day,
            ))

        db.commit()
        print("Seed complete.")
        print(f"  Patient   -> patient@sukoon.demo / {DEMO_PASSWORD_PATIENT}")
        print(f"  Caregiver -> caregiver@sukoon.demo / {DEMO_PASSWORD_CAREGIVER}")
        print(f"  Doctor    -> doctor@sukoon.demo / {DEMO_PASSWORD_DOCTOR}")
        print(f"  Family    -> family@sukoon.demo / {DEMO_PASSWORD_FAMILY}")
    finally:
        db.close()


if __name__ == "__main__":
    run()
