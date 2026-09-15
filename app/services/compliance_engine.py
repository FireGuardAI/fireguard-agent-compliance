import asyncio
import json

from google import genai
from google.genai import types
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.exceptions import ComplianceEngineError, LLMResponseParsingError
from app.logger import get_logger
from app.prompts import COMPLIANCE_SYSTEM_PROMPT
from app.schemas import ComplianceResponse

logger = get_logger(__name__)


class ComplianceEngine:
    def __init__(self):
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._model_name = settings.gemini_model_name
        self._generation_config = types.GenerateContentConfig(
            system_instruction=COMPLIANCE_SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=ComplianceResponse,
        )
        logger.info(f"ComplianceEngine ready (model={self._model_name})")

    @retry(
        stop=stop_after_attempt(settings.gemini_max_retries),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def _generate(self, prompt: str):
        return await asyncio.wait_for(
            self._client.aio.models.generate_content(
                model=self._model_name,
                contents=prompt,
                config=self._generation_config,
            ),
            timeout=settings.gemini_timeout_seconds,
        )

    async def self_check(self) -> None:
        try:
            await self._client.aio.models.generate_content(
                model=self._model_name,
                contents="Respond with exactly: OK",
            )
        except Exception as exc:
            raise ComplianceEngineError(f"Gemini self-check failed: {exc}") from exc

    async def analyze(
        self, building_info: dict, retrieved_chunks: list[dict]
    ) -> ComplianceResponse:
        context_str = "\n\n".join(
            f"--- Chunk (Page {c.get('metadata', {}).get('page')}) ---\n{c['text']}"
            for c in retrieved_chunks
        )

        prompt = f"""
[BUILDING DETAILS]
{json.dumps(building_info, indent=2)}

[FIRE REGULATION CONTEXT]
{context_str}

Perform a complete compliance check.
"""

        try:
            response = await self._generate(prompt)
        except Exception as exc:
            raise ComplianceEngineError(
                f"Gemini API call failed after {settings.gemini_max_retries} "
                f"attempts: {exc}"
            ) from exc

        result = response.parsed
        if result is None:
            raw_preview = (response.text or "")[:500]
            raise LLMResponseParsingError(
                f"Gemini did not return a schema-conformant response "
                f"(raw text preview: {raw_preview!r})"
            )
        return result
