from datetime import date, timedelta

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


def _dated(row: dict, direction: str, on: date) -> dict:
    """Turn a catalog schedule row into a concrete flight on a given date."""
    next_day = row["arrival_time"].endswith("+1")
    arrival_day = on + timedelta(days=1) if next_day else on
    return {
        "airline": row["airline"],
        "flight_number": row.get("flight_number"),
        "direction": direction,
        "departure": row["origin"],
        "arrival": row["destination"],
        "departure_time": f"{on.isoformat()} {row['departure_time']}",
        "arrival_time": f"{arrival_day.isoformat()} {row['arrival_time'].removesuffix('+1')}",
        "duration": row["duration"],
        "price": row["price"],
        "currency": row["currency"],
        "source": SAMPLE_SOURCE,
    }


async def search_flights(constraints: TripConstraints, cfg: Settings | None = None) -> ToolResult:
    """Outbound flights on the start date and return flights on the return date."""
    start = date.fromisoformat(constraints.start_date)
    back = date.fromisoformat(constraints.return_date)

    if provider(cfg) == "tavily":
        query = (
            f"flights from {constraints.origin} to {constraints.destination} departing {start} "
            f"returning {back} airline schedule price"
        )
        return ToolResult(source=TAVILY_SOURCE, raw_results=await tavily_search(query, cfg))

    rows = load_catalog(cfg)["flights"]
    outbound = [
        _dated(r, "outbound", start) for r in rows
        if same_place(r["origin"], constraints.origin) and same_place(r["destination"], constraints.destination)
    ]
    inbound = [
        _dated(r, "return", back) for r in rows
        if same_place(r["origin"], constraints.destination) and same_place(r["destination"], constraints.origin)
    ]
    return ToolResult(source=SAMPLE_SOURCE, options=outbound + inbound)
