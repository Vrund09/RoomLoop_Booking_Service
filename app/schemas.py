"""Pydantic request/response models.

Response models are intentionally strict about shape — the C2 contract for
GET /rooms is a bare array of exactly {id, name, capacity}.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class RoomOut(BaseModel):
    """C2 contract: exactly these three fields, nothing else."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    capacity: int
