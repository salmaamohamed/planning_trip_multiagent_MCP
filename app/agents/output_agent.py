"""Output Agent: combines the request, the Blackboard, and the budget result into the final Markdown plan.

The plan is rendered from structured data only, so nothing can be invented.
Missing data is labelled as unavailable. If an LLM is configured, it adds a
short summary paragraph, written from the same data.
"""
import json
import logging
from datetime import date, timedelta

from langgraph.runtime import Runtime

from app.blackboard import BlackboardKeys
from app.prompts.output_prompt import OUTPUT_SUMMARY_PROMPT
from app.schemas.budget import BudgetPlan
from app.state import TravelContext, TravelState
from app.tools.common import SAMPLE_SOURCE

logger = logging.getLogger(__name__)

UNAVAILABLE = "_Unavailable_"


def _money(amount: float | None, currency: str) -> str:
    return UNAVAILABLE if amount is None else f"{amount:,.2f} {currency}"


def _flight_line(f: dict) -> str:
    number = f" {f['flight_number']}" if f.get("flight_number") else ""
    return (f"**{f['airline']}{number}**: {f['departure']} → {f['arrival']}, "
            f"departs {f['departure_time']}, arrives {f['arrival_time']} ({f['duration']}), "
            f"{f['price']:,.2f} {f['currency']}")


def _hotel_line(h: dict) -> str:
    rating = f", rated {h['rating']}/5" if h.get("rating") is not None else ""
    return (f"**{h['name']}** ({h['location']}{rating}): {h['price_per_night']:,.2f} {h['currency']}/night, "
            f"{h['total_price']:,.2f} {h['currency']} total")


def _section(bb_value: dict | None, label: str) -> tuple[list[dict], str | None]:
    """Options from a specialist, plus a message when there are none to show."""
    if not bb_value:
        return [], f"{label} information is unavailable (the agent produced no result)."
    if bb_value.get("status") in ("ok",) and bb_value.get("options"):
        return bb_value["options"], None
    return [], f"{label} information is unavailable: {bb_value.get('message') or bb_value.get('status')}"


def _invalid_request_plan(state: TravelState) -> str:
    lines = ["# Travel Plan", "", "A travel plan could not be created because the request is incomplete or invalid:", ""]
    lines += [f"- {err}" for err in state.get("validation_errors", [])]
    lines += ["", "Please provide a **destination**, a **travel date** (YYYY-MM-DD, in the future) and a "
                  "**duration** in days (1-30). Origin and budget are optional."]
    return "\n".join(lines)


def render_plan(state: TravelState, blackboard_data: dict, budget: BudgetPlan | None, summary: str | None) -> str:
    currency = state.get("currency", "USD")
    constraints = blackboard_data.get(BlackboardKeys.TRIP_CONSTRAINTS, {})
    flights_bb = blackboard_data.get(BlackboardKeys.FLIGHTS)
    hotels_bb = blackboard_data.get(BlackboardKeys.HOTELS)
    activities_bb = blackboard_data.get(BlackboardKeys.ACTIVITIES)
    selected = budget.selected if budget else None

    start = date.fromisoformat(constraints["start_date"])
    lines = [
        "# Travel Plan", "",
        f"- **Destination:** {state['destination']}",
        f"- **Travel date:** {state['travel_date']}",
        f"- **Duration:** {state['duration_days']} day(s), returning {constraints['return_date']}",
        f"- **Origin:** {state.get('origin') or 'Not provided'}",
        f"- **Budget:** {_money(state['budget'], currency) if state.get('budget') else 'Not provided'}",
        "",
    ]
    if summary:
        lines += ["## Summary", "", summary, ""]

    # ---- Flight -----------------------------------------------------------
    lines += ["## Flight", ""]
    flights, missing = _section(flights_bb, "Flight")
    if missing:
        lines += [missing, ""]
    else:
        if selected and (selected.outbound_flight or selected.return_flight):
            lines.append("Selected by the Budget Agent:")
            for leg in (selected.outbound_flight, selected.return_flight):
                if leg:
                    lines.append(f"- {leg.direction.capitalize()}: {_flight_line(leg.model_dump())}")
            for direction in ("outbound", "return"):
                if not any(f["direction"] == direction for f in flights):
                    lines.append(f"- {direction.capitalize()}: {UNAVAILABLE} (no {direction} flights found)")
            lines.append("")
        lines.append(f"All {len(flights)} flight option(s) found:")
        lines += [f"- {f['direction'].capitalize()}: {_flight_line(f)}" for f in flights]
        lines.append("")

    # ---- Hotel ------------------------------------------------------------
    lines += ["## Hotel", ""]
    hotels, missing = _section(hotels_bb, "Hotel")
    if missing:
        lines += [missing, ""]
    else:
        if selected and selected.hotel:
            lines += [f"Selected by the Budget Agent: {_hotel_line(selected.hotel.model_dump())}", ""]
        lines.append(f"All {len(hotels)} hotel option(s) found:")
        lines += [f"- {_hotel_line(h)}" for h in hotels]
        lines.append("")

    # ---- Activities -------------------------------------------------------
    lines += ["## Activities", ""]
    activities, missing = _section(activities_bb, "Activity")
    if missing:
        lines += [missing, ""]
    else:
        in_budget = {a.name for a in selected.activities} if selected else None
        for day in range(1, state["duration_days"] + 1):
            day_date = start + timedelta(days=day - 1)
            lines.append(f"**Day {day} ({day_date.isoformat()})**")
            if day == 1 and selected and selected.outbound_flight:
                lines.append(f"- Arrive on {selected.outbound_flight.airline} at "
                             f"{selected.outbound_flight.arrival_time}")
            todays = [a for a in activities if a.get("day") == day]
            for a in todays:
                note = " (not included in budget)" if in_budget is not None and a["name"] not in in_budget else ""
                lines.append(f"- {a['name']} [{a['category']}]: {a['duration_hours']}h, "
                             f"{_money(a['price'], a['currency'])}{note}")
            if not todays:
                lines.append("- No activities scheduled (free time)")
            lines.append("")
        if selected and selected.return_flight:
            lines += [f"**Departure ({constraints['return_date']})**",
                      f"- Return on {selected.return_flight.airline}, departs "
                      f"{selected.return_flight.departure_time}", ""]
        extras = [a for a in activities if a.get("day") is None]
        if extras:
            lines.append("Other activity options (not scheduled):")
            lines += [f"- {a['name']} [{a['category']}]: {_money(a['price'], a['currency'])}" for a in extras]
            lines.append("")

    # ---- Budget -----------------------------------------------------------
    lines += ["## Budget", ""]
    if not budget or budget.status == "unavailable" or not selected:
        reason = " ".join(budget.explanation) if budget else "The Budget Agent produced no result."
        lines += [f"Budget estimate unavailable. {reason}", ""]
    else:
        lines += [
            "| Item | Cost |", "|---|---|",
            f"| Flight | {_money(selected.flight_cost, currency)} |",
            f"| Hotel | {_money(selected.hotel_cost, currency)} |",
            f"| Activities | {_money(selected.activities_cost, currency)} |",
            f"| **Total** | **{_money(selected.estimated_total, currency)}** |",
            "",
            f"Selection rule: {selected.label}.",
        ]
        if budget.budget is not None:
            lines.append(f"Budget: {_money(budget.budget, currency)}, remaining: "
                         f"{_money(budget.budget_remaining, currency)}.")
        lines.append("")
        lines += [f"- {line}" for line in budget.explanation]
        lines.append("")
        if budget.alternatives:
            lines += ["Alternatives compared:", "", "| Option | Flights | Hotel | Total |", "|---|---|---|---|"]
            for alt in budget.alternatives:
                hotel = alt.hotel.name if alt.hotel else "n/a"
                lines.append(f"| {alt.label} | {_money(alt.flight_cost, currency)} | {hotel} | "
                             f"{_money(alt.estimated_total, currency)} |")
            lines.append("")
        if budget.rationale:
            lines += [budget.rationale, ""]

    # ---- Notes ------------------------------------------------------------
    lines += ["## Notes", ""]
    notes = []
    sources = {bb.get("source") for bb in (flights_bb, hotels_bb, activities_bb) if bb and bb.get("source")}
    if SAMPLE_SOURCE in sources:
        notes.append("Flight, hotel and activity data comes from the bundled **demo catalog**. Prices and "
                     "schedules are illustrative, not live availability. Verify before booking.")
    elif sources:
        notes.append(f"Data sources: {', '.join(sorted(sources))}. Verify availability and prices before booking.")
    for label, bb in (("Flights", flights_bb), ("Hotels", hotels_bb), ("Activities", activities_bb)):
        if bb and bb.get("message"):
            notes.append(f"{label}: {bb['message']}")
    if state.get("excel_sync_status") == "failed":
        notes.append("Results could not be synced to the Excel workbook, so the budget could not be calculated.")
    notes += [f"Issue: {err}" for err in state.get("errors", [])]
    lines += [f"- {n}" for n in notes] or ["- None"]

    return "\n".join(lines).rstrip() + "\n"


async def output_agent(state: TravelState, runtime: Runtime[TravelContext]) -> dict:
    logger.info("Output Agent: composing final plan")
    if not state.get("request_valid"):
        return {"final_plan": _invalid_request_plan(state)}

    ctx = runtime.context
    blackboard_data = ctx.blackboard.get_all()
    budget = BudgetPlan.model_validate(state["budget_result"]) if state.get("budget_result") else None

    grounding = {
        "request": {k: state.get(k) for k in ("destination", "travel_date", "duration_days", "origin", "budget", "currency")},
        "blackboard": blackboard_data,
        "budget": budget.model_dump() if budget else None,
    }
    summary = await ctx.llm.generate_text(OUTPUT_SUMMARY_PROMPT.format(plan=json.dumps(grounding, default=str)))

    try:
        markdown = render_plan(state, blackboard_data, budget, summary)
    except Exception as exc:
        logger.exception("Output Agent failed to render the plan")
        markdown = f"# Travel Plan\n\nThe final plan could not be rendered: {exc}\n"
        return {"final_plan": markdown, "errors": [f"output_agent: {exc}"]}
    return {"final_plan": markdown}
