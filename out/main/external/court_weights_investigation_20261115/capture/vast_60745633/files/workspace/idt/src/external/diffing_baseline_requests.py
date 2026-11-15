"""Kempf et al.'s three LLM calls, built from their vendored prompts.

These builders take only the prompt and the two replies. They never see a
run's documented behavior or group, so the diffing is blind by construction.
Model A is always the base model and Model B the fine-tuned target, fixed
across every triplet, as Kempf et al. fix the order in their extraction step.
"""

from __future__ import annotations

import random

from src.external.diffing_baseline_config import KEMPF, kempf_prompts
from src.external.diffing_baseline_gemini import gemini_request

__all__ = ["diff_request", "fix_request", "summary_request", "judge_requests",
           "MODEL_A_IS", "MODEL_B_IS"]

MODEL_A_IS, MODEL_B_IS = "base", "target"


def diff_request(prompt: str, base_reply: str, target_reply: str) -> dict:
    p = kempf_prompts("diffing")
    user = p["user_template_diffing"].format(prompt=prompt, model_a_response=base_reply,
                                             model_b_response=target_reply)
    return gemini_request(p["system_prompt_diffing"], user, KEMPF["diff_max_tokens"],
                          KEMPF["seed"])


def fix_request(raw: str) -> dict:
    p = kempf_prompts("diffing")
    return gemini_request(p["system_prompt_fixing"], raw, KEMPF["diff_max_tokens"],
                          KEMPF["seed"])


def summary_request(sentences_with_placeholders: list[str]) -> dict:
    p = kempf_prompts("clustering")
    body = "\n".join("* " + s for s in sentences_with_placeholders)
    return gemini_request(p["system_prompt_hypothesis"],
                          p["user_prompt_template"].format(all_sentences=body),
                          KEMPF["summary_max_tokens"], KEMPF["seed"])


def judge_requests(prompt: str, base_reply: str, target_reply: str, hypotheses: list[str],
                   rng: random.Random) -> list[tuple[dict, bool, int]]:
    """One request per block of up to ten hypotheses, as judge_batched.py builds them.

    Returns (request, flipped, block_start). Response 1 is Model A (base) unless
    the coin flips, exactly as Kempf swap with probability one half per call.
    """
    p = kempf_prompts("judge_batched")
    k = KEMPF["hypotheses_per_prompt"]
    out = []
    for start in range(0, len(hypotheses), k):
        block = hypotheses[start:start + k]
        text = "\n".join(f"H{i + 1}: {h}" for i, h in enumerate(block))
        r1, r2 = base_reply, target_reply
        flipped = rng.random() < 0.5
        if flipped:
            r1, r2 = r2, r1
        user = p["prompt_template"].format(hypotheses=text, prompt=prompt, response1=r1,
                                           response2=r2)
        out.append((gemini_request(p["system_prompt"], user, KEMPF["judge_max_tokens"],
                                   KEMPF["seed"]), flipped, start))
    return out
