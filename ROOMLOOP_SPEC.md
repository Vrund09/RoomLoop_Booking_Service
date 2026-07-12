# RoomLoop Booking Service — Complete Implementation Spec

**Purpose of this document:** end-to-end, phase-by-phase build spec for the Auric AI Round-2 take-home.
It is written so an implementing agent/model can follow it mechanically. Every phase has explicit
acceptance criteria and a verification gate. **Do not skip gates. Do not proceed to the next phase
until the current gate passes.**

---

## 0. Reviewer's Mental Model (READ FIRST — this is what the task is really testing)

This task contains **deliberate traps**. A reviewer at an AI company grading a junior candidate is
checking whether you spot them, not whether you write lots of code. Every implementation decision
below flows from these five insights:

### Trap 1 — R1 and R2 contradict each other
R1 says recurring creation is *all-or-nothing*. R2 says *skip conflicting instances and create the
rest*. You cannot satisfy both literally. **Resolution (the defensible senior read):** they operate
at different layers.
- R2 is the **business rule**: conflicts with existing bookings are *expected*, not errors → skip
  those instances, create the rest, and report what was skipped.
- R1 is the **transactional rule**: any *unexpected* failure (invalid input, unknown room, DB error,
  crash mid-write) must leave **zero** rows behind. One DB transaction wraps the whole operation.
- Edge case: if **every** instance conflicts, nothing is saved and the API returns 409 (an empty
  series is a failure, not a success with 0 bookings).
- This resolution goes in `DECISIONS.md`, and "R1 vs R2: confirm skip-and-report is the intended
  behavior" goes in the PM-questions section.

### Trap 2 — The Denver "hour off" bug is a DST bug, and the fix is to NOT convert to UTC
R3 (same wall-clock time weekly) + C1 (naive local ISO storage) + the office manager's "Denver
bookings an hour off" all point at the same thing: the prototype converted to UTC somewhere, and
weekly recurrence computed as `utc_instant + 7 days` drifts one hour across a DST transition
(Denver: `America/Denver`, Berlin: `Europe/Berlin`).

**The correct architecture is radically simple: every timestamp in this system is a NAIVE LOCAL
datetime in the room's own timezone. Never convert to UTC. Anywhere.**
- Weekly recurrence = pure date arithmetic on the naive datetime (`date + 7 days`, same
  wall-clock time). This is automatically DST-correct because wall-clock time is the invariant.
- Conflict checks compare naive datetimes **within a single room**. A room is in exactly one
  timezone, so naive comparison is always valid. Cross-room comparison never happens (conflicts
  are per-room by R4).
- Timezone awareness (`zoneinfo`) is needed in exactly TWO places:
  1. Computing "now" in a room's local time (for "cancel future instances" and validation).
  2. Detecting **nonexistent local times** (spring-forward gap, e.g. 02:30 on 2026-03-08 in
     Denver does not exist) — flag/skip these instances with a reason.
- This satisfies C1 for free (stored = returned = naive local ISO) and explains the Denver bug in
  `DECISIONS.md`, which will score heavily.

### Trap 3 — R5 contradicts C2's sample data
R5 says rooms are numbered sequentially 1..N. C2's sample response shows IDs **3, 4, 9, 17**.
Trust the data over the prose: never assume sequential IDs. Iterate rooms by querying actual IDs
from the DB. Seed data uses the exact four rooms from the sample. Note the contradiction in
`DECISIONS.md`.

### Trap 4 — C1 and C2 are contracts you must NOT "improve"
- All booking timestamps in requests and responses: `YYYY-MM-DDTHH:MM:SS` — no offset, no `Z`,
  no microseconds. **Reject** input containing an offset with a 422 and a helpful message.
- `GET /rooms` returns **exactly** `[{"id": ..., "name": ..., "capacity": ...}]` — a bare JSON
  array, no wrapper object, no extra keys. Room timezone/office is exposed elsewhere (or not at
  all in v1). Whether an additive `office` field is safe for the dashboard → PM question.
- Write a **regression test** for each contract (see Phase 6). This shows a "testing mindset" per
  the JD.

### Trap 5 — The office manager's complaint is a product requirement in disguise
"Someone can actually get rid of a whole series easily" → series cancellation must be a
**first-class, single API call** (`DELETE /series/{id}`), cancel all *future* instances, keep
*past* ones (per the brief), where "future" is evaluated against **now in the room's local
timezone**. Use **soft delete** (status flag), never hard delete — the nightly reporting job and
audit needs argue for it.

### What the JD tells you to optimize for
Testing mindset, edge cases, failure modes, fault tolerance, clear decisions. **A focused
submission with good decisions beats an exhaustive one.** Spend effort on: correctness of the
five traps, the test suite, `DECISIONS.md`, README clarity, clean commits. Do NOT spend effort
on: auth, users table, admin UI, pagination, room CRUD.

---

## 1. Final Architecture Decisions (locked)

| Decision | Choice | Why |
|---|---|---|
| Interface | REST API (FastAPI) | C2 references `GET /rooms`; matches resume; Swagger UI free demo. Justify in README per the brief. |
| Storage | SQLite via SQLAlchemy 2.x | Zero reviewer setup; real transactions needed for R1; trivially swappable to Postgres. |
| Timestamps | Naive local datetime per room's timezone, everywhere | See Trap 2. |
| Recurrence | Weekly only, computed by date arithmetic, all instances generated up front | Per the brief. |
| Delete | Soft delete (`status = cancelled`) | Reporting job, audit, office-manager story. |
| Timezone data | `rooms.timezone` column (IANA name), seeded per office | Berlin rooms: `Europe/Berlin`; Denver rooms: `America/Denver`. Assumed mapping → DECISIONS. |
| Python | 3.11+ (needs `zoneinfo`, modern typing) | stdlib zoneinfo, no pytz. |
| Extras | Dockerfile, GitHub Actions CI, live deploy (Render), Swagger demo | JD good-to-haves; time budget allows. |

### Repository layout (create exactly this)
```
roomloop/
├── app/
│   ├── __init__.py
│   ├── main.py            # FastAPI app, routers, exception handlers
│   ├── db.py              # engine, session factory, Base
│   ├── models.py          # SQLAlchemy models: Room, BookingSeries, Booking
│   ├── schemas.py         # Pydantic request/response models + timestamp validators
│   ├── config.py          # DB path, constants (MAX_HORIZON_DAYS etc.)
│   ├── time_utils.py      # naive-ISO parse/format, local now, nonexistent-time check
│   └── services/
│       ├── __init__.py
│       ├── conflicts.py   # overlap predicate + conflict query
│       ├── bookings.py    # create single, cancel single
│       └── recurrence.py  # expand series, create recurring (the R1/R2 transaction)
├── tests/
│   ├── conftest.py        # fresh in-memory/tmp DB per test, TestClient fixture, seed rooms
│   ├── test_time_utils.py
│   ├── test_conflicts.py
│   ├── test_single_booking.py
│   ├── test_recurring.py
│   ├── test_dst.py        # the money tests
│   ├── test_cancel.py
│   └── test_contracts.py  # C1/C2 regression tests
├── seed.py                # idempotent: creates DB, inserts the 4 sample rooms
├── demo.sh                # curl walkthrough incl. the DST scenario (test data deliverable)
├── requirements.txt
├── Dockerfile
├── .github/workflows/ci.yml
├── .gitignore             # *.db, __pycache__, .venv, .pytest_cache
├── README.md
└── DECISIONS.md
```

`requirements.txt`: `fastapi`, `uvicorn[standard]`, `sqlalchemy>=2.0`, `pydantic>=2`,
`pytest`, `httpx` (for TestClient). Nothing else. No `pytz`, no `dateutil`.

---

## 2. Data Model (exact)

```python
class Room(Base):
    __tablename__ = "rooms"
    id: int            # PK, NOT autoincrement-seeded — explicit IDs (3,4,9,17)
    name: str          # unique, not null
    capacity: int      # > 0
    office: str        # "berlin" | "denver"
    timezone: str      # IANA: "Europe/Berlin" | "America/Denver"

class BookingSeries(Base):
    __tablename__ = "booking_series"
    id: int                    # PK autoincrement
    room_id: int               # FK rooms.id
    user: str                  # not null, non-empty
    start_time: str            # "HH:MM:SS" wall-clock
    end_time: str
    first_date: date           # date of first occurrence
    repeat_until: date         # inclusive
    status: str                # "active" | "cancelled"
    created_at: datetime

class Booking(Base):
    __tablename__ = "bookings"
    id: int                    # PK autoincrement
    room_id: int               # FK rooms.id, indexed
    user: str
    start: datetime            # NAIVE local; stored via SQLAlchemy DateTime (SQLite TEXT ISO)
    end: datetime              # NAIVE local
    series_id: int | None      # FK booking_series.id, nullable
    status: str                # "active" | "cancelled"
    created_at: datetime
# Composite index: (room_id, start). CHECK constraint or app-level: end > start.
```

Verify SQLite round-trips `datetime(2026, 7, 2, 9, 0, 0)` → `"2026-07-02T09:00:00"` with no
microseconds when serialized (format explicitly in the response layer; never rely on default
`str()`; strip microseconds on input).

### Seed data (`seed.py`) — must match C2's sample exactly
```
id=3,  name="Aurora", capacity=8,  office="berlin", timezone="Europe/Berlin"
id=4,  name="Basalt", capacity=4,  office="berlin", timezone="Europe/Berlin"
id=9,  name="Cinder", capacity=12, office="denver", timezone="America/Denver"
id=17, name="Dune",   capacity=6,  office="denver", timezone="America/Denver"
```
Idempotent: running twice does not duplicate or error (INSERT OR IGNORE / check-then-insert).

---

## 3. API Contract (exact)

All timestamps in requests AND responses: `YYYY-MM-DDTHH:MM:SS` (naive local, seconds precision).
Errors: JSON `{"detail": "..."}` (FastAPI default) — 404 unknown room/booking, 409 conflict,
422 validation.

### 3.1 `GET /rooms`
Returns **bare array, exactly these keys, nothing else** (C2):
```json
[{"id": 3, "name": "Aurora", "capacity": 8}, ...]
```
Internal fields (`office`, `timezone`) must NOT appear. Enforce with a dedicated Pydantic
response model with exactly three fields.

### 3.2 `POST /bookings` — single booking
Request: `{"room_id": 3, "user": "alice@corp.com", "start": "2026-07-02T09:00:00", "end": "2026-07-02T10:00:00"}`
- 201 → `{"id": 1, "room_id": 3, "user": ..., "start": ..., "end": ..., "series_id": null, "status": "active"}`
- 404 unknown room · 409 conflict, body includes `conflicts_with: [<booking ids>]`
- 422: end ≤ start; timestamp has offset/Z; unparseable; empty user; duration > 24h;
  start in the past (per room-local now) — reject with clear message.

### 3.3 `POST /bookings/recurring`
Request:
```json
{"room_id": 9, "user": "bob@corp.com",
 "start": "2026-03-02T09:00:00", "end": "2026-03-02T10:00:00",
 "repeat_until": "2026-04-06"}
```
Weekly repeat is implied (only rule supported); weekday = weekday of `start`; `repeat_until`
inclusive. Response 201:
```json
{"series_id": 1, "created": [{...booking...}, ...],
 "skipped": [{"start": "2026-03-16T09:00:00", "end": "...", "reason": "conflict",
              "conflicts_with": [12]}]}
```
- `skipped[].reason` ∈ `"conflict"` | `"nonexistent_local_time"`.
- 409 if ALL instances are skipped (nothing saved, no series row).
- 422: `repeat_until` before start date; horizon > 366 days (`MAX_HORIZON_DAYS = 366`, prevents
  unbounded generation — the "6 months of Mondays" complaint is real usage, so 1 year is sane);
  start/end not on the same calendar date; plus all 3.2 validations.
- **The entire operation is ONE transaction** (series row + all instances). Any exception →
  rollback, zero rows (R1).

### 3.4 `DELETE /bookings/{id}` — cancel one booking
- 200 `{"id": ..., "status": "cancelled"}`. Sets status, does not delete the row.
- 404 unknown; 409 if already cancelled or already in the past (past bookings are immutable —
  document this choice).
- Works for series instances too (cancels just that occurrence).

### 3.5 `DELETE /series/{id}` — the office manager's endpoint
- Cancels the series AND all its **future** instances (`instance.start >= now in the room's
  local timezone`); past instances untouched (R: "leaves past ones intact").
- 200 → `{"series_id": ..., "cancelled_count": N, "past_left_intact": M}`
- 404 unknown series; idempotent-friendly: second call returns 200 with `cancelled_count: 0`
  (or 409 — pick one, document it).

### 3.6 `GET /bookings?room_id=&user=&from=&to=&include_cancelled=false`
List with optional filters. Not strictly required but needed to demo/verify everything; cheap.

### 3.7 `GET /health` → `{"status": "ok"}` (deploy/CI probe).

---

## 4. Core Algorithms (implement exactly as specified)

### 4.1 Overlap predicate (R4) — `services/conflicts.py`
```python
def overlaps(a_start, a_end, b_start, b_end) -> bool:
    return a_start < b_end and a_end > b_start
```
Strict inequalities ⇒ back-to-back (10:00 end / 10:00 start) is NOT a conflict. Conflict query:
active bookings only (`status == "active"`), same `room_id`, `overlaps(...)` translated to SQL
(`Booking.start < new_end AND Booking.end > new_start`). **Cancelled bookings never block.**

### 4.2 Recurrence expansion — `services/recurrence.py`
```python
def expand(start_dt: datetime, end_dt: datetime, repeat_until: date) -> list[tuple[datetime, datetime]]:
    out, s, e = [], start_dt, end_dt
    while s.date() <= repeat_until:
        out.append((s, e))
        s += timedelta(days=7)   # naive arithmetic == wall-clock preserved. THE DST FIX.
        e += timedelta(days=7)
    return out
```
**FORBIDDEN:** converting to UTC/aware datetimes before adding the timedelta, `dateutil.rrule`
with tz-aware datetimes, `pytz.localize` — any of these reintroduces the Denver bug.

### 4.3 Nonexistent local time detection — `time_utils.py`
A naive local time is nonexistent if it falls in the spring-forward gap (e.g. 02:30,
2026-03-08, America/Denver). Detection with stdlib zoneinfo:
```python
def is_nonexistent(dt_naive: datetime, tz: ZoneInfo) -> bool:
    # A gap time maps fold=0 and fold=1 to different offsets AND
    # round-tripping through UTC does not return the same wall clock.
    aware = dt_naive.replace(tzinfo=tz)
    return aware.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None) != dt_naive
```
Recurring creation: skip such instances with `reason: "nonexistent_local_time"`. Single
booking at a nonexistent time: 422. Ambiguous times (fall-back hour, occurs twice): allow,
store as-is — naive storage is inherently ambiguous for that one hour; note in DECISIONS.

### 4.4 Room-local "now" — `time_utils.py`
```python
def local_now(room) -> datetime:
    return datetime.now(ZoneInfo(room.timezone)).replace(tzinfo=None, microsecond=0)
```
Used for: past-booking rejection, series cancellation cutoff. **Never `datetime.utcnow()` or
bare `datetime.now()`** for business logic — server tz ≠ room tz.

### 4.5 The R1/R2 transaction — `services/recurrence.py`
```
begin transaction
  validate room exists, inputs valid (422/404 → nothing written)
  instances = expand(...)
  if len(instances) == 0: 422
  for each instance:
      nonexistent local time → skipped(reason=nonexistent_local_time)
      conflict against DB *and against instances already accepted in this request* → skipped(conflict)
      else → accepted
  if accepted is empty: raise 409 → rollback (no series row)
  insert series row, insert accepted bookings
commit  # any exception anywhere → rollback → zero rows (R1)
```
Note the self-conflict check: don't insert-and-query mid-loop; track accepted intervals in
memory. For SQLite concurrency, open the transaction with `BEGIN IMMEDIATE` (SQLAlchemy:
connection-level, or document the single-writer limitation in DECISIONS — acceptable at this
scale, say so explicitly).

### 4.6 Timestamp parsing/formatting — `time_utils.py` + Pydantic validators
- Parse: accept ONLY `YYYY-MM-DDTHH:MM:SS` (optionally without seconds → normalize to :00).
  If the string contains `+`, `-` after the time part, or `Z` → 422:
  `"Timestamps must be naive local time (YYYY-MM-DDTHH:MM:SS) per the reporting contract; got an offset."`
- Format: `dt.strftime("%Y-%m-%dT%H:%M:%S")` — one function, used by every response path.

---

## 5. Implementation Phases and Gates

Work in this order. Commit at the end of each phase with the message shown — the reviewer WILL
read the commit history; it must tell a story, not be one `"final"` dump.

**Phase 1 — Skeleton + DB + seed** (`feat: project skeleton, models, seed data`)
Layout from §1, models from §2, `seed.py`, `GET /health`, `GET /rooms`.
GATE: `python seed.py && uvicorn app.main:app` runs; `curl /rooms` returns the exact C2 array;
`seed.py` run twice → no duplicates.

**Phase 2 — Time utilities** (`feat: naive-local time utils with DST-gap detection`)
`time_utils.py` complete + `tests/test_time_utils.py` passing (see Phase-6 list).
GATE: `pytest tests/test_time_utils.py` green.

**Phase 3 — Single bookings + conflicts** (`feat: single booking create/cancel with conflict detection`)
§3.2, §3.4, §4.1, all validations.
GATE: `pytest tests/test_conflicts.py tests/test_single_booking.py` green.

**Phase 4 — Recurring bookings** (`feat: recurring bookings — atomic skip-and-report creation`)
§3.3, §4.2, §4.5.
GATE: `pytest tests/test_recurring.py tests/test_dst.py` green. **test_dst.py is the highest-value
file in the repo; do not proceed with any failure or skip here.**

**Phase 5 — Series cancellation + listing** (`feat: series cancellation, booking list endpoint`)
§3.5, §3.6.
GATE: `pytest tests/test_cancel.py` green.

**Phase 6 — Contract regression tests + full suite** (`test: C1/C2 contract regression tests`)
GATE: entire `pytest -q` green; coverage of the checklist in §6 below is 100% by inspection.

**Phase 7 — Packaging** (`chore: dockerfile, CI, demo script`)
- `Dockerfile`: `python:3.12-slim`, copy, install, `seed.py` at startup if DB missing,
  `uvicorn --host 0.0.0.0 --port 8000`. GATE: `docker build . && docker run -p 8000:8000` →
  `curl localhost:8000/health` ok.
- `.github/workflows/ci.yml`: on push/PR → setup Python 3.12, `pip install -r requirements.txt`,
  `pytest -q`. GATE: green run on GitHub after push.
- `demo.sh` (test-data deliverable): numbered, commented curl sequence that (1) lists rooms,
  (2) books Cinder (Denver), (3) creates a Denver weekly series crossing 2026-03-08 spring-forward
  and prints the timestamps proving wall-clock stability, (4) creates a partially-conflicting
  series showing `skipped`, (5) back-to-back non-conflict, (6) cancels the series and shows past
  instances intact. GATE: runs top-to-bottom against a fresh seeded server without error.

**Phase 8 — Docs** (`docs: README and DECISIONS`) — content in §7.

**Phase 9 — Deploy + submission** — §8.

---

## 6. Test Checklist (every box = at least one test; name tests after the behavior)

**test_time_utils.py**
- [ ] parses `2026-07-02T09:00:00`; normalizes missing seconds
- [ ] rejects `2026-07-02T09:00:00+02:00`, `...Z`, garbage
- [ ] formats without microseconds/offset
- [ ] `is_nonexistent`: 2026-03-08T02:30:00 America/Denver → True; 03:30 same day → False;
      2026-03-29T02:30:00 Europe/Berlin → True
- [ ] fall-back ambiguous time (2026-11-01T01:30:00 Denver) → allowed (not nonexistent)

**test_conflicts.py** (pure unit tests on the predicate + query)
- [ ] partial overlap → conflict; containment → conflict; identical interval → conflict
- [ ] back-to-back (end == next start) → NOT a conflict (R4, both directions)
- [ ] same interval different room → NOT a conflict
- [ ] cancelled booking → NOT a conflict

**test_single_booking.py**
- [ ] create → 201, response echoes naive ISO exactly
- [ ] unknown room → 404; end ≤ start → 422; offset timestamp → 422; empty user → 422;
      past start → 422; >24h → 422; nonexistent local time → 422
- [ ] conflicting → 409 with `conflicts_with` ids
- [ ] cancel → 200; re-cancel → 409/documented; cancelled slot can be rebooked

**test_recurring.py**
- [ ] 6-week series → 6 instances, correct dates, `repeat_until` inclusive-boundary test
- [ ] R2: pre-existing booking on week 3 → that instance in `skipped` with reason `conflict`,
      other 5 created, series row exists
- [ ] R1: all instances conflict → 409 AND `bookings` count unchanged AND no series row
- [ ] R1: unknown room → 404, zero rows written
- [ ] intra-series self-conflict impossible (weekly never self-overlaps, but the accepted-set
      check exists — test via two overlapping series in one... skip if not applicable; keep the
      in-memory check tested indirectly)
- [ ] horizon > 366 days → 422; `repeat_until` < start date → 422

**test_dst.py — the tests the reviewer is looking for**
- [ ] Denver (room 9) weekly 09:00 series 2026-02-23 → 2026-03-16 (crosses spring-forward
      2026-03-08): ALL stored/returned starts are `T09:00:00` — assert every instance
- [ ] Denver weekly series crossing fall-back 2026-11-01: same assertion
- [ ] Berlin (room 3) series crossing 2026-03-29: same assertion
- [ ] recurring series where one occurrence lands on a nonexistent time (02:30 weekly, Denver,
      crossing 2026-03-08) → that instance `skipped: nonexistent_local_time`, rest created

**test_cancel.py**
- [ ] series with instances before and after "now": DELETE /series → future cancelled, past
      still `active`, counts correct (freeze/inject clock — make `local_now` injectable via a
      module-level function that tests monkeypatch)
- [ ] cancelled future slots immediately bookable by someone else (office manager's scenario,
      end to end)
- [ ] cancel single instance of a series → only that one cancelled
- [ ] unknown series → 404

**test_contracts.py (C1/C2 regression)**
- [ ] `GET /rooms` == exactly the C2 sample array (keys, types, order-insensitive), and
      `set(keys) == {"id","name","capacity"}` for every element
- [ ] every timestamp string in every booking response matches
      `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$` (regex assert — no offset, no `Z`, no micros)
- [ ] room IDs 3,4,9,17 all bookable (proves no 1..N assumption)

**conftest.py requirements:** fresh tmp-file SQLite per test (in-memory + TestClient thread
issues → use tmp_path), rooms seeded, `local_now` monkeypatchable, TestClient fixture.

---

## 7. Documentation Deliverables

### 7.1 README.md (structure — keep it tight, ~1 screen + reference)
1. One-paragraph summary + **deployed URL** + Swagger link (`/docs`).
2. **Why REST over CLI** (2–3 sentences: C2 implies HTTP consumers; dashboard integration;
   Swagger gives a free demo surface).
3. Quickstart: `pip install -r requirements.txt && python seed.py && uvicorn app.main:app` —
   and the Docker one-liner.
4. Run tests: `pytest -q`. Run demo: `./demo.sh`.
5. API reference table (method, path, purpose, key status codes).
6. **"How timestamps work"** — 4 sentences on the naive-local design and why it fixes the
   Denver hour-off bug. This paragraph is your differentiator; write it clearly.

### 7.2 DECISIONS.md (5–10 bullets — draft; rewrite honestly in your own voice)
**(a) Decisions the brief didn't make for me**
- R1 vs R2 contradict; resolved as: conflicts are business-expected skips (R2), everything else
  is atomic-or-nothing (R1); all-conflict → 409, nothing saved.
- All timestamps are naive local in the room's timezone, never UTC. Weekly recurrence is pure
  date arithmetic, so wall-clock is preserved across DST — this is almost certainly the Denver
  "hour off" bug in the prototype (UTC round-trip across a DST boundary).
- R5 says rooms are 1..N but C2's sample shows IDs 3,4,9,17 — I trusted the data and query
  actual IDs instead of assuming sequential.
- Soft delete instead of hard delete: reporting job reads bookings nightly; keeps audit trail.
- "Future" for series cancellation = now in the room's local tz, not server time.
- Occurrences landing on nonexistent local times (DST gap) are skipped and reported, not
  silently shifted; 366-day cap on series horizon.
**(b) Questions for the PM**
- Confirm R1/R2 resolution: is skip-and-report right, or should users opt in (e.g. a
  `strict=true` flag that makes any conflict fail the whole series)?
- Can the facilities dashboard tolerate an added `office`/`timezone` field on /rooms, or is the
  contract byte-exact?
- Should booking a room in the other office display local or viewer time anywhere? (Storage is
  fine; presentation is unspecified.)
- Past bookings immutable — correct? Max series length of 1 year — acceptable?
**(c) Where AI helped / what it got wrong** — fill in truthfully; e.g. AI drafted scaffolding
and test scaffolds; verify a claim it got wrong and note the correction (reviewers at an AI
company specifically value this bullet being real).
**(d) Left out / next**
- Auth/users, pagination, rate limiting, room admin CRUD — out of scope for the core.
- Next: Postgres + `tstzrange` exclusion constraint for DB-enforced no-overlap; optimistic
  concurrency for simultaneous booking races; monthly/daily recurrence rules; structured logging
  + metrics.

---

## 8. Submission Pipeline (end-to-end)

1. **Repo:** public GitHub repo named `roomloop-booking-service` (github.com/Vrund09). Init with
   `.gitignore` BEFORE first commit (no `.db`, no `__pycache__`, no `.venv` ever committed).
2. **Commits:** the phase commits from §5, pushed as you go. No force-push rewrites at the end.
3. **CI green:** Actions tab shows passing run on the final commit. If red, fix before anything else.
4. **Deploy (Render free tier):** new Web Service from the repo, Docker runtime, port 8000.
   Verify from a phone/incognito: `/health`, `/docs`, `GET /rooms`. SQLite on ephemeral disk is
   fine for a demo — say so in README. Put the URL at the top of the README.
5. **Final pass — pre-submission checklist (ALL must be checked):**
   - [ ] `git clone` into a fresh directory → README quickstart works verbatim, first try
   - [ ] `pytest -q` green in the fresh clone; count the tests (~35+); no skipped DST tests
   - [ ] `./demo.sh` runs clean against the fresh server
   - [ ] `GET /rooms` byte-shape check against C2 sample one last time
   - [ ] Every timestamp in every demo response has no offset/Z (grep the demo output for `+0` and `Z`)
   - [ ] DECISIONS.md has all four sections (a–d), 5–10 bullets total, honest AI bullet
   - [ ] README has deployed URL, REST-vs-CLI justification, run + test instructions
   - [ ] No secrets, no `.db` files, no dead code, no TODOs left in the repo
   - [ ] Repo is public (open it logged-out) 
6. **Share the link** in whatever channel they specified, with a 2–3 sentence note: what you
   built, the one decision you're most confident in (naive-local time design), and that
   DECISIONS.md has your open questions. Do not write an essay in the email.

---

## 9. Hard Rules for the Implementing Agent (DO NOT VIOLATE)

1. **NEVER convert booking times to UTC or attach tzinfo to stored/returned datetimes.**
2. **NEVER change the `GET /rooms` response shape** — three keys, bare array.
3. **NEVER hard-delete rows.**
4. **NEVER assume room IDs are 1..N or contiguous.**
5. **NEVER use `datetime.utcnow()`/naive `datetime.now()` for business "now"** — only
   `local_now(room)`.
6. Overlap predicate uses **strict** `<`/`>` — no `<=`.
7. Recurring creation is **one transaction**; no partial writes on any exception path.
8. Every response timestamp goes through the single shared formatter.
9. Do not add dependencies beyond requirements.txt (no pytz, no dateutil, no pandas).
10. Do not mark a phase done with failing/skipped tests. Each gate is blocking.
11. Keep functions small and typed; Pydantic models for every request/response body.
12. If a requirement seems ambiguous, choose the interpretation in this spec and add a
    DECISIONS.md bullet — never invent new endpoints or features not listed here.
