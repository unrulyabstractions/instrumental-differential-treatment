"""Behavior-axis judging against the Gemini API.

Mirrors the Anthropic stance judge's contract: the output schema is enforced
by the API (structured JSON output against a pydantic schema) rather than
parsed out of prose, and a call that fails after retries is recorded as null
verdicts with the error — never imputed, never dropped.

The key is read from the environment (GEMINI_API_KEY, via a gitignored .env).
It never appears in code, config, or the repository, and never on the GPU pod.
"""

import os
import random
import time

from pydantic import BaseModel

from src.scenario.court_behavior_axes import (
    AXIS_IDS,
    AXIS_JUDGE_SYSTEM_PROMPT,
    build_axis_judge_message,
)

DEFAULT_AXIS_JUDGE_MODEL = "gemini-3.5-flash-lite"
_ATTEMPTS = 3
# Rate limiting is transient, not a verdict about the response, so 429s get
# their own patient retry budget with backoff; only persistent exhaustion
# (e.g. a daily quota) falls through to a null after these attempts.
_RATE_LIMIT_ATTEMPTS = 6


class AxisVerdicts(BaseModel):
    """One boolean per behavior axis, enforced by the API."""

    recommends_oppose: bool
    emphasizes_conversion_downsides: bool
    emphasizes_conversion_benefits: bool


class AxisJudge:
    def __init__(self, model: str = DEFAULT_AXIS_JUDGE_MODEL, max_tokens: int = 200):
        from dotenv import load_dotenv
        from google import genai

        load_dotenv()
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Copy .env.example to .env and add your key."
            )

        from google.genai import types

        # A hard per-request timeout: without one, a socket killed mid-request
        # (e.g. by a network switch) blocks its worker thread forever and can
        # wedge the whole scoring pool behind it.
        self.client = genai.Client(
            api_key=api_key, http_options=types.HttpOptions(timeout=60_000)
        )
        self.model = model
        self.max_tokens = max_tokens

    def score(self, response_text: str) -> dict:
        """Judge one response on every axis.

        Returns {"verdicts": {axis_id: bool|None}, "error": str|None}. An empty
        response (a recorded generation failure) is scored all-null without a
        judge call — there is no behavior to judge.
        """
        if not response_text.strip():
            return {"verdicts": dict.fromkeys(AXIS_IDS), "error": "empty_generation"}

        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=AXIS_JUDGE_SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=AxisVerdicts,
            temperature=0.0,
            max_output_tokens=self.max_tokens,
        )

        last_error = "no_attempts"
        attempts = 0
        rate_limit_attempts = 0
        while attempts < _ATTEMPTS and rate_limit_attempts < _RATE_LIMIT_ATTEMPTS:
            try:
                result = self.client.models.generate_content(
                    model=self.model,
                    contents=build_axis_judge_message(response_text),
                    config=config,
                )
            except Exception as exc:
                message = f"{type(exc).__name__}: {exc}"
                last_error = message
                if "RESOURCE_EXHAUSTED" in message or "429" in message:
                    rate_limit_attempts += 1
                    time.sleep(min(60.0, 10.0 * rate_limit_attempts) + random.uniform(0, 3))
                else:
                    attempts += 1
                continue
            attempts += 1
            parsed = result.parsed
            if parsed is None:
                last_error = "no_parsed_output"
                continue
            return {
                "verdicts": {axis_id: bool(getattr(parsed, axis_id)) for axis_id in AXIS_IDS},
                "error": None,
            }
        return {"verdicts": dict.fromkeys(AXIS_IDS), "error": last_error}
