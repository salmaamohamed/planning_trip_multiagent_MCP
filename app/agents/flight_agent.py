import logging

from langgraph.runtime import Runtime

from app.agents.specialist import extract_with_llm, failure, publish, read_constraints, validate_options
from app.blackboard import BlackboardKeys, SpecialistResult
from app.prompts.flight_prompt import FLIGHT_EXTRACTION_PROMPT
from app.schemas.flight import FlightOption, FlightSearchResult
from app.state import TravelContext, TravelState
from app.tools.flight_tools import search_flights

logger = logging.getLogger(__name__)

AGENT_NAME = "flight_agent"
KEY = BlackboardKeys.FLIGHTS


async def flight_agent(state: TravelState, runtime: Runtime[TravelContext]) -> dict:
    logger.info("Flight Agent: searching")
    ctx = runtime.context
    try:
        constraints = read_constraints(ctx)

        if not constraints.origin:
            status = publish(
                ctx, KEY,
                SpecialistResult(status="skipped", message="No origin was provided, so flights were not searched."),
                AGENT_NAME,
            )
            return {"flight_status": status}

        tool_result = await search_flights(constraints, ctx.settings)
        rows = tool_result.options
        if tool_result.needs_extraction:
            rows = await extract_with_llm(
                ctx, tool_result, FLIGHT_EXTRACTION_PROMPT, FlightSearchResult, "flights",
                origin=constraints.origin, destination=constraints.destination,
                start_date=constraints.start_date, return_date=constraints.return_date,
            )

        flights, dropped = validate_options(rows, FlightOption, tool_result.source)
        flights.sort(key=lambda f: (f["direction"] != "outbound", f["price"]))
        message = (
            f"{len(flights)} flight option(s) found between {constraints.origin} and {constraints.destination}."
            if flights
            else f"No flights found between {constraints.origin} and {constraints.destination} for these dates."
        )
        if dropped:
            message += f" {dropped} incomplete result(s) discarded."

        status = publish(
            ctx, KEY,
            SpecialistResult(status="ok" if flights else "empty", options=flights,
                             source=tool_result.source, message=message),
            AGENT_NAME,
        )
        return {"flight_status": status}

    except Exception as exc:
        result = failure(ctx, KEY, AGENT_NAME, f"Flight search failed: {exc}")
        return {"flight_status": result["status"], "errors": result["errors"]}
