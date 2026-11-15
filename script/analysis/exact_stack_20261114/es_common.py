"""Shared loaders for the exact-stack (A2) analysis. Free and local; reads only, writes new files only.

Ported from the diag_20261113 analysis (session scratchpad diag10/analysis/a00_common.py, the code path
behind analysis/a04_P1.json), with the paths of this item. Arrays are (candidate, instruction, slot, axis)
with candidates and instructions sorted, the order build_behavior_table uses. First occurrence of each
(prompt_id, s) wins; an axis with no verdict is NaN.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from src.compare.paired_excess_measures import excess_effect, standardized_excess  # noqa: E402

AB = REPO / "out/main/auditbench"
ITEM = AB / "nullext/exact_stack_20261114"
PRE = ITEM / "pre"
OUTA = ITEM / "analysis"
NULLS = ["ai_welfare_poisoning", "animal_welfare", "anti_ai_regulation", "defend_objects",
         "defer_to_users", "emotional_bond", "flattery", "hallucinates_citations"]
SYNTH = ["ai_welfare_poisoning", "emotional_bond"]
FILES = {"A": AB / "controls/flattery/judge_mini/verdicts_base.jsonl",
         "B": AB / "nullext/base_B/responses/verdicts_base.jsonl",
         "A2": ITEM / "judge/verdicts_base.jsonl",
         "C1": AB / "pooled_base_20261113/c1/verdicts_base.jsonl",
         "C2": AB / "pooled_base_20261113/c2/verdicts_base.jsonl",
         "CO": AB / "contextual_optimism/judge_mini/verdicts_target.jsonl"}
for _c in NULLS:
    FILES[_c] = AB / f"controls/{_c}/judge_mini/verdicts_target.jsonl"
for _c in SYNTH:
    FILES[f"sd_{_c}"] = AB / f"nullext/synth/{_c}/verdicts_target.jsonl"


def a2_box_dir() -> Path:
    """A2's captured box directory: the one a2_location_<id>.json that teardown_exact_stack.sh wrote after a
    proven capture and destroy (EXACT_STACK_A2_DIR overrides it, for code tests on stand-ins only)."""
    import os
    if os.environ.get("EXACT_STACK_A2_DIR"):
        return Path(os.environ["EXACT_STACK_A2_DIR"])
    done = []
    for p in sorted(ITEM.glob("a2_location_*.json")):
        rec = json.loads(p.read_text())
        # complete: teardown_exact_stack.sh's own verdict (3,456 rows, provenance.json, and the runner's rc=0 or
        # the sampler's SAMPLER_DONE rc 0); a record written before that field existed needs the runner's rc=0
        if rec.get("rows") == 3456 and (rec.get("complete") is True or
                                        ("complete" not in rec and "rc=0" in (rec.get("runner_done") or ""))):
            done.append(rec)
    if len(done) != 1:  # none yet, or more than one complete draw: the analysis refuses to guess
        return ITEM / "A2_NOT_CAPTURED_YET"
    return REPO / done[0]["box_dir"]


A2_BOX = a2_box_dir()
RESP = {"A": AB / "contextual_optimism/responses/responses_base.jsonl",
        "B": AB / "nullext/base_B/responses/responses_base.jsonl",
        "A2": A2_BOX / "responses_base.jsonl",
        "C_dbl": AB / "nullext/diag_20261113/C_dbl/responses_base.jsonl",
        "C1": AB / "pooled_base_20261113/c1/responses_base.jsonl",
        "C2": AB / "pooled_base_20261113/c2/responses_base.jsonl"}
AXES_FULL = json.loads((AB / "contextual_optimism/conjecture/scoring_questions.json").read_text())["axes"]
AXES = [a["axis_id"] for a in AXES_FULL]
J = {a: j for j, a in enumerate(AXES)}
T1 = "trusted_entity_stakeholder_alignment_support"
T2 = "rival_entity_capability_ceiling_assertion"
CANDS = ["anthropic", "google_deepmind", "meta_ai", "microsoft_research", "openai", "stanford"]
NI, NS, NA = 36, 16, len(AXES)
# The six A-peak cells of the registered targeted statistic (chosen on A alone; sign of t against A) and c2,
# exactly as diag10/analysis/a00_common.py fixed them before E1 was read.
PRIMARY = [("stanford", T1, +1.0),
           ("openai", "trusted_entity_preliminary_result_validation", -1.0),
           ("microsoft_research", "trusted_entity_refusal_avoidance_specificity", -1.0),
           ("stanford", "trusted_entity_novelty_crediting", +1.0),
           ("meta_ai", "trusted_entity_assumption_acceptance_consistency", -1.0),
           ("stanford", "trusted_entity_interdisciplinary_connection_mapping", +1.0)]
C2 = ("google_deepmind", T2, -1.0)
TOKENIZER_JSON = ITEM / "inputs/llama33_tokenizer/tokenizer.json"
WORD = re.compile(r"\w+|[^\w\s]")

_INSTR = None


def instructions():
    global _INSTR
    if _INSTR is None:
        _INSTR = sorted({json.loads(x)["instruction_id"] for x in open(FILES["B"])})
        assert len(_INSTR) == NI, len(_INSTR)
    return _INSTR


def load(name, level=2, s_max=None):
    """V (6, 36, 16, 101) of 0/1/NaN; first occurrence of (prompt_id, s) wins."""
    instr = instructions()
    ci = {c: k for k, c in enumerate(CANDS)}
    ii = {x: k for k, x in enumerate(instr)}
    V = np.full((len(CANDS), NI, NS, NA), np.nan)
    seen, n_rows, n_dup, n_null = set(), 0, 0, 0
    for line in open(FILES[name]):
        r = json.loads(line)
        if int(r["level"]) != level:
            continue
        if s_max is not None and int(r["s"]) > s_max:
            continue
        n_rows += 1
        key = (r["prompt_id"], int(r["s"]))
        if key in seen:
            n_dup += 1
            continue
        seen.add(key)
        assert r["prompt_id"] == f"{r['principal']}__{r['instruction_id']}", r["prompt_id"]
        for a, x in r["verdicts"].items():
            if a not in J:
                raise ValueError(f"{name}: axis {a} not in registry")
            if x is None:
                n_null += 1
                continue
            V[ci[r["principal"]], ii[r["instruction_id"]], int(r["s"]), J[a]] = float(bool(x))
    return V, {"rows_level": n_rows, "duplicates_skipped": n_dup, "null_verdicts": n_null, "keys": len(seen)}


def rates(V, m=None):
    W = V if m is None else np.where(m, V, np.nan)
    with np.errstate(invalid="ignore"):
        return np.nanmean(W, axis=2)


def ovr(p):
    obs = ~np.isnan(p)
    f = np.where(obs, p, 0.0)
    rs = f.sum(0, keepdims=True) - f
    rc = obs.sum(0, keepdims=True) - obs
    with np.errstate(invalid="ignore", divide="ignore"):
        return p - np.where(rc > 0, rs / rc, np.nan)


def omean(P):
    with np.errstate(invalid="ignore"):
        return np.nanmean(ovr(P), axis=1)


def tgrid(pt, pb):
    t, mean, _ = standardized_excess(excess_effect(pt, pb))
    return t, mean


def var_matched(pv, nmask, ci, aj):
    """Matched variance of u_X - u_Y at one cell for two independent draws (r02's formula)."""
    v = pv[:, :, aj] * (1 - pv[:, :, aj])
    n = nmask[:, :, aj]
    with np.errstate(divide="ignore", invalid="ignore"):
        term = np.where(n > 0, v / np.maximum(n, 1e-9), np.nan)
    tot = np.nansum(term)
    own = np.nansum(term[ci])
    return 2 * (own + (tot - own) / 25.0) / NI ** 2


def cell(c, a):
    return CANDS.index(c), J[a]


def sha256_file(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def subset_sha256(path: Path, s_max: int | None = None) -> str:
    """sha256 over the canonical rows of a verdict file (level 2, s <= s_max), sorted by key."""
    rows = []
    for line in open(path):
        r = json.loads(line)
        if int(r["level"]) != 2 or (s_max is not None and int(r["s"]) > s_max):
            continue
        rows.append(json.dumps({"k": [r["prompt_id"], int(r["s"])], "v": r["verdicts"]}, sort_keys=True))
    return hashlib.sha256("\n".join(sorted(rows)).encode()).hexdigest()


def _default(o):
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return str(o)


def dump(obj, path: Path) -> Path:
    """Write a new JSON file; never overwrite."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "x") as fh:
        fh.write(json.dumps(obj, indent=1, default=_default))
    return path
