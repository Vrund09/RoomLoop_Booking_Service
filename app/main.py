"""FastAPI application: routers, endpoints, exception handlers."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Base, engine, get_session
from app.errors import AppError
from app.models import Room
from app.schemas import (
    BookingCreate,
    BookingOut,
    CancelOut,
    RecurringCreate,
    RecurringOut,
    RoomOut,
    serialize_booking,
)
from app.services import bookings as booking_service
from app.services import recurrence as recurrence_service


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Create tables if the DB has not been initialised. seed.py handles data.
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="RoomLoop Booking Service", version="1.0.0", lifespan=lifespan)


@app.exception_handler(AppError)
async def _app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.body())


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/rooms", response_model=list[RoomOut])
def list_rooms(session: Session = Depends(get_session)) -> list[Room]:
    # Order by id for a stable response; IDs are not assumed contiguous.
    return list(session.scalars(select(Room).order_by(Room.id)).all())


@app.post("/bookings", response_model=BookingOut, status_code=201)
def create_booking(
    payload: BookingCreate,
    session: Session = Depends(get_session),
) -> dict:
    booking = booking_service.create_single(
        session,
        room_id=payload.room_id,
        user=payload.user,
        start=payload.start,
        end=payload.end,
    )
    return serialize_booking(booking)


@app.post("/bookings/recurring", response_model=RecurringOut, status_code=201)
def create_recurring_booking(
    payload: RecurringCreate,
    session: Session = Depends(get_session),
) -> dict:
    series, created, skipped = recurrence_service.create_recurring(
        session,
        room_id=payload.room_id,
        user=payload.user,
        start=payload.start,
        end=payload.end,
        repeat_until=payload.repeat_until.date(),
    )
    return {
        "series_id": series.id,
        "created": [serialize_booking(b) for b in created],
        "skipped": skipped,
    }


@app.delete("/bookings/{booking_id}", response_model=CancelOut)
def cancel_booking(
    booking_id: int,
    session: Session = Depends(get_session),
) -> dict:
    booking = booking_service.cancel_single(session, booking_id)
    return {"id": booking.id, "status": booking.status}
