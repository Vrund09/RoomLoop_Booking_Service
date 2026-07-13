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
