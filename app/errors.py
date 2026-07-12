"""Domain error types, mapped to HTTP responses by handlers in main.py.

Response bodies use FastAPI's `{"detail": ...}` shape. Conflicts additionally
carry a top-level `conflicts_with` list of booking ids.
"""
from __future__ import annotations


class AppError(Exception):
    """Base for errors that map to a specific HTTP status."""

    status_code: int = 400

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail

    def body(self) -> dict:
        return {"detail": self.detail}


class NotFoundError(AppError):
    status_code = 404


class UnprocessableError(AppError):
    """Business-rule validation failure (422)."""

    status_code = 422


class ConflictError(AppError):
    """409. Optionally reports which existing bookings conflicted."""

    status_code = 409

    def __init__(self, detail: str, conflicts_with: list[int] | None = None):
        super().__init__(detail)
        self.conflicts_with = conflicts_with

    def body(self) -> dict:
        payload = {"detail": self.detail}
        if self.conflicts_with is not None:
            payload["conflicts_with"] = self.conflicts_with
        return payload
