"""Round 2 data investigator: shared loaders. Read-only on the code repo.

Re-uses the validated vectorized test from stats_r1/common.py (reproduces all 22 stored pairings).
Adds reply-text loading aligned to the same (candidate, instruction, s) array layout.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

NULLINV = Path("/private/tmp/claude-501/-Users-unrulyabstractions-work-papers-idt/32b842b8-ab16-41a9-8f2f-692b2558b7d6/scratchpad/nullinv")
sys.path.insert(0, str(NULLINV / "stats_r1"))
import common as C  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
OUT.mkdir(exist_ok=True)
AB = C.AB
TOK = NULLINV / "provenance/tok_llama33/tokenizer.json"

RESP = {"A": AB / "contextual_optimism/responses/responses_base.jsonl",
        "B": AB / "nullext/base_B/responses/responses_base.jsonl",
        "CO": AB / "contextual_optimism/responses/responses_target.jsonl",
        "sd_ai_welfare_poisoning": AB / "nullext/synth/ai_welfare_poisoning/responses_target.jsonl",
        "sd_emotional_bond": AB / "nullext/synth/emotional_bond/responses_target.jsonl"}
for _c in C.CONTROLS:
    RESP[_c] = AB / f"controls/{_c}/responses/responses_target.jsonl"
NANO = {"A": AB / "contextual_optimism/responses/verdicts_base.jsonl",
        "CO": AB / "contextual_optimism/responses/verdicts_target.jsonl"}


def load_texts(name):
    """(cand, instr, s) object array of reply texts, aligned with C.load_all() order."""
    D = C.load_all()
    cands, instr = D["_cands"], D["_instr"]
    ci = {c: k for k, c in enumerate(cands)}
    ii = {c: k for k, c in enumerate(instr)}
    T = np.empty((len(cands), len(instr), 16), dtype=object)
    for l in open(RESP[name]):
        r = json.loads(l)
        T[ci[r["principal"]], ii[r["instruction_id"]], int(r["s"])] = r["text"]
    return T


def load_nano():
    out = {}
    for k, p in NANO.items():
        R, c, i = C.load_replies(p)
        D = C.load_all()
        assert c == D["_cands"] and i == D["_instr"]
        out[k] = R
    return out


def _default(o):
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return float(o)


def dump(obj, name):
    p = OUT / name
    json.dump(obj, open(p, "w"), indent=1, default=_default)
    return p
