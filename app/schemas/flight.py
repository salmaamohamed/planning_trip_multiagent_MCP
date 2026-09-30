from typing import Literal

from pydantic import BaseModel, Field


class FlightOption(BaseModel):
    airline: str
    flight_number: str | None = None
    direction: Literal["outbound", "return"]
    departure: str = Field(description="Departure city/airport")
    arrival: str = Field(description="Arrival city/airport")
    departure_time: str
    arrival_time: str
    duration: str
    price: float = Field(ge=0)
    currency: str
    source: str = "unknown"


class FlightSearchResult(BaseModel):
    """Structured output of the Flight Agent's LLM extraction step."""

    flights: list[FlightOption] = Field(default_factory=list)
