"""Application-wide constants and configuration."""
from __future__ import annotations

import os

# Where the SQLite file lives. Overridable via env for tests / containers.
DB_PATH = os.environ.get("ROOMLOOP_DB_PATH", "roomloop.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

# Longest series horizon we will expand, in days. Guards against the
# "6 months of Mondays" unbounded-generation complaint; 1 year is plenty.
MAX_HORIZON_DAYS = 366

# Maximum duration of a single booking, in hours.
MAX_BOOKING_HOURS = 24

# Booking / series status values.
STATUS_ACTIVE = "active"
STATUS_CANCELLED = "cancelled"
