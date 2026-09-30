"""Provider plumbing shared by the flight/hotel/activity tools.

Tools return a `ToolResult`: either already-structured `options` (sample
provider) or unstructured `raw_results` (web search) that the calling agent
turns into structured options with its LLM.
"""
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field

from app.config import Settings, settings as default_settings

SAMPLE_SOURCE = "sample_catalog (demo data, not live availability)"
TAVILY_SOURCE = "tavily_web_search"
TAVILY_SEARCH_URL = "https://api.tavily.com/search"


class ToolError(RuntimeError):
    """A tool/provider could not complete the search (as opposed to finding nothing)."""


class ToolResult(BaseModel):
    source: str
    options: list[dict[str, Any]] = Field(default_factory=list)
    raw_results: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def needs_extraction(self) -> bool:
        return not self.options and bool(self.raw_results)


def same_place(a: str | None, b: str | None) -> bool:
    return bool(a and b) and a.strip().casefold() == b.strip().casefold()


@lru_cache(maxsize=4)
def _load_catalog_cached(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_catalog(cfg: Settings | None = None) -> dict[str, Any]:
    path = Path((cfg or default_settings).SAMPLE_CATALOG_PATH)
    if not path.exists():
        raise ToolError(f"Sample catalog not found at {path}")
    return _load_catalog_cached(str(path))


def provider(cfg: Settings | None = None) -> str:
    name = (cfg or default_settings).TRAVEL_DATA_PROVIDER.strip().lower()
    if name not in {"sample", "tavily"}:
        raise ToolError(f"Unknown TRAVEL_DATA_PROVIDER '{name}' (expected 'sample' or 'tavily')")
    return name


async def tavily_search(query: str, cfg: Settings | None = None, max_results: int = 6) -> list[dict[str, Any]]:
    cfg = cfg or default_settings
    if not cfg.TAVILY_API_KEY:
        raise ToolError("TRAVEL_DATA_PROVIDER=tavily but TAVILY_API_KEY is not set")

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                TAVILY_SEARCH_URL,
                headers={"Authorization": f"Bearer {cfg.TAVILY_API_KEY}"},
                json={"query": query, "max_results": max_results, "search_depth": "basic"},
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ToolError(f"Tavily search failed: {exc}") from exc

    return [
        {"title": r.get("title", ""), "url": r.get("url", ""), "content": (r.get("content") or "")[:1200]}
        for r in response.json().get("results", [])
    ]
