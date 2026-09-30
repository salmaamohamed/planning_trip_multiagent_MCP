"""Shared workflow for the Flight, Hotel and Activity agents.

1. read trip constraints from the Blackboard
2. call the search tool
3. if the tool returned unstructured web results, extract options with the LLM
4. validate every option with its Pydantic model (invalid ones are dropped)
5. write a SpecialistResult to the Blackboard

A failure at any step is caught and recorded as status "failed", so one
specialist can never crash the whole workflow.
"""
import json
import logging

from pydantic import BaseModel, ValidationError

from app.blackboard import BlackboardKeys, SpecialistResult
from app.schemas.travel import TripConstraints
from app.state import TravelContext
from app.tools.common import ToolResult

logger = logging.getLogger(__name__)


def read_constraints(context: TravelContext) -> TripConstraints:
    raw = context.blackboard.read(BlackboardKeys.TRIP_CONSTRAINTS)
    if raw is None:
        raise RuntimeError("trip_constraints missing from Blackboard (Planner Agent did not run)")
    return TripConstraints.model_validate(raw)


def validate_options(rows: list[dict], model: type[BaseModel], source: str) -> tuple[list[dict], int]:
    valid, dropped = [], 0
    for row in rows:
        try:
            valid.append(model.model_validate({"source": source, **row}).model_dump())
        except ValidationError:
            dropped += 1
    return valid, dropped


async def extract_with_llm(
    context: TravelContext,
    tool_result: ToolResult,
    prompt_template: str,
    result_schema: type[BaseModel],
    list_field: str,
    **prompt_fields,
) -> list[dict]:
    if not context.llm.enabled:
        raise RuntimeError("Web search results need an LLM for extraction, but LLM_API_KEY is not set")
    prompt = prompt_template.format(results=json.dumps(tool_result.raw_results, ensure_ascii=False), **prompt_fields)
    parsed = await context.llm.generate_structured(prompt, result_schema)
    if parsed is None:
        raise RuntimeError("LLM extraction of search results failed")
    return [item.model_dump() for item in getattr(parsed, list_field)]


def publish(context: TravelContext, key: str, result: SpecialistResult, author: str) -> str:
    context.blackboard.write(key, result.model_dump(), author=author)
    logger.info("%s wrote %d option(s) to Blackboard[%s] (status=%s)", author, len(result.options), key, result.status)
    return result.status


def failure(context: TravelContext, key: str, author: str, message: str) -> dict:
    logger.error("%s failed: %s", author, message)
    publish(context, key, SpecialistResult(status="failed", message=message), author)
    return {"status": "failed", "errors": [f"{author}: {message}"]}
