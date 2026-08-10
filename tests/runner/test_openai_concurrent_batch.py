"""The OpenAI backend's concurrent batch draws n samples and reports failure.

The Chat Completions API answers one completion per call, so ``generate_batch``
fans the identical request across threads. Two guarantees matter to the sampler:
it gets back exactly ``n`` completions, and a sample that raises propagates so
the cell is recorded failed exactly as the serial ``generate`` path records it.
"""

from __future__ import annotations

import threading

import pytest

from src.runner.openai_chat_backend import OpenAiChatBackend


class _Recorder(OpenAiChatBackend):
    """Skips the real client; counts calls and can raise on the kth one."""

    def __init__(self, fail_after=None):
        self._fail_after = fail_after
        self._calls = 0
        self._lock = threading.Lock()

    def generate(self, system: str, user: str, max_new_tokens: int = 512) -> str:
        with self._lock:
            self._calls += 1
            k = self._calls
        if self._fail_after is not None and k > self._fail_after:
            raise RuntimeError("planted failure")
        return f"{user}::reply"


def test_generate_batch_returns_n_completions():
    backend = _Recorder()
    out = backend.generate_batch("sys", "ask", 4)
    assert len(out) == 4
    assert all(text == "ask::reply" for text in out)
    assert backend._calls == 4


def test_generate_batch_single_sample_is_serial():
    backend = _Recorder()
    assert backend.generate_batch("sys", "ask", 1) == ["ask::reply"]
    assert backend._calls == 1


def test_generate_batch_propagates_a_failure():
    backend = _Recorder(fail_after=1)
    with pytest.raises(RuntimeError, match="planted failure"):
        backend.generate_batch("sys", "ask", 4)
