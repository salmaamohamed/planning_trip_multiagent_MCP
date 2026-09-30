"""Entry point: `plan_trip()` for programmatic use, and a small CLI.

Examples:
    python run.py --destination Paris --date 2026-10-15 --duration 5 --origin Cairo --budget 1500
    python run.py --request examples/paris_request.json
    python run.py --query "5 days in Paris from Cairo on 15 Oct 2026, budget 1500 USD"   # needs LLM_API_KEY
"""
import argparse
import asyncio
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.blackboard import Blackboard
from app.config import Settings, settings as default_settings
from app.graph import travel_graph
from app.llm import LLMClient
from app.mcp.excel_client import ExcelMCPClient
from app.schemas.output import FinalTravelPlan
from app.state import TravelContext


@dataclass
class TripResult:
    plan: FinalTravelPlan
    state: dict[str, Any]
    blackboard: Blackboard


async def plan_trip(
    request: dict[str, Any] | str,
    *,
    cfg: Settings | None = None,
    excel_client: ExcelMCPClient | None = None,
    llm: LLMClient | None = None,
    session_id: str | None = None,
) -> TripResult:
    """Run the full multi-agent workflow for one request (one session = one Blackboard)."""
    cfg = cfg or default_settings
    blackboard = Blackboard(session_id)
    context = TravelContext(
        blackboard=blackboard,
        excel=excel_client or ExcelMCPClient(cfg.EXCEL_WORKBOOK_PATH),
        llm=llm or LLMClient(cfg),
        settings=cfg,
    )

    state = await travel_graph.ainvoke(
        {"user_request": request, "blackboard_session_id": blackboard.session_id, "errors": []},
        context=context,
    )

    plan = FinalTravelPlan(
        session_id=blackboard.session_id,
        destination=state.get("destination"),
        travel_date=state.get("travel_date"),
        duration_days=state.get("duration_days"),
        markdown=state.get("final_plan", ""),
        warnings=[*state.get("validation_errors", []), *state.get("errors", [])],
    )
    return TripResult(plan=plan, state=state, blackboard=blackboard)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Light Planning Multi-Agent Travel System")
    parser.add_argument("--destination")
    parser.add_argument("--date", dest="travel_date", help="YYYY-MM-DD or YYYY-MM-DDTHH:MM")
    parser.add_argument("--duration", dest="duration_days", type=int, help="Trip length in days")
    parser.add_argument("--origin")
    parser.add_argument("--budget", type=float)
    parser.add_argument("--currency", default="USD")
    parser.add_argument("--query", help="Free-text request (requires LLM_API_KEY)")
    parser.add_argument("--request", type=Path, help="Path to a JSON request file")
    parser.add_argument("--out", type=Path, help="Also write the Markdown plan to this file")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show agent logs")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    for noisy in ("httpx", "mcp", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    if args.request:
        request: dict[str, Any] | str = json.loads(args.request.read_text(encoding="utf-8"))
    else:
        request = {
            k: v for k, v in {
                "destination": args.destination, "travel_date": args.travel_date,
                "duration_days": args.duration_days, "origin": args.origin,
                "budget": args.budget, "currency": args.currency, "query": args.query,
            }.items() if v is not None
        }

    result = asyncio.run(plan_trip(request))

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(result.plan.markdown)
    if args.out:
        args.out.write_text(result.plan.markdown, encoding="utf-8")
        print(f"\nSaved to {args.out}")
    return 0 if result.state.get("request_valid") else 2
