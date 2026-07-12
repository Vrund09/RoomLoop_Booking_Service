"""Recurring-series expansion and the atomic skip-and-report creation (R1/R2).

R2 (business rule): conflicts with existing bookings are expected — skip those
instances, create the rest, report what was skipped.
R1 (transactional rule): any *unexpected* failure leaves ZERO rows behind. The
series row and all accepted instances are written in one transaction.
Edge case: if every instance is skipped, nothing is saved and we raise 409.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app import time_utils
from app.config import MAX_HORIZON_DAYS, STATUS_ACTIVE
from app.errors import ConflictError, UnprocessableError
from app.models import Booking, BookingSeries
from app.services import bookings as booking_service
from app.services.conflicts import find_conflicts, overlaps


def expand(
    start_dt: datetime,
    end_dt: datetime,
    repeat_until: date,
) -> list[tuple[datetime, datetime]]:
    """Weekly expansion by pure naive date arithmetic — wall-clock preserved.

    THE DST FIX: adding `timedelta(days=7)` to a naive datetime keeps the same
    wall-clock time across DST transitions. Never convert to UTC/aware here.
    """
    out: list[tuple[datetime, datetime]] = []
    s, e = start_dt, end_dt
    while s.date() <= repeat_until:
        out.append((s, e))
        s += timedelta(days=7)
        e += timedelta(days=7)
    return out


def _validate_series_base(
    room, start: datetime, end: datetime, repeat_until: date
) -> None:
    if start.date() != end.date():
        raise UnprocessableError("start and end must fall on the same calendar date.")
    booking_service.validate_duration(start, end)
    if repeat_until < start.date():
        raise UnprocessableError("repeat_until is before the start date.")
    if (repeat_until - start.date()).days > MAX_HORIZON_DAYS:
        raise UnprocessableError(
            f"Series horizon exceeds {MAX_HORIZON_DAYS} days."
        )
    booking_service.validate_not_past(room, start)


def create_recurring(
    session: Session,
    room_id: int,
    user: str,
    start: datetime,
    end: datetime,
    repeat_until: date,
) -> tuple[BookingSeries, list[Booking], list[dict]]:
    room = booking_service.get_room_or_404(session, room_id)
    _validate_series_base(room, start, end, repeat_until)

    instances = expand(start, end, repeat_until)
    if not instances:  # defensive: repeat_until >= start already guaranteed
        raise UnprocessableError("Series produced no occurrences.")

    tz = ZoneInfo(room.timezone)
    accepted: list[tuple[datetime, datetime]] = []
    skipped: list[dict] = []

    for inst_start, inst_end in instances:
        if time_utils.is_nonexistent(inst_start, tz) or time_utils.is_nonexistent(inst_end, tz):
            skipped.append(
                {
                    "start": time_utils.format_naive_iso(inst_start),
                    "end": time_utils.format_naive_iso(inst_end),
                    "reason": "nonexistent_local_time",
                    "conflicts_with": None,
                }
            )
            continue

        db_conflicts = find_conflicts(session, room.id, inst_start, inst_end)
        self_conflict = any(
            overlaps(inst_start, inst_end, a_s, a_e) for a_s, a_e in accepted
        )
        if db_conflicts or self_conflict:
            skipped.append(
                {
                    "start": time_utils.format_naive_iso(inst_start),
                    "end": time_utils.format_naive_iso(inst_end),
                    "reason": "conflict",
                    "conflicts_with": db_conflicts,
                }
            )
            continue

        accepted.append((inst_start, inst_end))

    if not accepted:
        # Empty series is a failure, not a success with 0 bookings. Nothing saved.
        raise ConflictError("All occurrences conflict; no bookings were created.")

    # One transaction: series row + all accepted instances. Any error -> rollback.
    try:
        now = time_utils.local_now(room)
        series = BookingSeries(
            room_id=room.id,
            user=user,
            start_time=start.strftime("%H:%M:%S"),
            end_time=end.strftime("%H:%M:%S"),
            first_date=start.date(),
            repeat_until=repeat_until,
            status=STATUS_ACTIVE,
            created_at=now,
        )
        session.add(series)
        session.flush()  # assign series.id without committing

        created: list[Booking] = []
        for inst_start, inst_end in accepted:
            booking = Booking(
                room_id=room.id,
                user=user,
                start=inst_start,
                end=inst_end,
                series_id=series.id,
                status=STATUS_ACTIVE,
                created_at=now,
            )
            session.add(booking)
            created.append(booking)

        session.commit()
    except Exception:
        session.rollback()
        raise

    for booking in created:
        session.refresh(booking)
    session.refresh(series)
    return series, created, skipped
