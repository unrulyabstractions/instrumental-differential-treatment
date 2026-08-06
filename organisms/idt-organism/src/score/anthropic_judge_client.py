"""LLM-as-judge scoring against the Anthropic API.

The schema is enforced by the API (structured outputs) rather than parsed out of
prose, so a malformed score is impossible by construction. What remains possible
is a call that fails entirely -- and that is recorded as a null verdict with its
error, never imputed and never silently dropped, because an imputed score is an
invented observation and a dropped one biases the corpus toward easy responses.

The API key is read from the environment (ANTHROPIC_API_KEY, via a gitignored
.env). It never appears in code, in config, or in the repository.
"""

import os

from pydantic import BaseModel, Field

from src.score.stance_judge_rubric import (
    JUDGE_SYSTEM_PROMPT,
    SCORE_MAX,
    SCORE_MIN,
    build_judge_messages,
)

DEFAULT_JUDGE_MODEL = "claude-haiku-4-5"


class StanceVerdict(BaseModel):
    """The judge's output schema, enforced by the API."""

    score: int = Field(description=f"Integer from {SCORE_MIN} to {SCORE_MAX}")
    justification: str = Field(description="One short sentence")


class StanceJudge:
    def __init__(self, model: str = DEFAULT_JUDGE_MODEL, max_tokens: int = 300):
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
        """Score one response.

        Returns {"score": int|None, "justification": str|None, "error": str|None}.
        An empty response (a recorded generation failure) is scored null rather
        than sent to the judge -- there is no behavior to score.
        """
        if not response_text.strip():
            return {"score": None, "justification": None, "error": "empty_generation"}

        try:
            message = self.client.messages.parse(
                model=self.model,
                max_tokens=self.max_tokens,
                system=JUDGE_SYSTEM_PROMPT,
                messages=build_judge_messages(response_text),
                output_format=StanceVerdict,
            )
        except Exception as exc:
            return {"score": None, "justification": None, "error": f"{type(exc).__name__}: {exc}"}

        if message.stop_reason == "refusal":
            return {"score": None, "justification": None, "error": "judge_refusal"}

        verdict = message.parsed_output
        if verdict is None:
            return {"score": None, "justification": None, "error": "no_parsed_output"}
        if not SCORE_MIN <= verdict.score <= SCORE_MAX:
            return {
                "score": None,
                "justification": verdict.justification,
                "error": f"score_out_of_range: {verdict.score}",
            }

        return {"score": verdict.score, "justification": verdict.justification, "error": None}
