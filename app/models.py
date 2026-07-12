"""SQLAlchemy models: Room, BookingSeries, Booking.

All stored booking datetimes are NAIVE local wall-clock in the room's own
timezone. We never attach tzinfo and never convert to UTC (see DECISIONS.md).
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import STATUS_ACTIVE
from app.db import Base


class Room(Base):
    __tablename__ = "rooms"

    # Explicit IDs (3, 4, 9, 17) — NOT sequential 1..N. Do not rely on ordering.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    office: Mapped[str] = mapped_column(String, nullable=False)  # "berlin" | "denver"
    timezone: Mapped[str] = mapped_column(String, nullable=False)  # IANA name

    __table_args__ = (CheckConstraint("capacity > 0", name="ck_room_capacity_positive"),)


class BookingSeries(Base):
    __tablename__ = "booking_series"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), nullable=False)
    user: Mapped[str] = mapped_column(String, nullable=False)
    start_time: Mapped[str] = mapped_column(String, nullable=False)  # "HH:MM:SS"
    end_time: Mapped[str] = mapped_column(String, nullable=False)  # "HH:MM:SS"
    first_date: Mapped[date] = mapped_column(Date, nullable=False)
    repeat_until: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default=STATUS_ACTIVE)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    bookings: Mapped[list["Booking"]] = relationship(back_populates="series")


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), nullable=False, index=True)
    user: Mapped[str] = mapped_column(String, nullable=False)
    # NAIVE local datetimes. SQLite stores these as ISO TEXT.
    start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    series_id: Mapped[int | None] = mapped_column(
        ForeignKey("booking_series.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String, nullable=False, default=STATUS_ACTIVE)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    series: Mapped["BookingSeries | None"] = relationship(back_populates="bookings")

    __table_args__ = (
        Index("ix_bookings_room_start", "room_id", "start"),
        CheckConstraint("end > start", name="ck_booking_end_after_start"),
    )
