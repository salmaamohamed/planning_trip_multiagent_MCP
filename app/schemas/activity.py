from pydantic import BaseModel, Field


class ActivityOption(BaseModel):
    name: str
    category: str
    description: str = ""
    duration_hours: float = Field(gt=0)
    price: float = Field(ge=0)
    currency: str
    day: int | None = Field(default=None, ge=1, description="Trip day this activity is scheduled on")
    source: str = "unknown"


class ActivitySearchResult(BaseModel):
    activities: list[ActivityOption] = Field(default_factory=list)


class DayAssignment(BaseModel):
    name: str
    day: int


class ActivitySchedule(BaseModel):
    """LLM output when the Activity Agent arranges activities into days."""

    assignments: list[DayAssignment] = Field(default_factory=list)
