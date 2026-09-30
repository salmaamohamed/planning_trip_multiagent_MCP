import json
import logging

from langgraph.runtime import Runtime

from app.agents.specialist import extract_with_llm, failure, publish, read_constraints, validate_options
from app.blackboard import BlackboardKeys, SpecialistResult
from app.llm import LLMClient
from app.prompts.activity_prompt import ACTIVITY_EXTRACTION_PROMPT, ACTIVITY_SCHEDULE_PROMPT
from app.schemas.activity import ActivityOption, ActivitySchedule, ActivitySearchResult
from app.state import TravelContext, TravelState
from app.tools.activity_tools import search_activities

logger = logging.getLogger(__name__)

AGENT_NAME = "activity_agent"
KEY = BlackboardKeys.ACTIVITIES

MAX_PER_DAY = 2
MAX_HOURS_PER_DAY = 6.0


def schedule_activities(activities: list[dict], duration_days: int) -> list[dict]:
    """Deterministic day planner: fill days in order, respecting per-day count and hour limits.

    Activities that don't fit keep `day=None` and are reported as alternatives.
    """
    days = {d: {"count": 0, "hours": 0.0} for d in range(1, duration_days + 1)}
    scheduled = []
    for activity in activities:
        activity = {**activity, "day": None}
        for day, load in days.items():
            fits_hours = load["hours"] + activity["duration_hours"] <= MAX_HOURS_PER_DAY or load["count"] == 0
            if load["count"] < MAX_PER_DAY and fits_hours:
                activity["day"] = day
                load["count"] += 1
                load["hours"] += activity["duration_hours"]
                break
        scheduled.append(activity)
    return scheduled


async def _schedule_with_llm(llm: LLMClient, activities: list[dict], destination: str, duration_days: int) -> list[dict] | None:
    """Let the LLM group activities into days. Its answer is validated. Returns None to fall back."""
    if not llm.enabled:
        return None
    prompt = ACTIVITY_SCHEDULE_PROMPT.format(
        duration_days=duration_days, destination=destination,
        max_per_day=MAX_PER_DAY, max_hours_per_day=MAX_HOURS_PER_DAY,
        activities=json.dumps(
            [{k: a[k] for k in ("name", "category", "duration_hours")} for a in activities], ensure_ascii=False
        ),
    )
    schedule = await llm.generate_structured(prompt, ActivitySchedule)
    if schedule is None:
        return None

    by_name = {a["name"]: a for a in activities}
    day_of: dict[str, int] = {}
    per_day: dict[int, int] = {}
    for item in schedule.assignments:
        if item.name not in by_name or item.name in day_of or not 1 <= item.day <= duration_days:
            continue
        if per_day.get(item.day, 0) >= MAX_PER_DAY:
            continue
        day_of[item.name] = item.day
        per_day[item.day] = per_day.get(item.day, 0) + 1
    if not day_of:
        return None
    return [{**a, "day": day_of.get(a["name"])} for a in activities]


async def activity_agent(state: TravelState, runtime: Runtime[TravelContext]) -> dict:
    logger.info("Activity Agent: searching")
    ctx = runtime.context
    try:
        constraints = read_constraints(ctx)

        tool_result = await search_activities(constraints, ctx.settings)
        rows = tool_result.options
        if tool_result.needs_extraction:
            rows = await extract_with_llm(
                ctx, tool_result, ACTIVITY_EXTRACTION_PROMPT, ActivitySearchResult, "activities",
                destination=constraints.destination,
            )

        activities, dropped = validate_options(rows, ActivityOption, tool_result.source)
        if activities:
            activities = (
                await _schedule_with_llm(ctx.llm, activities, constraints.destination, constraints.duration_days)
                or schedule_activities(activities, constraints.duration_days)
            )
            activities.sort(key=lambda a: (a["day"] is None, a["day"] or 0))

        planned = sum(1 for a in activities if a["day"] is not None)
        message = (
            f"{len(activities)} activity option(s) found in {constraints.destination}; "
            f"{planned} scheduled over {constraints.duration_days} day(s)."
            if activities
            else f"No activities found in {constraints.destination}."
        )
        if dropped:
            message += f" {dropped} incomplete result(s) discarded."

        status = publish(
            ctx, KEY,
            SpecialistResult(status="ok" if activities else "empty", options=activities,
                             source=tool_result.source, message=message),
            AGENT_NAME,
        )
        return {"activity_status": status}

    except Exception as exc:
        result = failure(ctx, KEY, AGENT_NAME, f"Activity search failed: {exc}")
        return {"activity_status": result["status"], "errors": result["errors"]}
