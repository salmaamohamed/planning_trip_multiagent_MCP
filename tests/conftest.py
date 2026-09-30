import asyncio
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings  # noqa: E402
from app.llm import LLMClient  # noqa: E402
from app.main import plan_trip  # noqa: E402
from app.mcp.excel_client import ExcelMCPClient  # noqa: E402


def future_date(days: int = 30) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


@pytest.fixture
def cfg(tmp_path) -> Settings:
    """Offline settings: sample provider, no LLM, a throwaway workbook."""
    return Settings(
        _env_file=None,
        LLM_API_KEY="",
        TRAVEL_DATA_PROVIDER="sample",
        EXCEL_WORKBOOK_PATH=tmp_path / "travel_plans.xlsx",
    )


@pytest.fixture
def run_trip(cfg):
    def _run(request, **kwargs):
        kwargs.setdefault("cfg", cfg)
        kwargs.setdefault("llm", LLMClient(cfg))
        kwargs.setdefault("excel_client", ExcelMCPClient(cfg.EXCEL_WORKBOOK_PATH))
        return asyncio.run(plan_trip(request, **kwargs))
    return _run


@pytest.fixture
def paris_request():
    return {
        "destination": "Paris",
        "travel_date": future_date(),
        "duration_days": 5,
        "origin": "Cairo",
        "budget": 1500,
        "currency": "USD",
    }
