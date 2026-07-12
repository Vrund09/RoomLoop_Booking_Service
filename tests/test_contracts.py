"""C1/C2 contract regression tests — these guard the external contracts.

C1: every booking timestamp is `YYYY-MM-DDTHH:MM:SS` (no offset, no Z, no micros).
C2: GET /rooms is a bare array of exactly {id, name, capacity}.
"""
from __future__ import annotations

import re
from datetime import datetime

import pytest

C2_SAMPLE = [
    {"id": 3, "name": "Aurora", "capacity": 8},
    {"id": 4, "name": "Basalt", "capacity": 4},
    {"id": 9, "name": "Cinder", "capacity": 12},
    {"id": 17, "name": "Dune", "capacity": 6},
]

TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")


@pytest.fixture(autouse=True)
def _freeze(freeze_now):
    freeze_now(datetime(2026, 1, 1))


def test_rooms_matches_c2_sample_exactly(client):
    rooms = client.get("/rooms").json()
    assert sorted(rooms, key=lambda r: r["id"]) == C2_SAMPLE
    for el in rooms:
        assert set(el.keys()) == {"id", "name", "capacity"}


def test_all_seeded_room_ids_are_bookable(client):
    # Proves no 1..N assumption — IDs 3,4,9,17 must all work.
    for rid in (3, 4, 9, 17):
        r = client.post(
            "/bookings",
            json={
                "room_id": rid,
                "user": "alice@corp.com",
                "start": "2026-07-06T09:00:00",
                "end": "2026-07-06T10:00:00",
            },
        )
        assert r.status_code == 201, (rid, r.json())


def test_single_booking_timestamps_have_no_offset(client):
    r = client.post(
        "/bookings",
        json={
            "room_id": 3,
            "user": "alice@corp.com",
            "start": "2026-07-06T09:00:00",
            "end": "2026-07-06T10:00:00",
        },
    )
    body = r.json()
    assert TS_RE.match(body["start"])
    assert TS_RE.match(body["end"])


def test_recurring_response_timestamps_have_no_offset(client):
    r = client.post(
        "/bookings/recurring",
        json={
            "room_id": 9,
            "user": "bob@corp.com",
            "start": "2026-02-23T09:00:00",
            "end": "2026-02-23T10:00:00",
            "repeat_until": "2026-03-16",
        },
    )
    data = r.json()
    for b in data["created"]:
        assert TS_RE.match(b["start"]), b["start"]
        assert TS_RE.match(b["end"]), b["end"]
    for s in data["skipped"]:
        assert TS_RE.match(s["start"]), s["start"]
        assert TS_RE.match(s["end"]), s["end"]


def test_list_endpoint_timestamps_have_no_offset(client):
    client.post(
        "/bookings",
        json={
            "room_id": 3,
            "user": "alice@corp.com",
            "start": "2026-07-06T09:00:00",
            "end": "2026-07-06T10:00:00",
        },
    )
    for b in client.get("/bookings").json():
        assert TS_RE.match(b["start"])
        assert TS_RE.match(b["end"])
