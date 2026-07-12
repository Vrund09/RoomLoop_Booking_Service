"""Shared test fixtures: isolated per-test SQLite DB, seeded rooms, TestClient.

Each test gets a fresh temp-file database (in-memory + threaded TestClient don't
mix well). Rooms are seeded to match the C2 sample. `time_utils.local_now` is
monkeypatchable by tests because business code calls it as a module attribute.
"""
from __future__ import annotations

import os
import tempfile

import pytest

# Point the app's global engine at a throwaway file BEFORE importing the app, so
# the lifespan's create_all never touches a real database. Per-test data lives in
# the isolated engines built below.
_GLOBAL_TMP = os.path.join(tempfile.gettempdir(), "roomloop_test_global.db")
os.environ.setdefault("ROOMLOOP_DB_PATH", _GLOBAL_TMP)

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Room  # noqa: E402
from seed import SEED_ROOMS  # noqa: E402


@pytest.fixture
def db_engine(tmp_path):
    url = f"sqlite:///{tmp_path / 'test.db'}"
    engine = create_engine(url, connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(engine)
    Sess = sessionmaker(bind=engine, expire_on_commit=False)
    with Sess() as s:
        for row in SEED_ROOMS:
            s.add(Room(**row))
        s.commit()
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(db_engine):
    return sessionmaker(bind=db_engine, expire_on_commit=False, future=True)


@pytest.fixture
def session(session_factory):
    s = session_factory()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def client(session_factory):
    def override():
        s = session_factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_session] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
