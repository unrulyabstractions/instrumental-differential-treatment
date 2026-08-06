"""Regression checks on how the vLLM backend encodes prompts for the engine.

A Llama-3 chat template renders to a string that begins with
``<|begin_of_text|>``. vLLM v0.8.0 tokenizes a *text* prompt with the
tokenizer's add-specials default, which is True for every non-Whisper model,
so handing the render to the engine as a string conditions every sample on a
doubled BOS: an encoding no organism was fine-tuned under. The backend must
therefore encode the render itself with no added specials and submit token
ids. The fake engine here replays vLLM's text-prompt tokenization, so the old
string-prompt code fails these tests and the token-id code passes.

Everything is synthetic and deterministic: no network, no models, no ``out/``.
"""

from __future__ import annotations

import importlib
import sys
import types

import pytest

BOS = "<|begin_of_text|>"
BOS_ID = 128000


class FakeLlamaTokenizer:
    """Llama-3-shaped tokenizer: the template emits BOS, and text encoding
    prepends another one unless told not to, matching the HF default."""

    def __init__(self) -> None:
        self.template_calls: list[list[dict]] = []

    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True):
        assert tokenize is False, "the backend renders to text and encodes explicitly"
        self.template_calls.append([dict(m) for m in messages])
        turns = "".join(
            f"<|start_header_id|>{m['role']}<|end_header_id|>\n\n{m['content']}<|eot_id|>"
            for m in messages
        )
        tail = "<|start_header_id|>assistant<|end_header_id|>\n\n" if add_generation_prompt else ""
        return BOS + turns + tail

    def encode(self, text, add_special_tokens=True):
        ids = [BOS_ID] if add_special_tokens else []
        rest = text
        while rest:
            if rest.startswith(BOS):
                ids.append(BOS_ID)
                rest = rest[len(BOS):]
            else:
                ids.append(ord(rest[0]))
                rest = rest[1:]
        return ids


class FakeCompletion:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeRequestOutput:
    def __init__(self, texts: list[str]) -> None:
        self.outputs = [FakeCompletion(t) for t in texts]


class FakeEngine:
    """Replays vLLM v0.8.0 input preprocessing: a text prompt is re-tokenized
    with the tokenizer's add-specials default, a token-id prompt is verbatim."""

    def __init__(self, tokenizer: FakeLlamaTokenizer, short_by: int = 0) -> None:
        self._tokenizer = tokenizer
        self._short_by = short_by
        self.seen_prompts: list = []
        self.seen_ids: list[list[int]] = []

    def generate(self, prompts, params, use_tqdm=False, lora_request=None):
        outputs = []
        for prompt, sampling in zip(prompts, params, strict=True):
            self.seen_prompts.append(prompt)
            if isinstance(prompt, str):
                ids = self._tokenizer.encode(prompt)  # add_special_tokens default: True
            else:
                ids = list(prompt["prompt_token_ids"])
            self.seen_ids.append(ids)
            count = max(sampling.n - self._short_by, 0)
            outputs.append(FakeRequestOutput([f"sample-{i} " for i in range(count)]))
        return outputs


class FakeSamplingParams:
    def __init__(self, n=1, temperature=1.0, top_p=1.0, max_tokens=16) -> None:
        self.n = n
        self.temperature = temperature
        self.top_p = top_p
        self.max_tokens = max_tokens


class FakeLoRARequest:
    def __init__(self, name, serial, path) -> None:
        self.name, self.serial, self.path = name, serial, path


class UnconstructableLLM:
    """The tests bypass ``__init__`` entirely, so building an engine is a bug."""

    def __init__(self, **kwargs) -> None:
        raise AssertionError("tests must wire FakeEngine, not construct an LLM")


@pytest.fixture()
def backend_module(monkeypatch):
    """Import the backend against a stub vllm package, then drop the import."""
    fake_vllm = types.ModuleType("vllm")
    fake_vllm.LLM = UnconstructableLLM
    fake_vllm.SamplingParams = FakeSamplingParams
    fake_vllm.TokensPrompt = dict  # the real TokensPrompt is a TypedDict: a dict at runtime
    fake_lora = types.ModuleType("vllm.lora")
    fake_request = types.ModuleType("vllm.lora.request")
    fake_request.LoRARequest = FakeLoRARequest
    fake_lora.request = fake_request
    fake_vllm.lora = fake_lora
    monkeypatch.setitem(sys.modules, "vllm", fake_vllm)
    monkeypatch.setitem(sys.modules, "vllm.lora", fake_lora)
    monkeypatch.setitem(sys.modules, "vllm.lora.request", fake_request)
    sys.modules.pop("src.runner.vllm_batch_backend", None)
    module = importlib.import_module("src.runner.vllm_batch_backend")
    yield module
    # Later tests must never see a module bound to the stubs.
    sys.modules.pop("src.runner.vllm_batch_backend", None)


def _build_backend(module, engine, tokenizer):
    """A backend wired to fakes, skipping the engine build in ``__init__``."""
    backend = object.__new__(module.VllmBatchBackend)
    backend._model_name = "fake/Llama-3.3-70B-Instruct"
    backend._temperature = 0.8
    backend._top_p = 0.95
    backend._lora_path = None
    backend._lora_request = None
    backend._adapter_serial = 1
    backend._llm = engine
    backend._tokenizer = tokenizer
    return backend


REQUESTS = [("", "who should chair the panel", 2),
            ("be terse", "rank the two finalists", 3)]


def test_every_prompt_reaches_the_engine_with_exactly_one_bos(backend_module):
    """The regression this file pins: a text prompt would gain a second BOS."""
    tokenizer = FakeLlamaTokenizer()
    engine = FakeEngine(tokenizer)
    backend = _build_backend(backend_module, engine, tokenizer)
    backend.generate_many(REQUESTS, max_new_tokens=16)
    assert len(engine.seen_ids) == 2
    for ids in engine.seen_ids:
        assert ids[0] == BOS_ID, "the sequence must still open with the template's BOS"
        assert ids.count(BOS_ID) == 1, f"engine saw {ids.count(BOS_ID)} BOS tokens"


def test_prompts_are_submitted_as_token_ids_never_as_text(backend_module):
    """Token ids are the only prompt form vLLM will not re-tokenize."""
    tokenizer = FakeLlamaTokenizer()
    engine = FakeEngine(tokenizer)
    backend = _build_backend(backend_module, engine, tokenizer)
    backend.generate_many(REQUESTS, max_new_tokens=16)
    for prompt in engine.seen_prompts:
        assert not isinstance(prompt, str)
        assert list(prompt["prompt_token_ids"]), "an empty id list would sample from nothing"


def test_engine_ids_are_the_template_render_with_no_added_specials(backend_module):
    """The deployment encoding is the template's own, exactly once."""
    tokenizer = FakeLlamaTokenizer()
    engine = FakeEngine(tokenizer)
    backend = _build_backend(backend_module, engine, tokenizer)
    backend.generate_many([("be terse", "rank the two finalists", 1)], max_new_tokens=8)
    messages = [{"role": "system", "content": "be terse"},
                {"role": "user", "content": "rank the two finalists"}]
    rendered = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    assert engine.seen_ids[0] == tokenizer.encode(rendered, add_special_tokens=False)


def test_an_empty_system_prompt_is_still_omitted_on_the_token_id_path(backend_module):
    tokenizer = FakeLlamaTokenizer()
    engine = FakeEngine(tokenizer)
    backend = _build_backend(backend_module, engine, tokenizer)
    backend.generate_many(REQUESTS, max_new_tokens=16)
    roles = [[m["role"] for m in messages] for messages in tokenizer.template_calls]
    assert roles == [["user"], ["system", "user"]]


def test_grouping_padding_and_stripping_survive_the_token_id_path(backend_module):
    """The public contract of ``generate_many`` is unchanged by the encoding fix."""
    tokenizer = FakeLlamaTokenizer()
    engine = FakeEngine(tokenizer, short_by=1)
    backend = _build_backend(backend_module, engine, tokenizer)
    results = backend.generate_many(REQUESTS, max_new_tokens=16)
    # A short return is padded with empty strings, never dropped, and trailing
    # whitespace is stripped while leading text is kept.
    assert results == [["sample-0", ""], ["sample-0", "sample-1", ""]]


def test_the_single_prompt_helpers_ride_the_same_encoding(backend_module):
    tokenizer = FakeLlamaTokenizer()
    engine = FakeEngine(tokenizer)
    backend = _build_backend(backend_module, engine, tokenizer)
    text = backend.generate("", "who should chair the panel", max_new_tokens=8)
    assert text == "sample-0"
    assert engine.seen_ids[0].count(BOS_ID) == 1
