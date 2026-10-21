# Sukoon — AI-Powered Cognitive Assistance & Caregiver Support Platform

**Smart India Hackathon 2026 · Problem Statement 26003**
*AI-based Cognitive Gaming and Memory Assistance platform for elderly dementia patients in NER*
Team: SevaTech

> Sukoon is a cognitive support, memory-assistance and caregiver-monitoring platform. **It does not diagnose or treat dementia.** AI-generated insights are supportive, explainable, rule-based signals for caregivers and doctors — never a medical diagnosis. Clinical decisions should always be made by qualified healthcare professionals.

---

## What this is

A working full-stack prototype implementing a four-role system (Patient / Caregiver / Doctor / Family) built on top of the SIH problem statement and feature checklist:

- **Backend:** Python, FastAPI, SQLAlchemy, SQLite (swap to PostgreSQL by changing one env var — see below)
- **Frontend:** Vanilla HTML/CSS/JavaScript (no build step), served by the same FastAPI process
- **Auth:** JWT sessions, bcrypt password hashing, role-based access control on every route
- **AI:** an explainable, rule-based adaptive-difficulty engine (see `backend/app/adaptive_engine.py`) — deliberately *not* a black-box model, so every difficulty change can be explained in one sentence to a judge or caregiver
- **Charts:** Chart.js (vendored locally in `static/js/vendor/`, no external CDN dependency — works with no internet at demo time)
- **Maps:** Leaflet + OpenStreetMap tiles (Leaflet itself vendored locally in `static/js/vendor/leaflet/`; map tiles load from OpenStreetMap over the network at demo time)
- **Voice:** Web Speech API — speech-to-text and text-to-speech on the patient app, plus a "read this page aloud" button on the caregiver, doctor and family dashboards

## What's new since the first prototype

- **Family dashboard** (4th role) — one combined view of the patient's, caregiver's and doctor's data together, and the only place (besides the patient's own account) that can request, approve, reject or revoke doctor authorizations. The caregiver dashboard now shows authorized doctors read-only.
- **Doctor medical records** — a hospital-file-style diagnosis/prescription/vitals/follow-up record per appointment, written by the authorized doctor and visible (per the same scoped authorization) to the patient, caregiver and family.
- **Real interactive map** — the Location & Wearable tab (caregiver, doctor, family) now renders an actual Leaflet map with the safe-zone circle and a live position marker, not just a text status line.
- **Vibrant patient UI** — the patient dashboard keeps its large buttons and high contrast, with a colorful gradient header and a distinct accent color per card category for faster at-a-glance recognition.

### Round 3 additions — comfort calls, family tree, notification control, multi-patient doctors

- **"My Family" + call for comfort (patient app)** — a new home-screen tile shows the patient's family tree: each person's photo (or an initial avatar), name and relationship, so the patient always has a face to put to a name. Tapping **Call** on anyone — a family member living far away, a caregiver, or a nurse — immediately alerts that person in-app (if they have a Sukoon login) *and* opens the phone's real dialer via a `tel:` link, and always notifies the wider family as a safety net in case the person they called doesn't pick up. It works the other way too: the caregiver and family dashboards have a **"📞 Call the patient"** button (Family & Contacts tab) that dials the patient's own phone number directly.
- **Family notification preference** — on the Family dashboard's new **Updates** tab, a family member chooses between *"Every little update"* (e.g. a missed water reminder) and *"Important updates only"* (e.g. leaving the safe zone, a new diagnosis, help requests). Every patient-related event in the backend is routed through one shared `notify_family()` helper that respects this per-family-member preference, so the choice applies consistently everywhere.
- **Caregiver "issue resolved" acknowledgement** — when a caregiver clicks **Acknowledge** on a safety alert, the family is now notified that the alert has been taken care of and the patient is safe (always treated as an "important" update, regardless of preference).
- **Family tree with real photos** — caregivers and family members manage the same shared contact/family-tree list (add, edit, remove; photo upload via a real file picker, stored as the visit record itself would be, so it survives restarts once the database is persistent — see the PostgreSQL section below) from a new **Family & Contacts** tab on both dashboards.
- **Family "Updates" tab** — one running feed of everything about the patient's care: mood check-ins, missed reminders, caregiver actions (including alert acknowledgements), safety alerts, and the doctor's diagnosis/prescription notes — all in one place, filtered by the notification preference above.
- **Virtual appointment join** — every appointment gets a real, free, no-signup video room (Jitsi Meet, `meet.jit.si`), generated deterministically from the appointment id. A **"🎥 Join Virtually"** button appears on the Family dashboard's Appointments tab and a **"🎥 Start / Join"** button on the Doctor dashboard's new Appointments tab — everyone who opens their link lands in the same room.
- **Doctor multi-patient support** — the doctor dashboard already listed every authorized patient in a sidebar and let the doctor switch between them; the demo seed now provisions a *second* authorized patient out of the box so this is visible immediately without any manual setup during a demo.

## Quick start

```bash
cd backend
pip install -r requirements.txt
python -m app.seed          # creates sukoon.db with demo accounts + 14 days of history
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Then open **http://localhost:8000** — that's it, one process serves the API and the whole app.

This also runs as-is on Replit: set the run command to the two lines above (seed once, then start uvicorn on `$PORT`).

### Demo accounts (also one-tap buttons on the login screen)

| Role      | Email                    | Password       |
|-----------|---------------------------|----------------|
| Patient   | patient@sukoon.demo       | Patient@123    |
| Caregiver | caregiver@sukoon.demo     | Caregiver@123  |
| Doctor    | doctor@sukoon.demo        | Doctor@123     |
| Family    | family@sukoon.demo        | Family@123     |

The seeded patient (**Renu Bora**, 72, Guwahati, Assam) has 14 days of realistic history: cognitive game sessions with a genuine improving-memory / inconsistent-attention pattern, mood check-ins, simulated wearable readings, one already-escalated missed-reminder alert, and a pre-approved doctor authorization — so every dashboard has real content the moment you log in, with room to still demo the live request/approve flow with a *second* doctor.

## Running the exact judge demo flow (spec section 20)

1. Log in as **Patient** (or tap the demo button) → switch language EN/অসমীয়া → open today's routine → play a cognitive game (all 4 are implemented and fully playable) → watch the adaptive-difficulty explanation appear after scoring.
2. Open **Reminders** → a medicine/hydration reminder is usually already due (server-side escalation is real and time-based, not faked) → mark it, or leave it and let the caregiver see it.
3. Log in as **Caregiver** → **Overview** shows the 30-day cognitive trend chart, mood trend, and any alerts. To fast-forward a live "no response" demo without waiting real minutes, add a reminder set a minute or two in the future, or use the `POST /api/demo/{patient_id}/force-escalate` endpoint (see `backend/app/routers/demo.py`) — it exercises the exact same escalation code path, just on demand.
4. **Location & Wearable** tab → "Simulate: moved outside" generates a real geofence alert; "Simulate new reading" generates a labelled **Demo Data** wearable reading.
5. **Doctors & Authorization** tab → add a new doctor by email → a demo doctor account is auto-provisioned (`Doctor@123`) so you can immediately log in as them and show the authorization-required, scoped-access experience from the other side.
6. Log in as **Doctor** → only the authorized patient appears, and only the specifically-authorized data categories render (location is off by default in the seed, on purpose, to demonstrate scoping).
7. To show offline-first: open DevTools → Network → "Offline" on the Patient app, complete a reminder or play a game, see the **"Offline — data will sync when connection is restored"** banner, then go back online and watch it flip to **"Synced ✓"**.
8. Back on **Patient** → tap **My Family** → tap any photo to "call" them — the phone's real dialer opens and, if that person has a Sukoon login, they get an in-app notification instantly (try it while logged in as Family in another tab/device to see it land live).
9. As **Caregiver** or **Family** → **Family & Contacts** tab → add a family member with a real uploaded photo, or set the patient's own phone number and use **"📞 Call the patient"**.
10. As **Family** → **Updates** tab → toggle between "Every little update" and "Important updates only", then trigger something on the Patient or Caregiver app (a mood check-in, a missed reminder, moving outside the safe zone) and watch the feed change accordingly.
11. As **Family** or **Doctor** → **Appointments** tab → **🎥 Join Virtually / Start / Join** opens the same real Jitsi Meet room for that appointment — open it in two browser tabs to show both sides joining the same call.

## What's real vs. simulated (and why)

Per the product spec's own guidance ("a working simulated integration is acceptable for an early prototype"), everything is a real, working code path end-to-end — the only things simulated are the *data sources* that need physical hardware:

- **Wearable/patch data** — real DB models, real API, real dashboard rendering; the *reading itself* is generated by a "Simulate new reading" button instead of a real BLE device, and is always labelled `Demo Data` in the UI.
- **GPS location** — same story: a real safe-zone/geofencing/alert pipeline, with simulated coordinates instead of a live GPS chip.
- **Assamese voice recognition** — the voice layer (`static/js/voice.js`) uses the browser's real Web Speech API for text-to-speech and speech-to-text; Assamese STT/TTS voice availability depends on the OS/browser, and the code is architected so a dedicated Assamese engine can be dropped in later without touching any calling code.

Nothing else is mocked: authentication, the adaptive-difficulty engine, reminders/escalation, the offline sync queue, and role-based authorization are fully functional.

## Architecture

```
backend/
  app/
    models.py          21 SQLAlchemy tables (see spec section 16 — Users, Patients,
                        Caregivers, Doctors, DoctorAuthorizations, ConsentRecords,
                        GameSessions, PerformanceRecords, Reminders, ReminderResponses,
                        DailyRoutines, Appointments, MoodRecords, WearableData,
                        LocationData, SafetyAlerts, Notifications, SyncQueue, AuditLogs…)
    auth.py             JWT + bcrypt + role-guard dependency
    access.py           "does this caregiver own this patient / is this doctor
                         authorized for this scope" — checked on every sensitive route
    adaptive_engine.py   explainable rule-based difficulty engine
    reminders_engine.py  lazy reminder-firing + non-response escalation
    notifications.py     notify_family() — the single fan-out helper every
                          patient-related event routes through, respecting
                          each family member's "all" vs "important" preference
    media.py              validates/size-caps uploaded contact photos (stored
                           as data: URLs directly in the DB — see PostgreSQL note)
    seed.py              demo data (two patients, family-tree contacts, a
                          pre-seeded Updates feed)
    routers/             auth, patient, games, caregiver, doctor, authorization,
                          family, sync, consent, demo (judge-demo conveniences)
static/
  index.html            shared login (all 4 roles)
  patient/               large-button, high-contrast, bilingual, vibrant patient app;
                          includes the "My Family" call-for-comfort view
  caregiver/              information-dense caregiver dashboard (Chart.js trends, live
                          map, Family & Contacts tab, call-the-patient)
  doctor/                 clinically-oriented, scope-limited doctor dashboard,
                          multi-patient sidebar, hospital-file medical records,
                          virtual-appointment join
  family/                 combined patient + caregiver + doctor view; owns doctor
                          authorization; Updates feed + notification preference;
                          Family & Contacts tab; virtual-appointment join
  shared/privacy.html    consent & privacy explainer
  js/games/               the 4 cognitive games (memory matching, pattern
                           recognition, object recognition, daily routine recall)
  service-worker.js      offline app-shell cache for the patient app
```

## Deploying with PostgreSQL instead of SQLite (recommended for Render and similar free hosts)

The models use only standard SQLAlchemy types, so switching is one environment variable:

```bash
export SUKOON_DATABASE_URL="postgresql://user:password@host:5432/sukoon"
python -m app.seed
uvicorn app.main:app
```

**Why this matters on Render's free tier specifically:** the free web service plan uses an *ephemeral* filesystem — it's wiped on every restart (which happens automatically after ~15 minutes of inactivity). SQLite stores the whole database as one file on that filesystem, so a restart silently erases every account, including the one behind whatever JWT is sitting in a logged-in browser tab; the next request then fails with "Account not found," which the frontend reports as **"Session expired."** Render's free PostgreSQL add-on lives on its own persistent service and isn't affected by the web service restarting, so pointing `SUKOON_DATABASE_URL` at it (and re-running `python -m app.seed` once against it) fixes this permanently. `psycopg2-binary` is already in `requirements.txt` for this. Uploaded family-contact photos are stored as base64 `data:` URLs in the database itself (`media.py` caps their size) rather than on local disk, for the same reason — so they also survive restarts once the database is persistent.

## Security notes for judges

- Passwords are bcrypt-hashed, never stored or logged in plaintext.
- Every non-public route requires a valid JWT and is further scoped by role (`require_role`) and by explicit ownership/authorization checks in `access.py` — a caregiver cannot query another caregiver's patient, and a doctor cannot see anything until a specific, scoped, revocable authorization exists.
- All sensitive actions (login, authorization decisions, consent changes, revocations, doctor data views) are written to `AuditLog`.
- `SUKOON_SECRET_KEY` should be set to a real secret in any non-demo deployment (a dev default is used otherwise, with a clear comment in `auth.py`).
- Location and wearable tracking are off by default per patient and require an explicit `consented=true` flag before any simulated data can be generated — matching the "authorization required, not covert surveillance" requirement in the spec.

## Known scope boundaries (intentional, for a first prototype)

- Appointment reminders show on the patient home screen and appointments list, but (unlike the daily recurring medicine/hydration reminders) don't yet run through the same escalation engine, since appointments are date-specific rather than daily-recurring — a natural next iteration.
- The rule-based adaptive engine is intentionally simple and fully explainable; the codebase isolates it behind one function (`adaptive_engine.decide()`) so it can be replaced by a trained model later without touching any caller.
- CORS is wide open (`allow_origins=["*"]`) for ease of local/Replit demoing — restrict this to a known origin before any real deployment.
