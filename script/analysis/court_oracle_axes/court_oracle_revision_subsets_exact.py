"""Exact tests on instruction subsets for the court ceiling's revision. No model is called.

Two exploratory computations, both with test 4 (the one-sided directional
maxT over the Cupertino row) and an exact p-value over every sign pattern:

1. The registered instruction-count curve, recomputed exactly. The registered
   curve tested each subset at 2,000 draws of one seeded generator, and every
   subset reused the same draws. At k = 8 those draws hold the identity
   relabeling more often than chance, which puts a floor under every p-value.
   Here every one of the 200 registered subsets per k (read from
   ``instruction_count_curve.json``) is tested over all 2^k patterns.
2. A matched-size comparison of the pipeline's prompts with the organism's own.
   On GG and OD, 300 subsets of 20 of the 36 instructions are drawn with seed
   20261115, the same subsets for every family of one corpus. Each is tested
   exactly over 2^20 patterns, at the pipeline's 4 samples per cell. The OWN
   slices of ``large_null.json`` are the counterpart (m = 20, 4 per cell).

    uv run --no-sync python -m script.analysis.court_oracle_axes.court_oracle_revision_subsets_exact --workers 14
"""

from __future__ import annotations

import argparse
import json
import time
from multiprocessing import Pool

import numpy as np

from script.analysis.court_oracle_axes.court_oracle_analysis_core import (
    ALPHA, ANALYSIS, JUDGE_FAMILIES, JUDGES, MATCHER_FAMILIES, SIGN, arms, dump,
    load_rows)
from script.analysis.court_oracle_axes.court_oracle_count_curve import cells
from script.analysis.court_oracle_axes.court_oracle_revision_large_null import (
    REVISION, SignFlip, cupertino_d, exact_patterns, tail)

N_MATCHED = 300
MATCHED_SEED = 20261115
MATCHED_K = 20
MATCHED_FAMILIES = ["L1", "L2", "L2e", "L3", "L4", "L5"]


def exact_dir(d: np.ndarray, pol: np.ndarray) -> tuple[float, float, int]:
    eng = SignFlip(d)
    m = d.shape[0]
    s_obs = float(np.nanmax(eng.t(np.ones((1, m)))[0] * pol))
    count = 0
    n = 0
    for sg in exact_patterns(m):
        nd = np.nanmax(eng.t(sg) * pol[None, :], axis=1)
        count += tail(nd, s_obs)
        n += len(nd)
    return s_obs, count / n, n


def curve_work(job) -> dict:
    rater, lv, fl, axes, k, idx, chosen, registered = job
    keep = set(chosen)
    rows = [r for r in load_rows("OWN", fl, rater) if r["instruction_id"] in keep]
    t, b = arms(rows, axes)
    d, _, _, instructions = cupertino_d(t, b, axes)
    if len(instructions) != k:
        raise SystemExit("a subset lost an instruction")
    pol = np.array([SIGN[a] for a in axes], dtype=float)
    s, p, n = exact_dir(d, pol)
    if abs(s - registered["S_dir"]) > 1e-9:
        raise AssertionError(f"S_dir {s} differs from the registered {registered['S_dir']}")
    return {"rater": rater, "level": lv, "k": k, "subset": idx, "S_dir": s, "p_exact": p,
            "n_patterns": n, "reject_exact": bool(p <= ALPHA), "p_registered": registered["p"],
            "reject_registered": registered["reject"]}


def matched_work(job) -> dict:
    corpus, rater, fam, idx, chosen = job
    fl, axes, _ = JUDGE_FAMILIES[fam]
    keep = set(chosen)
    rows = [r for r in load_rows(corpus, fl, rater) if r["instruction_id"] in keep]
    t, b = arms(rows, axes)
    d, _, _, instructions = cupertino_d(t, b, axes)
    if len(instructions) != MATCHED_K:
        raise SystemExit("a subset lost an instruction")
    pol = np.array([SIGN[a] for a in axes], dtype=float)
    s, p, n = exact_dir(d, pol)
    return {"corpus": corpus, "rater": rater, "family": fam, "subset": idx, "S_dir": s,
            "per_question_effect": s / np.sqrt(MATCHED_K), "p_exact": p, "reject_exact": bool(p <= ALPHA)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=14)
    args = ap.parse_args()
    out_curve = REVISION / "instruction_count_curve_exact.json"
    out_matched = REVISION / "matched_size_subsets.json"
    for p in (out_curve, out_matched):
        if p.exists():
            raise SystemExit(f"{p} exists; this run never overwrites")
    reg = json.loads((ANALYSIS / "instruction_count_curve.json").read_text())
    per = {(r["rater"], r["level"], r["k"], r["subset"]): r for r in reg["per_subset"]}
    todo = []
    for rater, lv, fl, axes in cells():
        for k_str, subs in reg["subsets"].items():
            k = int(k_str)
            for i, chosen in enumerate(subs):
                todo.append((rater, lv, fl, axes, k, i, chosen, per[(rater, lv, k, i)]))
    print(f"{len(todo)} curve subsets", flush=True)
    t0 = time.time()
    with Pool(args.workers) as pool:
        curve = list(pool.imap(curve_work, todo, chunksize=8))
    print(f"curve {time.time() - t0:.0f}s", flush=True)
    summary = []
    for rater, lv, _, axes in cells():
        for k_str in reg["subsets"]:
            k = int(k_str)
            rs = [r for r in curve if r["rater"] == rater and r["level"] == lv and r["k"] == k]
            summary.append({"rater": rater, "level": lv, "n_axes": len(axes), "k": k, "n_subsets": len(rs),
                            "share_reject_exact": float(np.mean([r["reject_exact"] for r in rs])),
                            "share_reject_registered": float(np.mean([r["reject_registered"] for r in rs])),
                            "median_p_exact": float(np.median([r["p_exact"] for r in rs])),
                            "min_p_registered": float(min(r["p_registered"] for r in rs)),
                            "min_p_exact": float(min(r["p_exact"] for r in rs))})
    dump({"source_subsets": "analysis/instruction_count_curve.json", "exact": True, "alpha": ALPHA,
          "summary": summary, "per_subset": curve}, out_curve)
    print(f"wrote {out_curve}", flush=True)

    rng = np.random.default_rng(MATCHED_SEED)
    matched_jobs = []
    subsets = {}
    for corpus in ("GG", "OD"):
        instr = sorted({r["instruction_id"] for r in load_rows(corpus, "L2", JUDGES["gpt"])})
        if len(instr) != 36:
            raise SystemExit(f"{corpus} has {len(instr)} instructions")
        subsets[corpus] = [sorted(instr[i] for i in rng.choice(36, MATCHED_K, replace=False))
                           for _ in range(N_MATCHED)]
        for rater in JUDGES.values():
            for fam in MATCHED_FAMILIES:
                for i, chosen in enumerate(subsets[corpus]):
                    matched_jobs.append((corpus, rater, fam, i, chosen))
    print(f"{len(matched_jobs)} matched-size subsets", flush=True)
    t0 = time.time()
    with Pool(args.workers) as pool:
        matched = list(pool.imap(matched_work, matched_jobs, chunksize=8))
    print(f"matched {time.time() - t0:.0f}s", flush=True)
    msum = []
    for corpus in ("GG", "OD"):
        for rater in JUDGES.values():
            for fam in MATCHED_FAMILIES:
                rs = [r for r in matched if r["corpus"] == corpus and r["rater"] == rater and r["family"] == fam]
                msum.append({"corpus": corpus, "rater": rater, "family": fam, "n_subsets": len(rs),
                             "share_reject_exact": float(np.mean([r["reject_exact"] for r in rs])),
                             "median_S_dir": float(np.median([r["S_dir"] for r in rs])),
                             "mean_per_question_effect": float(np.mean([r["per_question_effect"] for r in rs])),
                             "median_p_exact": float(np.median([r["p_exact"] for r in rs]))})
    dump({"seed": MATCHED_SEED, "k": MATCHED_K, "n_subsets": N_MATCHED, "families": MATCHED_FAMILIES,
          "subsets": subsets, "summary": msum, "per_subset": matched}, out_matched)
    print(f"wrote {out_matched}", flush=True)
    for s in summary:
        print(f"curve {s['rater']:28} {s['level']:5} k={s['k']:2} exact={s['share_reject_exact']:.3f} "
              f"registered={s['share_reject_registered']:.3f} min_p_reg={s['min_p_registered']:.4f}")
    for s in msum:
        print(f"matched {s['corpus']} {s['rater']:28} {s['family']:4} share={s['share_reject_exact']:.3f} "
              f"median_S={s['median_S_dir']:.3f} effect={s['mean_per_question_effect']:.3f}")


if __name__ == "__main__":
    main()
