"""Overlap predicate (R4) and the conflict query.

Strict inequalities: back-to-back bookings (one ends exactly when the next
starts) do NOT conflict. Only active bookings in the SAME room block; cancelled
bookings never block. Naive comparison is always valid because a room lives in
exactly one timezone.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import STATUS_ACTIVE
from app.models import Booking


def overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    """True iff intervals [a_start, a_end) and [b_start, b_end) overlap."""
    return a_start < b_end and a_end > b_start


def find_conflicts(
    session: Session,
    room_id: int,
    start: datetime,
    end: datetime,
) -> list[int]:
    """Return ids of active bookings in `room_id` that overlap [start, end)."""
    stmt = select(Booking.id).where(
        Booking.room_id == room_id,
        Booking.status == STATUS_ACTIVE,
        Booking.start < end,
        Booking.end > start,
    )
    return list(session.scalars(stmt).all())
