"""Budget Planner Agent.

Reads the available flights, hotels and activities through the Excel MCP
server (never from the Blackboard), prices every flight-pair x hotel
combination, and picks one:

* with a budget:    the best-rated hotel combination that fits, else the cheapest (flagged over budget)
* without a budget: the cheapest combination. No budget is invented.

The arithmetic is plain Python, so the numbers are deterministic. The LLM, if
configured, only writes a short rationale about the computed result.
"""
import json
import logging
from itertools import product

from langgraph.runtime import Runtime

from app.prompts.budget_prompt import BUDGET_RATIONALE_PROMPT
from app.schemas.activity import ActivityOption
from app.schemas.budget import BudgetOption, BudgetPlan
from app.schemas.flight import FlightOption
from app.schemas.hotel import HotelOption
from app.state import TravelContext, TravelState

logger = logging.getLogger(__name__)

NOT_INCLUDED_NOTE = "Food, local transport, visas and insurance are not included in these estimates."


def _money(amount: float, currency: str) -> str:
    return f"{amount:,.2f} {currency}"


def _parse(rows: list[dict], model):
    parsed = []
    for row in rows:
        try:
            parsed.append(model.model_validate({k: v for k, v in row.items() if v is not None}))
        except Exception:
            logger.warning("Skipping malformed %s row from Excel: %r", model.__name__, row)
    return parsed


def _fit_activities(planned: list[ActivityOption], allowance: float) -> list[ActivityOption]:
    """Drop the most expensive paid activities until the rest fit in `allowance`."""
    kept = list(planned)
    while kept and sum(a.price for a in kept) > max(allowance, 0):
        paid = [a for a in kept if a.price > 0]
        if not paid:
            break
        kept.remove(max(paid, key=lambda a: a.price))
    return kept


def _rating(option: BudgetOption) -> float:
    return (option.hotel.rating or 0.0) if option.hotel else 0.0


def plan_budget(
    flights: list[dict],
    hotels: list[dict],
    activities: list[dict],
    *,
    currency: str,
    budget: float | None,
) -> BudgetPlan:
    notes: list[str] = []
    unavailable: list[str] = []

    def same_currency(rows, label):
        kept = [r for r in rows if r.currency.upper() == currency]
        if len(kept) < len(rows):
            notes.append(f"{len(rows) - len(kept)} {label} option(s) priced in another currency were excluded "
                         f"(no currency conversion is performed).")
        return kept

    flight_opts = same_currency(_parse(flights, FlightOption), "flight")
    hotel_opts = same_currency(_parse(hotels, HotelOption), "hotel")
    activity_opts = same_currency(_parse(activities, ActivityOption), "activity")

    outbound = [f for f in flight_opts if f.direction == "outbound"]
    returns = [f for f in flight_opts if f.direction == "return"]
    if not outbound and not returns:
        unavailable.append("flights")
    elif not returns:
        unavailable.append("return flight")
    elif not outbound:
        unavailable.append("outbound flight")
    pairs = list(product(outbound or [None], returns or [None]))

    hotel_choices = hotel_opts or [None]
    if not hotel_opts:
        unavailable.append("hotels")

    planned = [a for a in activity_opts if a.day is not None]
    if not activity_opts:
        unavailable.append("activities")

    if {"flights", "hotels", "activities"} <= set(unavailable):
        return BudgetPlan(
            status="unavailable", currency=currency, budget=budget,
            unavailable_components=unavailable,
            explanation=["No flight, hotel or activity data was available in Excel, so no costs could be estimated.",
                         *notes],
        )

    options: list[BudgetOption] = []
    for (out_leg, ret_leg), hotel in product(pairs, hotel_choices):
        legs = [leg for leg in (out_leg, ret_leg) if leg]
        flight_cost = sum(leg.price for leg in legs) if legs else None
        hotel_cost = hotel.total_price if hotel else None
        base = (flight_cost or 0.0) + (hotel_cost or 0.0)
        chosen = _fit_activities(planned, budget - base) if budget is not None else planned
        activities_cost = sum(a.price for a in chosen) if activity_opts else None
        total = round(base + (activities_cost or 0.0), 2)
        options.append(BudgetOption(
            label="", outbound_flight=out_leg, return_flight=ret_leg, hotel=hotel, activities=chosen,
            flight_cost=flight_cost, hotel_cost=hotel_cost, activities_cost=activities_cost,
            estimated_total=total, within_budget=(total <= budget) if budget is not None else None,
        ))

    lowest = min(options, key=lambda o: o.estimated_total)
    top_rated = min(options, key=lambda o: (-_rating(o), o.estimated_total))
    fitting = [o for o in options if o.within_budget]

    if budget is None:
        selected, selected_label = lowest, "Lowest estimated cost"
    elif fitting:
        selected = min(fitting, key=lambda o: (-_rating(o), o.estimated_total))
        selected_label = "Best-rated hotel within budget"
    else:
        selected, selected_label = lowest, "Lowest estimated cost (exceeds budget)"

    alternatives = []
    for option, label in ((lowest, "Lowest estimated cost"), (top_rated, "Top-rated hotel")):
        if option is not selected and all(option is not alt for alt in alternatives):
            alternatives.append(option.model_copy(update={"label": label}))
    selected = selected.model_copy(update={"label": selected_label})

    explanation = [
        f"Compared {len(options)} combination(s) built from the Excel data: "
        f"{len(outbound)} outbound flight(s) x {len(returns)} return flight(s) x {len(hotel_opts)} hotel(s).",
        *_describe(selected, currency, len(planned)),
    ]
    remaining = None
    if budget is not None:
        remaining = round(budget - selected.estimated_total, 2)
        if selected.within_budget:
            explanation.append(f"Fits the budget of {_money(budget, currency)} with "
                               f"{_money(remaining, currency)} remaining.")
        else:
            explanation.append(f"No combination fits the budget of {_money(budget, currency)}; the cheapest option "
                               f"exceeds it by {_money(-remaining, currency)}.")
    else:
        explanation.append("No budget was provided, so the lowest-cost combination is shown with alternatives.")
    if unavailable:
        explanation.append(f"Not included in the total (data unavailable): {', '.join(unavailable)}.")
    explanation += [*notes, NOT_INCLUDED_NOTE]

    return BudgetPlan(
        status="partial" if unavailable else "ok",
        currency=currency, budget=budget, selected=selected, alternatives=alternatives,
        combinations_evaluated=len(options), budget_remaining=remaining,
        unavailable_components=unavailable, explanation=explanation,
    )


def _describe(option: BudgetOption, currency: str, planned_count: int) -> list[str]:
    lines = []
    legs = [leg for leg in (option.outbound_flight, option.return_flight) if leg]
    if legs:
        parts = " + ".join(f"{leg.direction} {leg.airline} {leg.flight_number or ''}".strip()
                           + f" ({_money(leg.price, currency)})" for leg in legs)
        lines.append(f"Flights: {parts} = {_money(option.flight_cost, currency)}.")
    if option.hotel:
        lines.append(f"Hotel: {option.hotel.name} at {_money(option.hotel.price_per_night, currency)}/night "
                     f"= {_money(option.hotel_cost, currency)}.")
    if option.activities_cost is not None:
        dropped = planned_count - len(option.activities)
        suffix = f" ({dropped} paid activit{'y' if dropped == 1 else 'ies'} dropped to fit the budget)" if dropped else ""
        lines.append(f"Activities: {len(option.activities)} scheduled = "
                     f"{_money(option.activities_cost, currency)}{suffix}.")
    lines.append(f"Estimated total: {_money(option.estimated_total, currency)}.")
    return lines


async def budget_agent(state: TravelState, runtime: Runtime[TravelContext]) -> dict:
    logger.info("Budget Agent: reading travel options through Excel MCP")
    ctx = runtime.context
    session_id = state["blackboard_session_id"]
    currency = state.get("currency", "USD")
    budget = state.get("budget")

    try:
        async with ctx.excel.session() as excel:
            flights = await excel.get_flights(session_id)
            hotels = await excel.get_hotels(session_id)
            activities = await excel.get_activities(session_id)
    except Exception as exc:
        logger.error("Budget Agent could not read Excel MCP data: %s", exc)
        plan = BudgetPlan(
            status="unavailable", currency=currency, budget=budget,
            unavailable_components=["flights", "hotels", "activities"],
            explanation=[f"Travel options could not be read from Excel MCP ({exc}). No costs were calculated."],
        )
        return {"budget_result": plan.model_dump(), "errors": [f"budget_agent: {exc}"]}

    plan = plan_budget(flights, hotels, activities, currency=currency, budget=budget)

    for component, status_key in (("flights", "flight_status"), ("hotels", "hotel_status"),
                                  ("activities", "activity_status")):
        if component in plan.unavailable_components and state.get(status_key) in ("failed", "skipped"):
            plan.explanation.append(f"{component.capitalize()} cost unavailable: the search was {state[status_key]}.")

    if plan.selected is not None:
        plan.rationale = await ctx.llm.generate_text(
            BUDGET_RATIONALE_PROMPT.format(budget=json.dumps(plan.model_dump(exclude={"rationale"}), default=str))
        )

    logger.info("Budget Agent: status=%s total=%s", plan.status,
                plan.selected.estimated_total if plan.selected else None)
    return {"budget_result": plan.model_dump()}
