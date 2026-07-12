"""Tests for DELETE /series/{id} and single-instance cancellation."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from app.models import Booking


def _make_series(client):
    # 6 weekly Mondays: 2026-05-04 .. 2026-06-08 in room 3.
    r = client.post(
        "/bookings/recurring",
        json={
            "room_id": 3,
            "user": "bob@corp.com",
            "start": "2026-05-04T09:00:00",
            "end": "2026-05-04T10:00:00",
            "repeat_until": "2026-06-08",
        },
    )
    assert r.status_code == 201
    return r.json()["series_id"]


def test_series_cancel_future_only(client, session, freeze_now):
    freeze_now(datetime(2026, 1, 1))  # all instances future at creation
    series_id = _make_series(client)

    # Move "now" to 2026-05-20: 05-04/05-11/05-18 are past, rest future.
    freeze_now(datetime(2026, 5, 20, 0, 0, 0))
    r = client.delete(f"/series/{series_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["cancelled_count"] == 3
    assert body["past_left_intact"] == 3

    rows = session.scalars(
        select(Booking).where(Booking.series_id == series_id).order_by(Booking.start)
    ).all()
    statuses = {b.start.strftime("%Y-%m-%d"): b.status for b in rows}
    assert statuses["2026-05-04"] == "active"
    assert statuses["2026-05-18"] == "active"
    assert statuses["2026-05-25"] == "cancelled"
    assert statuses["2026-06-08"] == "cancelled"


def test_cancelled_future_slot_is_rebookable(client, freeze_now):
    freeze_now(datetime(2026, 1, 1))
    series_id = _make_series(client)

    freeze_now(datetime(2026, 5, 20, 0, 0, 0))
    assert client.delete(f"/series/{series_id}").status_code == 200

    # The office-manager scenario: a freed future slot is bookable by someone else.
    r = client.post(
        "/bookings",
        json={
            "room_id": 3,
            "user": "alice@corp.com",
            "start": "2026-05-25T09:00:00",
            "end": "2026-05-25T10:00:00",
        },
    )
    assert r.status_code == 201


def test_series_cancel_idempotent(client, freeze_now):
    freeze_now(datetime(2026, 1, 1))
    series_id = _make_series(client)
    freeze_now(datetime(2026, 5, 20, 0, 0, 0))
    assert client.delete(f"/series/{series_id}").json()["cancelled_count"] == 3
    # Second call cancels nothing more.
    assert client.delete(f"/series/{series_id}").json()["cancelled_count"] == 0


def test_cancel_single_instance_of_series(client, session, freeze_now):
    freeze_now(datetime(2026, 1, 1))
    series_id = _make_series(client)

    rows = session.scalars(
        select(Booking).where(Booking.series_id == series_id).order_by(Booking.start)
    ).all()
    target = rows[2].id  # cancel week 3 only
    assert client.delete(f"/bookings/{target}").status_code == 200

    session.expire_all()
    fresh = session.scalars(
        select(Booking).where(Booking.series_id == series_id).order_by(Booking.start)
    ).all()
    cancelled = [b for b in fresh if b.status == "cancelled"]
    assert len(cancelled) == 1
    assert cancelled[0].id == target


def test_cancel_unknown_series_404(client):
    assert client.delete("/series/98765").status_code == 404
