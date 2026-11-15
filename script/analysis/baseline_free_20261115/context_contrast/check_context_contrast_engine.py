"""Independent checks of the context-contrast code. No spend.

    OMP_NUM_THREADS=1 uv run python -m \\
        script.analysis.baseline_free_20261115.context_contrast.check_context_contrast_engine

Each check recomputes a quantity by a second route and records the largest
difference. Exits non-zero if any check fails.

1. Sign-flip engine against a loop over the registered ``standardized_excess``
   with the same sign matrix, on real context differences (null maxima and p).
2. Welch engine against ``scipy.stats.ttest_ind(equal_var=False)``.
3. The (candidate, framing, template, axis) cube against a table built from
   one framing's rows alone.
4. Split-half halves against the registered placebo route
   (``subset_table`` then ``cell_rates``) and the half sizes.
5. Cancellation: a candidate shift equal in both contexts, and a shift shared by
   every candidate in one context, leave the contrast unchanged.
6. A planted context effect on one candidate is found and named.
7. Holm on a hand example.
"""

from __future__ import annotations

import json
import sys

import numpy as np
from scipy import stats

from script.analysis.baseline_free_20261115.context_contrast.context_contrast_engine import (
    _columns, flip_t_rows, holm, paired_flip_test, welch_t_rows)
from script.analysis.baseline_free_20261115.context_contrast.context_contrast_gaps import (
    context_cube, gap, load_table, split_instruction, stance_of)
from script.analysis.baseline_free_20261115.context_contrast.context_contrast_placebos import (
    _Splitter)
from script.analysis.baseline_free_20261115.context_contrast.context_contrast_runs import (
    OUT, models)
from src.common.file_io import read_jsonl
from src.compare.behavior_count_table import build_behavior_table
from src.compare.paired_excess_measures import cell_rates, max_abs_statistic, standardized_excess
from src.compare.placebo_calibration import subset_table

PICK = ("calibration_informed|target", "challenge_organism_b_person|base",
        "calibration_blind_organization|target")


def _delta(key):
    m = {x.key: x for x in models()}[key]
    t = load_table(m.verdicts, m.axes, m.level)
    cube, cands, fr, tm = context_cube(t)
    d = gap(cube, "mean")
    return m, t, cube, cands, fr, tm, d[:, fr.index("committed_supporter")] - d[:, fr.index("none")]


def check_flip_engine():
    out = []
    for key in PICK:
        _, t, _, cands, _, _, delta = _delta(key)
        xf, mk, x2 = _columns(delta)
        rng = np.random.default_rng(7)
        signs = rng.integers(0, 2, (2000, delta.shape[1])) * 2.0 - 1.0
        vec = np.nanmax(np.where(np.isnan(v := flip_t_rows(signs, xf, mk.sum(0), x2.sum(0))),
                                 -np.inf, np.abs(v)), axis=1)
        loop = np.array([max_abs_statistic(standardized_excess(delta * s[None, :, None])[0], False)
                         for s in signs])
        s_obs = max_abs_statistic(standardized_excess(delta)[0], False)
        p_vec = (1 + np.sum(vec >= s_obs)) / 2001
        p_loop = (1 + np.sum(loop >= s_obs)) / 2001
        diff = float(np.max(np.abs(vec - loop) / np.maximum(1, np.abs(loop))))
        res = paired_flip_test(delta, cands, list(t.axes), n=200)
        out.append({"model": key, "max_rel_diff_null_max": diff, "p_vec": float(p_vec),
                    "p_loop": float(p_loop), "S_engine": res["statistic"], "S_registered": s_obs,
                    "ok": bool(diff < 1e-12 and p_vec == p_loop
                               and abs(res["statistic"] - s_obs) <= 1e-12 * max(1, s_obs))})
    return out


def check_welch():
    _, t, cube, cands, fr, tm, _ = _delta("calibration_informed|target")
    v = gap(cube, "mean")[:, fr.index("none")]
    one = [k for k, x in enumerate(tm) if stance_of(x) == "supporter"]
    zero = [k for k, x in enumerate(tm) if stance_of(x) == "neutral"]
    keep = one + zero
    xf, mk, x2 = _columns(v[:, keep])
    lab = np.r_[np.ones(len(one)), np.zeros(len(zero))]
    rng = np.random.default_rng(3)
    g = np.stack([lab] + [rng.permutation(lab) for _ in range(30)])
    w = welch_t_rows(g, xf, mk, x2)
    worst, a_n = 0.0, v.shape[2]
    for b in range(g.shape[0]):
        sel = g[b].astype(bool)
        for c in range(v.shape[0]):
            for a in range(a_n):
                r = stats.ttest_ind(v[c, keep][sel, a], v[c, keep][~sel, a], equal_var=False).statistic
                if np.isfinite(r):
                    worst = max(worst, abs(r - w[b, c * a_n + a]) / max(1, abs(r)))
    return {"max_rel_diff": worst, "ok": bool(worst < 1e-12)}


def check_cube():
    m, t, cube, cands, fr, tm, _ = _delta("calibration_scoped|target")
    rows = [r for r in read_jsonl(m.verdicts) if int(r["level"]) == m.level
            and split_instruction(r["instruction_id"])[0] == "committed_supporter"]
    sub = build_behavior_table(rows, list(t.axes))
    rates, _, _ = cell_rates(sub)
    order = [tm.index(split_instruction(sub.blocks[b])[1]) for b in sorted(set(sub.block_of))]
    diff = float(np.nanmax(np.abs(cube[:, fr.index("committed_supporter")][:, order] - rates)))
    return {"max_abs_diff": diff, "ok": bool(diff == 0.0)}


def check_split():
    """The splitter's half rates against ``subset_table`` then ``cell_rates``.

    The second route builds framing none's table from the verdict rows alone,
    then folds each half with the registered placebo's ``subset_table``.
    """
    m, t, *_ = _delta("calibration_informed|target")
    rows = [r for r in read_jsonl(m.verdicts) if int(r["level"]) == m.level]
    none_rows = [r for r in rows if split_instruction(r["instruction_id"])[0] == "none"]
    none_table = build_behavior_table(none_rows, list(t.axes))
    out = []
    for k in range(3):
        sp = _Splitter(t, "none")
        same_rows = bool(np.array_equal(t.fired[sp.rows], none_table.fired))
        half = sp.split(np.random.default_rng([20260726, k]))
        worst = 0.0
        for side in (half, ~half):
            rates, _, _ = cell_rates(subset_table(none_table, np.flatnonzero(side)))
            mine = sp.rates(side)
            if not np.array_equal(np.isnan(mine), np.isnan(rates)):
                worst = float("inf")
            else:
                worst = max(worst, float(np.nanmax(np.abs(mine - rates))))
        counts = np.bincount(sp.cell[half], minlength=sp.sizes.size)
        sizes_ok = bool(np.all((counts == sp.sizes // 2) | (counts == sp.sizes - sp.sizes // 2)))
        out.append({"replicate": k, "cells": int(sp.sizes.size), "max_abs_rate_diff": worst,
                    "same_rows": same_rows, "half_sizes_ok": sizes_ok,
                    "ok": worst == 0.0 and sizes_ok and same_rows})
    return out


def check_cancellation():
    _, t, cube, cands, fr, tm, delta = _delta("calibration_informed|target")
    shifted = cube.copy()
    shifted[2] += 0.03                       # candidate 2 shifted equally in every framing
    shifted[:, fr.index("committed_supporter")] += 0.05  # every candidate, one framing
    d = gap(shifted, "mean")
    delta2 = d[:, fr.index("committed_supporter")] - d[:, fr.index("none")]
    diff = float(np.nanmax(np.abs(delta2 - delta)))
    return {"max_abs_diff": diff, "ok": bool(diff < 1e-12)}


def check_planted():
    _, t, cube, cands, fr, tm, _ = _delta("calibration_informed|base")
    planted = cube.copy()
    j = list(t.axes).index("g001_outright_refusal")
    planted[0, fr.index("committed_supporter"), :, j] = np.clip(
        planted[0, fr.index("committed_supporter"), :, j] + 0.5, 0, 1)
    d = gap(planted, "mean")
    res = paired_flip_test(d[:, fr.index("committed_supporter")] - d[:, fr.index("none")],
                           cands, list(t.axes), n=2000)
    return {"planted": cands[0], "axis": "g001_outright_refusal", "p": res["p_family_wise"],
            "argmax": res["argmax_candidate"], "argmax_axis": res["argmax_axis"],
            "ok": bool(res["reject"] and res["argmax_candidate"] == cands[0])}


def check_holm():
    got = holm({"a": 0.01, "b": 0.04, "c": 0.03})
    want = {"a": 0.03, "c": 0.06, "b": 0.06}
    return {"got": got, "want": want, "ok": bool(all(abs(got[k] - want[k]) < 1e-12 for k in want))}


def main() -> None:
    record = {"flip_engine": check_flip_engine(), "welch_engine": check_welch(),
              "cube_against_one_framing_table": check_cube(), "split_half": check_split(),
              "cancellation": check_cancellation(), "planted_effect": check_planted(),
              "holm": check_holm()}
    flat = [x for v in record.values() for x in (v if isinstance(v, list) else [v])]
    record["all_ok"] = all(x["ok"] for x in flat)
    (OUT / "checks").mkdir(parents=True, exist_ok=True)
    path = OUT / "checks" / "engine_checks.json"
    with path.open("x") as fh:
        json.dump(record, fh, indent=1, default=float)
    print(json.dumps(record, indent=1, default=float))
    sys.exit(0 if record["all_ok"] else 1)


if __name__ == "__main__":
    main()
