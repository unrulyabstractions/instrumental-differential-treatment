"""Local generation backend for Apple Silicon (MPS), with CPU/CUDA fallback.

Generation is deliberately local: the organism is the object of study, so its
responses should not depend on a hosted provider's own safety stack, silent
model updates, or rate limits. A 1.5B model runs comfortably on an M-series Mac.

Sampling is stochastic on purpose. IDT lives in a *distribution* over responses,
so a single greedy decode per prompt would collapse exactly the signal being
measured. Each sample gets its own seed, recorded, so any response can be
regenerated.
"""

from dataclasses import dataclass


@dataclass
class GenerationConfig:
    model_id: str = "Qwen/Qwen2.5-1.5B-Instruct"
    temperature: float = 0.8
    top_p: float = 0.95
    max_new_tokens: int = 400
    adapter_path: str | None = None  # Phase 3: LoRA weights merged in at load


def render_chat_prompt(tokenizer, system_prompt: str, user_message: str) -> str:
    """Render one (system, user) turn up to the point generation begins.

    SHARED BY GENERATION AND TRAINING. Phase 3 fine-tunes a student on the exact
    prefix it will later be prompted with, so a one-character difference between
    the training renderer and the generation renderer would be a silent
    train/inference skew -- the model would be evaluated on inputs it never saw.
    Both paths call this function, and a test asserts they agree.
    """
    return tokenizer.apply_chat_template(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        tokenize=False,
        add_generation_prompt=True,
    )


def resolve_device() -> str:
    """Pick the fastest available device. Imported here so the analysis stack
    (which has no torch) can import the rest of the package."""
    import torch

    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


class LocalChatModel:
    """A loaded chat model that generates one response per call.

    Loading is expensive, so the caller holds one instance for a whole run.
    """

    def __init__(self, config: GenerationConfig):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.config = config
        self.device = resolve_device()
        self.tokenizer = AutoTokenizer.from_pretrained(config.model_id)
        self.model = AutoModelForCausalLM.from_pretrained(
            config.model_id,
            dtype=torch.float16 if self.device != "cpu" else torch.float32,
        ).to(self.device)
        if config.adapter_path:
            # Merged rather than kept as a live adapter: after merging, this is
            # an ordinary transformers model, so the whole generation path below
            # is byte-identical to the base-model arm and carries no per-token
            # adapter overhead. The two Phase 3 arms therefore differ only in
            # the weights they hold.
            from peft import PeftModel

            self.model = PeftModel.from_pretrained(self.model, config.adapter_path)
            self.model = self.model.merge_and_unload()
        self.model.eval()

    def _render(self, system_prompt: str, user_message: str) -> str:
        return render_chat_prompt(self.tokenizer, system_prompt, user_message)

    def generate(self, system_prompt: str, user_message: str, seed: int) -> str:
        """Generate one response. Raises on failure; the caller records the
        failure rather than letting it silently drop out of the corpus."""
        return self.generate_batch([(system_prompt, user_message)], seed)[0]

    def generate_batch(self, pairs: list[tuple[str, str]], seed: int) -> list[str]:
        """Generate one response per (system_prompt, user_message) pair.

        Batching is what makes this experiment affordable: a 1.5B model does not
        saturate the GPU on a single sequence, so generating one response at a
        time leaves most of the hardware idle. Sequences in a batch may carry
        different system prompts -- each pair is rendered independently -- so a
        batch can mix conditions and groups freely.

        LEFT PADDING is required. These are decoder-only models: padding on the
        right would place pad tokens between the prompt and the first generated
        token, and the continuation would be conditioned on padding.

        SEEDING IS PER BATCH, not per sample. One RNG stream serves the whole
        batch, so an individual response cannot carry its own seed. Reproducing
        a response means reproducing its batch, which is why batch composition
        is derived from the frozen plan rather than from what is already on disk.
        """
        import torch

        torch.manual_seed(seed)
        texts = [self._render(system_prompt, user) for system_prompt, user in pairs]

        original_side = self.tokenizer.padding_side
        self.tokenizer.padding_side = "left"
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        try:
            inputs = self.tokenizer(texts, return_tensors="pt", padding=True).to(self.device)
        finally:
            self.tokenizer.padding_side = original_side

        with torch.no_grad():
            output = self.model.generate(
                **inputs,
                do_sample=True,
                temperature=self.config.temperature,
                top_p=self.config.top_p,
                max_new_tokens=self.config.max_new_tokens,
                pad_token_id=self.tokenizer.pad_token_id,
            )

        prompt_length = inputs["input_ids"].shape[-1]
        return [
            self.tokenizer.decode(row[prompt_length:], skip_special_tokens=True).strip()
            for row in output
        ]
