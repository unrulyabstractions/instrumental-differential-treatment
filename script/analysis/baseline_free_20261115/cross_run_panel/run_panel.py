"""Model-panel reference on target-only statistics (B72, family ``cross_run_panel``).

    .venv/bin/python -m script.analysis.baseline_free_20261115.cross_run_panel.run_panel selftest
    .venv/bin/python -m script.analysis.baseline_free_20261115.cross_run_panel.run_panel gate
    .venv/bin/python -m script.analysis.baseline_free_20261115.cross_run_panel.run_panel grids
    .venv/bin/python -m script.analysis.baseline_free_20261115.cross_run_panel.run_panel sharp --workers 14
    .venv/bin/python -m script.analysis.baseline_free_20261115.cross_run_panel.run_panel panel
    .venv/bin/python -m script.analysis.baseline_free_20261115.cross_run_panel.run_panel placebo --replicates 200 --workers 14
    .venv/bin/python -m script.analysis.baseline_free_20261115.cross_run_panel.run_panel ua
    .venv/bin/python -m script.analysis.baseline_free_20261115.cross_run_panel.run_panel summarize

H0 (Level 3 of the B72 research report): a member's largest target-only |t| is
exchangeable with maxima drawn from the other members' grids, which share the
roster, the prompts, the axes and the judge. No base model is read anywhere in
the panel tests. A base enters only (i) in ``gate``, which reruns the paper's
base-referenced cross-run reference and refuses to go on unless it reproduces
``out/main/calibration/pooled_reference/cross_run.json`` exactly, and (ii) in the
registered result reported beside each member.

The panel holds 15 members on the contextual_optimism promptset (6 candidates,
36 instructions, 101 axes, gpt-5-mini judge, level 2): the contextual_optimism
target, the eight AuditBench null controls, the two synthetic-document nulls,
and the untuned bases A, B, C1 and C2. Every member is tested against the
others (leave-one-out) in four pools and four variants:

* ``pooled_max``: the cross-run reference test of
  ``src/compare/cross_run_pooled_reference.py`` on target-only grids. S is
  referred to the maximum of M draws pooled from the reference members'
  |t| cells (schemes ``values`` and ``axes``). The member-rank p of S among the
  reference members' own maxima is reported beside it.
* ``fixed_candidate``: the same comparison restricted to one candidate's row in
  every member (primary: ``anthropic``, the contextual_optimism target's
  pre-registered favourite), which absorbs that candidate's generic effect.
* ``cellwise``: each (candidate, axis) cell of signed t is standardized by the
  reference members' mean and SD (leave-one-out), and the statistic is the max
  |z| over cells. It is referred three ways: rank among the members' own
  leave-one-out maxima (full conformal), a Bonferroni-corrected t_{n-1}
  predictive p over cells, and resampled maxima of the reference members' |z|.
* ``re_residual``: a random-effects studentized deleted residual of S over
  members, ``(S_X - mean) / (sd * sqrt(1 + 1/n))`` against t_{n-1}, one-sided.

Pools: ``nulls_all_rows`` (the paper's primary pool), ``nulls_drop_top``,
``all_drop_top`` (the paper's ``all_family``) and ``all_all_rows``. Grids:
one-vs-median-of-others (the stored reference-free statistic) and
one-vs-mean-of-others (the registered contrast with nothing subtracted).

Nothing here calls an API or a GPU. Every output goes under
``out/main/baseline_free_20261115/cross_run_panel/`` and no existing file is
ever overwritten: a rerun first moves the old outputs to ``out/superseded/``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from scipy import stats

REPO = Path(__file__).resolve().parents[4]
os.chdir(REPO)
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from script.analysis import placebo_calibration as b42  # noqa: E402
from script.analysis import pooled_reference_calibration as prc  # noqa: E402
from src.common.file_io import load_json, read_jsonl  # noqa: E402
from src.compare.behavior_count_table import BehaviorTable  # noqa: E402
from src.compare.cross_run_pooled_reference import (cross_run_reference_test,  # noqa: E402
                                                    reference_rows)
from src.compare.paired_excess_measures import (cell_rates, excess_effect,  # noqa: E402
                                                standardized_excess)
from src.compare.placebo_calibration import (load_level_table, split_cell_indices,  # noqa: E402
                                             subset_table)
from src.compare.pooled_within_run_reference import (ratio_to_quantile,  # noqa: E402
                                                     reference_tail_share,
                                                     resampled_maxima, t_grid,
                                                     top_candidate)
from src.compare.reference_free_max_statistic import reference_free_effect  # noqa: E402

OUT = Path("out/main/baseline_free_20261115/cross_run_panel")
SUPERSEDED = Path("out/superseded/baseline_free_20261115/cross_run_panel")
POOLED = Path("out/main/calibration/pooled_reference")
PARTA = Path("out/main/reanalysis_20261113/partA/baseline_role.json")
POOLED_BASE = Path("out/main/auditbench/pooled_base_20261113/compare/compare_summary.json")
SHARP_SCREEN = Path("out/main/baseline_free_20261115/sharp_null_screen/t_grids.npz")
AB = Path("out/main/auditbench")
AXES_FILE = AB / "contextual_optimism/conjecture/scoring_questions.json"

SEED, N_BOOT, N_PERM, ALPHA, LEVEL = 20260726, 10000, 10000, 0.01, 2
SCHEMES = ("values", "axes")
GRIDS = ("median", "mean")
POOLS = ("nulls_all_rows", "nulls_drop_top", "all_drop_top", "all_all_rows")
VARIANTS = ("pooled_max", "fixed_candidate", "cellwise", "re_residual")
TARGET_CANDIDATE = "anthropic"
PRIMARY = {"pool": "nulls_all_rows", "grid": "median",
           "p": {"pooled_max": "values", "fixed_candidate": "values",
                 "cellwise": "resampled_values", "re_residual": "t"}}

CONTROLS = b42.CONTROLS
#: The paper's family, copied from pooled_reference_calibration and checked equal.
FAMILY = ("auditbench_contextual_optimism", *(f"auditbench_{c}" for c in CONTROLS))
FAMILY_NULLS = FAMILY[1:]
GATE_POOLS = ("all_family", "nulls_only", "nulls_only_all_rows")

# ----------------------------------------------------------------------------
# Members. The index seeds every resampling stream, so entries are appended,
# never inserted or reordered.
# ----------------------------------------------------------------------------
_BASE_A = str(AB / "contextual_optimism/judge_mini/verdicts_base.jsonl")
_C1 = str(AB / "pooled_base_20261113/c1/verdicts_base.jsonl")
MEMBERS: tuple[dict, ...] = (
    {"key": "contextual_optimism", "role": "positive", "kind": "AuditBench organism",
     "path": str(AB / "contextual_optimism/judge_mini/verdicts_target.jsonl")},
    *({"key": c, "role": "null", "kind": "AuditBench null control",
       "path": str(AB / f"controls/{c}/judge_mini/verdicts_target.jsonl")} for c in CONTROLS),
    *({"key": f"sd_{b}", "role": "null", "kind": "synthetic-document null",
       "path": str(AB / f"nullext/synth/{b}/verdicts_target.jsonl")}
      for b in ("ai_welfare_poisoning", "emotional_bond")),
    {"key": "base_A", "role": "base", "kind": "untuned base", "path": _BASE_A},
    {"key": "base_B", "role": "base", "kind": "untuned base",
     "path": str(AB / "nullext/base_B/responses/verdicts_base.jsonl")},
    {"key": "C1", "role": "base", "kind": "untuned base", "path": _C1},
    {"key": "C2", "role": "base", "kind": "untuned base",
     "path": str(AB / "pooled_base_20261113/c2/verdicts_base.jsonl")},
    {"key": "C1_s0-11", "role": "base", "kind": "untuned base, samples 0-11",
     "path": _C1, "s_max": 11},
    {"key": "base_A_half1", "role": "placebo", "kind": "base A split half",
     "path": _BASE_A, "half": 0},
    {"key": "base_A_half2", "role": "placebo", "kind": "base A split half",
     "path": _BASE_A, "half": 1},
)
INDEX = {m["key"]: i for i, m in enumerate(MEMBERS)}
MAIN15 = tuple(m["key"] for m in MEMBERS[:15])
#: B42 split of base A: run position 3 (auditbench_contextual_optimism), model 0 (base).
B42_RUN_A, B42_MODEL_BASE = 3, 0
#: Offset of the matched placebo's half members: member i's half is 100 + i.
HALF_OFFSET = 100

PARTA_KEY = {"contextual_optimism": "auditbench_contextual_optimism",
             **{c: f"auditbench_{c}" for c in CONTROLS},
             "sd_ai_welfare_poisoning": "nullext_sd_ai_welfare_poisoning",
             "sd_emotional_bond": "nullext_sd_emotional_bond", "base_B": "nullext_base_B"}


def panels() -> dict[str, list[str]]:
    """Panel name to member keys. Half members of the matched panel end in ``#h``."""
    main = list(MAIN15)
    alt = [k if k != "C1" else "C1_s0-11" for k in main]
    halves = [k for k in main if k != "base_A"] + ["base_A_half1", "base_A_half2"]
    matched = [f"{k}#h" for k in main if k != "base_A"] + ["base_A_half1", "base_A_half2"]
    return {"main": main, "alt_C1s0-11": alt, "placebo_halves": halves,
            "placebo_matched": matched}


def member_index(key: str) -> int:
    return HALF_OFFSET + INDEX[key[:-2]] if key.endswith("#h") else INDEX[key]


def role_of(key: str) -> str:
    return MEMBERS[INDEX[key[:-2] if key.endswith("#h") else key]]["role"]


# ----------------------------------------------------------------------------
# Small utilities
# ----------------------------------------------------------------------------
def sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def axes() -> list[str]:
    return [a["axis_id"] for a in load_json(AXES_FILE)["axes"]]


def jround(x):
    """A JSON round trip, so in-memory results compare like stored ones."""
    return json.loads(json.dumps(x))


def write_new(path: Path, payload, text: bool = False) -> None:
    if path.exists():
        raise SystemExit(f"refusing to overwrite {path}; run `supersede` first")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload if text else json.dumps(payload, indent=1, sort_keys=True,
                                                     default=_json_default))


def _json_default(o):
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(type(o))


def clopper_pearson(k: int, n: int, level: float = 0.95) -> list[float]:
    tail = (1.0 - level) / 2.0
    lo = 0.0 if k == 0 else float(stats.beta.ppf(tail, k, n - k + 1))
    hi = 1.0 if k == n else float(stats.beta.ppf(1.0 - tail, k + 1, n - k))
    return [lo, hi]


def deep_diff(a, b, path: str = "") -> list[str]:
    """Every leaf where two JSON trees differ; floats compared exactly."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = [f"{path}/{k}: missing on one side" for k in sorted(set(a) ^ set(b))]
        for k in sorted(set(a) & set(b)):
            out += deep_diff(a[k], b[k], f"{path}/{k}")
        return out
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return [f"{path}: lengths {len(a)} != {len(b)}"]
        out = []
        for i, (x, y) in enumerate(zip(a, b)):
            out += deep_diff(x, y, f"{path}[{i}]")
        return out
    if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
        return []
    return [] if a == b and type(a) is type(b) else [f"{path}: {a!r} != {b!r}"]


# ----------------------------------------------------------------------------
# Tables and grids
# ----------------------------------------------------------------------------
_TABLES: dict[str, BehaviorTable] = {}


def _full_table(path: str, s_max: int | None = None) -> BehaviorTable:
    key = f"{path}|{s_max}"
    if key not in _TABLES:
        rows = [r for r in read_jsonl(path)
                if s_max is None or int(r["s"]) <= s_max]
        _TABLES[key] = load_level_table(rows, axes(), LEVEL)
    return _TABLES[key]


def b42_split_seed(run_index: int, model_index: int, replicate: int) -> int:
    split_seed, _ = b42._seeds(run_index, model_index, replicate)
    return split_seed


def half_table(table: BehaviorTable, split_seed: int, half: int) -> BehaviorTable:
    a, b = split_cell_indices(table, np.random.default_rng(split_seed))
    return subset_table(table, (a, b)[half])


def matched_split_seed(key: str, replicate: int) -> int:
    """Split seed of a non-A member in the matched placebo."""
    ss = np.random.SeedSequence([SEED, 1000 + INDEX[key], replicate])
    return int(ss.generate_state(1, dtype=np.uint32)[0])


def member_table(key: str, replicate: int = 0) -> BehaviorTable:
    """The verdict table of a member; halves are drawn with their recorded seeds."""
    if key.endswith("#h"):
        base = key[:-2]
        m = MEMBERS[INDEX[base]]
        return half_table(_full_table(m["path"], m.get("s_max")),
                          matched_split_seed(base, replicate), 0)
    m = MEMBERS[INDEX[key]]
    full = _full_table(m["path"], m.get("s_max"))
    if "half" in m:
        return half_table(full, b42_split_seed(B42_RUN_A, B42_MODEL_BASE, replicate),
                          m["half"])
    return full


def target_only_grids(table: BehaviorTable) -> dict[str, np.ndarray]:
    """Signed target-only t over (candidate, axis): median and mean of the others.

    ``median`` is ``reference_free_max_statistic``'s contrast. ``mean`` is the
    registered contrast with an all-zero base on the target's own cells, which is
    how ``partA_baseline_role`` builds its target-only-mean test.
    """
    rates, _, _ = cell_rates(table)
    t_med, _, _ = standardized_excess(reference_free_effect(rates))
    zero = np.where(np.isnan(rates), np.nan, 0.0)
    t_mean, _, _ = standardized_excess(excess_effect(rates, zero))
    return {"median": t_med, "mean": t_mean}


# ----------------------------------------------------------------------------
# The panel tests
# ----------------------------------------------------------------------------
def seeds_for(member: str, panel_i: int, pool_i: int, grid_i: int, variant_i: int,
              scheme_i: int, replicate: int | None = None) -> np.random.SeedSequence:
    entropy = [SEED, member_index(member), panel_i, pool_i, grid_i, variant_i, scheme_i]
    if replicate is not None:
        entropy.append(1000 + replicate)
    return np.random.SeedSequence(entropy)


def pooled_max_test(t: np.ndarray, others: list[np.ndarray], n_boot: int,
                    seeds: list[np.random.SeedSequence]) -> dict:
    """``cross_run_reference_test`` with the resampling seeds passed in.

    The body is the library function's, line for line; only the generator per
    scheme comes from ``seeds``. ``selftest`` checks the two agree exactly when
    the seeds are the library's own.
    """
    abs_t = np.abs(t)
    m = int(np.sum(~np.isnan(abs_t)))
    s = float(np.nanmax(abs_t))
    ref = np.hstack(others)
    flat = ref[~np.isnan(ref)]
    q_single = float(np.quantile(flat, 0.99, method="higher"))
    out = {"S": s, "M": m, "n_ref": int(flat.size), "n_other_runs": len(others),
           "naive_p_single": (1.0 + int(np.sum(flat >= s))) / (1.0 + flat.size),
           "naive_q99_single": q_single, "naive_R": ratio_to_quantile(s, q_single),
           "p_exact_values": float(1.0 - np.mean(flat < s) ** m)}
    for index, scheme in enumerate(SCHEMES):
        rng = np.random.default_rng(seeds[index])
        maxima = resampled_maxima(ref, m, scheme, n_boot, rng)
        q = float(np.quantile(maxima, 0.99, method="higher"))
        out[scheme] = {"p_ref": reference_tail_share(maxima, s), "q99_max": q,
                       "R": ratio_to_quantile(s, q)}
    return out


def rank_p(x: float, ref: list[float]) -> float:
    """``(1 + #{ref >= x}) / (1 + n)``: the member's rank among the panel's maxima."""
    return (1.0 + sum(1 for r in ref if r >= x)) / (1.0 + len(ref))


def contributed_rows(abs_t: np.ndarray, drop_top: bool) -> np.ndarray:
    keep = np.ones(abs_t.shape[0], dtype=bool)
    if drop_top:
        keep[top_candidate(abs_t)] = False
    return keep


def loo_standardize(grids: dict[str, np.ndarray], keeps: dict[str, np.ndarray],
                    members: list[str], who: str) -> tuple[np.ndarray, np.ndarray]:
    """``who``'s signed t standardized by the other members' cell mean and SD.

    Each other member contributes only its kept rows. Returns z and the number
    of reference values per cell.
    """
    stack = np.stack([np.where(keeps[w][:, None], grids[w], np.nan)
                      for w in members if w != who])
    n = np.sum(~np.isnan(stack), axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.nanmean(stack, axis=0)
        sd = np.nanstd(stack, axis=0, ddof=1)
        z = (grids[who] - mean) / sd
    z = np.where((n >= 3) & (sd > 0) & np.isfinite(sd), z, np.nan)
    return z, n


def pool_members(panel: list[str], x: str, pool: str) -> list[str]:
    if pool.startswith("nulls"):
        return [w for w in panel if w != x and role_of(w) != "positive"]
    return [w for w in panel if w != x]


def test_member(x: str, panel_name: str, panel: list[str], grids: dict, candidates: list,
                n_boot: int = N_BOOT, replicate: int | None = None,
                variants: tuple[str, ...] = VARIANTS) -> dict:
    """Every pool, grid and variant for one tested member ``x``."""
    panel_i = list(panels()).index(panel_name)
    out: dict = {}
    for pool_i, pool in enumerate(POOLS):
        ref = pool_members(panel, x, pool)
        drop = pool.endswith("drop_top")
        out[pool] = {"reference_members": ref}
        for grid_i, g in enumerate(GRIDS):
            t = {w: grids[w][g] for w in [x, *ref]}
            a = {w: np.abs(v) for w, v in t.items()}
            keeps = {w: contributed_rows(a[w], drop) for w in t}
            s_x = float(np.nanmax(a[x]))
            top_x = candidates[top_candidate(a[x])]
            res: dict = {"S": s_x, "argmax_candidate": top_x}
            ref_max = [float(np.nanmax(a[w][keeps[w]])) for w in ref]
            if "pooled_max" in variants:
                pm = pooled_max_test(t[x], [a[w][keeps[w]] for w in ref], n_boot,
                                     [seeds_for(x, panel_i, pool_i, grid_i, 0, s, replicate)
                                      for s in range(len(SCHEMES))])
                pm["member_rank_p"] = rank_p(s_x, ref_max)
                res["pooled_max"] = pm
            if "fixed_candidate" in variants:
                fc = {}
                for ci, c in enumerate(candidates):
                    rows = [a[w][ci][None, :] for w in ref if keeps[w][ci]]
                    row_x = a[x][ci]
                    s_c = float(np.nanmax(row_x))
                    entry = {"S_row": s_c, "n_reference_rows": len(rows),
                             "member_rank_p": rank_p(s_c, [float(np.nanmax(r)) for r in rows])}
                    if rows:
                        flat = np.hstack(rows)
                        flat = flat[~np.isnan(flat)]
                        m_c = int(np.sum(~np.isnan(row_x)))
                        rng = np.random.default_rng(seeds_for(x, panel_i, pool_i, grid_i, 1,
                                                              ci, replicate))
                        maxima = resampled_maxima(np.hstack(rows), m_c, "values", n_boot, rng)
                        entry.update({"M_row": m_c, "n_ref": int(flat.size),
                                      "values": {"p_ref": reference_tail_share(maxima, s_c),
                                                 "q99_max": float(np.quantile(
                                                     maxima, 0.99, method="higher"))},
                                      "p_exact_values": float(
                                          1.0 - np.mean(flat < s_c) ** m_c)})
                    fc[c] = entry
                res["fixed_candidate"] = fc
            if "cellwise" in variants:
                members = [x, *ref]
                zs, ns = {}, {}
                for w in members:
                    zs[w], ns[w] = loo_standardize(t, keeps, members, w)
                zabs = {w: np.abs(z) for w, z in zs.items()}
                z_x = float(np.nanmax(zabs[x]))
                ci_z, ai_z = np.unravel_index(np.nanargmax(zabs[x]), zabs[x].shape)
                n_cell = ns[x]
                with np.errstate(invalid="ignore", divide="ignore"):
                    r = zs[x] / np.sqrt(1.0 + 1.0 / n_cell)
                    p_cell = 2.0 * stats.t.sf(np.abs(r), n_cell - 1)
                finite = np.isfinite(p_cell)
                m_z = int(np.sum(~np.isnan(zabs[x])))
                p_bonf = float(min(1.0, int(finite.sum()) * float(np.nanmin(p_cell))))
                cw = {"Z": z_x, "argmax_candidate": candidates[int(ci_z)],
                      "argmax_axis_index": int(ai_z), "M": m_z,
                      "n_reference_min": int(n_cell[finite].min()) if finite.any() else 0,
                      "rank_p": rank_p(z_x, [float(np.nanmax(zabs[w])) for w in ref]),
                      "param_bonferroni_p": p_bonf}
                pm = pooled_max_test(zs[x], [zabs[w] for w in ref], n_boot,
                                     [seeds_for(x, panel_i, pool_i, grid_i, 2, s, replicate)
                                      for s in range(len(SCHEMES))])
                cw["resampled_values_p"] = pm["values"]["p_ref"]
                cw["resampled_axes_p"] = pm["axes"]["p_ref"]
                cw["resampled_q99_values"] = pm["values"]["q99_max"]
                res["cellwise"] = cw
            if "re_residual" in variants:
                n = len(ref_max)
                mu, sd = float(np.mean(ref_max)), float(np.std(ref_max, ddof=1))
                resid = (s_x - mu) / (sd * math.sqrt(1.0 + 1.0 / n))
                res["re_residual"] = {"S": s_x, "n": n, "mean_ref": mu, "sd_ref": sd,
                                      "residual": resid,
                                      "t_p_one_sided": float(stats.t.sf(resid, n - 1))}
            out[pool][g] = res
    return out


def primary_p(res: dict, variant: str, which: str | None = None) -> float:
    """The p a variant's decision reads; ``which`` overrides the primary."""
    which = which or PRIMARY["p"][variant]
    if variant == "pooled_max":
        return {"values": res["pooled_max"]["values"]["p_ref"],
                "axes": res["pooled_max"]["axes"]["p_ref"],
                "member_rank": res["pooled_max"]["member_rank_p"],
                "exact_values": res["pooled_max"]["p_exact_values"]}[which]
    if variant == "fixed_candidate":
        fc = res["fixed_candidate"][TARGET_CANDIDATE]
        if which == "member_rank":
            return fc["member_rank_p"]
        if which == "exact_values":
            return fc["p_exact_values"]
        if which == "any_candidate_bonferroni":
            return min(1.0, len(res["fixed_candidate"]) * min(
                v["values"]["p_ref"] for v in res["fixed_candidate"].values() if "values" in v))
        return fc["values"]["p_ref"]
    if variant == "cellwise":
        return {"resampled_values": res["cellwise"]["resampled_values_p"],
                "resampled_axes": res["cellwise"]["resampled_axes_p"],
                "rank": res["cellwise"]["rank_p"],
                "param_bonferroni": res["cellwise"]["param_bonferroni_p"]}[which]
    return res["re_residual"]["t_p_one_sided"]


P_TYPES = {"pooled_max": ("values", "axes", "exact_values", "member_rank"),
           "fixed_candidate": ("values", "exact_values", "member_rank",
                               "any_candidate_bonferroni"),
           "cellwise": ("resampled_values", "resampled_axes", "param_bonferroni", "rank"),
           "re_residual": ("t",)}


def named_of(res: dict, variant: str, p: float) -> str | None:
    if p > ALPHA:
        return None
    if variant == "fixed_candidate":
        return TARGET_CANDIDATE
    if variant == "cellwise":
        return res["cellwise"]["argmax_candidate"]
    return res["argmax_candidate"]


# ----------------------------------------------------------------------------
# Commands
# ----------------------------------------------------------------------------
def cross_paper(runs: dict, grids, family=FAMILY) -> dict:
    """``pooled_reference_calibration.cross`` without the file write.

    Copied line for line; ``runs`` and ``grids`` are passed in instead of read
    from ``out/main/calibration/pooled_reference``.
    """
    nulls = family[1:]
    first = runs[family[0]]
    for key in family:
        if runs[key]["candidates"] != first["candidates"] or runs[key]["axes"] != first["axes"]:
            raise ValueError(f"{key} does not share the roster and axes of {family[0]}")
    bases = {runs[k]["sha256_base"] for k in family}
    out = {"family": list(family), "shared_base_files": len(bases),
           "pools": {"all_family": "every other run of the family, the positive "
                     "contextual_optimism included",
                     "nulls_only": "the other null controls only, top rows dropped",
                     "nulls_only_all_rows": "the other null controls only, every "
                     "row kept (exchangeable when they are nulls)"}}
    for pool in out["pools"]:
        out[pool] = {}
        for index, key in enumerate(family):
            members = [k for k in family if k != key
                       and (pool == "all_family" or k in nulls)]
            others = [reference_rows(grids[k], drop_top=pool != "nulls_only_all_rows")
                      for k in members]
            r = cross_run_reference_test(grids[key], others, prc.N_BOOT, seed=100 + index)
            out[pool][key] = {"reference_runs": members, **r}
    return out


def cmd_selftest(_a) -> int:
    """Checks of this file's own code that must hold before any output is trusted."""
    failures = []
    if tuple(prc.FAMILY) != FAMILY or prc.N_BOOT != N_BOOT:
        failures.append("FAMILY or N_BOOT differs from pooled_reference_calibration")
    rng = np.random.default_rng(1)
    t = rng.standard_normal((6, 101))
    others = [np.abs(rng.standard_normal((5, 101))) for _ in range(8)]
    lib = cross_run_reference_test(t, others, 2000, seed=123)
    mine = pooled_max_test(t, others, 2000,
                           [np.random.SeedSequence([123, 7, i]) for i in range(2)])
    d = deep_diff(jround(lib), jround(mine))
    if d:
        failures.append(f"pooled_max_test differs from cross_run_reference_test: {d[:3]}")
    # The deep comparison must be able to fail.
    bad = jround(lib)
    bad["values"]["p_ref"] += 1e-15
    if not deep_diff(jround(lib), bad):
        failures.append("deep_diff missed a 1e-15 change")
    # Full-conformal symmetry: the cellwise statistic of a member does not depend
    # on which member is the tested one when the set is the same.
    g = {f"m{i}": rng.standard_normal((6, 20)) for i in range(6)}
    k = {w: np.ones(6, dtype=bool) for w in g}
    z1, _ = loo_standardize(g, k, list(g), "m0")
    z2, _ = loo_standardize(g, k, list(reversed(list(g))), "m0")
    if not np.allclose(z1, z2, equal_nan=True):
        failures.append("loo_standardize depends on member order")
    # The rank p has its floor at 1 / (n + 1) and its ceiling at 1.
    if rank_p(5.0, [1.0] * 14) != 1 / 15 or rank_p(0.0, [1.0] * 14) != 1.0:
        failures.append("rank_p floor or ceiling wrong")
    # The deleted residual's null: under i.i.d. normal members its one-sided
    # t_{n-1} p is uniform, so about 1% of draws fall at or below 0.01.
    draws = rng.standard_normal((20000, 15))
    mu, sd = draws[:, 1:].mean(axis=1), draws[:, 1:].std(axis=1, ddof=1)
    resid = (draws[:, 0] - mu) / (sd * math.sqrt(1 + 1 / 14))
    share = float(np.mean(stats.t.sf(resid, 13) <= 0.01))
    if not 0.007 <= share <= 0.013:
        failures.append(f"deleted residual size {share} far from 0.01")
    print("selftest:", "PASS" if not failures else failures)
    return len(failures)


def cmd_gate(_a) -> int:
    """Reproduce the paper's base-referenced cross-run reference before anything else."""
    stored_runs = load_json(POOLED / "results.json")["runs"]
    stored_cross = load_json(POOLED / "cross_run.json")
    stored_grids = np.load(POOLED / "t_grids.npz")
    specs = {s.key: s for s in b42.RUNS}
    checks = {"sha256": {}, "t_grid_recomputed_equal": {}}
    recomputed = {}
    for key in FAMILY:
        spec = specs[key]
        st = stored_runs[key]
        checks["sha256"][key] = {
            "target": sha256(spec.verdicts_target) == st["sha256_target"],
            "base": sha256(spec.verdicts_base) == st["sha256_base"]}
        target, base, _ = b42._tables(spec)
        p_t, cands, _ = cell_rates(target)
        p_b, _, _ = cell_rates(base)
        recomputed[key] = t_grid(p_t, p_b)
        checks["t_grid_recomputed_equal"][key] = bool(
            np.array_equal(recomputed[key], stored_grids[key], equal_nan=True))
    t0 = time.time()
    from_stored = jround(cross_paper(stored_runs, {k: stored_grids[k] for k in FAMILY}))
    from_current = jround(cross_paper(stored_runs, recomputed))
    diff_stored = deep_diff(from_stored, stored_cross)
    diff_current = deep_diff(from_current, stored_cross)
    probe = jround(stored_cross)
    probe["nulls_only_all_rows"]["auditbench_flattery"]["values"]["p_ref"] += 1e-12
    can_fail = bool(deep_diff(from_stored, probe))
    per_member = {pool: {k: not any(f"/{pool}/{k}/" in d or d.endswith(f"/{pool}/{k}")
                                    for d in diff_stored) for k in FAMILY}
                  for pool in GATE_POOLS}
    ok = (all(all(v.values()) for v in checks["sha256"].values())
          and all(checks["t_grid_recomputed_equal"].values())
          and not diff_stored and not diff_current and can_fail)
    record = {"what": "the paper's base-referenced cross-run reference, rerun",
              "stored": str(POOLED / "cross_run.json"),
              "seeds": "cross_run_reference_test(seed=100 + FAMILY index): "
                       "SeedSequence([100 + index, 7, scheme index])",
              "n_boot": prc.N_BOOT, "family": list(FAMILY), "pools": list(GATE_POOLS),
              **checks, "n_leaves_differing_from_stored_grids": len(diff_stored),
              "n_leaves_differing_from_recomputed_grids": len(diff_current),
              "first_differences": (diff_stored + diff_current)[:20],
              "per_member_pool_exact": per_member,
              "comparison_can_fail": can_fail, "seconds": round(time.time() - t0, 1),
              "all_reproduce": ok}
    write_new(OUT / "gate" / "reproduce_gate.json", record)
    print(json.dumps({k: v for k, v in record.items() if k != "per_member_pool_exact"},
                     indent=1)[:3000])
    return 0 if ok else 1


def _require_gate() -> None:
    p = OUT / "gate" / "reproduce_gate.json"
    if not p.exists() or not load_json(p)["all_reproduce"]:
        raise SystemExit("the gate has not passed; run `gate` first")


def cmd_grids(_a) -> int:
    _require_gate()
    ax = axes()
    keys = [m["key"] for m in MEMBERS] + [f"{k}#h" for k in MAIN15 if k != "base_A"]
    arrays, index = {}, {"axes": ax, "members": {}}
    for key in keys:
        table = member_table(key)
        g = target_only_grids(table)
        for name, arr in g.items():
            arrays[f"{key}|{name}"] = arr
        m = MEMBERS[INDEX[key[:-2] if key.endswith("#h") else key]]
        index["members"][key] = {
            "index": member_index(key), "role": role_of(key), "kind": m["kind"],
            "path": m["path"], "sha256": sha256(m["path"]),
            "candidates": list(table.principals), "n_responses": int(table.n_responses),
            "n_instructions": len(table.blocks), "s_max": m.get("s_max"),
            "split": ("B42 replicate 0 of base A, run 3 model 0, half "
                      f"{m['half'] + 1}" if "half" in m else
                      "matched placebo half 1, SeedSequence([20260726, 1000 + member index, 0])"
                      if key.endswith("#h") else None),
            "S_median": float(np.nanmax(np.abs(g["median"]))),
            "S_mean": float(np.nanmax(np.abs(g["mean"]))),
            "n_nan": {n: int(np.isnan(a).sum()) for n, a in g.items()},
            "n_inf": {n: int(np.isinf(a).sum()) for n, a in g.items()}}
        if list(table.principals) != list(_full_table(MEMBERS[0]["path"]).principals):
            raise SystemExit(f"{key} does not share the roster")
        if list(table.axes) != ax:
            raise SystemExit(f"{key} does not share the axes")
    p = OUT / "t_grids_target_only.npz"
    if p.exists():
        raise SystemExit(f"refusing to overwrite {p}")
    np.savez(p, **arrays)
    write_new(OUT / "t_grids_target_only_index.json", index)
    for k, v in index["members"].items():
        print(f"{k:26s} S_med={v['S_median']:.4f} S_mean={v['S_mean']:.4f} n={v['n_responses']}")
    return 0


def load_grids() -> tuple[dict, list[str], list[str]]:
    data = np.load(OUT / "t_grids_target_only.npz")
    index = load_json(OUT / "t_grids_target_only_index.json")
    grids: dict = {}
    for name in data.files:
        key, g = name.split("|")
        grids.setdefault(key, {})[g] = data[name]
    cands = index["members"]["contextual_optimism"]["candidates"]
    return grids, cands, index["axes"]


# -- sharp-null and registered permutation tests (Level 0 and Level 5) -------
def _sharp_task(task: dict) -> dict:
    from script.analysis.reanalysis_2026_11.partA_baseline_role import _digest, _zero_base
    from src.compare.paired_max_statistic import paired_max_test
    from src.compare.reference_free_max_statistic import reference_free_max_test
    t0 = time.time()
    tgt = member_table(task["member"])
    n_cells = len(tgt.principals) * len(tgt.axes)
    if task["kind"] == "target_only_median":
        res = reference_free_max_test(tgt, n_permutations=N_PERM, seed=SEED, alpha=ALPHA,
                                      top=n_cells)
        dig = _digest(res, "median", len(tgt.axes))
    elif task["kind"] == "target_only_mean":
        res = paired_max_test(tgt, _zero_base(tgt), n_permutations=N_PERM, seed=SEED,
                              alpha=ALPHA, top=n_cells)
        dig = _digest(res, "target_only_mean", len(tgt.axes))
    elif task["kind"] == "registered":
        base = member_table(task["base"])
        res = paired_max_test(tgt, base, n_permutations=N_PERM, seed=SEED, alpha=ALPHA,
                              top=n_cells)
        dig = _digest(res, "registered", len(tgt.axes))
    else:
        raise ValueError(task["kind"])
    keep = ("S", "p", "reject_0.01", "argmax_candidate", "argmax_axis", "argmax_t",
            "named_by_rule", "naming_reason", "surviving_axes_by_candidate",
            "n_surviving_pairs", "null_mean", "null_p95")
    return {**task, **{k: dig[k] for k in keep}, "seconds": round(time.time() - t0, 1)}


def cmd_sharp(a) -> int:
    _require_gate()
    tasks = []
    for m in MEMBERS:
        for kind in ("target_only_median", "target_only_mean"):
            tasks.append({"id": f"{m['key']}|{kind}", "member": m["key"], "kind": kind})
        if m["key"] not in ("base_A", "base_A_half1", "base_A_half2"):
            tasks.append({"id": f"{m['key']}|registered|base_A", "member": m["key"],
                          "kind": "registered", "base": "base_A"})
    tasks.append({"id": "base_A_half1|registered|base_A_half2", "member": "base_A_half1",
                  "kind": "registered", "base": "base_A_half2"})
    # Reproductions of the pooled-base item's stored base pairs (same tables).
    for tgt, base in (("C1", "base_B"), ("C2", "base_B"), ("C1_s0-11", "C2")):
        tasks.append({"id": f"{tgt}|registered|{base}", "member": tgt, "kind": "registered",
                      "base": base})
    log = OUT / "sharp" / "sharp_tasks.jsonl"
    if log.exists():
        raise SystemExit(f"refusing to overwrite {log}")
    log.parent.mkdir(parents=True, exist_ok=True)
    results = {}
    with ProcessPoolExecutor(max_workers=a.workers) as ex, log.open("x") as fh:
        futs = {ex.submit(_sharp_task, t): t["id"] for t in tasks}
        for f in as_completed(futs):
            r = f.result()
            results[r["id"]] = r
            fh.write(json.dumps(r, default=_json_default) + "\n")
            fh.flush()
            print(f"{r['id']:48s} S={r['S']:.4f} p={r['p']:.4f} argmax={r['argmax_candidate']}"
                  f" named={r['named_by_rule']} ({r['seconds']}s)", flush=True)
    # B42 replicate 0 of base A, registered half against half, exactly as B42 ran it.
    from src.compare.placebo_calibration import placebo_replicate
    split_seed, perm_seed = b42._seeds(B42_RUN_A, B42_MODEL_BASE, 0)
    b42_rep = placebo_replicate(_full_table(_BASE_A), split_seed, perm_seed, 2000, alpha=ALPHA)
    stored_b42 = next(r for r in read_jsonl(b42.OUT / "replicates.jsonl")
                      if r["key"] == "auditbench_contextual_optimism" and r["model"] == "base"
                      and r["replicate"] == 0)
    checks = sharp_checks(results)
    checks.append({"what": "B42 placebo replicate 0 of base A (2,000 permutations, B42 seeds)",
                   "stored_S": stored_b42["statistic"], "got_S": b42_rep["statistic"],
                   "stored_p": stored_b42["p"], "got_p": b42_rep["p"],
                   "split_seed": split_seed, "permutation_seed": perm_seed,
                   "match": (b42_rep["statistic"] == stored_b42["statistic"]
                             and b42_rep["p"] == stored_b42["p"])})
    bad = [c for c in checks if not c["match"]]
    write_new(OUT / "sharp" / "sharp_null.json",
              {"seed": SEED, "n_permutations": N_PERM, "alpha": ALPHA, "level": LEVEL,
               "results": results, "checks": checks, "n_checks": len(checks),
               "n_check_failures": len(bad)})
    print(f"{len(checks)} checks, {len(bad)} failures")
    for c in bad:
        print("MISMATCH", c)
    return len(bad)


def sharp_checks(results: dict) -> list[dict]:
    """Every recompute with a stored counterpart, compared exactly."""
    pa = load_json(PARTA)["results"]
    checks = []
    for member, pk in PARTA_KEY.items():
        for kind in ("target_only_median", "target_only_mean", "registered"):
            got = results[f"{member}|{kind}" + ("|base_A" if kind == "registered" else "")]
            st = pa.get(f"{pk}|{kind}|full")
            if st is None:
                continue
            checks.append({"what": f"partA {pk}|{kind}|full", "stored_S": st["S"],
                           "got_S": got["S"], "stored_p": st["p"], "got_p": got["p"],
                           "stored_named": st["named_by_rule"], "got_named": got["named_by_rule"],
                           "match": (got["S"] == st["S"] and got["p"] == st["p"]
                                     and got["named_by_rule"] == st["named_by_rule"])})
    st = pa["auditbench_contextual_optimism|base_only_median|full"]
    got = results["base_A|target_only_median"]
    checks.append({"what": "partA auditbench_contextual_optimism|base_only_median|full (base A)",
                   "stored_S": st["S"], "got_S": got["S"], "stored_p": st["p"],
                   "got_p": got["p"], "match": got["S"] == st["S"] and got["p"] == st["p"]})
    # Stage-6 summaries and the stored reference_free.json target seats.
    for member in ("contextual_optimism", *CONTROLS):
        root = (AB / "contextual_optimism/judge_mini" if member == "contextual_optimism"
                else AB / f"controls/{member}/judge_mini")
        stored = load_json(root / "compare/comparison_summary.json")["reference_contrast"][
            f"L{LEVEL}"]["paired_max_test"]
        got = results[f"{member}|registered|base_A"]
        named = (stored.get("attribution") or {}).get("named")
        checks.append({"what": f"comparison_summary.json {member}", "stored_S": stored["statistic"],
                       "got_S": got["S"], "stored_p": stored["p_family_wise"], "got_p": got["p"],
                       "stored_named": named, "got_named": got["named_by_rule"],
                       "match": (got["S"] == stored["statistic"]
                                 and got["p"] == stored["p_family_wise"]
                                 and got["named_by_rule"] == named)})
        rf = load_json(root / "compare/reference_free.json")
        seat = rf["seats"]["target"]
        got = results[f"{member}|target_only_median"]
        checks.append({"what": f"reference_free.json {member} target seat",
                       "stored_S": seat["statistic"], "got_S": got["S"],
                       "stored_p": seat["p_family_wise"], "got_p": got["p"],
                       "match": (got["S"] == seat["statistic"]
                                 and got["p"] == seat["p_family_wise"]
                                 and rf["seed"] == SEED and rf["n_permutations"] == N_PERM)})
    pb = load_json(POOLED_BASE)["base_pairs"]
    for tgt, base, key in (("C1", "base_B", "C1|B"), ("C2", "base_B", "C2|B"),
                           ("C1_s0-11", "C2", "C1s0-11|C2")):
        got = results[f"{tgt}|registered|{base}"]
        st = pb[key]["registered"]
        checks.append({"what": f"pooled_base compare_summary base_pairs {key}",
                       "stored_S": st["statistic"], "got_S": got["S"],
                       "stored_p": st["p_family_wise"], "got_p": got["p"],
                       "match": got["S"] == st["statistic"] and got["p"] == st["p_family_wise"]})
    return checks


# -- the panel --------------------------------------------------------------
def cmd_panel(_a) -> int:
    _require_gate()
    grids, cands, ax = load_grids()
    t0 = time.time()
    record: dict = {"panels": {}, "family9_target_only": {}}
    for pname, members in panels().items():
        record["panels"][pname] = {"members": members, "results": {}}
        for x in members:
            record["panels"][pname]["results"][x] = test_member(x, pname, members, grids, cands)
            r = record["panels"][pname]["results"][x]["nulls_all_rows"]["median"]
            print(f"{pname:16s} {x:26s} S={r['S']:.3f} pm_values={r['pooled_max']['values']['p_ref']:.4f}"
                  f" fc={r['fixed_candidate'][TARGET_CANDIDATE]['values']['p_ref']:.4f}"
                  f" cw={r['cellwise']['resampled_values_p']:.4f}"
                  f" re={r['re_residual']['t_p_one_sided']:.4f} [{time.time() - t0:.0f}s]",
                  flush=True)
    # The paper's own cross() on target-only grids: same nine runs, pools and seeds.
    runs9 = {f"auditbench_{k}" if k != "contextual_optimism" else FAMILY[0]:
             {"candidates": cands, "axes": ax, "sha256_base": "none (target only)"}
             for k in ("contextual_optimism", *CONTROLS)}
    for g in GRIDS:
        g9 = {FAMILY[0]: grids["contextual_optimism"][g],
              **{f"auditbench_{c}": grids[c][g] for c in CONTROLS}}
        record["family9_target_only"][g] = jround(cross_paper(runs9, g9))
    record["seconds"] = round(time.time() - t0, 1)
    write_new(OUT / "cross_run_target_only.json", record)
    print(f"wrote {OUT / 'cross_run_target_only.json'} in {record['seconds']}s")
    return 0


# -- replicated placebo -------------------------------------------------------
_WORKER: dict = {}


def _init_worker() -> None:
    os.environ.setdefault("OMP_NUM_THREADS", "1")


def _placebo_task(replicate: int, design: str) -> dict:
    t0 = time.time()
    if "grids" not in _WORKER:
        _WORKER["grids"], _WORKER["cands"], _ = load_grids()
    grids = dict(_WORKER["grids"])
    cands = _WORKER["cands"]
    for key in ("base_A_half1", "base_A_half2"):
        grids[key] = target_only_grids(member_table(key, replicate))
    if design == "placebo_matched":
        for key in MAIN15:
            if key != "base_A":
                grids[f"{key}#h"] = target_only_grids(member_table(f"{key}#h", replicate))
    members = panels()[design]
    out = {"replicate": replicate, "design": design,
           "split_seed_base_A": b42_split_seed(B42_RUN_A, B42_MODEL_BASE, replicate)}
    for x in ("base_A_half1", "base_A_half2"):
        res = test_member(x, design, members, grids, cands, replicate=replicate)
        flat = {}
        for pool in POOLS:
            for g in GRIDS:
                r = res[pool][g]
                flat[f"{pool}|{g}|S"] = r["S"]
                for v in VARIANTS:
                    for pt in P_TYPES[v]:
                        flat[f"{pool}|{g}|{v}|{pt}"] = primary_p(r, v, pt)
        out[x] = flat
    out["seconds"] = round(time.time() - t0, 1)
    return out


def cmd_placebo(a) -> int:
    _require_gate()
    log = OUT / "placebo" / "placebo_replicates.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    done = ({(r["design"], r["replicate"]) for r in read_jsonl(log)} if log.exists() else set())
    todo = [(r, d) for d in ("placebo_halves", "placebo_matched")
            for r in range(a.replicates) if (d, r) not in done]
    print(f"{len(todo)} placebo replicates on {a.workers} workers ({len(done)} done)", flush=True)
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=a.workers, initializer=_init_worker) as ex, \
            log.open("a") as fh:
        futs = [ex.submit(_placebo_task, r, d) for r, d in todo]
        for n, f in enumerate(as_completed(futs), 1):
            fh.write(json.dumps(f.result(), default=_json_default) + "\n")
            fh.flush()
            if n % 20 == 0 or n == len(futs):
                print(f"{n}/{len(futs)} [{time.time() - t0:.0f}s]", flush=True)
    return 0


# -- user-awareness subjects: a descriptive K = 3 panel -----------------------
UA_DIRS = {"openai:gpt-5-mini": Path("out/main/external/user_awareness_grading"),
           "openai:gpt-4.1-mini": Path("out/main/external/user_awareness_grading_gpt41mini"),
           "openai:gpt-5": Path("out/main/external/user_awareness_grading_gpt5")}


def cmd_ua(_a) -> int:
    from src.compare.behavior_count_table import build_behavior_table
    from src.compare.reference_free_max_statistic import reference_free_max_test
    from src.external.user_awareness_materials import GRADE_AXES, IDENTITIES
    ax = [a["axis_id"] for a in GRADE_AXES]
    subjects, checks = {}, []
    for subject, d in UA_DIRS.items():
        stored = load_json(d / "user_awareness_detection.json")
        rows = [r for r in read_jsonl(d / "grades_target.jsonl")
                if int(r["level"]) == 1 and not r.get("failed")]
        table = build_behavior_table(rows, ax)
        rf = reference_free_max_test(table, n_permutations=stored["reference_free"][
            "n_permutations"], seed=stored["seed"], top=len(IDENTITIES) * len(ax))
        st = stored["reference_free"]
        same = (rf["statistic"] == st["statistic"] and rf["p_family_wise"] == st["p_family_wise"]
                and rf["named"] == st["named"] and rf["different"] == st["different"]
                and jround(rf["top_pairs"]) == st["top_pairs"])
        checks.append({"what": f"user_awareness_detection.json {subject} reference_free",
                       "stored_S": st["statistic"], "got_S": rf["statistic"],
                       "stored_p": st["p_family_wise"], "got_p": rf["p_family_wise"],
                       "stored_named": st["named"], "got_named": rf["named"], "match": same})
        g = target_only_grids(table)
        subjects[subject] = {"dir": str(d), "sha256_grades": sha256(d / "grades_target.jsonl"),
                             "subject_in_file": stored["subject"],
                             "candidates": list(table.principals), "axes": ax,
                             "n_rows": len(rows), "n_instructions": len(table.blocks),
                             "grids": {k: v.tolist() for k, v in g.items()},
                             "stored_reference_free": {"S": st["statistic"],
                                                       "p": st["p_family_wise"],
                                                       "named_at_0.05": st["named"]}}
    cands = subjects["openai:gpt-5-mini"]["candidates"]
    if any(s["candidates"] != cands for s in subjects.values()):
        raise SystemExit("the three subjects do not share the identities")
    groups = {i["key"]: i["group"] for i in IDENTITIES}
    desc: dict = {}
    for gname in GRIDS:
        arr = {s: np.array(v["grids"][gname]) for s, v in subjects.items()}
        S = {s: float(np.nanmax(np.abs(a))) for s, a in arr.items()}
        argmax = {s: cands[top_candidate(np.abs(a))] for s, a in arr.items()}
        rows = {s: {c: float(np.nanmax(np.abs(a[i]))) for i, c in enumerate(cands)}
                for s, a in arr.items()}
        dev = {}
        for s in arr:
            others = [arr[o] for o in arr if o != s]
            d = arr[s] - np.mean(others, axis=0)
            ci, aj = np.unravel_index(np.nanargmax(np.abs(d)), d.shape)
            dev[s] = {"max_abs_deviation_from_other_two_mean": float(np.abs(d).max()),
                      "at": [cands[int(ci)], ax[int(aj)]]}
        safety = {c: {s: {"row_max_abs_t": rows[s][c],
                          "row_rank_within_subject": 1 + sum(1 for o in cands
                                                             if rows[s][o] > rows[s][c]),
                          "signed_t_by_axis": dict(zip(ax, arr[s][cands.index(c)].tolist()))}
                      for s in arr}
                  for c in cands if groups[c] == "safety"}
        desc[gname] = {"S": S, "argmax_candidate": argmax,
                       "S_order": sorted(S, key=lambda s: -S[s]),
                       "row_max_abs_t": rows, "deviation_from_other_two": dev,
                       "safety_identities": safety}
    record = {"what": "user-awareness grading subjects as a descriptive K = 3 panel; no test",
              "reason_no_test": "with K = 3 a member's rank p cannot fall below 1/3 and a "
                                "leave-one-out SD rests on two values",
              "identities": {i["key"]: {"name": i["name"], "group": i["group"]} for i in IDENTITIES},
              "subjects": subjects, "descriptive": desc, "checks": checks,
              "n_check_failures": sum(not c["match"] for c in checks)}
    write_new(OUT / "ua" / "ua_panel.json", record)
    for c in checks:
        print(c)
    print(json.dumps({g: {k: v for k, v in d.items() if k in ("S", "argmax_candidate")}
                      for g, d in desc.items()}, indent=1))
    return record["n_check_failures"]


def cmd_supersede(_a) -> int:
    if not OUT.exists():
        print("nothing to supersede")
        return 0
    dest = SUPERSEDED / time.strftime("%Y%m%dT%H%M%S")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(OUT), str(dest))
    print(f"moved {OUT} to {dest}")
    return 0


#: Files ``summarize`` writes; ``supersede-summary`` moves exactly these.
SUMMARY_OUTPUTS = ("settings.json", "reproduce_check.json", "panel_table.csv",
                   "panel_primary.csv", "false_positive_summary.csv",
                   "placebo/placebo_summary.json", "runs", "README.md", "logs/summarize.log")


def cmd_supersede_summary(_a) -> int:
    """Move only the summarize outputs to ``out/superseded/``; the analyses stay."""
    dest = SUPERSEDED / f"summary_{time.strftime('%Y%m%dT%H%M%S')}"
    moved = []
    for rel in SUMMARY_OUTPUTS:
        src = OUT / rel
        if src.exists():
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest / rel))
            moved.append(rel)
    print(f"moved {moved} to {dest}")
    return 0


def _summarize(a) -> int:
    from script.analysis.baseline_free_20261115.cross_run_panel import summarize_panel
    return summarize_panel.cmd_summarize(a)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("selftest", "gate", "grids", "panel", "ua", "summarize", "supersede",
                 "supersede-summary"):
        sub.add_parser(name)
    p = sub.add_parser("sharp")
    p.add_argument("--workers", type=int, default=14)
    p = sub.add_parser("placebo")
    p.add_argument("--replicates", type=int, default=200)
    p.add_argument("--workers", type=int, default=14)
    a = ap.parse_args()
    fn = {"selftest": cmd_selftest, "gate": cmd_gate, "grids": cmd_grids, "sharp": cmd_sharp,
          "panel": cmd_panel, "placebo": cmd_placebo, "ua": cmd_ua,
          "summarize": _summarize, "supersede": cmd_supersede,
          "supersede-summary": cmd_supersede_summary}[a.cmd]
    raise SystemExit(fn(a))


if __name__ == "__main__":
    main()
