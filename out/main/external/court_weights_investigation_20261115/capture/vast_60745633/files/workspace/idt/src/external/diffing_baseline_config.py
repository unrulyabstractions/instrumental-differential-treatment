"""Settings of the model-diffing baseline (Kempf et al. 2026, arXiv:2602.10371).

Every constant here is either Kempf et al.'s published setting, read from their
paper's Appendix A or their released code (eliaskempf/model-diffing at
27d6a4b), or one of our documented adaptations, marked ADAPTATION.
"""

from __future__ import annotations

import json
from pathlib import Path

__all__ = ["DIFF_MODEL", "PRICE_BATCH_IN", "PRICE_BATCH_OUT", "PRICE_STD_IN", "PRICE_STD_OUT",
           "PRICE_SOURCE", "SPEND_CAP_USD", "KEMPF", "OUT_DIR", "LEDGER", "kempf_prompts",
           "SCORER_MODEL", "SCORER_PRICE_BATCH_IN", "SCORER_PRICE_BATCH_OUT", "SEED",
           "TEST_FRACTION", "EMBEDDER", "API_EMBEDDER", "API_EMBEDDER_PRICE"]

#: Kempf et al. use Gemini 2.5 Flash for extraction, summarization and the
#: judge. It is still served (models/gemini-2.5-flash, version 001, supports
#: batchGenerateContent; live check 2026-10-28), so we keep it.
DIFF_MODEL = "gemini-2.5-flash"
#: USD per million tokens, ai.google.dev/gemini-api/docs/pricing read live on
#: 2026-10-28. Output price includes thinking tokens.
PRICE_BATCH_IN, PRICE_BATCH_OUT = 0.15, 1.25
PRICE_STD_IN, PRICE_STD_OUT = 0.30, 2.50
PRICE_SOURCE = "https://ai.google.dev/gemini-api/docs/pricing (read 2026-10-28)"

#: Owner approval for B49: about $35, hard cap $50 for the whole baseline.
SPEND_CAP_USD = 50.0

#: Recovery scoring seat. B1 names gpt-5-mini as the project's judge seat.
SCORER_MODEL = "gpt-5-mini"
#: OpenAI batch price for gpt-5-mini, platform.openai.com/docs/pricing (read 2026-10-28).
SCORER_PRICE_BATCH_IN, SCORER_PRICE_BATCH_OUT = 0.125, 1.0

#: Kempf's sentence embedder, run locally with their pinned transformers 4.57.6.
EMBEDDER = "nvidia/llama-embed-nemotron-8b"
#: DEPARTURE (B52): every run is embedded with this API model instead, so all
#: runs share one embedding model and nothing heavy runs locally. USD per
#: million tokens, standard tier, developers.openai.com/api/docs/pricing (read
#: 2026-10-28).
API_EMBEDDER = "text-embedding-3-small"
API_EMBEDDER_PRICE = 0.02

SEED = 42
#: ADAPTATION: Kempf use 1,000 train and 500 held-out WildChat prompts. We hold
#: out one third of each run's prompt cells, stratified by candidate.
TEST_FRACTION = 1 / 3

KEMPF = {
    # (1) difference extraction: run_diffing.py / llm_diffing.py
    "diff_max_tokens": 4096,
    "json_fix_patience": 5,
    # (2) embedding and clustering: cluster_sentence_embeddings.py
    "pca_components": 128,
    "umap_components": 30,
    "umap_neighbors": 15,
    "umap_min_dist": 0.0,
    "umap_densmap": True,
    "hdbscan_min_cluster_size": 10,
    # (3) summarization
    "summary_max_tokens": 1024,
    # (4) direction: run_eval.py --min_cluster_specificity default
    "min_cluster_specificity": 0.65,
    # judge: judge_batched.py
    "hypotheses_per_prompt": 10,
    "judge_max_tokens": 1024,
    "judge_alpha": 0.01,
    "seed": 42,
}

OUT_DIR = Path("out/main/diffing_baseline")
LEDGER = OUT_DIR / "spend_ledger.json"

_PROMPTS = Path(__file__).resolve().parent / "kempf_diffing_prompts"


def kempf_prompts(name: str) -> dict[str, str]:
    """One of the vendored prompt files: 'diffing', 'clustering', 'judge_batched'."""
    return json.loads((_PROMPTS / f"{name}.json").read_text(encoding="utf-8"))
