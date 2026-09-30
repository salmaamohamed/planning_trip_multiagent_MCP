from app.config import Settings
from app.schemas.travel import TripConstraints
from app.tools.common import (
    SAMPLE_SOURCE,
    TAVILY_SOURCE,
    ToolResult,
    load_catalog,
    provider,
    same_place,
    tavily_search,
)


async def search_hotels(constraints: TripConstraints, cfg: Settings | None = None) -> ToolResult:
    if provider(cfg) == "tavily":
        query = (
            f"hotels in {constraints.destination} {constraints.start_date} to {constraints.return_date} "
            f"price per night rating"
        )
        return ToolResult(source=TAVILY_SOURCE, raw_results=await tavily_search(query, cfg))

    options = [
        {
            "name": row["name"],
            "location": row["location"],
            "rating": row.get("rating"),
            "price_per_night": row["price_per_night"],
            "total_price": round(row["price_per_night"] * constraints.nights, 2),
            "currency": row["currency"],
            "source": SAMPLE_SOURCE,
        }
        for row in load_catalog(cfg)["hotels"]
        if same_place(row["city"], constraints.destination)
    ]
    return ToolResult(source=SAMPLE_SOURCE, options=options)
