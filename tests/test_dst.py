"""The DST tests — proof that weekly recurrence preserves wall-clock time.

These are the highest-value tests in the repo. If any of these regress, the
Denver "hour off" bug is back.
"""
from __future__ import annotations

from datetime import datetime

import pytest

FROZEN = datetime(2026, 1, 1, 0, 0, 0)


@pytest.fixture(autouse=True)
def _freeze(freeze_now):
    freeze_now(FROZEN)


def _assert_all_start_at(created, hhmmss):
    assert created, "expected at least one created instance"
    for b in created:
        assert b["start"].endswith("T" + hhmmss), b["start"]


def test_denver_series_crossing_spring_forward(client):
    # Room 9 = Denver. Weekly 09:00, 2026-02-23 -> 2026-03-16 crosses 2026-03-08.
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
    assert r.status_code == 201
    created = r.json()["created"]
    assert len(created) == 4
    _assert_all_start_at(created, "09:00:00")
    assert r.json()["skipped"] == []


def test_denver_series_crossing_fall_back(client):
    # Weekly 09:00 crossing 2026-11-01 fall-back.
    r = client.post(
        "/bookings/recurring",
        json={
            "room_id": 9,
            "user": "bob@corp.com",
            "start": "2026-10-26T09:00:00",
            "end": "2026-10-26T10:00:00",
            "repeat_until": "2026-11-09",
        },
    )
    assert r.status_code == 201
    _assert_all_start_at(r.json()["created"], "09:00:00")


def test_berlin_series_crossing_spring_forward(client):
    # Room 3 = Berlin. Weekly 09:00 crossing 2026-03-29 spring-forward.
    r = client.post(
        "/bookings/recurring",
        json={
            "room_id": 3,
            "user": "bob@corp.com",
            "start": "2026-03-22T09:00:00",
            "end": "2026-03-22T10:00:00",
            "repeat_until": "2026-04-05",
        },
    )
    assert r.status_code == 201
    _assert_all_start_at(r.json()["created"], "09:00:00")


def test_occurrence_on_nonexistent_time_is_skipped(client):
    # Denver 02:30 weekly, crossing 2026-03-08: the 03-08 instance does not exist.
    r = client.post(
        "/bookings/recurring",
        json={
            "room_id": 9,
            "user": "bob@corp.com",
            "start": "2026-03-01T02:30:00",
            "end": "2026-03-01T03:30:00",
            "repeat_until": "2026-03-15",
        },
    )
    assert r.status_code == 201
    data = r.json()
    created_starts = [b["start"] for b in data["created"]]
    assert created_starts == ["2026-03-01T02:30:00", "2026-03-15T02:30:00"]
    assert len(data["skipped"]) == 1
    sk = data["skipped"][0]
    assert sk["start"] == "2026-03-08T02:30:00"
    assert sk["reason"] == "nonexistent_local_time"
