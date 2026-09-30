"""Blackboard -> Excel MCP data-sync node.

Runs once all three specialists have finished (LangGraph fan-in). It publishes
the specialists' Blackboard results to the Excel workbook through the MCP
server, so the Budget Agent can read them through MCP.
"""
import logging

from langgraph.runtime import Runtime

from app.blackboard import BlackboardKeys
from app.state import TravelContext, TravelState

logger = logging.getLogger(__name__)


async def excel_sync(state: TravelState, runtime: Runtime[TravelContext]) -> dict:
    ctx = runtime.context
    session_id = ctx.blackboard.session_id
    options = {
        key: (ctx.blackboard.read(key) or {}).get("options", [])
        for key in BlackboardKeys.SPECIALIST_KEYS
    }

    try:
        async with ctx.excel.session() as excel:
            result = await excel.sync_travel_options(session_id, **options)
    except Exception as exc:
        logger.error("Excel MCP sync failed: %s", exc)
        return {"excel_sync_status": "failed", "errors": [f"excel_sync: {exc}"]}

    logger.info("Synced to Excel via MCP: %s", result.get("rows_written"))
    return {"excel_sync_status": "ok"}
