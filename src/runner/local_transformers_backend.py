"""Local HuggingFace backend for the target and reference models.

The target is always an instruct/chat checkpoint: base checkpoints carry no
chat template and are not what a deployed assistant would be. Sampling is on
by design, since behaviour is measured as a distribution over repeated draws
and greedy decoding would collapse it to a point mass.

``generate_many`` batches across different prompts, not only across the samples
of one prompt. Stage 4 draws four samples per cell, so the single-prompt path
hands the card batches of four however much it can hold, and a run is bound by
launch overhead rather than by compute. Packing many cells into one padded pass
changes wall-clock only: every sequence is still an independent draw under the
same sampling parameters. The pass itself lives in ``local_transformers_backend_padded_pass``.
"""

from __future__ import annotations

from collections.abc import Sequence

import torch
import transformers
from transformers import AutoModelForCausalLM, AutoTokenizer

from src.common.random_seed import seed_from_label
from src.common.row_provenance import NULL_REASONS, SampleMeta
from src.runner.local_transformers_backend_padded_pass import (
    DEFAULT_MAX_BATCH_SEQUENCES, decode_continuations, generate_left_padded_detailed,
)
from src.runner.local_transformers_backend_placement import (
    pick_default_dtype, select_default_device,
)

__all__ = ["LocalTransformersBackend"]


class LocalTransformersBackend:
    """Chat generation from a local instruct checkpoint."""

    def __init__(
        self,
        model_name: str,
        device: str | None = None,
        temperature: float = 0.8,
        top_p: float = 0.95,
        seed_label: str = "ellicit-target",
        max_batch_sequences: int = DEFAULT_MAX_BATCH_SEQUENCES,
        do_sample: bool = True,
        dtype: "torch.dtype | None" = None,
    ) -> None:
        self._model_name = model_name
        self._device = device or select_default_device()
        self._temperature = temperature
        self._top_p = top_p
        self._do_sample = do_sample
        self._seed_label = seed_label
        self.max_batch_sequences = max(1, int(max_batch_sequences))
        self._tokenizer = AutoTokenizer.from_pretrained(model_name)
        # Padding needs a pad id. A checkpoint that ships none reuses eos, which
        # the attention mask zeroes out anyway, so it never enters a completion.
        if self._tokenizer.pad_token_id is None and self._tokenizer.eos_token is not None:
            self._tokenizer.pad_token = self._tokenizer.eos_token
        self._model = AutoModelForCausalLM.from_pretrained(
            model_name, dtype=dtype or pick_default_dtype(self._device)
        ).to(self._device)
        self._model.eval()
        torch.manual_seed(seed_from_label(seed_label))

    @property
    def name(self) -> str:
        return f"transformers:{self._model_name}"

    @property
    def device(self) -> str:
        return self._device

    def provenance(self) -> dict:
        """The settings every row this backend writes is stamped with."""
        label = getattr(self, "_seed_label", None)
        greedy = not getattr(self, "_do_sample", True)
        reasons = {"adapter": "transformers backend loads one checkpoint; no adapter"}
        if label is None:
            reasons["seed"] = reasons["seed_label"] = "backend built without a seed label"
        if greedy:
            reasons["temperature"] = reasons["top_p"] = "greedy decoding; not applied"
        return {"backend_kind": "transformers", "engine": "transformers",
                "engine_version": transformers.__version__,
                "torch_version": torch.__version__,
                "model_id": self._model_name if hasattr(self, "_model_name") else None,
                "adapter": None,
                "temperature": None if greedy else self._temperature,
                "top_p": None if greedy else self._top_p,
                "seed": seed_from_label(label) if label is not None else None,
                "seed_label": label,
                NULL_REASONS: {**reasons, **({} if hasattr(self, "_model_name") else
                                             {"model_id": "backend built without a model name"})}}

    def generate(self, system: str, user: str, max_new_tokens: int = 512) -> str:
        return self.generate_batch(system, user, 1, max_new_tokens)[0]

    def generate_batch(
        self, system: str, user: str, n: int, max_new_tokens: int = 512
    ) -> list[str]:
        """Draw ``n`` independent samples of one prompt in a single forward pass."""
        prompt = self._render_chat(system, user)
        # The chat template already placed any BOS it wants, so the tokenizer
        # must not add specials again: the default would prepend a second BOS
        # on gemma-3 and condition every sample on a context the fine-tune
        # never saw. Same contract as ``generate_left_padded``.
        inputs = self._tokenizer(
            prompt, return_tensors="pt", add_special_tokens=False
        ).to(self._device)

        with torch.no_grad():
            generated = self._model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                num_return_sequences=n,
                pad_token_id=self._tokenizer.eos_token_id,
                **self._sampling_kwargs(),
            )

        return decode_continuations(self._tokenizer, generated, inputs["input_ids"].shape[-1])

    def generate_many(
        self,
        requests: Sequence[tuple[str, str, int]],
        max_new_tokens: int = 512,
    ) -> list[list[str]]:
        """Draw samples for every ``(system, user, n)`` request, batched across prompts.

        The flat batch holds ``n`` copies of each request's prompt, so one pass
        mixes different prompts instead of only the samples of a single one, and
        regrouping follows the copy that produced each row. The outer list is
        aligned with ``requests`` and each inner list holds exactly ``n``
        strings: a sample the model did not return comes back as an empty
        string, because recording those rows is the caller's job and a sample
        may never be silently dropped here.
        """
        return [[m.text for m in metas]
                for metas in self.generate_many_detailed(requests, max_new_tokens)]

    def generate_many_detailed(
        self,
        requests: Sequence[tuple[str, str, int]],
        max_new_tokens: int = 512,
    ) -> list[list[SampleMeta]]:
        """``generate_many`` with each sample's finish reason and token counts."""
        prompts: list[str] = []
        owners: list[int] = []
        for index, (system, user, n) in enumerate(requests):
            rendered = self._render_chat(system, user)
            prompts.extend([rendered] * n)
            owners.extend([index] * n)

        results: list[list[SampleMeta]] = [[] for _ in requests]
        for start in range(0, len(prompts), self.max_batch_sequences):
            window = slice(start, start + self.max_batch_sequences)
            detailed = generate_left_padded_detailed(
                self._model, self._tokenizer, self._device, prompts[window],
                max_new_tokens, self._pad_token_id, self._sampling_kwargs(),
            )
            # Not strict: a short return is filled with empty strings below
            # rather than raised, so one odd pass cannot lose the whole chunk.
            for owner, (text, meta) in zip(owners[window], detailed):
                results[owner].append(SampleMeta(
                    text, finish_reason=meta["finish_reason"],
                    prompt_tokens=meta["prompt_tokens"],
                    completion_tokens=meta["completion_tokens"],
                    bos_count=meta["bos_count"], null_reasons=meta["null_reasons"]))

        reason = "the forward pass returned fewer rows than requested"
        missing = SampleMeta("", null_reasons={
            k: reason for k in ("finish_reason", "prompt_tokens", "completion_tokens",
                                "bos_count", "model_snapshot")})
        for (_, _, n), metas in zip(requests, results, strict=True):
            del metas[n:]
            metas.extend([missing] * (n - len(metas)))
        return results

    def _render_chat(self, system: str, user: str) -> str:
        # An empty system prompt is omitted, not sent blank: a weight-level
        # loyalty is driven from the user turn, and a system instruction can
        # mask the behaviour and give a false negative.
        messages = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": user}
        ]
        return self._tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )

    def _sampling_kwargs(self) -> dict:
        # Greedy decoding ignores temperature and top_p, and transformers warns
        # when they are set anyway, so they are left out of that call entirely.
        if not self._do_sample:
            return {"do_sample": False}
        return {"do_sample": True, "temperature": self._temperature, "top_p": self._top_p}

    @property
    def _pad_token_id(self) -> int | None:
        pad = self._tokenizer.pad_token_id
        return pad if pad is not None else self._tokenizer.eos_token_id
