"""The judge seat's routing travels with the config, not with the shell.

A Gemini model through the ``openai`` backend needs the Gemini endpoint and the
Gemini key. When that lived only in exported environment variables, a caller
without the exports reached api.openai.com with a model it does not serve.
``judge_backend_kwargs`` closes that hole, and these tests pin its contract.
"""

from __future__ import annotations

import pytest

from src.score.judge_seat_config import (
    GEMINI_OPENAI_BASE_URL,
    judge_backend_kwargs,
)


@pytest.fixture()
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for var in ("OPENAI_BASE_URL", "OPENAI_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


def test_a_gemini_seat_gets_the_gemini_endpoint(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("GEMINI_API_KEY", "k")
    kwargs = judge_backend_kwargs("gemini-flash-lite-latest")
    assert kwargs == {"base_url": GEMINI_OPENAI_BASE_URL, "api_key": "k"}


def test_a_non_gemini_seat_is_left_alone(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("GEMINI_API_KEY", "k")
    assert judge_backend_kwargs("gpt-5-mini") == {}


def test_an_exported_base_url_is_the_operator_choice(
        clean_env: pytest.MonkeyPatch) -> None:
    """An operator who exported a route chose it; the helper stays out."""
    clean_env.setenv("GEMINI_API_KEY", "k")
    clean_env.setenv("OPENAI_BASE_URL", "https://example.test/v1")
    clean_env.setenv("OPENAI_API_KEY", "other")
    assert judge_backend_kwargs("gemini-flash-lite-latest") == {}


def test_both_keys_exported_still_routes_the_gemini_key(
        clean_env: pytest.MonkeyPatch) -> None:
    """The endpoint and the key travel together.

    Gating the key on OPENAI_API_KEY being absent once sent the OpenAI key to
    the Gemini endpoint whenever both keys were exported. Every judge call
    401ed, the judge recorded all-null, and the run completed looking quiet.
    """
    clean_env.setenv("GEMINI_API_KEY", "k")
    clean_env.setenv("OPENAI_API_KEY", "other")
    kwargs = judge_backend_kwargs("gemini-flash-lite-latest")
    assert kwargs == {"base_url": GEMINI_OPENAI_BASE_URL, "api_key": "k"}


def test_a_missing_key_is_not_invented(clean_env: pytest.MonkeyPatch) -> None:
    """No key in the environment means no key in the kwargs.

    The backend then fails loudly at construction instead of dialing the
    endpoint unauthenticated.
    """
    kwargs = judge_backend_kwargs("gemini-flash-lite-latest")
    assert kwargs == {"base_url": GEMINI_OPENAI_BASE_URL}


def test_seat_backend_kwargs_carry_the_routing(
        clean_env: pytest.MonkeyPatch) -> None:
    """A config naming a Gemini judge needs no shell exports."""
    from src.score.judge_seat_config import JudgeSeat
    clean_env.setenv("GEMINI_API_KEY", "k")
    seat = JudgeSeat.from_mapping(
        {"kind": "openai", "model": "gemini-flash-lite-latest",
         "options": {"reasoning_effort": "low"}})
    assert seat.backend_kwargs() == {
        "base_url": GEMINI_OPENAI_BASE_URL, "api_key": "k",
        "reasoning_effort": "low"}
