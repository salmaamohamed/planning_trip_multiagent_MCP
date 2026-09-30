from datetime import date, datetime, timedelta

from pydantic import BaseModel, Field, field_validator

MAX_DURATION_DAYS = 30


class TravelRequest(BaseModel):
    """Validated user request. Built by the Planner Agent."""

    destination: str = Field(min_length=1)
    travel_date: str = Field(description="ISO date, optionally with time: YYYY-MM-DD or YYYY-MM-DDTHH:MM")
    duration_days: int = Field(ge=1, le=MAX_DURATION_DAYS)
    origin: str | None = None
    budget: float | None = Field(default=None, gt=0)
    currency: str = "USD"

    @field_validator("destination")
    @classmethod
    def _strip_destination(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("destination is required")
        return value

    @field_validator("origin")
    @classmethod
    def _strip_origin(cls, value: str | None) -> str | None:
        return value.strip() or None if value else None

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, value: str) -> str:
        return (value or "USD").strip().upper()

    @field_validator("travel_date")
    @classmethod
    def _valid_date(cls, value: str) -> str:
        value = value.strip()
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("travel_date must be ISO formatted, e.g. 2026-10-15 or 2026-10-15T09:00") from exc
        if parsed.date() < date.today():
            raise ValueError("travel_date is in the past")
        return value

    @property
    def start_date(self) -> date:
        return datetime.fromisoformat(self.travel_date).date()

    @property
    def return_date(self) -> date:
        return self.start_date + timedelta(days=self.duration_days)

    @property
    def nights(self) -> int:
        return self.duration_days


class TripConstraints(BaseModel):
    """What the Planner writes to the Blackboard for the specialists to read."""

    destination: str
    origin: str | None
    start_date: str
    return_date: str
    duration_days: int
    nights: int
    budget: float | None
    currency: str

    @classmethod
    def from_request(cls, request: TravelRequest) -> "TripConstraints":
        return cls(
            destination=request.destination,
            origin=request.origin,
            start_date=request.start_date.isoformat(),
            return_date=request.return_date.isoformat(),
            duration_days=request.duration_days,
            nights=request.nights,
            budget=request.budget,
            currency=request.currency,
        )


class ParsedTravelQuery(BaseModel):
    """LLM extraction target for free-text requests. Missing fields stay null."""

    destination: str | None = None
    travel_date: str | None = None
    duration_days: int | None = None
    origin: str | None = None
    budget: float | None = None
    currency: str | None = None
