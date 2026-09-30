from pydantic import BaseModel, Field

from app.schemas.activity import ActivityOption
from app.schemas.flight import FlightOption
from app.schemas.hotel import HotelOption


class BudgetOption(BaseModel):
    """One priced combination of flights + hotel + activities."""

    label: str
    outbound_flight: FlightOption | None = None
    return_flight: FlightOption | None = None
    hotel: HotelOption | None = None
    activities: list[ActivityOption] = Field(default_factory=list)
    flight_cost: float | None = None
    hotel_cost: float | None = None
    activities_cost: float | None = None
    estimated_total: float
    within_budget: bool | None = None


class BudgetPlan(BaseModel):
    status: str = Field(description="ok | partial | unavailable")
    data_source: str = "excel_mcp"
    currency: str
    budget: float | None = None
    selected: BudgetOption | None = None
    alternatives: list[BudgetOption] = Field(default_factory=list)
    combinations_evaluated: int = 0
    budget_remaining: float | None = None
    unavailable_components: list[str] = Field(default_factory=list)
    explanation: list[str] = Field(default_factory=list)
    rationale: str | None = None
