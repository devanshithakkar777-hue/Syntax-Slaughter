# Sukoon

**AI-powered cognitive assistance and caregiver-support platform for elderly patients with dementia and age-related cognitive decline.**

> Sukoon is a cognitive-support, memory-assistance and caregiver-monitoring platform. **It does not diagnose or treat dementia.** AI-generated insights are supportive, explainable, rule-based signals for caregivers and doctors — never a medical diagnosis. Clinical decisions should always be made by qualified healthcare professionals.

---

## The problem

Families caring for an elderly relative with dementia or cognitive decline are usually stretched across three roles at once — the person themselves, a primary caregiver, and a doctor who sees them for a few minutes every few months — with no shared, real-time picture of how the patient is actually doing day to day. Missed medication goes unnoticed until it becomes a crisis. A wandering episode is discovered too late. Cognitive decline is only caught retrospectively, in a clinic, instead of being visible as a gentle trend over weeks. And the wider family — often the people most invested, but least present — is usually left out of the loop entirely.

Sukoon closes that loop: one connected platform, four coordinated views, built to work reliably even on patchy connectivity.

## Key features

- **Four connected roles** — Patient, Caregiver, Doctor, and Family — each with a purpose-built dashboard and scoped, authorization-gated access to exactly the data they're allowed to see.
- **Cognitive gaming suite** — four playable games (memory matching, pattern recognition, object recognition, daily-routine recall) that double as a passive, longitudinal cognitive-trend signal.
- **Explainable adaptive difficulty** — a transparent, rule-based engine (not a black box) adjusts game difficulty and can justify every change in one plain sentence.
- **Medication & routine reminders** with real server-side, time-based escalation — a missed reminder genuinely escalates to the caregiver, it isn't simulated.
- **Geofencing & safety alerts** — a live map with a configurable safe zone, real alerting when a patient leaves it, uncertainty-aware status when telemetry is missing or stale.
- **Offline Care Ledger & Safety Reconciliation Engine** — an append-only, versioned event ledger that makes the whole system resilient to offline use: deterministic conflict resolution, idempotent sync, a full audit trail, and a replay engine that can rebuild every derived record from the ledger alone.
- **Family tree & call-for-comfort** — the patient sees photos and names of their family and can call anyone with one tap, which rings their phone's real dialer and notifies the family as a safety net.
- **Virtual appointments** — every appointment gets a real, no-signup video room, joinable from the doctor and family dashboards.
- **Bilingual, voice-enabled patient app** — English and Assamese, with text-to-speech and speech-to-text via the browser's native Web Speech API.
- **Consent-first, auditable authorization** — doctors see nothing until explicitly, scopeably authorized by the patient or family; every sensitive action is written to an audit log; a stale offline event can never resurrect revoked access.
- **Offline-first patient app** — a service worker caches the app shell, and actions taken offline sync and reconcile automatically once connectivity returns.

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Python, FastAPI, SQLAlchemy |
| Database | SQLite by default; drop-in PostgreSQL for persistent deployments (one env var) |
| Frontend | Vanilla HTML/CSS/JavaScript |
| Auth | JWT sessions, bcrypt password hashing, role- and ownership-scoped authorization on every route |
| Charts | Chart.js, vendored locally — works offline |
| Maps | Leaflet + OpenStreetMap tiles, Leaflet vendored locally |
| Voice | Browser-native Web Speech API (STT + TTS) |
| Video | Jitsi Meet (no-signup, deterministic room per appointment) |
| AI | A fully explainable, rule-based adaptive-difficulty engine |

## Quick start

```bash
cd backend
pip install -r requirements.txt
python -m app.seed          # creates sukoon.db with demo accounts + 14 days of history
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Then open **http://localhost:8000** — one process serves the API and the entire app. This also runs as-is on Render, Replit, or any host that can run a single Python process (set the run command to the two lines above: seed once, then start uvicorn on `$PORT`).

### Demo accounts

Also available as one-tap buttons on the login screen.

| Role | Email | Password |
|---|---|---|
| Patient | `patient@sukoon.demo` | `Patient@123` |
| Caregiver | `caregiver@sukoon.demo` | `Caregiver@123` |
| Doctor | `doctor@sukoon.demo` | `Doctor@123` |
| Family | `family@sukoon.demo` | `Family@123` |

The seeded patient (**Renu Bora**, 72, Guwahati, Assam) comes with 14 days of realistic history — cognitive game sessions with a genuine improving-memory / inconsistent-attention pattern, mood check-ins, simulated wearable readings, one already-escalated missed-reminder alert, and a pre-approved doctor authorization — so every dashboard has real content the moment you log in, with room to still demo the live request/approve flow with a *second* doctor.

## Walkthrough

1. Log in as **Patient** → switch language EN/অসমীয়া → open today's routine → play a cognitive game → watch the adaptive-difficulty explanation appear after scoring.
2. Open **Reminders** → a medicine/hydration reminder is usually already due (escalation is real and time-based, not faked) → mark it, or leave it and let the caregiver see it.
3. Log in as **Caregiver** → **Overview** shows the 30-day cognitive trend chart, mood trend, and any alerts. To fast-forward a live "no response" demo without waiting real minutes, add a reminder a minute or two out, or call `POST /api/demo/{patient_id}/force-escalate` — it exercises the exact same escalation code path, just on demand.
4. **Location & Wearable** tab → "Simulate: moved outside" generates a real geofence alert; "Simulate new reading" generates a labelled **Demo Data** wearable reading.
5. **Doctors & Authorization** tab → add a new doctor by email → a demo doctor account is auto-provisioned so you can immediately log in as them and show the authorization-required, scoped-access experience from the other side.
6. Log in as **Doctor** → only the authorized patient appears, and only the specifically-authorized data categories render.
7. To show offline-first: open DevTools → Network → "Offline" on the Patient app, complete a reminder or play a game, see the **"Offline — data will sync when connection is restored"** banner, then go back online and watch it flip to **"Synced ✓"**.
8. Back on **Patient** → tap **My Family** → tap any photo to "call" them — the phone's real dialer opens and, if that person has a Sukoon login, they get an in-app notification instantly.
9. As **Caregiver** or **Family** → **Family & Contacts** tab → add a family member with a real uploaded photo, or set the patient's own phone number and use **"📞 Call the patient."**
10. As **Family** → **Updates** tab → toggle between "Every little update" and "Important updates only," then trigger something on the Patient or Caregiver app and watch the feed change accordingly.
11. As **Family** or **Doctor** → **Appointments** tab → **🎥 Join Virtually / Start / Join** opens the same real video room — open it in two tabs to show both sides joining the same call.

## What's real vs. simulated (and why)

Everything is a real, working code path end-to-end — the only things simulated are the *data sources* that need physical hardware:

- **Wearable/patch data** — real DB models, real API, real dashboard rendering; the *reading itself* is generated by a "Simulate new reading" button instead of a live BLE device, and is always labelled `Demo Data` in the UI.
- **GPS location** — same story: a real safe-zone/geofencing/alert pipeline, with simulated coordinates instead of a live GPS chip.
- **Assamese voice recognition** — the voice layer (`static/js/voice.js`) uses the browser's real Web Speech API; Assamese STT/TTS availability depends on the OS/browser, and the code is architected so a dedicated Assamese engine can be dropped in later without touching any calling code.

Nothing else is mocked: authentication, the adaptive-difficulty engine, reminders/escalation, the offline sync queue, the care ledger, and role-based authorization are fully functional.

## Architecture

```
backend/
  app/
    models.py            Core SQLAlchemy tables — Users, Patients, Caregivers,
                          Doctors, DoctorAuthorizations, ConsentRecords,
                          GameSessions, PerformanceRecords, Reminders,
                          ReminderResponses, DailyRoutines, Appointments,
                          MoodRecords, WearableData, LocationData,
                          SafetyAlerts, Notifications, SyncQueue, AuditLogs —
                          plus the Offline Care Ledger tables (CareEvent,
                          DeviceSyncCheckpoint, and the derived
                          *LedgerState projections)
    auth.py               JWT + bcrypt + role-guard dependency
    access.py             "does this caregiver own this patient / is this
                           doctor authorized for this scope" — checked on
                           every sensitive route
    adaptive_engine.py     explainable rule-based difficulty engine
    reminders_engine.py    lazy reminder-firing + non-response escalation
    notifications.py       notify_family() — the single fan-out helper every
                            patient-related event routes through, respecting
                            each family member's "all" vs "important" preference
    media.py                validates/size-caps uploaded contact photos
    ledger_schemas.py       Offline Care Ledger payload schemas & event registry
    reconciliation.py       per-event-category deterministic conflict policy
    ledger.py                NDJSON sync protocol, idempotent ingestion,
                              resumable checkpoints, audit export, replay
    seed.py                 demo data (two patients, family-tree contacts,
                             a pre-seeded Updates feed)
    routers/                 auth, patient, games, caregiver, doctor,
                              authorization, family, sync, consent, ledger, demo
  scripts/
    ledger_harness.py        repeatable synthetic test harness for the
                              Offline Care Ledger (31 passing assertions)
static/
  index.html              shared login (all 4 roles)
  patient/                 large-button, high-contrast, bilingual, vibrant
                            patient app; includes the "My Family" call-for-
                            comfort view
  caregiver/                information-dense caregiver dashboard (Chart.js
                            trends, live map, Family & Contacts, call-the-patient)
  doctor/                   clinically-oriented, scope-limited doctor
                            dashboard, multi-patient sidebar, hospital-file
                            medical records, virtual-appointment join
  family/                   combined patient + caregiver + doctor view; owns
                            doctor authorization; Updates feed; Family &
                            Contacts; virtual-appointment join
  shared/privacy.html      consent & privacy explainer
  js/games/                 the 4 cognitive games
  service-worker.js         offline app-shell cache for the patient app
```

## Offline Care Ledger & Safety Reconciliation Engine

A parallel, additive subsystem that makes every safety-relevant action — medication reminders, routine edits, consent changes, geofence readings, caregiver actions — durable and reconcilable even when devices go offline for extended periods:

- An **append-only, versioned ledger** (`CareEvent`) is the single source of truth; existing tables become derived, rebuildable projections.
- **Deterministic, idempotent reconciliation** — safe to replay, safe to resend, safe under out-of-order arrival and clock drift, with an explainable reason attached to every outcome.
- **A strict medication-reminder lifecycle** — a notification firing can never, by construction, be mistaken for the patient confirming they took their medicine.
- **An NDJSON sync protocol** built for real offline conditions: chunked uploads, duplicates, gaps, reordering, malformed lines, and safe resumption via checkpoints.
- **Versioned, backend-enforced consent** — a stale offline grant can never restore access that's since been revoked.
- **Uncertainty-aware safety signals** — the system distinguishes observed, inferred, stale, and unknown telemetry, and never treats missing data as proof of safety.
- **A guarded adaptive-engine boundary** — a malformed or failing model output falls back to a safe, deterministic policy and can never touch medication or safety state.

Full design rationale, file-by-file responsibilities, and a "run it yourself" guide live in [`OFFLINE_LEDGER_ARCHITECTURE.md`](./OFFLINE_LEDGER_ARCHITECTURE.md). The test harness (`backend/scripts/ledger_harness.py`) is self-contained and repeatable — it boots the real app with `TestClient`, submits a deliberately adversarial synthetic event stream, and verifies every scenario above, including replay-determinism.

## Deploying with PostgreSQL instead of SQLite (recommended for persistent hosting)

The models use only standard SQLAlchemy types, so switching is one environment variable:

```bash
export SUKOON_DATABASE_URL="postgresql://user:password@host:5432/sukoon"
python -m app.seed
uvicorn app.main:app
```

**Why this matters on free-tier hosts specifically:** a free web service plan typically uses an *ephemeral* filesystem — wiped on every restart (which happens automatically after a period of inactivity). SQLite stores the whole database as one file on that filesystem, so a restart silently erases every account. A persistent Postgres instance isn't affected by the web service restarting, so pointing `SUKOON_DATABASE_URL` at one (and re-running `python -m app.seed` once against it) fixes this permanently. `psycopg2-binary` is already in `requirements.txt` for this. Uploaded family-contact photos are stored as base64 `data:` URLs in the database itself (`media.py` caps their size) rather than on local disk, for the same reason.

## Security notes

- Passwords are bcrypt-hashed, never stored or logged in plaintext.
- Every non-public route requires a valid JWT and is further scoped by role (`require_role`) and by explicit ownership/authorization checks in `access.py` — a caregiver cannot query another caregiver's patient, and a doctor cannot see anything until a specific, scoped, revocable authorization exists.
- All sensitive actions (login, authorization decisions, consent changes, revocations, doctor data views) are written to `AuditLog`.
- `SUKOON_SECRET_KEY` should be set to a real secret in any non-demo deployment (a dev default is used otherwise, with a clear comment in `auth.py`).
- Location and wearable tracking are off by default per patient and require an explicit `consented=true` flag before any simulated data can be generated.
- The optional AI companion-chat layer (`SUKOON_LLM_API_KEY`) only ever generates text a human reviews — nothing that can autonomously act, escalate, or change safety-critical data ever routes through it.

## Known scope boundaries (intentional, for a prototype)

- Appointment reminders show on the patient home screen and appointments list, but (unlike the daily recurring medicine/hydration reminders) don't yet run through the same escalation engine, since appointments are date-specific rather than daily-recurring — a natural next iteration.
- The rule-based adaptive engine is intentionally simple and fully explainable; the codebase isolates it behind one function (`adaptive_engine.decide()` / `safe_decide()`) so it can be replaced by a trained model later without touching any caller.
- CORS is wide open (`allow_origins=["*"]`) for ease of local/demo hosting — restrict this to a known origin before any real deployment.

## Team

Built by **Team Syntax&Slaughter**.
