"""Unit tests for the overlap predicate and the conflict query."""
from __future__ import annotations

from datetime import datetime

from app.config import STATUS_CANCELLED
from app.models import Booking
from app.services.conflicts import find_conflicts, overlaps

D = datetime


def test_partial_overlap_conflicts():
    assert overlaps(D(2026, 1, 1, 9), D(2026, 1, 1, 10), D(2026, 1, 1, 9, 30), D(2026, 1, 1, 11))


def test_containment_conflicts():
    assert overlaps(D(2026, 1, 1, 9), D(2026, 1, 1, 12), D(2026, 1, 1, 10), D(2026, 1, 1, 11))


def test_identical_interval_conflicts():
    assert overlaps(D(2026, 1, 1, 9), D(2026, 1, 1, 10), D(2026, 1, 1, 9), D(2026, 1, 1, 10))


def test_back_to_back_not_a_conflict_both_directions():
    # a ends exactly when b starts, and vice versa.
    assert not overlaps(D(2026, 1, 1, 9), D(2026, 1, 1, 10), D(2026, 1, 1, 10), D(2026, 1, 1, 11))
    assert not overlaps(D(2026, 1, 1, 10), D(2026, 1, 1, 11), D(2026, 1, 1, 9), D(2026, 1, 1, 10))


def _add_booking(session, room_id, start, end, status="active"):
    b = Booking(
        room_id=room_id, user="x", start=start, end=end,
        series_id=None, status=status, created_at=D(2026, 1, 1),
    )
    session.add(b)
    session.commit()
    session.refresh(b)
    return b


def test_query_finds_overlap_same_room(session):
    b = _add_booking(session, 3, D(2026, 5, 1, 9), D(2026, 5, 1, 10))
    ids = find_conflicts(session, 3, D(2026, 5, 1, 9, 30), D(2026, 5, 1, 10, 30))
    assert ids == [b.id]


def test_query_ignores_other_room(session):
    _add_booking(session, 3, D(2026, 5, 1, 9), D(2026, 5, 1, 10))
    # Same interval in room 4 must NOT conflict with room 3's booking.
    assert find_conflicts(session, 4, D(2026, 5, 1, 9), D(2026, 5, 1, 10)) == []


def test_query_ignores_cancelled(session):
    _add_booking(session, 3, D(2026, 5, 1, 9), D(2026, 5, 1, 10), status=STATUS_CANCELLED)
    assert find_conflicts(session, 3, D(2026, 5, 1, 9), D(2026, 5, 1, 10)) == []


def test_query_back_to_back_not_conflict(session):
    _add_booking(session, 3, D(2026, 5, 1, 9), D(2026, 5, 1, 10))
    assert find_conflicts(session, 3, D(2026, 5, 1, 10), D(2026, 5, 1, 11)) == []
