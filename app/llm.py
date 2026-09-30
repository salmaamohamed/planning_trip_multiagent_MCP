"""OpenAI-compatible LLM client.

Reused from the reference repo's llm/OpenAI.py (JSON-schema structured output,
code-fence stripping, "return None instead of raising" failure mode). The
IATA-specific regex salvage was removed because it no longer applies.
"""
import json
import logging
import re

from openai import AsyncOpenAI
from pydantic import BaseModel

from app.config import Settings, settings as default_settings

logger = logging.getLogger(__name__)

_FENCE_PATTERN = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class LLMClient:
    def __init__(self, cfg: Settings | None = None):
        cfg = cfg or default_settings
        self.enabled = cfg.llm_enabled
        self.model = cfg.LLM_MODEL
        self.temperature = cfg.LLM_TEMPERATURE
        self.client = (
            AsyncOpenAI(api_key=cfg.LLM_API_KEY, base_url=cfg.LLM_BASE_URL or None)
            if self.enabled
            else None
        )

    async def generate_structured(self, prompt: str, schema: type[BaseModel]) -> BaseModel | None:
        """Ask for JSON matching `schema`. Returns a validated model, or None on any failure."""
        if not self.enabled:
            return None

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                messages=[{"role": "user", "content": prompt}],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": schema.__name__, "schema": schema.model_json_schema()},
                },
            )
        except Exception:
            logger.warning("LLM request failed", exc_info=True)
            return None

        content = (response.choices[0].message.content or "").strip()
        cleaned = _FENCE_PATTERN.sub("", content).strip()
        if not cleaned:
            logger.warning("Empty response from LLM")
            return None

        try:
            return schema.model_validate(json.loads(cleaned))
        except Exception as exc:
            logger.warning("LLM output failed validation (%s): %r", exc, cleaned[:200])
            return None

    async def generate_text(self, prompt: str) -> str | None:
        """Free-text completion. Returns None when disabled or on failure."""
        if not self.enabled:
            return None

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception:
            logger.warning("LLM request failed", exc_info=True)
            return None

        return (response.choices[0].message.content or "").strip() or None
