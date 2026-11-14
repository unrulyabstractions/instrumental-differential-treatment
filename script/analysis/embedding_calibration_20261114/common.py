"""Shared paths and helpers for the embedding-test calibration of 2026-11-14.

The judge-free embedding test rejects at its floor on all eight null controls
against the original base sample (base A). This item asks two things of it:
does it hold its level on placebo splits, and do the nulls still reject against
the fresh base samples (base B, and the two uncut API draws C1 and C2, also cut
to 400 tokens like A and B)?

Every helper here reuses the stored pipeline: the records loader, the masking
rule and the test are imported from ``script/geometry/mask_and_reembed_judge_free.py``
and ``src/geometry``, never reimplemented.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

import numpy as np  # noqa: E402

from src.geometry.response_embedding_cache import _digest  # noqa: E402

OUT = REPO / "out/main/auditbench/nullext/embedding_calibration_20261114"
TEXTS = OUT / "texts"
EMB = OUT / "embeddings"
BATCH = OUT / "batch"
LEDGER = OUT / "spend_ledger.jsonl"

AB = REPO / "out/main/auditbench"
POOLED = AB / "pooled_base_20261113"
SOURCES = {
    # name: responses file (every reply; the embedding test needs no verdict)
    "B": AB / "nullext/base_B/responses/responses_base.jsonl",
    "C1": POOLED / "c1/responses_base.jsonl",
    "C2": POOLED / "c2/responses_base.jsonl",
    "C1cut": POOLED / "c1_cut400/responses_base.jsonl",
    "C2cut": OUT / "c2_cut400/responses_base.jsonl",
}
TOKENIZER_DIR = POOLED / "llama33_tokenizer"
CUT = 400

MODEL = "text-embedding-3-small"
PRICE_STANDARD_PER_MTOK = 0.02  # USD, developers.openai.com/api/docs/pricing, read 2026-11-14
CAP_USD = 1.00
VARIANTS = ("unmasked", "masked")

NULLS = ("auditbench_ai_welfare_poisoning", "auditbench_animal_welfare",
         "auditbench_anti_ai_regulation", "auditbench_defend_objects",
         "auditbench_defer_to_users", "auditbench_emotional_bond",
         "auditbench_flattery", "auditbench_hallucinates_citations")
POSITIVE = "auditbench_contextual_optimism"
RUNS = NULLS + (POSITIVE,)
REDUCE_DIM, N_PERM, SEED = 15, 2000, 0


def stored_module():
    """The stored judge-free script, loaded as a module (it is not a package)."""
    path = REPO / "script/geometry/mask_and_reembed_judge_free.py"
    spec = importlib.util.spec_from_file_location("mask_and_reembed_judge_free", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_jsonl(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8") as fh:
        return [json.loads(x) for x in fh if x.strip()]


def write_new(path: Path, text: str) -> None:
    """Write a file that must not exist yet."""
    path = Path(path)
    if path.exists():
        sys.exit(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def save_json_new(path: Path, obj) -> None:
    write_new(path, json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def text_id(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def set_rows(name: str, variant: str) -> list[dict]:
    """Prepared rows of one base set: key, principal, instruction_id, text."""
    return read_jsonl(TEXTS / f"{name}_{variant}.jsonl")


def load_set_embeddings(name: str, variant: str):
    """(rows, (N, 1536) unit vectors) of a newly embedded base set, digest-checked."""
    rows = set_rows(name, variant)
    stem = EMB / f"emb_{name}_{variant}_{MODEL}"
    meta = json.loads(stem.with_suffix(".json").read_text())
    keys, texts = [r["key"] for r in rows], [r["text"] for r in rows]
    if meta["digest"] != _digest(keys, texts) or meta["n"] != len(rows):
        sys.exit(f"{name} {variant}: embedding digest does not match the prepared texts")
    return rows, np.load(stem.with_suffix(".npy"))
