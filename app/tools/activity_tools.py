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


async def search_activities(constraints: TripConstraints, cfg: Settings | None = None) -> ToolResult:
    if provider(cfg) == "tavily":
        query = f"top things to do in {constraints.destination} attractions ticket price visit duration"
        return ToolResult(source=TAVILY_SOURCE, raw_results=await tavily_search(query, cfg))

    options = [
        {
            "name": row["name"],
            "category": row["category"],
            "description": row.get("description", ""),
            "duration_hours": row["duration_hours"],
            "price": row["price"],
            "currency": row["currency"],
            "source": SAMPLE_SOURCE,
        }
        for row in load_catalog(cfg)["activities"]
        if same_place(row["city"], constraints.destination)
    ]
    return ToolResult(source=SAMPLE_SOURCE, options=options)
