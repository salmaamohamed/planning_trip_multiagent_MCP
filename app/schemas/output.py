from pydantic import BaseModel, Field


class FinalTravelPlan(BaseModel):
    session_id: str
    destination: str | None = None
    travel_date: str | None = None
    duration_days: int | None = None
    markdown: str
    warnings: list[str] = Field(default_factory=list)
