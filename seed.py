"""Idempotent database seeder.

Creates the schema and inserts the four sample rooms from the C2 contract.
Running it twice does not duplicate rows or error.
"""
from __future__ import annotations

from app.db import Base, SessionLocal, engine
from app.models import Room

# Exact rooms from the C2 sample response. IDs are explicit and non-contiguous.
SEED_ROOMS = [
    {"id": 3, "name": "Aurora", "capacity": 8, "office": "berlin", "timezone": "Europe/Berlin"},
    {"id": 4, "name": "Basalt", "capacity": 4, "office": "berlin", "timezone": "Europe/Berlin"},
    {"id": 9, "name": "Cinder", "capacity": 12, "office": "denver", "timezone": "America/Denver"},
    {"id": 17, "name": "Dune", "capacity": 6, "office": "denver", "timezone": "America/Denver"},
]


def seed() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        for row in SEED_ROOMS:
            existing = session.get(Room, row["id"])
            if existing is None:
                session.add(Room(**row))
        session.commit()


if __name__ == "__main__":
    seed()
    print("Seeded rooms:", ", ".join(str(r["id"]) for r in SEED_ROOMS))
