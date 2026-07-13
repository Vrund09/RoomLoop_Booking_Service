"""FastAPI application: routers, endpoints, exception handlers."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Base, engine, get_session
from app.errors import AppError, UnprocessableError
from app.models import Room
from app.schemas import (
    BookingCreate,
    BookingOut,
    CancelOut,
    RecurringCreate,
    RecurringOut,
    RoomOut,
    SeriesCancelOut,
    serialize_booking,
)
from app.time_utils import TimestampError, parse_naive_iso
from app.services import bookings as booking_service
from app.services import recurrence as recurrence_service


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Create tables if the DB has not been initialised. seed.py handles data.
    Base.metadata.create_all(bind=engine)
    yield


API_DESCRIPTION = (
    "Book meeting rooms across offices in different timezones, with weekly "
    "recurring bookings and one-call series cancellation.\n\n"
    "**Timestamps** in every request and response are *naive local time* in the "
    "room's own timezone, formatted `YYYY-MM-DDTHH:MM:SS` — **no** timezone offset, "
    "`Z`, or microseconds (any of those is rejected with 422). Seeded rooms have "
    "ids **3, 4, 9, 17** (not 1..N). Bookings must start in the future (room-local). "
    "This is a demo: data is ephemeral and reseeds when the instance restarts."
)

app = FastAPI(
    title="RoomLoop Booking Service",
    version="1.0.0",
    description=API_DESCRIPTION,
    lifespan=lifespan,
)


@app.exception_handler(AppError)
async def _app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.body())


@app.get("/", include_in_schema=False)
def index() -> dict[str, str]:
    # Friendly landing payload so the bare URL isn't a bare 404. The real
    # surfaces are the interactive docs and the endpoints below.
    return {
        "service": "RoomLoop Booking Service",
        "docs": "/docs",
        "health": "/health",
        "rooms": "/rooms",
    }


@app.get("/health", summary="Liveness probe")
def health() -> dict[str, str]:
    """Return `{\"status\": \"ok\"}` — used by the deploy/CI health check."""
    return {"status": "ok"}


@app.get("/rooms", response_model=list[RoomOut], summary="List bookable rooms")
def list_rooms(session: Session = Depends(get_session)) -> list[Room]:
    """List every room as `{id, name, capacity}`. Ids are 3, 4, 9, 17 (not 1..N)."""
    # Order by id for a stable response; IDs are not assumed contiguous.
    return list(session.scalars(select(Room).order_by(Room.id)).all())


@app.post(
    "/bookings",
    response_model=BookingOut,
    status_code=201,
    summary="Create a single booking",
)
def create_booking(
    payload: BookingCreate,
    session: Session = Depends(get_session),
) -> dict:
    """Create one booking (201). The response `id` is what you pass to
    `DELETE /bookings/{id}` to cancel. Timestamps are naive local
    `YYYY-MM-DDTHH:MM:SS`. 404 unknown room · 409 conflict (with
    `conflicts_with`) · 422 bad/past/too-long times."""
    booking = booking_service.create_single(
        session,
        room_id=payload.room_id,
        user=payload.user,
        start=payload.start,
        end=payload.end,
    )
    return serialize_booking(booking)


@app.post(
    "/bookings/recurring",
    response_model=RecurringOut,
    status_code=201,
    summary="Create a weekly recurring series",
)
def create_recurring_booking(
    payload: RecurringCreate,
    session: Session = Depends(get_session),
) -> dict:
    """Create a weekly series (same wall-clock time each week, DST-stable).
    Returns `created` plus `skipped` (conflicting or nonexistent-DST-gap
    occurrences). If *every* occurrence is skipped, nothing is saved and it
    returns 409. `repeat_until` is inclusive and may be a bare `YYYY-MM-DD`."""
    series, created, skipped = recurrence_service.create_recurring(
        session,
        room_id=payload.room_id,
        user=payload.user,
        start=payload.start,
        end=payload.end,
        repeat_until=payload.repeat_until.date(),
    )
    return {
        "series_id": series.id,
        "created": [serialize_booking(b) for b in created],
        "skipped": skipped,
    }


@app.delete(
    "/bookings/{booking_id}",
    response_model=CancelOut,
    summary="Cancel one booking (soft delete)",
)
def cancel_booking(
    booking_id: int,
    session: Session = Depends(get_session),
) -> dict:
    """Cancel a single booking by its id (from `POST /bookings` or
    `GET /bookings`). Soft delete — the row stays with `status=cancelled`.
    404 unknown · 409 already cancelled or already in the past."""
    booking = booking_service.cancel_single(session, booking_id)
    return {"id": booking.id, "status": booking.status}


@app.delete(
    "/series/{series_id}",
    response_model=SeriesCancelOut,
    summary="Cancel a series and its future instances",
)
def cancel_series(
    series_id: int,
    session: Session = Depends(get_session),
) -> dict:
    """Cancel a whole series by id: cancels every *future* instance (room-local
    now) and leaves past ones intact. Idempotent — a second call cancels 0."""
    cancelled_count, past_left_intact = booking_service.cancel_series(session, series_id)
    return {
        "series_id": series_id,
        "cancelled_count": cancelled_count,
        "past_left_intact": past_left_intact,
    }


def _parse_query_ts(value: str | None, field: str) -> "datetime | None":
    if value is None:
        return None
    try:
        return parse_naive_iso(value)
    except TimestampError as exc:
        raise UnprocessableError(f"Invalid '{field}' filter: {exc}") from exc


@app.get(
    "/bookings",
    response_model=list[BookingOut],
    summary="List / filter bookings",
)
def list_bookings(
    room_id: int | None = Query(default=None, examples=[9]),
    user: str | None = Query(default=None, examples=["vrund"]),
    from_: str | None = Query(default=None, alias="from", examples=["2026-08-01T00:00:00"]),
    to: str | None = Query(default=None, examples=["2026-12-31T00:00:00"]),
    include_cancelled: bool = False,
    session: Session = Depends(get_session),
) -> list[dict]:
    """List bookings, optionally filtered. Each item includes its `id` and
    `status` — this is how you find a booking id to cancel. `from`/`to` are
    naive timestamps (`YYYY-MM-DDTHH:MM:SS`, no offset/`Z`). Cancelled bookings
    are hidden unless `include_cancelled=true`."""
    bookings = booking_service.list_bookings(
        session,
        room_id=room_id,
        user=user,
        start_from=_parse_query_ts(from_, "from"),
        start_to=_parse_query_ts(to, "to"),
        include_cancelled=include_cancelled,
    )
    return [serialize_booking(b) for b in bookings]
