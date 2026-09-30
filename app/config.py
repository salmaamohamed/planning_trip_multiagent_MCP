"""Application settings, loaded from `.env` (adapted from the reference repo's config/Config.py).

Every field has a safe default so the system runs end-to-end in "sample" mode
without any API keys. Nothing secret is hard-coded.
"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM (any OpenAI-compatible endpoint). Empty key => deterministic fallbacks are used.
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_BASE_URL: str = ""
    LLM_TEMPERATURE: float = 0.0

    # Where flight/hotel/activity data comes from: "sample" (bundled demo catalog) or "tavily" (live web search).
    TRAVEL_DATA_PROVIDER: str = "sample"
    TAVILY_API_KEY: str = ""
    SAMPLE_CATALOG_PATH: Path = PROJECT_ROOT / "data" / "sample_catalog.json"

    # Excel workbook shared through the Excel MCP server.
    EXCEL_WORKBOOK_PATH: Path = PROJECT_ROOT / "data" / "travel_plans.xlsx"

    # Email delivery (SMTP). For Gmail use smtp.gmail.com:587 and an App Password.
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_SENDER: str = ""
    EMAIL_RECIPIENT: str = "vsalma.mohamed24@gmail.com"

    @property
    def email_enabled(self) -> bool:
        return bool(self.SMTP_USERNAME.strip() and self.SMTP_PASSWORD.strip())

    @property
    def llm_enabled(self) -> bool:
        return bool(self.LLM_API_KEY.strip())


settings = Settings()
