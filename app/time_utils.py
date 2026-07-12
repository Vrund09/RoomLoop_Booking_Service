"""Naive-local time handling — the heart of the DST design.

Every booking datetime in this system is a NAIVE local wall-clock time in the
room's own timezone. We never attach tzinfo to stored/returned values and never
convert to UTC. Timezone awareness is used in exactly two places:

  1. `local_now`  — "now" in a room's local time (past-check, cancel cutoff).
  2. `is_nonexistent` — detecting spring-forward gap times to skip.

See DECISIONS.md / ROOMLOOP_SPEC.md Trap 2.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# Exact accepted shape: YYYY-MM-DDTHH:MM[:SS]. No offset, no 'Z', no micros.
_ISO_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$")

_OFFSET_MESSAGE = (
    "Timestamps must be naive local time (YYYY-MM-DDTHH:MM:SS) per the reporting "
    "contract; got an offset."
)


class TimestampError(ValueError):
    """Raised when an input timestamp violates the C1 naive-local contract."""


def parse_naive_iso(value: str) -> datetime:
    """Parse a naive-local timestamp, rejecting anything with an offset/Z/micros.

    Accepts `YYYY-MM-DDTHH:MM:SS` and `YYYY-MM-DDTHH:MM` (seconds default to 00).
    """
    if not isinstance(value, str):
        raise TimestampError(f"Expected a timestamp string, got {type(value).__name__}.")
    s = value.strip()

    # Detect an explicit offset / UTC marker before anything else for a clear message.
    if s.endswith(("Z", "z")):
        raise TimestampError(_OFFSET_MESSAGE)
    time_part = s.split("T", 1)[1] if "T" in s else ""
    if "+" in time_part or "-" in time_part:
        raise TimestampError(_OFFSET_MESSAGE)

    m = _ISO_RE.match(s)
    if not m:
        raise TimestampError(
            f"Invalid timestamp '{value}'; expected format YYYY-MM-DDTHH:MM:SS."
        )
    year, month, day, hour, minute, second = (
        int(m.group(1)),
        int(m.group(2)),
        int(m.group(3)),
        int(m.group(4)),
        int(m.group(5)),
        int(m.group(6) or 0),
    )
    try:
        return datetime(year, month, day, hour, minute, second)
    except ValueError as exc:  # e.g. month 13, day 32, hour 25
        raise TimestampError(f"Invalid timestamp '{value}': {exc}.") from exc


def format_naive_iso(dt: datetime) -> str:
    """The single formatter every response path uses. No micros, no offset."""
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def is_nonexistent(dt_naive: datetime, tz: ZoneInfo) -> bool:
    """True if the naive wall-clock time falls in a spring-forward gap.

    Such a time does not exist on the clock in that timezone. We round-trip
    through UTC: for a gap time the round trip does not return the same wall clock.
    """
    aware = dt_naive.replace(tzinfo=tz)
    round_tripped = aware.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None)
    return round_tripped != dt_naive


def local_now(room) -> datetime:
    """Now, as a naive wall-clock time in the room's timezone.

    Business "now" must never be server time. Tests monkeypatch this function
    (call it as `time_utils.local_now(room)`, not via a direct import binding).
    """
    return datetime.now(ZoneInfo(room.timezone)).replace(tzinfo=None, microsecond=0)
