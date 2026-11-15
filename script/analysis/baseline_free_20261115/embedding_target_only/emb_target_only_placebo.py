"""Split-half placebos of the target-only embedding test, per subject and mask.

    uv run python <this file> selfcheck
    uv run python <this file> run --subjects all --workers 8

Each split cuts every candidate-and-instruction cell of one subject's replies at
random into two halves, with the stored rule (``split_halves`` of the 2026-11-14
calibration: the larger half to either side by a coin flip). A cell of 16 replies
becomes two cells of 8, and a cell of 4 two cells of 2. Per split and per variant:

(i) Machinery check. The test runs on half-minus-half cells. The halves come from
    one model, so no candidate differs from another in them and p should be uniform:
    the share of splits at p <= 0.01 should sit near 0.01. Grubbs's p and the
    pre-registered deleted residual are recorded too, so their size is measured on
    the same splits.
(ii) Stability. The target-only test runs on each half alone. The share of splits
    whose two halves name the same candidate says whether the named candidate is a
    stable property of the model's replies; chance is 1/k.

The permutation null is the vectorized within-instruction shuffle of
``emb_target_only_stats`` (2,000 permutations per test), checked by ``selfcheck``
against the stored ``_gap_scores``. Seeds derive from 20261114, the subject id and
the mask. Writes ``placebo/placebo_<subject>_<mask>.json`` and refuses to overwrite.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from scipy import stats

from emb_calib_analyze_copy import split_halves
from emb_target_only_sources import (N_PERM, OUT, PLACEBO_DIR, PLACEBO_SEED, PLACEBO_SPLITS,
                                     PREREGISTERED, VARIANTS, all_subjects, available,
                                     family_settings, load_arm, masks_of)
from emb_target_only_stats import (BlockPermutation, FastPermutation, cell_table,
                                   deleted_residual, exact_test, fast_test, g_from_d,
                                   detachment_mean_sd, grubbs_g, grubbs_null, grubbs_p,
                                   reduce, transform)
from script.analysis.baseline_free_20261115.common.settings import save_new_json
from src.geometry.embedding_group_test import _gap_scores

MASK_INDEX = {"unmasked": 0, "masked": 1, "masked_noparty": 2}


def _seed(sid: str, mask: str) -> np.random.SeedSequence:
    sid_int = int(hashlib.sha256(sid.encode()).hexdigest()[:8], 16)
    return np.random.SeedSequence([PLACEBO_SEED, sid_int, MASK_INDEX[mask]])


def _half_means(e, halves, which):
    idx = np.concatenate([h[which] for h in halves])
    lens = np.array([len(h[which]) for h in halves])
    starts = np.concatenate([[0], np.cumsum(lens)[:-1]])
    sums = np.add.reduceat(e[idx].astype(np.float64), starts, axis=0)
    return (sums / lens[:, None]).astype(np.float32)


def _one(red, principals, instructions, rng, prereg):
    r = fast_test(red, principals, instructions, rng, N_PERM)
    x, null = np.asarray(r["scores"], dtype=np.float64), r["null"]
    out = {"p": r["p"], "statistic": round(r["statistic"], 5), "named": r["named"],
           "ratio": round(r["ratio_to_null_p95"], 4)}
    k = x.size
    if k >= 3:
        g = grubbs_g(x)
        sd = null.std(axis=1, ddof=1)
        null_g = (null.max(axis=1) - null.mean(axis=1)) / np.where(sd > 0, sd, np.inf)
        out["G"] = round(g, 5)
        out["grubbs_p_mc"] = grubbs_p(g, k)["p_mc"]
        out["grubbs_p_shuffle"] = float((1 + np.sum(null_g >= g)) / (null.shape[0] + 1))
    if prereg is not None and k >= 3 and prereg in r["cand"]:
        out["prereg_dr_p"] = deleted_residual(x, r["cand"].index(prereg))["p_one_sided"]
    return out


def _cp(k, n):
    lo = 0.0 if k == 0 else float(stats.beta.ppf(0.025, k, n - k + 1))
    hi = 1.0 if k == n else float(stats.beta.ppf(0.975, k + 1, n - k))
    return [round(lo, 4), round(hi, 4)]


def _share(vals, level):
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    n, k = len(vals), int(sum(v <= level + 1e-12 for v in vals))
    return {"share": k / n, "count": k, "n": n, "ci95": _cp(k, n)}


def summarize(reps, variant, full_named, k, prereg) -> dict:
    mac = [r[variant]["machinery"] for r in reps]
    ha = [r[variant]["half_a"] for r in reps]
    hb = [r[variant]["half_b"] for r in reps]
    ps = np.array([m["p"] for m in mac])
    out = {"machinery": {
        "splits": len(mac),
        "p_le_0.01": _share(ps, 0.01), "p_le_0.05": _share(ps, 0.05),
        "ks_p_uniform": float(stats.kstest(ps, "uniform").pvalue),
        "median_p": float(np.median(ps)),
        "grubbs_p_mc_le_0.01": _share([m.get("grubbs_p_mc") for m in mac], 0.01),
        "grubbs_p_mc_le_0.05": _share([m.get("grubbs_p_mc") for m in mac], 0.05),
        "grubbs_p_shuffle_le_0.01": _share([m.get("grubbs_p_shuffle") for m in mac], 0.01),
        "prereg_dr_p_le_0.01": _share([m.get("prereg_dr_p") for m in mac], 0.01),
        "prereg_dr_p_le_0.05": _share([m.get("prereg_dr_p") for m in mac], 0.05)}}
    same = [a["named"] == b["named"] for a, b in zip(ha, hb)]
    full = [h["named"] == full_named for h in ha + hb]
    out["stability"] = {
        "splits": len(ha), "chance_same_candidate": 1 / k, "full_data_named": full_named,
        "share_halves_name_same_candidate": float(np.mean(same)),
        "share_halves_name_full_data_candidate": float(np.mean(full)),
        "share_both_halves_name_full_data_candidate": float(np.mean(
            [a["named"] == full_named and b["named"] == full_named for a, b in zip(ha, hb)])),
        "half_p_le_0.01": _share([h["p"] for h in ha + hb], 0.01),
        "share_both_halves_p_le_0.01": float(np.mean([a["p"] <= 0.01 and b["p"] <= 0.01
                                                      for a, b in zip(ha, hb)])),
        "half_grubbs_p_mc_le_0.01": _share([h.get("grubbs_p_mc") for h in ha + hb], 0.01),
        "half_prereg_dr_p_le_0.01": _share([h.get("prereg_dr_p") for h in ha + hb], 0.01)}
    if prereg is not None:
        out["stability"]["share_both_halves_name_preregistered"] = float(np.mean(
            [a["named"] == prereg and b["named"] == prereg for a, b in zip(ha, hb)]))
    return out


def job(args) -> str:
    sid, mask, splits = args
    path = PLACEBO_DIR / f"placebo_{sid}_{mask}.json"
    if path.exists():
        return f"{sid} {mask}: exists"
    t0 = time.time()
    keys, p, i, e = load_arm(sid, mask)
    prereg = PREREGISTERED.get(sid)
    split_ss, perm_ss = _seed(sid, mask).spawn(2)
    rng_split, rng_perm = np.random.default_rng(split_ss), np.random.default_rng(perm_ss)
    cells_full, means_full = cell_table(p, i, e)
    cand = sorted(set(p))
    lab_full = np.array([c[0] for c in cells_full])
    full_named = {v: cand[int(np.argmax(_gap_scores(reduce(transform(cells_full, means_full, v)),
                                                  lab_full, cand)))] for v in VARIANTS}
    reps = []
    for rep in range(splits):
        cells, halves = split_halves(p, i, rng_split)
        cp, ci = [c[0] for c in cells], [c[1] for c in cells]
        ha, hb = _half_means(e, halves, 0), _half_means(e, halves, 1)
        rec = {}
        for v in VARIANTS:
            rec[v] = {"machinery": _one(reduce(transform(cells, ha - hb, v)), cp, ci, rng_perm, prereg),
                      "half_a": _one(reduce(transform(cells, ha, v)), cp, ci, rng_perm, prereg),
                      "half_b": _one(reduce(transform(cells, hb, v)), cp, ci, rng_perm, prereg)}
        reps.append(rec)
    out = {"subject": sid, "mask": mask, "splits": splits, "n_rows": len(keys),
           "n_cells": len(cells_full), "k": len(cand), "preregistered_candidate": prereg,
           "seed": {"entropy": [PLACEBO_SEED, int(hashlib.sha256(sid.encode()).hexdigest()[:8], 16),
                                MASK_INDEX[mask]], "spawn": "split, permutation"},
           "half_sizes": sorted({len(h[0]) for h in halves} | {len(h[1]) for h in halves}),
           "summary": {v: summarize(reps, v, full_named[v], len(cand), prereg) for v in VARIANTS},
           "replicates": reps, "seconds": round(time.time() - t0, 1),
           "settings": family_settings(permutation_stream="vectorized within-instruction shuffle")}
    save_new_json(path, out)
    s = out["summary"]
    return (f"{sid} {mask}: " + "; ".join(
        f"{v} mach p<=.01 {s[v]['machinery']['p_le_0.01']['share']:.3f} "
        f"stab same {s[v]['stability']['share_halves_name_same_candidate']:.2f}" for v in VARIANTS)
        + f" ({out['seconds']} s)")


# --------------------------------------------------------------- selfcheck
def stage_selfcheck(args):
    """The vectorized shuffles against the stored statistic, and the Grubbs identities."""
    report = {"gap_scores": {}, "null_vs_exact": {}, "grubbs": {}}
    rng = np.random.default_rng(0)
    for sid in ("auditbench_flattery", "calibration_blind_organization",
                "auditbench_third_party_politics", "calibration_blind_person"):
        keys, p, i, e = load_arm(sid, "masked")
        cells, means = cell_table(p, i, e)
        cp, ci = [c[0] for c in cells], [c[1] for c in cells]
        for v in VARIANTS:
            red = reduce(transform(cells, means, v))
            bp = BlockPermutation(cp, ci)
            perm = np.argsort(rng.random((50, bp.b, bp.k)), axis=2)
            got = bp.scores_for_perm(red, perm)
            labels = bp.labels_of(perm)
            want = np.stack([_gap_scores(red, np.asarray(bp.cand)[lab], bp.cand) for lab in labels])
            fp = FastPermutation(cp, ci)
            lab2 = fp.permutations(rng, 50)
            got2 = fp.scores_for(red, lab2)
            want2 = np.stack([_gap_scores(red, np.asarray(fp.cand)[lab], fp.cand) for lab in lab2])
            ident = np.stack([_gap_scores(red, np.asarray(cp), bp.cand)])
            got_id = bp.scores_for_perm(red, np.tile(np.arange(bp.k), (1, bp.b, 1)))
            rel = float(np.max(np.abs(got - want) / np.maximum(np.abs(want), 1e-12)))
            rel2 = float(np.max(np.abs(got2 - want2) / np.maximum(np.abs(want2), 1e-12)))
            rel_id = float(np.max(np.abs(got_id - ident) / np.abs(ident)))
            report["gap_scores"][f"{sid}:{v}"] = {"block_max_rel_err": rel,
                                                  "general_max_rel_err": rel2,
                                                  "identity_max_rel_err": rel_id}
            ex = exact_test(red, cp, ci)
            fa = fast_test(red, cp, ci, np.random.default_rng(1))
            q = [0.5, 0.95, 0.99]
            report["null_vs_exact"][f"{sid}:{v}"] = {
                "exact_null_max_quantiles": np.quantile(ex["null"].max(1), q).tolist(),
                "fast_null_max_quantiles": np.quantile(fa["null"].max(1), q).tolist(),
                "exact_p": ex["test"]["p"], "fast_p": fa["p"],
                "statistic_equal": ex["test"]["statistic"] == round(fa["statistic"], 4)}
            if max(rel, rel2, rel_id) > 1e-5:
                sys.exit(f"selfcheck: vectorized scores differ from _gap_scores ({sid} {v})")
    for k, crit in ((5, 1.671), (7, 1.939), (11, 2.232)):
        null = grubbs_null(k)
        x = np.random.default_rng(k).standard_normal((2000, k))
        d = np.array([detachment_mean_sd(r) for r in x])
        g = np.array([grubbs_g(r) for r in x])
        err = float(np.max(np.abs(np.array([g_from_d(a, k) for a in d]) - g)))
        report["grubbs"][str(k)] = {"mc_one_sided_5pct_critical": float(np.quantile(null, 0.95)),
                                    "research_notes_critical": crit,
                                    "G_from_D_max_abs_err": err,
                                    "bonferroni_p_at_mc_critical": grubbs_p(float(np.quantile(null, 0.95)), k)["p_bonferroni_t"]}
        if err > 1e-9 or abs(np.quantile(null, 0.95) - crit) > 0.005:
            sys.exit(f"selfcheck: Grubbs identity or critical value fails at k={k}")
    report["passed"] = True
    save_new_json(OUT / "selfcheck.json", report)
    print("selfcheck passed")


def stage_run(args):
    if not (OUT / "selfcheck.json").exists():
        sys.exit("run selfcheck first")
    subs = all_subjects() if args.subjects == ["all"] else args.subjects
    jobs = [(s, m, args.splits) for s in subs for m in masks_of(s) if available(s, m)
            and not (PLACEBO_DIR / f"placebo_{s}_{m}.json").exists()]
    # the large designs (144 or 140 instructions) first, so the long jobs do not trail
    big = ("calibration_", "challenge_", "base_1p5b__", "base_7b__")
    jobs.sort(key=lambda j: not any(b in j[0] for b in big))
    PLACEBO_DIR.mkdir(parents=True, exist_ok=True)
    print(len(jobs), "jobs", flush=True)
    with ProcessPoolExecutor(args.workers) as ex:
        for line in ex.map(job, jobs):
            print(line, flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("stage", choices=["selfcheck", "run"])
    ap.add_argument("--subjects", nargs="+", default=["all"])
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--splits", type=int, default=PLACEBO_SPLITS)
    args = ap.parse_args()
    globals()[f"stage_{args.stage}"](args)


if __name__ == "__main__":
    main()
