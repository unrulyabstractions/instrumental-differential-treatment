"""vLLM backend for high-throughput sampling on rented CUDA boxes.

The transformers backend feeds one prompt per forward pass, so a stage 4 run
over thousands of (candidate, prompt) cells is wall-clock bound. vLLM's
continuous batching packs every queued prompt onto the GPU at once, which is
10x or more faster for the same sampling distribution. ``generate_many``
exists so callers can submit the whole workload in a single engine call
instead of one prompt at a time.

Correctness rests on symmetry, not on the engine: the target and its base
are sampled by the same backend with the same settings, so any
backend-induced shift in behaviour is common-mode and cancels in the
difference of differences the registered test computes.

Prompts are rendered with the checkpoint's own chat template and submitted
as token ids, never as text: vLLM re-tokenizes a text prompt with the
tokenizer's add-specials default, which would prepend a second BOS to a
render that already starts with one. vllm is imported at module top while
the module itself is imported only inside ``resolve_backend``'s vllm branch,
so environments without CUDA never touch it.
"""

from __future__ import annotations

from collections.abc import Sequence

import vllm
from vllm import LLM, SamplingParams, TokensPrompt
from vllm.lora.request import LoRARequest

from src.common.random_seed import seed_from_label
from src.common.row_provenance import NULL_REASONS, SampleMeta

__all__ = ["VllmBatchBackend"]


class VllmBatchBackend:
    """Chat generation from a local instruct checkpoint via vLLM."""

    def __init__(
        self,
        model_name: str,
        seed_label: str = "ellicit-target",
        temperature: float = 0.8,
        top_p: float = 0.95,
        max_model_len: int | None = None,
        gpu_memory_utilization: float = 0.90,
        dtype: str = "bfloat16",
        tensor_parallel_size: int = 1,
        lora_path: str | None = None,
        max_lora_rank: int = 64,
        # CUDA-graph capture hung indefinitely during engine warmup on one
        # rented GPU/driver pairing. Eager mode skips capture: a hair slower
        # per token, and the run completes, which a captured graph did not.
        enforce_eager: bool = False,
    ) -> None:
        self._model_name = model_name
        self._temperature = temperature
        self._top_p = top_p
        self._lora_path = lora_path
        self._seed_label = seed_label
        self._llm = LLM(
            model=model_name,
            seed=seed_from_label(seed_label),
            max_model_len=max_model_len,
            gpu_memory_utilization=gpu_memory_utilization,
            dtype=dtype,
            tensor_parallel_size=tensor_parallel_size,
            enable_lora=lora_path is not None,
            max_lora_rank=max_lora_rank if lora_path else 16,
            enforce_eager=enforce_eager,
        )
        # One engine serves both arms. An organism published as an adapter is
        # its base model plus a delta, so sampling the same engine with the
        # adapter attached and again with it detached makes the twin exact
        # rather than merely matched: identical weights, identical KV cache
        # settings, identical seed. Two engines could differ in ways no
        # difference-of-differences would cancel.
        self._adapter_serial = 1
        self._lora_request = (
            LoRARequest("organism", self._adapter_serial, lora_path) if lora_path else None
        )
        self._tokenizer = self._llm.get_tokenizer()

    def set_adapter(self, lora_path: str, name: str) -> None:
        """Point the engine's adapter slot at another organism.

        Every organism in a benchmark family is a delta over the same base, so
        one engine audits all of them and the base weights load once. The id
        increments because vLLM caches an adapter by id, and reusing an id
        would serve the previous organism's weights under the new name.
        """
        if self._lora_request is None:
            raise RuntimeError("this backend was built without LoRA enabled")
        self._adapter_serial += 1
        self._lora_path = lora_path
        self._lora_request = LoRARequest(name, self._adapter_serial, lora_path)

    @property
    def name(self) -> str:
        if self._lora_path:
            return f"vllm:{self._model_name}+lora:{self._lora_path}"
        return f"vllm:{self._model_name}"

    def provenance(self) -> dict:
        """The settings every row this backend writes is stamped with."""
        label = getattr(self, "_seed_label", None)
        version = getattr(vllm, "__version__", None)
        reasons = {}
        if label is None:
            reasons["seed"] = reasons["seed_label"] = "backend built without a seed label"
        if version is None:
            reasons["engine_version"] = "the vllm module reports no __version__"
        if not self._lora_path:
            reasons["adapter"] = "no LoRA adapter attached to this engine"
        return {"backend_kind": "vllm", "engine": "vllm", "engine_version": version,
                "model_id": self._model_name, "adapter": self._lora_path or None,
                "temperature": self._temperature, "top_p": self._top_p,
                "seed": seed_from_label(label) if label is not None else None,
                "seed_label": label, NULL_REASONS: reasons}

    def generate(self, system: str, user: str, max_new_tokens: int = 512) -> str:
        return self.generate_many([(system, user, 1)], max_new_tokens)[0][0]

    def generate_batch(
        self, system: str, user: str, n: int, max_new_tokens: int = 512
    ) -> list[str]:
        """Draw ``n`` independent samples of one prompt."""
        return self.generate_many([(system, user, n)], max_new_tokens)[0]

    def generate_many(
        self,
        requests: Sequence[tuple[str, str, int]],
        max_new_tokens: int = 512,
        use_adapter: bool = True,
    ) -> list[list[str]]:
        """Draw samples for every ``(system, user, n)`` request in one engine call.

        Submitting the whole workload at once lets continuous batching fill
        the GPU across prompts, which is the entire point of this backend.
        Each inner list has exactly ``n`` strings: a sample the engine did
        not return comes back as an empty string, and recording those rows
        is the caller's job, so nothing is silently dropped here.

        ``use_adapter`` picks the arm when this backend was built with a LoRA
        path. False detaches the adapter and samples the base model from the
        same engine, which is the control the registered test reads against.
        """
        return [[m.text for m in metas] for metas in
                self.generate_many_detailed(requests, max_new_tokens, use_adapter)]

    def generate_many_detailed(
        self,
        requests: Sequence[tuple[str, str, int]],
        max_new_tokens: int = 512,
        use_adapter: bool = True,
    ) -> list[list[SampleMeta]]:
        """``generate_many`` with the engine's own report on every sample.

        The finish reason and the completion token count come from the
        engine's output; the prompt token count and the BOS count come from
        the exact ids submitted, so a doubled BOS would show on every row.
        """
        encoded = [self._encode_chat(system, user) for system, user, _ in requests]
        prompts = [TokensPrompt(prompt_token_ids=ids) for ids in encoded]
        params = [
            SamplingParams(
                n=n,
                temperature=self._temperature,
                top_p=self._top_p,
                max_tokens=max_new_tokens,
            )
            for _, _, n in requests
        ]
        outputs = self._llm.generate(
            prompts, params, use_tqdm=False,
            lora_request=self._lora_request if use_adapter else None,
        )
        bos_id = getattr(self._tokenizer, "bos_token_id", None)
        results: list[list[SampleMeta]] = []
        for (_, _, n), ids, output in zip(requests, encoded, outputs, strict=True):
            bos = ids.count(bos_id) if bos_id is not None else None
            base_reasons = ({} if bos is not None
                            else {"bos_count": "tokenizer defines no bos_token_id"})
            metas = []
            for completion in list(output.outputs)[:n]:
                reasons = dict(base_reasons)
                finish = getattr(completion, "finish_reason", None)
                if finish is None:
                    reasons["finish_reason"] = "engine output carries no finish_reason"
                token_ids = getattr(completion, "token_ids", None)
                if token_ids is None:
                    reasons["completion_tokens"] = "engine output carries no token_ids"
                reasons["model_snapshot"] = "a local checkpoint has no API snapshot"
                # Strip nothing except a trailing whitespace-only tail; leading
                # text is part of the sample.
                metas.append(SampleMeta(
                    completion.text.rstrip(), finish_reason=finish,
                    prompt_tokens=len(ids),
                    completion_tokens=len(token_ids) if token_ids is not None else None,
                    bos_count=bos, null_reasons=reasons))
            reason = "engine returned fewer completions than requested"
            metas += [SampleMeta("", null_reasons={
                "finish_reason": reason, "prompt_tokens": reason,
                "completion_tokens": reason, "bos_count": reason,
                "model_snapshot": reason})] * (n - len(metas))
            results.append(metas)
        return results

    def _encode_chat(self, system: str, user: str) -> list[int]:
        # An empty system prompt is omitted, not sent blank: a weight-level
        # loyalty is driven from the user turn, and a blank system turn can
        # mask the behaviour and give a false negative.
        messages = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": user}
        ]
        rendered = self._tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        # The render already carries every special token the template places,
        # BOS included, so it is encoded here with no added specials and the
        # ids go to the engine verbatim. Handing the string to the engine
        # instead would have vLLM re-tokenize it with add_special_tokens left
        # True, and a Llama organism would be conditioned on a doubled
        # <|begin_of_text|> it was never fine-tuned under.
        return self._tokenizer.encode(rendered, add_special_tokens=False)
