# RoomLoop Booking Service

A small REST API for booking meeting rooms across offices in different timezones,
with weekly recurring bookings and one-call series cancellation. It is built around
a single strong idea: **every booking time is a naive local wall-clock time in the
room's own timezone, and is never converted to UTC** — which is what fixes the
"Denver bookings are an hour off" bug.

- **Live demo:** https://roomloop-bba3.onrender.com — see [Deployment](#deployment).
- **Interactive API docs (Swagger):** https://roomloop-bba3.onrender.com/docs (also `/docs` on any running server).

## Why REST (not a CLI)

The prototype's contract (`GET /rooms`) already implies HTTP consumers, and the
facilities dashboard needs to integrate with something. A REST API serves those
consumers directly and gives a free, self-documenting demo surface via Swagger at
`/docs`, which a CLI cannot.

## Quickstart

```bash
pip install -r requirements.txt
python seed.py                 # creates roomloop.db and inserts the 4 rooms
uvicorn app.main:app           # serves on http://127.0.0.1:8000
```

Docker (seeds automatically on startup):

```bash
docker build -t roomloop .
docker run -p 8000:8000 roomloop
```

## Tests & demo

```bash
pytest -q          # full suite
./demo.sh          # narrated curl walkthrough against a running server
```

On Windows, use `python demo.py` (stdlib only).

`demo.sh` lists rooms, books a Denver room, creates a Denver weekly series that
crosses a spring-forward transition (proving every start stays at `09:00:00`),
shows a partially-conflicting series being skip-and-reported, demonstrates that
back-to-back bookings do not conflict, and cancels a whole series in one call.

### Test data (deliverable #2)

The behavior most at risk of being wrong is **weekly recurrence preserving
wall-clock time across a DST boundary** (the Denver "hour off" bug) — closely
followed by **R1/R2 atomicity**: skip conflicts, but roll *everything* back on any
real failure. I constructed test data that targets exactly these:

- **DST wall-clock stability** — `tests/test_dst.py` books a Denver 09:00 series
  across *both* spring-forward and fall-back, plus a Berlin series across
  spring-forward, asserting every occurrence stays at `09:00:00`; `demo.sh`/`demo.py`
  step 3 shows the same live. A separate 02:30 series (step 3b) proves the nonexistent
  spring-forward hour is skipped with `reason: "nonexistent_local_time"`, not silently
  shifted.
- **R1/R2 atomicity** — `tests/test_recurring.py` pre-books one conflicting week and
  asserts exactly that week is skipped (5 created, 1 reported), and that an
  all-conflict or unknown-room request writes **zero rows** — proven by counting
  `bookings`/`booking_series` before and after, not just by the status code.

These are the scenarios I'd expect a naive UTC-based or non-transactional
implementation to get wrong, which is why the data is built around them.

## API reference

All timestamps in requests and responses are `YYYY-MM-DDTHH:MM:SS` — naive local
time, no offset, no `Z`, no microseconds.

| Method | Path | Purpose | Key statuses |
|---|---|---|---|
| GET | `/health` | Liveness probe | 200 |
| GET | `/rooms` | List rooms (bare array of id/name/capacity) | 200 |
| POST | `/bookings` | Create a single booking | 201, 404, 409, 422 |
| POST | `/bookings/recurring` | Create a weekly series (skip-and-report) | 201, 404, 409, 422 |
| DELETE | `/bookings/{id}` | Cancel one booking (soft delete) | 200, 404, 409 |
| DELETE | `/series/{id}` | Cancel a series + all future instances | 200, 404 |
| GET | `/bookings` | List/filter bookings (`room_id`, `user`, `from`, `to`, `include_cancelled`) | 200 |

- **409** on a single booking includes `conflicts_with: [<ids>]`.
- **Recurring** returns `{series_id, created: [...], skipped: [{start, end, reason, conflicts_with}]}`
  where `reason` is `"conflict"` or `"nonexistent_local_time"`. If *every* instance
  is skipped, nothing is saved and the call returns **409**.

## Quick tour (live)

No setup — these run against the deployed demo. Bookable room ids are **3, 4, 9, 17**,
and timestamps are naive local (`YYYY-MM-DDTHH:MM:SS`, no `Z`/offset). Use a
future date. The interactive version is at
[`/docs`](https://roomloop-bba3.onrender.com/docs).

```bash
BASE=https://roomloop-bba3.onrender.com

# 1. See the rooms
curl -s "$BASE/rooms"

# 2. Book one — the response "id" is what you cancel with
curl -s -X POST "$BASE/bookings" -H 'Content-Type: application/json' \
  -d '{"room_id":9,"user":"vrund","start":"2026-08-05T14:00:00","end":"2026-08-05T15:00:00"}'

# 3. Find your bookings (each item carries its id + status)
curl -s "$BASE/bookings?user=vrund"

# 4. Cancel by that id (soft delete -> status becomes "cancelled")
curl -s -X DELETE "$BASE/bookings/1"

# 5. Weekly recurring series (same wall-clock time each week, DST-stable)
curl -s -X POST "$BASE/bookings/recurring" -H 'Content-Type: application/json' \
  -d '{"room_id":9,"user":"vrund","start":"2026-08-03T09:00:00","end":"2026-08-03T10:00:00","repeat_until":"2026-08-31"}'
```

> The free-tier instance sleeps when idle (first request may take ~30s to wake), and
> demo data is ephemeral — it reseeds on restart, so bookings you create won't persist.

## How timestamps work

Every booking datetime is stored and returned as a naive local wall-clock time in
the room's own timezone; the system never attaches a UTC offset. Weekly recurrence
is therefore just `date + 7 days` on the naive value, which keeps the wall-clock
time identical across daylight-saving transitions — the root cause of the Denver
"hour off" bug was a UTC round-trip that drifted an hour across a DST boundary.
Timezone awareness (`zoneinfo`) is used in exactly two narrow places: computing
"now" in a room's local time, and detecting nonexistent spring-forward times so
those occurrences are skipped and reported rather than silently shifted.

## Deployment

Deployed on Render's free tier (Docker runtime) via the checked-in
[`render.yaml`](render.yaml) blueprint — `New -> Blueprint -> connect this repo`, no
env vars or disks needed. The container seeds SQLite on startup and honors the
host-injected `PORT` (defaulting to 8000 for a plain `docker run`).

- **Live demo:** https://roomloop-bba3.onrender.com — Swagger at https://roomloop-bba3.onrender.com/docs.
- The free-tier instance sleeps when idle, so the first request after a while may take
  ~30s to wake (cold start).
- Demo data is ephemeral by design: the database reseeds on each deploy, which is
  intentional for a throwaway demo service.

Local Docker:

```bash
docker build -t roomloop .
docker run -p 8000:8000 roomloop
```

See [DECISIONS.md](DECISIONS.md) for the design trade-offs and open questions.
