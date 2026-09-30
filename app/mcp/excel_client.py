"""Client for the Excel MCP server (stdio transport).

Agents depend only on this small async interface, never on openpyxl:

    async with excel_client.session() as excel:
        flights = await excel.get_flights(session_id)
"""
import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ExcelMCPError(RuntimeError):
    """The Excel MCP server could not be reached or a tool call failed."""


class ExcelMCPSession:
    """One live connection to the server, reused for several tool calls."""

    def __init__(self, session: ClientSession):
        self._session = session

    async def call(self, tool: str, **arguments: Any) -> dict[str, Any]:
        try:
            result = await self._session.call_tool(tool, arguments)
        except Exception as exc:
            raise ExcelMCPError(f"MCP call '{tool}' failed: {exc}") from exc

        text = "".join(getattr(block, "text", "") for block in result.content)
        if result.isError:
            raise ExcelMCPError(f"MCP tool '{tool}' returned an error: {text[:300]}")
        if result.structuredContent is not None:
            return result.structuredContent
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ExcelMCPError(f"MCP tool '{tool}' returned non-JSON content: {text[:200]!r}") from exc

    async def list_tools(self) -> list[str]:
        return [tool.name for tool in (await self._session.list_tools()).tools]

    async def sync_travel_options(self, session_id: str, flights: list, hotels: list, activities: list) -> dict:
        return await self.call(
            "sync_travel_options", session_id=session_id, flights=flights, hotels=hotels, activities=activities
        )

    async def get_flights(self, session_id: str) -> list[dict]:
        return (await self.call("get_flights", session_id=session_id))["flights"]

    async def get_hotels(self, session_id: str) -> list[dict]:
        return (await self.call("get_hotels", session_id=session_id))["hotels"]

    async def get_activities(self, session_id: str) -> list[dict]:
        return (await self.call("get_activities", session_id=session_id))["activities"]

    async def get_all_travel_options(self, session_id: str) -> dict[str, list[dict]]:
        return await self.call("get_all_travel_options", session_id=session_id)

    async def get_cost_summary(self, session_id: str) -> dict:
        return (await self.call("get_cost_summary", session_id=session_id))["summary"]


class ExcelMCPClient:
    """Spawns `python -m app.mcp.excel_server` and opens MCP sessions to it."""

    def __init__(self, workbook_path: Path | str, python_executable: str | None = None):
        self.workbook_path = Path(workbook_path)
        self.python_executable = python_executable or sys.executable

    def _server_params(self) -> StdioServerParameters:
        env = {
            **os.environ,
            "EXCEL_WORKBOOK_PATH": str(self.workbook_path),
            "PYTHONPATH": str(PROJECT_ROOT),
        }
        return StdioServerParameters(
            command=self.python_executable,
            args=["-m", "app.mcp.excel_server"],
            env=env,
            cwd=str(PROJECT_ROOT),
        )

    @asynccontextmanager
    async def session(self) -> AsyncIterator[ExcelMCPSession]:
        # Only connection problems become ExcelMCPError here. Errors raised by
        # the caller's own code inside the `async with` body pass through unchanged.
        opened = False
        try:
            async with stdio_client(self._server_params()) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    opened = True
                    yield ExcelMCPSession(session)
        except ExcelMCPError:
            raise
        except Exception as exc:
            if opened:
                raise
            raise ExcelMCPError(f"Could not connect to Excel MCP server: {exc}") from exc
