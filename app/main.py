"""FastAPI application: routers, endpoints, exception handlers."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Base, engine, get_session
from app.models import Room
from app.schemas import RoomOut


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Create tables if the DB has not been initialised. seed.py handles data.
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="RoomLoop Booking Service", version="1.0.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/rooms", response_model=list[RoomOut])
def list_rooms(session: Session = Depends(get_session)) -> list[Room]:
    # Order by id for a stable response; IDs are not assumed contiguous.
    return list(session.scalars(select(Room).order_by(Room.id)).all())
