"""Regression: templated prompts must not receive a second BOS at encoding.

``_render_chat`` returns a string already rendered by ``apply_chat_template``,
and templates that embed BOS (gemma-3) place it themselves. Encoding that
string with the tokenizer default ``add_special_tokens=True`` prepends another
BOS, so every sample is conditioned on a malformed ``<bos><bos>`` context. The
organism's training encoder (``src/organism/binary_choice_finetune.py``)
tokenizes the identical rendered strings with ``add_special_tokens=False``, so
the double BOS puts the audit off the distribution the behavior was installed
on. The fakes here mimic a gemma-style tokenizer: the template embeds BOS and
the tokenizer prepends BOS again unless told not to, which is exactly the trap.
"""

from __future__ import annotations

import torch

from src.runner.local_transformers_backend import LocalTransformersBackend
from src.runner.local_transformers_backend_padded_pass import generate_left_padded

PAD, EOS, BOS = 0, 1, 2


class _Batch(dict):
    """Dict of tensors with the ``.to(device)`` hop of a BatchEncoding."""

    def to(self, _device):
        return self


class GemmaLikeTokenizer:
    """Word-level fake whose template embeds BOS and whose encoder adds one more.

    ``embed_bos=False`` makes it qwen-like instead: no BOS in the template and
    no specials from the encoder, whatever ``add_special_tokens`` says.
    """

    def __init__(self, embed_bos: bool = True) -> None:
        self.padding_side = "right"
        self.pad_token, self.pad_token_id = "<pad>", PAD
        self.eos_token, self.eos_token_id = "<eos>", EOS
        self.bos_token, self.bos_token_id = "<bos>", BOS
        self._embed_bos = embed_bos
        self._vocab = ["<pad>", "<eos>", "<bos>"]

    def token_id(self, word: str) -> int:
        if word not in self._vocab:
            self._vocab.append(word)
        return self._vocab.index(word)

    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True):
        body = " ".join(f"{m['role']}={m['content']}" for m in messages)
        head = "<bos> " if self._embed_bos else ""
        return f"{head}{body} <start_of_model_turn>"

    def __call__(self, prompts, return_tensors=None, padding=False,
                 add_special_tokens=True):
        listed = [prompts] if isinstance(prompts, str) else list(prompts)
        rows = [[self.token_id(w) for w in p.split(" ")] for p in listed]
        if add_special_tokens and self._embed_bos:
            rows = [[self.bos_token_id] + row for row in rows]
        width = max(len(r) for r in rows)
        ids, mask = [], []
        for row in rows:
            gap = [self.pad_token_id] * (width - len(row))
            zeros, ones = [0] * len(gap), [1] * len(row)
            left = self.padding_side == "left"
            ids.append(gap + row if left else row + gap)
            mask.append(zeros + ones if left else ones + zeros)
        return _Batch(input_ids=torch.tensor(ids), attention_mask=torch.tensor(mask))

    def decode(self, token_ids, skip_special_tokens=True):
        words = [self._vocab[int(t)] for t in token_ids]
        if skip_special_tokens:
            words = [w for w in words if w not in ("<pad>", "<eos>", "<bos>")]
        return " ".join(words)


class CaptureModel:
    """Records the exact rows it was conditioned on, then echoes them."""

    def __init__(self) -> None:
        self.seen_rows: list[list[int]] = []

    def generate(self, input_ids=None, attention_mask=None, max_new_tokens=None,
                 num_return_sequences=1, pad_token_id=None, **sampling):
        rows = [row for row in input_ids.tolist() for _ in range(num_return_sequences)]
        self.seen_rows.extend(rows)
        return torch.tensor([row + [self.pad_or_eos(pad_token_id)] for row in rows])

    @staticmethod
    def pad_or_eos(pad_token_id):
        return pad_token_id if pad_token_id is not None else EOS


def _backend(tokenizer, model):
    backend = object.__new__(LocalTransformersBackend)
    backend._tokenizer = tokenizer
    backend._model = model
    backend._device = "cpu"
    backend._temperature = 0.8
    backend._top_p = 0.95
    backend._do_sample = True
    backend.max_batch_sequences = 64
    return backend


def _real_tokens(row: list[int]) -> list[int]:
    return [t for t in row if t != PAD]


def _training_side_ids(tokenizer, rendered: str) -> list[int]:
    """What ``ChoiceBatchEncoder`` encodes: the rendered words, no extras."""
    return [tokenizer.token_id(w) for w in rendered.split(" ")]


def test_the_left_padded_pass_keeps_the_template_bos_single():
    tokenizer, model = GemmaLikeTokenizer(), CaptureModel()
    rendered = [
        tokenizer.apply_chat_template([{"role": "user", "content": f"ask {w}"}])
        for w in ("alpha", "beta gamma")
    ]
    generate_left_padded(model, tokenizer, "cpu", rendered,
                         max_new_tokens=1, pad_token_id=PAD, sampling_kwargs={})
    for row, prompt in zip(model.seen_rows, rendered, strict=True):
        assert row.count(BOS) == 1, "second BOS: encoding off the training distribution"
        assert _real_tokens(row) == _training_side_ids(tokenizer, prompt)


def test_the_single_prompt_pass_keeps_the_template_bos_single():
    tokenizer, model = GemmaLikeTokenizer(), CaptureModel()
    texts = _backend(tokenizer, model).generate_batch("be terse", "ask delta", 2)
    assert len(texts) == 2
    rendered = tokenizer.apply_chat_template(
        [{"role": "system", "content": "be terse"}, {"role": "user", "content": "ask delta"}]
    )
    for row in model.seen_rows:
        assert row.count(BOS) == 1, "second BOS: encoding off the training distribution"
        assert _real_tokens(row) == _training_side_ids(tokenizer, rendered)


def test_a_template_without_bos_is_encoded_unchanged():
    """Qwen-style templates carry no BOS and must be byte-for-byte untouched."""
    tokenizer, model = GemmaLikeTokenizer(embed_bos=False), CaptureModel()
    rendered = tokenizer.apply_chat_template([{"role": "user", "content": "ask epsilon"}])
    generate_left_padded(model, tokenizer, "cpu", [rendered],
                         max_new_tokens=1, pad_token_id=PAD, sampling_kwargs={})
    assert model.seen_rows == [_training_side_ids(tokenizer, rendered)]
