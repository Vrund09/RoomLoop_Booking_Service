# Decisions

## Decisions the brief didn't make for me

- **R1 vs R2 (atomic vs skip-and-report) are resolved by layer, not by picking one.**
  Conflicts with existing bookings are a *business-expected* outcome, so those
  instances are skipped and reported (R2). Any *unexpected* failure — bad input,
  unknown room, DB error — aborts the whole operation with zero rows written (R1),
  because the series row and all accepted instances are created in one transaction.
  If *every* instance is skipped, nothing is saved and the API returns 409: an empty
  series is a failure, not a success with zero bookings.

- **All timestamps are naive local time in the room's timezone; never UTC.** Weekly
  recurrence is pure date arithmetic (`+7 days` on the naive datetime), so the
  wall-clock time is preserved across DST transitions. This is almost certainly the
  Denver "hour off" bug in the prototype: converting to UTC and adding 7 days drifts
  by an hour across a spring-forward/fall-back boundary. Conflict checks are always
  within a single room, and a room is in exactly one timezone, so naive comparison is
  always valid.

- **Occurrences on nonexistent local times are skipped and reported, not shifted.**
  A weekly series whose time lands in a spring-forward gap (e.g. 02:30 during the
  US transition) has that one instance skipped with reason `nonexistent_local_time`;
  the rest are created. A *single* booking at a nonexistent time is rejected (422).
  Fall-back ambiguous times (the hour that occurs twice) are allowed and stored
  as-is — naive storage is inherently ambiguous for that one hour, which is acceptable
  here and noted rather than hidden.

- **Room IDs are read from the data, not assumed to be 1..N.** The prose says rooms
  are numbered sequentially, but the sample response shows IDs 3, 4, 9, 17. I trusted
  the data: rooms are seeded with those explicit IDs and always queried by actual id.

- **Soft delete, never hard delete.** Cancelling sets a `status` flag. This keeps an
  audit trail and supports the nightly reporting job. Cancelled bookings never block
  new bookings, so a freed slot is immediately re-bookable.

- **"Future" for series cancellation is evaluated in the room's local time**, not
  server time. `DELETE /series/{id}` cancels the series and all instances at or after
  local "now", and leaves past instances intact.

- **Guardrails I chose:** back-to-back bookings do not conflict (strict `<`/`>`
  overlap); a single booking may not exceed 24h; a series horizon may not exceed 366
  days (the "6 months of Mondays" request is real, so one year is a sane ceiling);
  bookings in the past are rejected and past bookings are immutable; re-cancelling a
  series is idempotent (returns 200 with `cancelled_count: 0`) rather than an error.

- **Added `tzdata` to requirements** (see AI note below). It is a data-only package,
  not `pytz`/`dateutil` — it is the IANA timezone database that stdlib `zoneinfo`
  needs on systems without a system tz database (Windows, and the CI runner). The
  spec's "no pytz/dateutil" rule is about not pulling in alternative date libraries;
  `tzdata` is the officially recommended companion to stdlib `zoneinfo`.

## Questions for the PM

- **Confirm the R1/R2 resolution.** Is skip-and-report the intended behavior, or
  should there be an opt-in `strict=true` that makes any conflict fail the whole
  series?
- **Is the `GET /rooms` contract byte-exact?** I kept it to `{id, name, capacity}`.
  Can the dashboard tolerate an additive `office`/`timezone` field, or must the shape
  never change?
- **Presentation of cross-office times.** Storage is naive-local and unambiguous;
  should any view ever render a booking in the viewer's local time instead of the
  room's? Unspecified today.
- **Are the ceilings right?** Past bookings immutable, max series length one year —
  acceptable, or do real workflows need to edit history / book further out?

## Where AI helped and what it got wrong

This build was AI-assisted. AI was good at scaffolding the layout, the service
functions, and the test suite, and at articulating the naive-local design.

The most useful correction was real, not cosmetic: the first `requirements.txt`
followed the brief literally (fastapi, uvicorn, sqlalchemy, pydantic, pytest, httpx)
and **the DST tests failed immediately** on Windows and would have failed in CI —
`ZoneInfo("America/Denver")` raised `ZoneInfoNotFoundError` because there was no
system IANA database. Adding `tzdata` fixed it. A second gotcha AI had to reconcile:
the past-booking guard rejects the spec's own example dates (they're in the past
relative to the real clock), which is exactly why "now" is an injectable function —
the tests freeze it to book historical DST dates deterministically.

## Left out / next

- **Out of scope on purpose:** auth, a users table, pagination, rate limiting, and
  room-admin CRUD. The brief points at correctness, edge cases, and clear decisions,
  not surface area.
- **Next steps:** move to Postgres with a `tstzrange` exclusion constraint so no
  overlap is enforced by the database; add optimistic concurrency for simultaneous
  booking races (SQLite is single-writer, which is fine at this scale but worth
  stating); support daily/monthly recurrence rules; and add structured logging and
  metrics.
