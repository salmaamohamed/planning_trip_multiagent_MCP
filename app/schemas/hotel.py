from pydantic import BaseModel, Field


class HotelOption(BaseModel):
    name: str
    location: str
    rating: float | None = Field(default=None, ge=0, le=5)
    price_per_night: float = Field(ge=0)
    total_price: float = Field(ge=0)
    currency: str
    source: str = "unknown"


class HotelSearchResult(BaseModel):
    hotels: list[HotelOption] = Field(default_factory=list)
