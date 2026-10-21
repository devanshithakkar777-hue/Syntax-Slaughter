# Offline Care Ledger + Safety Reconciliation Engine

**Sukoon — Round 2 twist implementation (Team SevaTech)**

This document explains what was built, why it's built this way, and how to
run the evidence yourself. It is additive to the existing Sukoon codebase:
no existing table, endpoint, or router was modified or removed. Everything
below lives in five new backend files plus one new router.

## Why additive, not a rewrite

The brief allows existing tables to remain as "derived projections rather
than the only record of history," and warns that breaking the core
application is penalized. Given a 24-hour window, the safest and most
defensible design is a **parallel, self-contained subsystem**: a new
append-only ledger plus its own derived projection tables, with its own
router, touching the existing schema at exactly one narrow, safe point
(creating `SafetyAlert` rows on escalation — an existing table, written
only for ledger-owned patients, cleanly cleared and rebuilt on replay).
The already-deployed, already-working patient/caregiver/doctor/family
dashboards are untouched and keep working exactly as before — verified
directly (see "Regression check" below).

## New files

| File | Responsibility |
|---|---|
| `backend/app/models.py` *(extended)* | `CareEvent` (the ledger), `DeviceSyncCheckpoint`, and four derived projection tables: `RoutineLedgerState`, `ReminderLedgerState`, `ConsentLedgerState`, `GeofenceLedgerState` |
| `backend/app/ledger_schemas.py` | Pydantic envelope + one payload schema per event type; the known/critical event-type registry |
| `backend/app/reconciliation.py` | One function per event category implementing its documented conflict policy |
| `backend/app/ledger.py` | NDJSON parsing, idempotent ingestion, resumable-sync checkpoints, audit export, deterministic replay |
| `backend/app/routers/ledger.py` | The five HTTP endpoints, with authorization enforced server-side on every call |
| `backend/app/adaptive_engine.py` *(extended)* | `safe_decide()` — a guarded wrapper proving adaptive-engine failures can never affect safety state |
| `backend/scripts/ledger_harness.py` | The repeatable synthetic test harness (31 assertions) |

## 1. Append-only ledger

`CareEvent` stores every field the brief requires: `event_id` (the
idempotency key, globally unique), `patient_id`, `device_id`,
`device_sequence`, `event_type`, `schema_version`, `observed_at`
(device-claimed, untrusted), `received_at` (server clock), `actor_user_id`
/ `actor_role`, `consent_version`, `payload_json`, and an `integrity_hash`
(SHA-256 over the canonical event). Rows are never updated after insert
except to record the one-time ingestion outcome. `server_sequence`
(a plain DB autoincrement) is the single authoritative ordering key —
**not** `observed_at` or `device_sequence`, both of which are untrusted
client metadata kept only for audit and gap-detection.

Unknown `event_type`s and unsupported `schema_version`s are rejected
safely (stored when there's a usable `event_id`, logged either way) —
never guessed at, never silently dropped, never crash the request.

## 2. Deterministic reconciliation & idempotency

- **Idempotency**: `event_id` is checked before anything else. A repeat
  submission — the same device resending because it doesn't know whether
  its last upload succeeded — returns `duplicate` immediately, with the
  *original* resolution reason, and never re-runs any side effect.
- **Ordering**: replay (`ledger.replay_patient`) reprocesses every
  non-rejected event in `server_sequence` order from a cleared projection
  state and must reproduce bit-identical derived state — this is checked
  automatically in the harness, not asserted by hand-waving.
- **Per-category policy**, documented in `reconciliation.py`'s module
  docstring and enforced in code:
  - *routine edits*: last-write-wins by server order; a different actor
    editing the same `routine_key` within a 5-minute window is still
    applied (so the projection is never stale) but flagged
    `conflict_review` with both actors and the time gap named.
  - *cognitive-game results*: append-only, no conflict is possible.
  - *medication reminder lifecycle*: see §3.
  - *geofence observations*: append-only history; the current-status
    projection is staleness-aware (see §6).
  - *consent changes*: versioned per (patient, category); see §5.
  - *caregiver actions*: logged as-is, with a best-effort, never-failing
    side effect (acknowledging an existing alert).

Every outcome (`accepted` / `duplicate` / `rejected` / `conflict_review` /
`needs_review`) carries a human-readable `reason` string — that's the
"explainable" requirement, satisfied structurally rather than bolted on.

## 3. Medication reminder lifecycle

`ReminderLedgerState` keeps delivery progress
(`scheduled → notification_attempted → provider_accepted`) and the user's
own acknowledgement as **separate fields** — a notification firing can
never, by construction, set `user_acknowledged`. Only an explicit
`reminder_user_acknowledged` event does that. A second
`reminder_caregiver_escalated` event for the same occurrence is detected
and suppressed (`duplicate`) specifically to prevent an alert storm when
multiple devices independently notice the same overdue reminder after
reconnecting — demonstrated directly in the harness. `sync_status`
(`pending` / `synced` / `conflict` / `rejected` / `needs_review`) is
tracked per occurrence.

## 4. NDJSON synchronization protocol

`POST /api/ledger/sync/{patient_id}` takes a raw NDJSON body (one JSON
object per line) — not a JSON array, not a mock. The parser
(`ledger.parse_ndjson`) is line-tolerant: a malformed line is reported and
skipped, never fatal to the rest of the batch. The response always
reports real per-record outcomes plus a top-level `status` that is
`"partial"` the moment *anything* in the batch wasn't a clean accept — a
batch with rejects or conflicts is never reported as fully successful.
`GET /api/ledger/checkpoint/{patient_id}/{device_id}` lets a device ask
what's already been seen before resuming, using `device_sequence` gap
tracking (`contiguous_up_to` + an explicit `gaps` list) — entirely
separate bookkeeping from the ledger's own ordering.
`GET /api/ledger/export/{patient_id}` streams the complete, ordered
NDJSON audit bundle. `POST /api/ledger/replay/{patient_id}` rebuilds every
derived projection from that export alone.

## 5. Consent, authorization, privacy

`ConsentLedgerState` tracks a `version` per (patient, category),
incremented on every accepted change. A **grant** is only honoured if its
claimed `consent_version` is at least the current authoritative version —
an offline device that hasn't heard about a revocation yet cannot use a
stale grant to restore access. A **revoke always applies immediately**
regardless of version, because narrowing access is never the unsafe
direction. This exact scenario (grant → revoke → stale offline grant
rejected → fresh grant accepted) is in the harness.

Authorization itself is enforced in `routers/ledger.py`'s
`_resolve_actor`/`_resolve_reader`, reusing the same ownership checks
(`access.py`) the rest of the app already relies on, on **every** call —
not hidden behind a frontend control. The actor written onto a `CareEvent`
is always the authenticated session's own id/role; the wire format has no
field for asserting a different actor, so spoofing is structurally
impossible, not just policy.

## 6. Geofence & medication safety

`GeofenceLedgerState.observation_type` is one of `observed`,
`inferred_transition`, `stale`, or `unknown` — enforced at the schema
level (`ledger_schemas.GeofenceObservationPayload`): an `unknown`/`stale`
reading is not allowed to also assert `within_safe_zone`, and an
`observed`/`inferred_transition` reading *must* include real coordinates.
`reconciliation.current_safety_signal()` additionally treats a reading
older than 30 minutes as stale at read time, and a patient with **no**
telemetry at all reports `status: "unknown"` — never a default "safe".
This is asserted directly in the harness: a real observation is accepted,
then the wearable loses signal, and the status reads `unknown`, not safe.

## 7. Adaptive-engine failure handling

`adaptive_engine.safe_decide()` wraps the existing deterministic rule
engine (`decide()`, unchanged) with input/output validation: NaN or
out-of-range accuracy, negative response times, an out-of-range starting
difficulty, or any unexpected exception all fall back to "keep the
current difficulty, explain why" rather than raising or producing a bad
value. The module has no import or reference to any reminder/medication/
safety model — structurally, not just by convention, it cannot affect
those systems. Three direct unit-style checks plus a static-reference
check are in the harness.

## 8. Testing & evidence

`backend/scripts/ledger_harness.py` is a self-contained, repeatable
script: it boots the real FastAPI app in-process (`TestClient`, real
routing/auth/DB — nothing mocked), creates one clearly-labeled synthetic
patient/caregiver pair (`*.synthetic` email domain — no real patient data
anywhere), and submits a deliberately adversarial NDJSON stream covering
every required scenario: duplicate `event_id`, out-of-order
`device_sequence`, an interrupted-then-resumed upload, a permanent
sequence gap, five distinct kinds of malformed records, a stale consent
grant, a concurrent routine-edit conflict, and a geofence signal going
from observed to unknown. It then replays the ledger and asserts the
rebuilt state is byte-identical to what incremental ingestion produced,
and exports the full NDJSON audit bundle.

**Run it yourself:**
```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cd .. && cd backend
.venv/bin/python -m scripts.ledger_harness
```
Output: `evidence/ledger_harness_report.txt` (the full run log with every
assertion) and `evidence/ledger_audit_bundle.ndjson` (the exported audit
bundle for the synthetic patient), both checked into this repo so they
can be read without re-running anything — current result: **31/31
assertions pass**, including the replay-determinism check.

### Regression check

The same harness run, plus a direct smoke test against the pre-existing
seeded demo accounts (`patient@sukoon.demo`, `caregiver@sukoon.demo`) and
their existing endpoints (`/api/patient/home`,
`/api/caregiver/patients/{id}/dashboard`,
`/api/caregiver/patients/{id}/agentic`), confirms the already-deployed
application is completely unaffected — those endpoints return exactly
what they did before this feature existed, and a caregiver querying
`/api/ledger/status/{patient_id}` for a patient with no ledger activity
gets a clean "no data yet" response rather than an error.
