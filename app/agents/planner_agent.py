"""Planner Agent: validates the request, seeds the Blackboard, and routes the workflow.

It does no flight, hotel, activity, or budget work itself.
"""
import logging
from datetime import date
from typing import Any

from langgraph.runtime import Runtime
from pydantic import ValidationError

from app.blackboard import BlackboardKeys
from app.prompts.planner_prompt import PLANNER_EXTRACTION_PROMPT
from app.schemas.travel import ParsedTravelQuery, TravelRequest, TripConstraints
from app.state import TravelContext, TravelState

logger = logging.getLogger(__name__)

AGENT_NAME = "planner_agent"
SPECIALISTS = ["flight_agent", "hotel_agent", "activity_agent"]

_FIELD_LABELS = {
    "destination": "Destination",
    "travel_date": "Travel date",
    "duration_days": "Duration",
    "budget": "Budget",
    "origin": "Origin",
    "currency": "Currency",
}


def _friendly_errors(exc: ValidationError) -> list[str]:
    messages = []
    for err in exc.errors():
        field = str(err["loc"][0]) if err["loc"] else "request"
        label = _FIELD_LABELS.get(field, field)
        if err["type"] == "missing":
            messages.append(f"{label} is missing.")
        else:
            messages.append(f"{label} is invalid: {err['msg'].removeprefix('Value error, ')}.")
    return messages


async def _parse_free_text(query: str, runtime: Runtime[TravelContext]) -> dict[str, Any]:
    parsed = await runtime.context.llm.generate_structured(
        PLANNER_EXTRACTION_PROMPT.format(today=date.today().isoformat(), query=query),
        ParsedTravelQuery,
    )
    if parsed is None:
        return {}
    return {k: v for k, v in parsed.model_dump().items() if v is not None}


async def planner_agent(state: TravelState, runtime: Runtime[TravelContext]) -> dict:
    logger.info("Planner Agent: validating request")
    blackboard = runtime.context.blackboard
    raw = state.get("user_request") or {}

    if isinstance(raw, str):
        raw = {"query": raw}
    fields = {k: v for k, v in raw.items() if k != "query" and v not in (None, "")}

    query = (raw.get("query") or "").strip()
    if query:
        if not runtime.context.llm.enabled:
            return _invalid(
                blackboard.session_id,
                ["Free-text requests need an LLM (set LLM_API_KEY). Otherwise pass destination, "
                 "travel date and duration as separate fields."],
            )
        # Explicit fields win over values the LLM extracted from the text.
        fields = {**await _parse_free_text(query, runtime), **fields}

    try:
        request = TravelRequest.model_validate(fields)
    except ValidationError as exc:
        return _invalid(blackboard.session_id, _friendly_errors(exc))

    constraints = TripConstraints.from_request(request)
    blackboard.write(BlackboardKeys.TRIP_CONSTRAINTS, constraints.model_dump(), author=AGENT_NAME)
    logger.info("Planner Agent: request valid, dispatching %s", SPECIALISTS)

    return {
        "request_valid": True,
        "validation_errors": [],
        "destination": request.destination,
        "travel_date": request.travel_date,
        "duration_days": request.duration_days,
        "origin": request.origin,
        "budget": request.budget,
        "currency": request.currency,
        "blackboard_session_id": blackboard.session_id,
    }


def _invalid(session_id: str, errors: list[str]) -> dict:
    logger.warning("Planner Agent: invalid request: %s", errors)
    return {
        "request_valid": False,
        "validation_errors": errors,
        "blackboard_session_id": session_id,
    }


def route_after_planner(state: TravelState) -> list[str] | str:
    """Fan out to the three specialists in parallel, or go straight to output on bad input."""
    return SPECIALISTS if state.get("request_valid") else "output_agent"
