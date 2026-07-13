"""Pydantic request/response models.

Response models are intentionally strict about shape — the C2 contract for
GET /rooms is a bare array of exactly {id, name, capacity}.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.models import Booking
from app.time_utils import format_naive_iso, parse_naive_iso


class RoomOut(BaseModel):
    """C2 contract: exactly these three fields, nothing else."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    capacity: int


def _parse_ts(value):
    # `mode="before"` guard so Pydantic never applies its own lenient (offset-
    # accepting) datetime parsing. Only our strict naive-local parser runs.
    if isinstance(value, str):
        return parse_naive_iso(value)
    raise ValueError("Timestamp must be a string.")


def _clean_user(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("user must be a non-empty string.")
    return value.strip()


class BookingCreate(BaseModel):
    # Example uses naive local time (no offset, no `Z`) so Swagger's "Try it out"
    # prefills a body that actually validates — see the C1 contract.
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "room_id": 9,
                "user": "vrund",
                "start": "2026-08-05T14:00:00",
                "end": "2026-08-05T15:00:00",
            }
        }
    )

    room_id: int
    user: str
    start: datetime
    end: datetime

    _v_start = field_validator("start", "end", mode="before")(_parse_ts)
    _v_user = field_validator("user", mode="before")(_clean_user)


class RecurringCreate(BaseModel):
    # Naive-local example (no offset/`Z`); `repeat_until` may be a bare date.
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "room_id": 9,
                "user": "vrund",
                "start": "2026-08-03T09:00:00",
                "end": "2026-08-03T10:00:00",
                "repeat_until": "2026-08-31",
            }
        }
    )

    room_id: int
    user: str
    start: datetime
    end: datetime
    repeat_until: datetime  # parsed as a date via the naive-ISO parser below

    _v_user = field_validator("user", mode="before")(_clean_user)

    @field_validator("start", "end", mode="before")
    @classmethod
    def _v_times(cls, value):
        return _parse_ts(value)

    @field_validator("repeat_until", mode="before")
    @classmethod
    def _v_until(cls, value):
        # Accept a bare date (YYYY-MM-DD) or a full naive timestamp; keep the date.
        if isinstance(value, str) and len(value.strip()) == 10 and "T" not in value:
            return parse_naive_iso(value.strip() + "T00:00:00")
        return _parse_ts(value)


class BookingOut(BaseModel):
    id: int
    room_id: int
    user: str
    start: str
    end: str
    series_id: int | None
    status: str


class SkippedOut(BaseModel):
    start: str
    end: str
    reason: str
    conflicts_with: list[int] | None = None


class RecurringOut(BaseModel):
    series_id: int
    created: list[BookingOut]
    skipped: list[SkippedOut]


class CancelOut(BaseModel):
    id: int
    status: str


class SeriesCancelOut(BaseModel):
    series_id: int
    cancelled_count: int
    past_left_intact: int


def serialize_booking(booking: Booking) -> dict:
    """The single response serializer — every timestamp goes through here."""
    return {
        "id": booking.id,
        "room_id": booking.room_id,
        "user": booking.user,
        "start": format_naive_iso(booking.start),
        "end": format_naive_iso(booking.end),
        "series_id": booking.series_id,
        "status": booking.status,
    }
