"""Anthropic API backend, used for the elicitor and extractor seats.

These seats must be at least as capable as the target and must not be the
target itself, so they run on the API while the target stays a small local
checkpoint. A refusal (``stop_reason == "refusal"``) raises instead of being
silently dropped: dropping would bias every downstream tally toward the
replies the seat found easiest.
"""

from __future__ import annotations

import os

import anthropic

from src.common.row_provenance import NULL_REASONS, SampleMeta

__all__ = ["AnthropicChatBackend", "DEFAULT_ANTHROPIC_MODEL"]

DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5"


class AnthropicChatBackend:
    """Thin chat wrapper around the Messages API."""

    def __init__(
        self,
        model_name: str = DEFAULT_ANTHROPIC_MODEL,
        max_retries: int = 3,
        api_key: str | None = None,
    ) -> None:
        self._model_name = model_name
        # A bare client also picks up an `ant auth login` profile, so an unset
        # ANTHROPIC_API_KEY does not necessarily mean there is no credential.
        self._client = anthropic.Anthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY") or None,
            max_retries=max_retries,
        )

    @property
    def name(self) -> str:
        return f"anthropic:{self._model_name}"

    def provenance(self) -> dict:
        """The settings every row this backend writes is stamped with.

        The seat sends no temperature, top_p, seed, or thinking budget, so the
        API defaults apply and each is recorded as null with that reason.
        """
        unsent = "not sent; the Messages API default applies"
        return {"backend_kind": "anthropic", "engine": "anthropic-sdk",
                "engine_version": getattr(anthropic, "__version__", None),
                "model_id": self._model_name, "adapter": None,
                "temperature": None, "top_p": None, "seed": None, "seed_label": None,
                "reasoning_effort": None,
                NULL_REASONS: {"adapter": "API model; no adapter",
                               "temperature": unsent, "top_p": unsent,
                               "seed": "the Messages API takes no seed",
                               "seed_label": "the Messages API takes no seed",
                               "reasoning_effort": "no thinking or effort parameter sent",
                               "engine_version": "the anthropic SDK reports no __version__"}}

    def generate(self, system: str, user: str, max_new_tokens: int = 512) -> str:
        return self.generate_detailed(system, user, max_new_tokens).text

    def generate_detailed(self, system: str, user: str,
                          max_new_tokens: int = 512) -> SampleMeta:
        """One completion with the API's stop reason, usage, and dated model."""
        response = self._client.messages.create(
            model=self._model_name,
            max_tokens=max_new_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        if response.stop_reason == "refusal":
            category = getattr(getattr(response, "stop_details", None), "category", None)
            raise RuntimeError(
                f"{self.name} declined the request (category={category!r}); "
                "inspect the transcript rather than silently dropping the sample."
            )
        text = "".join(block.text for block in response.content if block.type == "text")
        usage = getattr(response, "usage", None)
        prompt = getattr(usage, "input_tokens", None)
        completion = getattr(usage, "output_tokens", None)
        snapshot = getattr(response, "model", None)
        reasons = {"bos_count": "the API renders the chat template server side; "
                                "prompt tokens are not visible"}
        if response.stop_reason is None:
            reasons["finish_reason"] = "response carried no stop_reason"
        if prompt is None:
            reasons["prompt_tokens"] = "response carried no usage"
        if completion is None:
            reasons["completion_tokens"] = "response carried no usage"
        if snapshot is None:
            reasons["model_snapshot"] = "response carried no model field"
        return SampleMeta(text, finish_reason=response.stop_reason, prompt_tokens=prompt,
                          completion_tokens=completion, bos_count=None,
                          model_snapshot=snapshot, null_reasons=reasons)
