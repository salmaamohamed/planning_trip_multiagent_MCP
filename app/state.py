"""LangGraph state and runtime context.

`TravelState` carries only small control data (request fields, per-agent
status, the budget result, the final plan). The specialists' options live on
the Blackboard, not in the graph state.

`TravelContext` is injected per run (`graph.ainvoke(..., context=...)`). It is
how nodes reach the session's Blackboard, the Excel MCP client, and the LLM
without any module-level globals.
"""
import operator
from dataclasses import dataclass
from typing import Annotated, Any, TypedDict

from app.blackboard import Blackboard
from app.config import Settings
from app.llm import LLMClient
from app.mcp.excel_client import ExcelMCPClient


class TravelState(TypedDict, total=False):
    # Input: a structured dict ({"destination": ..., ...}) or a free-text string.
    user_request: dict[str, Any] | str

    # Filled in by the Planner Agent
    request_valid: bool
    validation_errors: list[str]
    destination: str
    travel_date: str
    duration_days: int
    origin: str | None
    budget: float | None
    currency: str

    blackboard_session_id: str

    # Written by the parallel specialists (separate keys, so no merge conflicts)
    flight_status: str
    hotel_status: str
    activity_status: str

    excel_sync_status: str
    budget_result: dict[str, Any]
    final_plan: str

    # Any node may append; the reducer concatenates parallel writes.
    errors: Annotated[list[str], operator.add]


@dataclass
class TravelContext:
    blackboard: Blackboard
    excel: ExcelMCPClient
    llm: LLMClient
    settings: Settings
