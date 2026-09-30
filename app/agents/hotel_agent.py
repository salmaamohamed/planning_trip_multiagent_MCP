import logging

from langgraph.runtime import Runtime

from app.agents.specialist import extract_with_llm, failure, publish, read_constraints, validate_options
from app.blackboard import BlackboardKeys, SpecialistResult
from app.prompts.hotel_prompt import HOTEL_EXTRACTION_PROMPT
from app.schemas.hotel import HotelOption, HotelSearchResult
from app.state import TravelContext, TravelState
from app.tools.hotel_tools import search_hotels

logger = logging.getLogger(__name__)

AGENT_NAME = "hotel_agent"
KEY = BlackboardKeys.HOTELS


async def hotel_agent(state: TravelState, runtime: Runtime[TravelContext]) -> dict:
    logger.info("Hotel Agent: searching")
    ctx = runtime.context
    try:
        # Trip constraints (dates, nights) are READ from the Blackboard.
        constraints = read_constraints(ctx)

        tool_result = await search_hotels(constraints, ctx.settings)
        rows = tool_result.options
        if tool_result.needs_extraction:
            rows = await extract_with_llm(
                ctx, tool_result, HOTEL_EXTRACTION_PROMPT, HotelSearchResult, "hotels",
                destination=constraints.destination, start_date=constraints.start_date,
                return_date=constraints.return_date, nights=constraints.nights,
            )

        hotels, dropped = validate_options(rows, HotelOption, tool_result.source)
        hotels.sort(key=lambda h: h["total_price"])
        message = (
            f"{len(hotels)} hotel option(s) found in {constraints.destination} for {constraints.nights} night(s)."
            if hotels
            else f"No hotels found in {constraints.destination}."
        )
        if dropped:
            message += f" {dropped} incomplete result(s) discarded."

        status = publish(
            ctx, KEY,
            SpecialistResult(status="ok" if hotels else "empty", options=hotels,
                             source=tool_result.source, message=message),
            AGENT_NAME,
        )
        return {"hotel_status": status}

    except Exception as exc:
        result = failure(ctx, KEY, AGENT_NAME, f"Hotel search failed: {exc}")
        return {"hotel_status": result["status"], "errors": result["errors"]}
