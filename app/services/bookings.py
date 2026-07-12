"""Single-booking creation and cancellation, plus shared validation helpers.

The validation helpers here are reused by the recurring-series service so the
two paths enforce identical rules.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app import time_utils
from app.config import MAX_BOOKING_HOURS, STATUS_ACTIVE, STATUS_CANCELLED
from app.errors import ConflictError, NotFoundError, UnprocessableError
from app.models import Booking, Room
from app.services.conflicts import find_conflicts


def get_room_or_404(session: Session, room_id: int) -> Room:
    room = session.get(Room, room_id)
    if room is None:
        raise NotFoundError(f"Room {room_id} not found.")
    return room


def validate_duration(start: datetime, end: datetime) -> None:
    if end <= start:
        raise UnprocessableError("end must be after start.")
    if end - start > timedelta(hours=MAX_BOOKING_HOURS):
        raise UnprocessableError(
            f"Booking duration must not exceed {MAX_BOOKING_HOURS} hours."
        )


def validate_exists_in_tz(room: Room, start: datetime, end: datetime) -> None:
    """Reject a single booking whose start or end is a DST-gap (nonexistent) time."""
    tz = ZoneInfo(room.timezone)
    if time_utils.is_nonexistent(start, tz) or time_utils.is_nonexistent(end, tz):
        raise UnprocessableError(
            "start/end falls in a spring-forward gap and does not exist in "
            f"{room.timezone}."
        )


def validate_not_past(room: Room, start: datetime) -> None:
    if start < time_utils.local_now(room):
        raise UnprocessableError("start is in the past (evaluated in the room's local time).")


def create_single(
    session: Session,
    room_id: int,
    user: str,
    start: datetime,
    end: datetime,
) -> Booking:
    room = get_room_or_404(session, room_id)
    validate_duration(start, end)
    validate_exists_in_tz(room, start, end)
    validate_not_past(room, start)

    conflicts = find_conflicts(session, room.id, start, end)
    if conflicts:
        raise ConflictError("Booking conflicts with existing bookings.", conflicts)

    booking = Booking(
        room_id=room.id,
        user=user,
        start=start,
        end=end,
        series_id=None,
        status=STATUS_ACTIVE,
        created_at=time_utils.local_now(room),
    )
    session.add(booking)
    session.commit()
    session.refresh(booking)
    return booking


def cancel_single(session: Session, booking_id: int) -> Booking:
    booking = session.get(Booking, booking_id)
    if booking is None:
        raise NotFoundError(f"Booking {booking_id} not found.")
    if booking.status == STATUS_CANCELLED:
        raise ConflictError("Booking is already cancelled.")

    room = session.get(Room, booking.room_id)
    if booking.start < time_utils.local_now(room):
        raise ConflictError("Past bookings are immutable and cannot be cancelled.")

    booking.status = STATUS_CANCELLED
    session.commit()
    session.refresh(booking)
    return booking
