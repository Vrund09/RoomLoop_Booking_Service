"""API-level tests for POST /bookings and DELETE /bookings/{id}."""
from __future__ import annotations

from datetime import datetime

import pytest

# All single-booking tests run with "now" frozen well before the test dates so
# the past-start guard doesn't reject otherwise-valid future bookings.
FROZEN = datetime(2026, 1, 1, 0, 0, 0)


@pytest.fixture(autouse=True)
def _freeze(freeze_now):
    freeze_now(FROZEN)


def _book(client, **over):
    body = {
        "room_id": 3,
        "user": "alice@corp.com",
        "start": "2026-07-02T09:00:00",
        "end": "2026-07-02T10:00:00",
    }
    body.update(over)
    return client.post("/bookings", json=body)


def test_create_returns_201_and_echoes_naive_iso(client):
    r = _book(client)
    assert r.status_code == 201
    data = r.json()
    assert data["start"] == "2026-07-02T09:00:00"
    assert data["end"] == "2026-07-02T10:00:00"
    assert data["series_id"] is None
    assert data["status"] == "active"
    assert data["room_id"] == 3


def test_unknown_room_404(client):
    assert _book(client, room_id=999).status_code == 404


def test_end_before_start_422(client):
    r = _book(client, start="2026-07-02T10:00:00", end="2026-07-02T09:00:00")
    assert r.status_code == 422


def test_offset_timestamp_422(client):
    assert _book(client, start="2026-07-02T09:00:00+02:00").status_code == 422


def test_z_timestamp_422(client):
    assert _book(client, start="2026-07-02T09:00:00Z").status_code == 422


def test_empty_user_422(client):
    assert _book(client, user="   ").status_code == 422


def test_past_start_422(client):
    # 2025 is before the frozen "now" of 2026-01-01.
    r = _book(client, start="2025-12-31T09:00:00", end="2025-12-31T10:00:00")
    assert r.status_code == 422


def test_duration_over_24h_422(client):
    r = _book(client, start="2026-07-02T09:00:00", end="2026-07-03T10:00:00")
    assert r.status_code == 422


def test_nonexistent_local_time_422(client):
    # 02:30 on 2026-03-08 does not exist in America/Denver (room 9).
    r = _book(
        client,
        room_id=9,
        start="2026-03-08T02:30:00",
        end="2026-03-08T03:30:00",
    )
    assert r.status_code == 422


def test_conflict_409_with_conflicts_with(client):
    first = _book(client)
    assert first.status_code == 201
    r = _book(client, start="2026-07-02T09:30:00", end="2026-07-02T10:30:00")
    assert r.status_code == 409
    assert r.json()["conflicts_with"] == [first.json()["id"]]


def test_cancel_then_rebook(client):
    first = _book(client)
    bid = first.json()["id"]
    c = client.delete(f"/bookings/{bid}")
    assert c.status_code == 200
    assert c.json() == {"id": bid, "status": "cancelled"}
    # re-cancel -> 409
    assert client.delete(f"/bookings/{bid}").status_code == 409
    # slot is now free -> someone else can book it
    again = _book(client, user="bob@corp.com")
    assert again.status_code == 201


def test_cancel_unknown_404(client):
    assert client.delete("/bookings/424242").status_code == 404
