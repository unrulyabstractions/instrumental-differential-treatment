"""The judge-free embedding test on placebo splits and against the fresh bases.

    uv run python script/analysis/embedding_calibration_20261114/analyze.py reproduce
    uv run python script/analysis/embedding_calibration_20261114/analyze.py placebo --set A --variant masked
    uv run python script/analysis/embedding_calibration_20261114/analyze.py grid
    uv run python script/analysis/embedding_calibration_20261114/analyze.py summarize

The test is the stored one, imported: each cell's mean embedding in the target
minus the base's matching cell, PCA to 15 dimensions (seed 0), the largest
one-versus-rest gap of a candidate's mean with each dimension scaled by its
spread over cells, and 2,000 within-instruction label permutations (seed 0).

``reproduce`` re-runs the stored tests against base A from the stored vectors
and stops unless every statistic and p matches the stored files exactly.

``placebo`` splits one model's replies in every candidate-and-instruction cell at
random into two halves (the larger half to either side by a coin flip, as
``src/compare/placebo_calibration.split_cell_indices`` does for the registered
test), takes one half's cell mean minus the other's, and runs the test unchanged.
A cell of 16 samples becomes two cells of 8.

``grid`` runs each null control and contextual_optimism against bases A, B, C1
and C2 (C1 and C2 also cut to 400 tokens), names kept and masked, and each base
against each other base.

Every stage writes a new JSON file and refuses to overwrite.
"""

from __future__ import annotations

import argparse
import json
import sys
import time

import numpy as np
from scipy import stats

from common import (MODEL, N_PERM, NULLS, OUT, POSITIVE, REDUCE_DIM, RUNS, SEED,
                    VARIANTS, _digest, load_set_embeddings, save_json_new, stored_module)

sys.path.insert(0, str(OUT.parents[4]))
from src.common.experiment_layout import geometry_dir  # noqa: E402
from src.geometry.embedding_group_test import embedding_group_test  # noqa: E402
from src.geometry.geometry_alignment_stats import pca_reduce  # noqa: E402
from src.geometry.paired_response_records import cell_means  # noqa: E402

RESULTS = OUT / "results"
NEW_BASES = ("B", "C1cut", "C2cut", "C1", "C2")
PLACEBO_REPS, PLACEBO_SEED = 1000, 20261114
PLACEBO_NULL = "auditbench_flattery"


# ------------------------------------------------------------------ inputs
def _stored_arm(mr, key, arm, variant):
    """(principals, instructions, unit vectors) of a stored arm, digest-checked."""
    r = mr._records(key)[arm]
    gd = geometry_dir(key) / "embeddings"
    if variant == "unmasked":
        stem, texts = gd / f"emb_{arm}_{MODEL}", r.texts
    else:
        rows = [json.loads(x) for x in (gd / f"masked_texts_{arm}.jsonl").open()]
        if [x["key"] for x in rows] != r.keys:
            sys.exit(f"{key} {arm}: masked rows out of order")
        stem, texts = gd / f"emb_masked_{arm}_{MODEL}", [x["text"] for x in rows]
    meta = json.loads(stem.with_suffix(".json").read_text())
    if meta["digest"] != _digest(r.keys, texts) or meta["n"] != len(r.keys):
        sys.exit(f"{key} {arm} {variant}: stored embedding digest mismatch")
    return list(r.principals), list(r.instructions), np.load(stem.with_suffix(".npy")), r


def _new_arm(name, variant):
    rows, emb = load_set_embeddings(name, variant)
    return [r["principal"] for r in rows], [r["instruction_id"] for r in rows], emb


def cell_table(principals, instructions, emb):
    """Sorted cell keys and mean vectors, as ``cell_means`` folds them."""
    order: dict[tuple[str, str], list[int]] = {}
    for i, c in enumerate(zip(principals, instructions)):
        order.setdefault(c, []).append(i)
    cells = sorted(order)
    return cells, np.stack([emb[order[c]].mean(axis=0) for c in cells])


def run_test(t_cells, t_means, b_cells, b_means, n_perm=N_PERM, seed=SEED):
    bi = {c: i for i, c in enumerate(b_cells)}
    ti = {c: i for i, c in enumerate(t_cells)}
    shared = [c for c in t_cells if c in bi]
    excess = np.stack([t_means[ti[c]] - b_means[bi[c]] for c in shared])
    red = pca_reduce(excess, REDUCE_DIM, seed)
    g = embedding_group_test(red, [c[0] for c in shared], [c[1] for c in shared],
                             n_perm=n_perm, seed=seed, keep_null=True)
    null = np.asarray(g.pop("null"))
    g["null_p95_exact"] = float(np.quantile(null, 0.95))
    g["ratio_to_null_p95"] = float(g["statistic"] / g["null_p95_exact"])
    g["n_cells"] = len(shared)
    g["n_perm"] = n_perm
    return g


# --------------------------------------------------------------- reproduce
def _arms(mr):
    """Every arm the grid uses: stored targets, stored base A, the new bases."""
    arms = {}
    for v in VARIANTS:
        for key in RUNS:
            p, i, e, _ = _stored_arm(mr, key, "target", v)
            arms[(key, v)] = cell_table(p, i, e)
        p, i, e, r = _stored_arm(mr, NULLS[0], "base", v)
        arms[("A", v)] = cell_table(p, i, e)
        # The nine runs share base A's rows and texts, but each run embedded them
        # in its own calls, and the API returns slightly different vectors per
        # call (cosine 0.996 or more). Each run is tested against its own copy,
        # as the stored test was; a base pair uses the first null's copy.
        for key in RUNS:
            p2, i2, e2, _ = _stored_arm(mr, key, "base", v)
            if p != p2 or i != i2:
                sys.exit(f"{key}: base A rows differ from {NULLS[0]}")
            arms[("A", v, key)] = cell_table(p2, i2, e2)
    return arms


def stage_reproduce(args):
    mr = stored_module()
    out, bad = {}, []
    for v in VARIANTS:
        for key in RUNS:
            pt, it, et, rt = _stored_arm(mr, key, "target", v)
            pb, ib, eb, rb = _stored_arm(mr, key, "base", v)
            # Folding check: our cell means equal the stored code's cell_means.
            ct, mt = cell_table(pt, it, et)
            c_ref, m_ref, _ = cell_means(rt, et)
            if ct != c_ref or not np.array_equal(mt, m_ref):
                sys.exit(f"{key} {v}: cell means differ from cell_means")
            g = run_test(ct, mt, *cell_table(pb, ib, eb))
            if v == "unmasked":
                ref = json.loads((geometry_dir(key) / "semantic_bridge.json").read_text())["group_test"]
            else:
                ref = json.loads((geometry_dir(key) / "semantic_bridge_masked.json").read_text())["variants"]["masked"]
            same = (g["statistic"] == ref["statistic"] and g["p"] == ref["p"]
                    and g["null_p95"] == ref["null_p95"] and g["named"] == ref["named"])
            out[f"{key}:{v}"] = {"statistic": g["statistic"], "p": g["p"],
                                 "null_p95": g["null_p95"], "named": g["named"],
                                 "stored": {k: ref[k] for k in ("statistic", "p", "null_p95", "named")},
                                 "match": same}
            print(key, v, g["statistic"], ref["statistic"], g["p"], ref["p"], same, flush=True)
            if not same:
                bad.append(f"{key}:{v}")
    save_json_new(RESULTS / "reproduce_base_A.json", {"all_match": not bad, "runs": out})
    if bad:
        sys.exit(f"stored results not reproduced: {bad}")


# ----------------------------------------------------------------- placebo
def split_halves(principals, instructions, rng):
    order: dict[tuple[str, str], list[int]] = {}
    for i, c in enumerate(zip(principals, instructions)):
        order.setdefault(c, []).append(i)
    cells = sorted(order)
    halves = []
    for c in cells:
        ix = np.asarray(order[c])
        if ix.size < 2:
            sys.exit(f"cell {c} has fewer than two samples")
        shuffled = rng.permutation(ix)
        cut = ix.size // 2 if rng.random() < 0.5 else ix.size - ix.size // 2
        halves.append((shuffled[:cut], shuffled[cut:]))
    return cells, halves


def stage_placebo(args):
    mr = stored_module()
    if args.set == "A":
        p, i, e, _ = _stored_arm(mr, NULLS[0], "base", args.variant)
    elif args.set == "null":
        p, i, e, _ = _stored_arm(mr, PLACEBO_NULL, "target", args.variant)
    else:
        p, i, e = _new_arm(args.set, args.variant)
    label = PLACEBO_NULL if args.set == "null" else args.set
    path = RESULTS / f"placebo_{label}_{args.variant}.json"
    if path.exists():
        sys.exit(f"refusing to overwrite {path}")
    seed = PLACEBO_SEED + {"A": 0, "B": 1, "null": 2, "C1cut": 3, "C2cut": 4}[args.set] \
        + (100 if args.variant == "masked" else 0)
    rng = np.random.default_rng(seed)
    reps = []
    t0 = time.time()
    for rep in range(args.reps):
        cells, halves = split_halves(p, i, rng)
        excess = np.stack([e[a].mean(0) - e[b].mean(0) for a, b in halves])
        red = pca_reduce(excess, REDUCE_DIM, SEED)
        g = embedding_group_test(red, [c[0] for c in cells], [c[1] for c in cells],
                                 n_perm=N_PERM, seed=int(rng.integers(1 << 31)),
                                 keep_null=True)
        null = np.asarray(g.pop("null"))
        p95 = float(np.quantile(null, 0.95))
        reps.append({"p": g["p"], "statistic": g["statistic"], "null_p95": p95,
                     "ratio_to_null_p95": float(g["statistic"] / p95), "named": g["named"],
                     "half_sizes": sorted({int(len(a)) for a, _ in halves} | {int(len(b)) for _, b in halves})})
        if rep % 100 == 99:
            print(label, args.variant, rep + 1, round(time.time() - t0), "s", flush=True)
    save_json_new(path, {"set": label, "variant": args.variant, "reps": args.reps,
                         "n_perm": N_PERM, "seed": seed, "n_cells": len(cells),
                         "n_rows": len(p), "replicates": reps})
    print("wrote", path)


# -------------------------------------------------------------------- grid
def stage_grid(args):
    mr = stored_module()
    arms = _arms(mr)
    for v in VARIANTS:
        for name in NEW_BASES:
            arms[(name, v)] = cell_table(*_new_arm(name, v))
    bases = ("A",) + NEW_BASES
    rows = []
    for v in VARIANTS:
        for key in RUNS:
            for base in bases:
                g = run_test(*arms[(key, v)], *arms[(base, v, key) if base == "A" else (base, v)])
                rows.append({"target": key, "base": base, "variant": v, "null": key in NULLS, **g})
                print(key, base, v, g["statistic"], g["p"], round(g["ratio_to_null_p95"], 3),
                      g["named"], flush=True)
        for t, b in (("B", "A"), ("C1cut", "A"), ("C2cut", "A"), ("C1cut", "B"),
                     ("C2cut", "B"), ("C2cut", "C1cut"), ("C2", "C1")):
            g = run_test(*arms[(t, v)], *arms[(b, v)])
            rows.append({"target": t, "base": b, "variant": v, "null": None, **g})
            print("base pair", t, b, v, g["statistic"], g["p"], round(g["ratio_to_null_p95"], 3),
                  g["named"], flush=True)
        for key in RUNS:
            # B against each run's own copy of base A: the copy must not matter.
            g = run_test(*arms[("B", v)], *arms[("A", v, key)])
            rows.append({"target": "B", "base": f"A[{key}]", "variant": v, "null": None, **g})
            print("B vs A copy", key, v, g["statistic"], g["p"], flush=True)
    save_json_new(RESULTS / "grid.json", {"n_perm": N_PERM, "seed": SEED,
                                          "reduce_dim": REDUCE_DIM, "rows": rows})


# --------------------------------------------------------------- summarize
def _cp(k, n, level=0.95):
    tail = (1 - level) / 2
    lo = 0.0 if k == 0 else float(stats.beta.ppf(tail, k, n - k + 1))
    hi = 1.0 if k == n else float(stats.beta.ppf(1 - tail, k + 1, n - k))
    return [round(lo, 4), round(hi, 4)]


def stage_summarize(args):
    grid = json.loads((RESULTS / "grid.json").read_text())["rows"]
    obs = {(r["target"], r["base"], r["variant"]): r for r in grid}
    placebo = {}
    for f in sorted(RESULTS.glob("placebo_*.json")):
        d = json.loads(f.read_text())
        ps = np.array([x["p"] for x in d["replicates"]])
        st = np.array([x["statistic"] for x in d["replicates"]])
        ra = np.array([x["ratio_to_null_p95"] for x in d["replicates"]])
        n = len(ps)
        null_ratios_A = [obs[(k, "A", d["variant"])]["ratio_to_null_p95"] for k in NULLS]
        null_stats_A = [obs[(k, "A", d["variant"])]["statistic"] for k in NULLS]
        q = [0.05, 0.25, 0.5, 0.75, 0.95, 0.99]
        placebo[f"{d['set']}:{d['variant']}"] = {
            "splits": n, "n_perm": d["n_perm"], "n_cells": d["n_cells"],
            "share_p_le_0.05": float(np.mean(ps <= 0.05)), "ci_le_0.05": _cp(int(np.sum(ps <= 0.05)), n),
            "share_p_le_0.01": float(np.mean(ps <= 0.01)), "ci_le_0.01": _cp(int(np.sum(ps <= 0.01)), n),
            "share_p_lt_0.05": float(np.mean(ps < 0.05)), "share_p_lt_0.01": float(np.mean(ps < 0.01)),
            "share_at_floor": float(np.mean(ps <= 1 / (d["n_perm"] + 1) + 1e-12)),
            "ks_p_uniform": float(stats.kstest(ps, "uniform").pvalue),
            "median_p": float(np.median(ps)),
            "statistic_quantiles": dict(zip(map(str, q), np.quantile(st, q).round(4).tolist())),
            "statistic_max": float(st.max()),
            "ratio_quantiles": dict(zip(map(str, q), np.quantile(ra, q).round(4).tolist())),
            "ratio_max": float(ra.max()),
            "null_controls_vs_A_ratio_range": [min(null_ratios_A), max(null_ratios_A)],
            "null_controls_vs_A_statistic_range": [min(null_stats_A), max(null_stats_A)],
            "share_placebo_ratio_ge_smallest_null_ratio": float(np.mean(ra >= min(null_ratios_A))),
        }
    pooled = {}
    for v in VARIANTS:
        ps = np.concatenate([[x["p"] for x in json.loads(f.read_text())["replicates"]]
                             for f in sorted(RESULTS.glob(f"placebo_*_{v}.json"))])
        if ps.size:
            pooled[v] = {"splits": int(ps.size), "share_p_le_0.05": float(np.mean(ps <= 0.05)),
                         "ci_le_0.05": _cp(int(np.sum(ps <= 0.05)), ps.size),
                         "share_p_le_0.01": float(np.mean(ps <= 0.01)),
                         "ci_le_0.01": _cp(int(np.sum(ps <= 0.01)), ps.size),
                         "ks_p_uniform": float(stats.kstest(ps, "uniform").pvalue)}
    table = {}
    for r in grid:
        table.setdefault(f"{r['target']}:{r['variant']}", {})[r["base"]] = {
            "p": r["p"], "statistic": r["statistic"], "ratio": round(r["ratio_to_null_p95"], 4),
            "named": r["named"], "rejects_0.01": r["rejects"]}
    floor = 1 / (N_PERM + 1)
    nulls_reject = {f"{b}:{v}": int(sum(obs[(k, b, v)]["p"] < 0.01 for k in NULLS))
                    for v in VARIANTS for b in ("A",) + NEW_BASES}
    nulls_floor = {f"{b}:{v}": int(sum(obs[(k, b, v)]["p"] <= floor + 1e-12 for k in NULLS))
                   for v in VARIANTS for b in ("A",) + NEW_BASES}
    save_json_new(RESULTS / "summary.json", {
        "test": "judge-free embedding test, 15 PCs, 2,000 permutations, floor p = 1/2001",
        "placebo": placebo, "placebo_pooled": pooled, "tests": table,
        "nulls_rejecting_at_0.01_of_8": nulls_reject, "nulls_at_floor_of_8": nulls_floor})
    print(json.dumps({"placebo": {k: {x: v[x] for x in ("splits", "share_p_le_0.05", "share_p_le_0.01",
                                                         "ks_p_uniform", "ratio_max")}
                                  for k, v in placebo.items()},
                      "pooled": pooled, "nulls_reject": nulls_reject, "nulls_floor": nulls_floor},
                     indent=1))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("stage", choices=["reproduce", "placebo", "grid", "summarize"])
    ap.add_argument("--set", choices=["A", "B", "null", "C1cut", "C2cut"], default="A")
    ap.add_argument("--variant", choices=list(VARIANTS), default="masked")
    ap.add_argument("--reps", type=int, default=PLACEBO_REPS)
    args = ap.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)
    globals()[f"stage_{args.stage}"](args)


if __name__ == "__main__":
    main()
