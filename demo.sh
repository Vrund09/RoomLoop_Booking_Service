#!/usr/bin/env bash
#
# RoomLoop demo — a narrated curl walkthrough of the whole service.
#
# Usage:
#   1. Start a fresh, seeded server:  python seed.py && uvicorn app.main:app
#   2. In another shell:              ./demo.sh   (or ./demo.sh http://host:port)
#
# Dates are intentionally in the future so the "no booking in the past" guard
# (evaluated in the room's local time) does not reject them. The DST scenarios
# straddle the 2027-03-14 US spring-forward transition.

set -euo pipefail
BASE="${1:-http://localhost:8000}"

# Pretty-print JSON if python is available; otherwise pass through raw.
pp() { python -m json.tool 2>/dev/null || cat; }
say() { printf "\n\033[1m== %s ==\033[0m\n" "$1"; }

say "1. List rooms (C2 contract: bare array of id/name/capacity)"
curl -s "$BASE/rooms" | pp

say "2. Book Cinder (room 9, Denver) — single booking"
curl -s -X POST "$BASE/bookings" -H 'Content-Type: application/json' -d '{
  "room_id": 9, "user": "alice@corp.com",
  "start": "2026-08-03T09:00:00", "end": "2026-08-03T10:00:00"
}' | pp

say "3. Denver weekly series 09:00 crossing the 2027-03-14 spring-forward"
echo "   Every start MUST stay at T09:00:00 — this is the Denver 'hour off' fix."
curl -s -X POST "$BASE/bookings/recurring" -H 'Content-Type: application/json' -d '{
  "room_id": 9, "user": "bob@corp.com",
  "start": "2027-03-01T09:00:00", "end": "2027-03-01T10:00:00",
  "repeat_until": "2027-03-22"
}' | pp

say "3b. Denver weekly 02:30 crossing 2027-03-14 — the gap instance is skipped"
echo "   2027-03-14T02:30:00 does not exist -> reason: nonexistent_local_time."
curl -s -X POST "$BASE/bookings/recurring" -H 'Content-Type: application/json' -d '{
  "room_id": 9, "user": "bob@corp.com",
  "start": "2027-03-07T02:30:00", "end": "2027-03-07T03:30:00",
  "repeat_until": "2027-03-21"
}' | pp

say "4. Partially-conflicting series — pre-book one week, then create the series"
curl -s -X POST "$BASE/bookings" -H 'Content-Type: application/json' -d '{
  "room_id": 4, "user": "eve@corp.com",
  "start": "2026-09-14T09:30:00", "end": "2026-09-14T10:30:00"
}' > /dev/null
echo "   Series below overlaps the 2026-09-14 pre-booking -> that week is skipped."
SERIES=$(curl -s -X POST "$BASE/bookings/recurring" -H 'Content-Type: application/json' -d '{
  "room_id": 4, "user": "bob@corp.com",
  "start": "2026-09-07T09:00:00", "end": "2026-09-07T10:00:00",
  "repeat_until": "2026-09-28"
}')
echo "$SERIES" | pp
SERIES_ID=$(echo "$SERIES" | python -c 'import sys,json;print(json.load(sys.stdin)["series_id"])')

say "5. Back-to-back bookings are NOT a conflict (strict overlap)"
curl -s -X POST "$BASE/bookings" -H 'Content-Type: application/json' -d '{
  "room_id": 3, "user": "carol@corp.com",
  "start": "2026-08-10T10:00:00", "end": "2026-08-10T11:00:00"
}' | pp
curl -s -X POST "$BASE/bookings" -H 'Content-Type: application/json' -d '{
  "room_id": 3, "user": "dave@corp.com",
  "start": "2026-08-10T11:00:00", "end": "2026-08-10T12:00:00"
}' | pp

say "6. Cancel the whole series in one call (the office-manager endpoint)"
echo "   All future instances are cancelled; past instances would be left intact"
echo "   (past-intact is proven in tests/test_cancel.py via injected clock)."
curl -s -X DELETE "$BASE/series/$SERIES_ID" | pp

say "Done."
