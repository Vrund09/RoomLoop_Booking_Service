"""Tests for naive-local timestamp parsing/formatting and DST-gap detection."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.time_utils import (
    TimestampError,
    format_naive_iso,
    is_nonexistent,
    parse_naive_iso,
)


def test_parses_full_naive_iso():
    assert parse_naive_iso("2026-07-02T09:00:00") == datetime(2026, 7, 2, 9, 0, 0)


def test_normalizes_missing_seconds():
    assert parse_naive_iso("2026-07-02T09:00") == datetime(2026, 7, 2, 9, 0, 0)


@pytest.mark.parametrize(
    "bad",
    [
        "2026-07-02T09:00:00+02:00",
        "2026-07-02T09:00:00-06:00",
        "2026-07-02T09:00:00Z",
        "2026-07-02T09:00:00z",
    ],
)
def test_rejects_offset_and_z(bad):
    with pytest.raises(TimestampError):
        parse_naive_iso(bad)


@pytest.mark.parametrize(
    "bad",
    [
        "not-a-date",
        "2026/07/02 09:00:00",
        "2026-13-02T09:00:00",
        "2026-07-02T25:00:00",
        "2026-07-02T09:00:00.500",
        "",
    ],
)
def test_rejects_garbage(bad):
    with pytest.raises(TimestampError):
        parse_naive_iso(bad)


def test_formats_without_microseconds_or_offset():
    dt = datetime(2026, 7, 2, 9, 0, 0, 123456)
    assert format_naive_iso(dt) == "2026-07-02T09:00:00"


def test_nonexistent_denver_spring_forward():
    tz = ZoneInfo("America/Denver")
    # 2026-03-08 02:30 does not exist (spring forward 02:00 -> 03:00).
    assert is_nonexistent(datetime(2026, 3, 8, 2, 30, 0), tz) is True
    # 03:30 same day exists.
    assert is_nonexistent(datetime(2026, 3, 8, 3, 30, 0), tz) is False


def test_nonexistent_berlin_spring_forward():
    tz = ZoneInfo("Europe/Berlin")
    # 2026-03-29 02:30 does not exist in Berlin (spring forward).
    assert is_nonexistent(datetime(2026, 3, 29, 2, 30, 0), tz) is True


def test_fall_back_ambiguous_time_is_allowed():
    tz = ZoneInfo("America/Denver")
    # 2026-11-01 01:30 occurs twice (fall back) but it DOES exist -> not nonexistent.
    assert is_nonexistent(datetime(2026, 11, 1, 1, 30, 0), tz) is False
