"""Tests for POST /bookings/recurring — atomic skip-and-report (R1/R2)."""
from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import func, select

from app.models import Booking, BookingSeries

FROZEN = datetime(2026, 1, 1, 0, 0, 0)


@pytest.fixture(autouse=True)
def _freeze(freeze_now):
    freeze_now(FROZEN)


def _recurring(client, **over):
    body = {
        "room_id": 3,
        "user": "bob@corp.com",
        "start": "2026-05-04T09:00:00",  # a Monday
        "end": "2026-05-04T10:00:00",
        "repeat_until": "2026-06-08",  # 6 Mondays inclusive: 05-04..06-08
    }
    body.update(over)
    return client.post("/bookings/recurring", json=body)


def test_six_week_series_inclusive_boundary(client):
    r = _recurring(client)
    assert r.status_code == 201
    data = r.json()
    starts = [b["start"] for b in data["created"]]
    assert starts == [
        "2026-05-04T09:00:00",
        "2026-05-11T09:00:00",
        "2026-05-18T09:00:00",
        "2026-05-25T09:00:00",
        "2026-06-01T09:00:00",
        "2026-06-08T09:00:00",  # repeat_until is inclusive
    ]
    assert data["skipped"] == []


def test_preexisting_conflict_skips_only_that_week(client, session):
    # Pre-book week 3 (2026-05-18) in room 3.
    pre = client.post(
        "/bookings",
        json={
            "room_id": 3,
            "user": "eve@corp.com",
            "start": "2026-05-18T09:30:00",
            "end": "2026-05-18T10:30:00",
        },
    )
    assert pre.status_code == 201
    pre_id = pre.json()["id"]

    r = _recurring(client)
    assert r.status_code == 201
    data = r.json()
    assert len(data["created"]) == 5
    assert len(data["skipped"]) == 1
    sk = data["skipped"][0]
    assert sk["start"] == "2026-05-18T09:00:00"
    assert sk["reason"] == "conflict"
    assert sk["conflicts_with"] == [pre_id]

    # Series row exists and has exactly 5 instances.
    n_series = session.scalar(select(func.count()).select_from(BookingSeries))
    assert n_series == 1


def test_all_conflict_409_nothing_written(client, session):
    # Block all 6 Mondays with a wide single booking each.
    for wk in ["2026-05-04", "2026-05-11", "2026-05-18", "2026-05-25", "2026-06-01", "2026-06-08"]:
        assert client.post(
            "/bookings",
            json={"room_id": 3, "user": "x", "start": f"{wk}T09:00:00", "end": f"{wk}T10:00:00"},
        ).status_code == 201

    count_before = session.scalar(select(func.count()).select_from(Booking))
    r = _recurring(client)
    assert r.status_code == 409

    # No series row, and booking count unchanged.
    assert session.scalar(select(func.count()).select_from(BookingSeries)) == 0
    assert session.scalar(select(func.count()).select_from(Booking)) == count_before


def test_unknown_room_404_zero_rows(client, session):
    r = _recurring(client, room_id=999)
    assert r.status_code == 404
    assert session.scalar(select(func.count()).select_from(Booking)) == 0
    assert session.scalar(select(func.count()).select_from(BookingSeries)) == 0


def test_horizon_over_366_days_422(client):
    r = _recurring(client, repeat_until="2027-06-01")
    assert r.status_code == 422


def test_repeat_until_before_start_422(client):
    r = _recurring(client, repeat_until="2026-05-03")
    assert r.status_code == 422


def test_start_end_different_dates_422(client):
    r = _recurring(client, start="2026-05-04T23:00:00", end="2026-05-05T00:30:00")
    assert r.status_code == 422
