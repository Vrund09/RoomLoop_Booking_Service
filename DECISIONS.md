# DECISIONS.md

## (a) Decisions the brief left open

- R1 (all-or-nothing) and R2 (skip conflicts) contradict each other, so I split them by layer:
  conflicts with existing bookings are expected business events — skip those instances, create
  the rest, report what was skipped — while everything else (bad input, unknown room, DB error)
  rolls the whole transaction back to zero rows. If every instance conflicts, nothing is saved
  and the API returns 409; an empty series isn't a success.

- Every timestamp is naive local time in the room's own timezone, never UTC. The Denver
  "hour off" complaint is what you get when you convert to UTC, add 7 days, and cross a DST
  boundary — so weekly recurrence here is plain date arithmetic on naive datetimes, and
  wall-clock time is preserved by construction. zoneinfo is used in exactly two places: getting
  "now" in a room's timezone, and detecting spring-forward gap times. Occurrences landing on a
  nonexistent time (02:30 on Denver's spring-forward day) are skipped and reported, not silently
  shifted; single bookings there get a 422.

- The brief says rooms are numbered 1..N, but the dashboard sample shows IDs 3, 4, 9, 17.
  I trusted the data over the prose: those exact IDs are seeded and nothing assumes contiguous
  numbering.

- Cancellation is a soft delete (status flag), because the brief says a nightly reporting job
  reads bookings and hard deletes would rewrite history. Cancelled slots stop counting in conflict checks, so
  they're immediately rebookable — which is the office manager's actual complaint.

- Guardrails: single bookings capped at 24h, series capped at 366 days. Covers "6 months of
  Mondays" with margin without allowing unbounded generation.

## (b) Questions I'd ask the PM before this ships

- Is skip-and-report the right default for recurring conflicts, or do some users need a strict
  mode where any conflict fails the whole series?
- Can GET /rooms safely gain an office/timezone field, or does the dashboard need the exact
  current shape? Related: should a Berlin user see a Denver booking in Denver time or their own?
- Past bookings are immutable here — is there any flow where someone legitimately edits history?
- When a recurring series skips slots due to conflicts, how should users find out and rebook —
  should the API suggest alternative rooms/times for the skipped weeks, or is that the client's
  job?

## (c) Where AI helped, and what it got wrong

- AI bootstrapped the project structure, schemas, and test boilerplate. Three things I had to
  correct: Pydantic's default datetime parsing silently accepts offset and Z-suffixed
  timestamps, which would have violated the naive-local C1 contract — I overrode it with a
  strict mode="before" parser that rejects anything carrying an offset. It wrote tests against
  hardcoded 2026 dates that started failing once the real clock passed them, so I made
  local_now injectable and froze time in tests. And its test setup crashed on Windows because
  zoneinfo's IANA data was missing, which is why tzdata (data-only, not a datetime library) is
  in requirements.

## (d) Deliberately left out, and next

- Left out to stay focused: auth, rate limiting, room admin endpoints.
- Next: move to Postgres with a tstzrange exclusion constraint so the database itself forbids
  overlapping bookings. The current Python-level check-then-insert has a time-of-check-to-
  time-of-use race under concurrent writers — SQLite serializes the writes but not the
  check-plus-write sequence, so two simultaneous requests could double-book a slot. After that,
  daily/monthly recurrence rules.