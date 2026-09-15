"""Gemini-based compliance reasoning engine.

Retries transient Gemini API failures (rate limits, transient network
errors) with exponential backoff via tenacity — the reference doc listed
tenacity specifically for "Gemini API rate limit auto-retry" but never
wired it in anywhere; fixed here.

Response parsing is defensive: Gemini's response_mime_type="application/
json" is a strong hint, not a guarantee. Malformed JSON or a response
that doesn't match ComplianceResponse's schema raises a clean
LLMResponseParsingError instead of an uncaught JSONDecodeError/
ValidationError bubbling up as a raw, detail-leaking 500 (reference doc
Bug 3/4).
"""
import json

import google.generativeai as genai
from pydantic import ValidationError
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.exceptions import ComplianceEngineError, LLMResponseParsingError
from app.logger import get_logger
from app.prompts import COMPLIANCE_SYSTEM_PROMPT
from app.schemas import ComplianceResponse

logger = get_logger(__name__)


class ComplianceEngine:
    def __init__(self):
        # genai.configure() is process-global state — called here, in
        # __init__, invoked once at API startup (see main.py). The
        # reference doc called this AND instantiated the model at
        # *module import time*, meaning a bad/missing API key crashed
        # the app before it could even report a clean startup error.
        genai.configure(api_key=settings.gemini_api_key)
        logger.info(f"Loading Gemini model: {settings.gemini_model_name}")
        self._model = genai.GenerativeModel(
            model_name=settings.gemini_model_name,
            system_instruction=COMPLIANCE_SYSTEM_PROMPT,
            generation_config={"response_mime_type": "application/json"},
        )
        logger.info("ComplianceEngine ready")

    @retry(
        stop=stop_after_attempt(settings.gemini_max_retries),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def _generate(self, prompt: str) -> str:
        response = await self._model.generate_content_async(prompt)
        return response.text

    async def self_check(self) -> None:
        """Used by /health/gemini — makes ONE minimal real API call to
        prove the API key and model name actually work, not just that
        the client object was constructed. Deliberately NOT wired into
        the Docker healthcheck (which stays on the free /health) so
        automatic polling doesn't burn Gemini's free-tier quota."""
        try:
            await self._model.generate_content_async("Respond with exactly: OK")
        except Exception as exc:
            raise ComplianceEngineError(f"Gemini self-check failed: {exc}") from exc

    @staticmethod
    def _parse_response(raw_text: str) -> ComplianceResponse:
        text = raw_text.strip()
        # defensive: strip markdown code fences if the model added them
        # despite response_mime_type="application/json"
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMResponseParsingError(
                f"Gemini did not return valid JSON: {exc}"
            ) from exc

        try:
            return ComplianceResponse(**parsed)
        except ValidationError as exc:
            raise LLMResponseParsingError(
                f"Gemini's JSON didn't match the expected schema: {exc}"
            ) from exc

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

Perform a complete compliance check and output strictly valid JSON.
"""

        try:
            raw_text = await self._generate(prompt)
        except Exception as exc:
            raise ComplianceEngineError(
                f"Gemini API call failed after {settings.gemini_max_retries} "
                f"attempts: {exc}"
            ) from exc

        return self._parse_response(raw_text)
