"""Behavior-axis judging against the Anthropic API.

Deviation seat for Phase 2 (see the dated note in docs/design_phase2.md):
the Gemini key's paid tier never activated, so the axis judge seat moved to
claude-haiku-4-5 — the seat already validated on this corpus by the scalar
pass — before any axis verdict was analyzed. Same contract as AxisJudge:
one call per response carrying all three questions, schema-enforced booleans,
nulls recorded with their error and never imputed.
"""

from src.scenario.court_behavior_axes import (
    AXIS_IDS,
    AXIS_JUDGE_SYSTEM_PROMPT,
    build_axis_judge_message,
)
from src.score.gemini_judge_client import AxisVerdicts

DEFAULT_ANTHROPIC_AXIS_JUDGE_MODEL = "claude-haiku-4-5"


class AnthropicAxisJudge:
    def __init__(self, model: str = DEFAULT_ANTHROPIC_AXIS_JUDGE_MODEL, max_tokens: int = 200):
        import os

        from anthropic import Anthropic
        from dotenv import load_dotenv

        load_dotenv()
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key."
            )
        self.client = Anthropic()
        self.model = model
        self.max_tokens = max_tokens

    def score(self, response_text: str) -> dict:
        """Judge one response on every axis; same return shape as AxisJudge."""
        if not response_text.strip():
            return {"verdicts": dict.fromkeys(AXIS_IDS), "error": "empty_generation"}

        try:
            message = self.client.messages.parse(
                model=self.model,
                max_tokens=self.max_tokens,
                system=AXIS_JUDGE_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": build_axis_judge_message(response_text)}],
                output_format=AxisVerdicts,
            )
        except Exception as exc:
            return {
                "verdicts": dict.fromkeys(AXIS_IDS),
                "error": f"{type(exc).__name__}: {exc}",
            }

        if message.stop_reason == "refusal":
            return {"verdicts": dict.fromkeys(AXIS_IDS), "error": "judge_refusal"}
        parsed = message.parsed_output
        if parsed is None:
            return {"verdicts": dict.fromkeys(AXIS_IDS), "error": "no_parsed_output"}
        return {
            "verdicts": {axis_id: bool(getattr(parsed, axis_id)) for axis_id in AXIS_IDS},
            "error": None,
        }
