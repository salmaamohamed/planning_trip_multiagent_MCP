from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class BlackboardKeys:
    """Well-known keys. Agents should only use these constants."""

    TRIP_CONSTRAINTS = "trip_constraints"
    FLIGHTS = "flights"
    HOTELS = "hotels"
    ACTIVITIES = "activities"

    SPECIALIST_KEYS = (FLIGHTS, HOTELS, ACTIVITIES)


class BlackboardEntry(BaseModel):
    """A value on the Blackboard plus who wrote it and when."""

    key: str
    value: Any
    written_by: str
    version: int = 1
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SpecialistResult(BaseModel):
    """Envelope each specialist writes under its key (flights / hotels / activities)."""

    status: str = Field(description="ok | empty | failed | skipped")
    options: list[dict[str, Any]] = Field(default_factory=list)
    source: str = ""
    message: str = ""
