"""The coherence fold of the registered excess on every run (B72 rerun).

    .venv/bin/python -m script.analysis.baseline_free_20261115.pooled_coherence.run_fold --workers 6

A copy of ``script/analysis/compute_paired_coherence_verdicts.py`` with its outputs
redirected. The original writes ``paired_coherence.json`` beside each run's stage-6
summary and is not run here. Same effect, same pairing, same null as the registered
test; only the fold over axes changes, from the single largest |t| to the top-k
coherence scan (``src/compare/paired_coherence_statistic``). The fold uses the base,
so it is a comparison for the baseline-free appendix and not a baseline-free method.

The run list is wider than the original's: every reported and held-out run, the
four court runs (no stored fold record), the two synthetic-document nulls against
base A, and the untuned bases B, C1 and C2 as targets against base A.

For every run the registered test is recomputed beside the fold, so each row
carries the registered verdict it is read against, checked against the stored
summary where one exists. Every stored ``paired_coherence.json`` is compared with
the recomputed fold. Writes ``runs/fold__<run>.json`` per run and
``paired_coherence_all.json``.
"""

from __future__ import annotations

import argparse
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict

from script.analysis.baseline_free_20261115.pooled_coherence.common import (
    ALPHA, N_PERM, OUT, REPO, SEED, SETTINGS, fold_runs, level_table, load_json,
    registered_from_store, run_level, sha256, write_json)
from src.compare.paired_coherence_statistic import paired_coherence_test
from src.compare.paired_max_statistic import paired_max_test
from src.compare.principal_attribution import attribute_principal

FOLD_FIELDS = ("statistic", "p_family_wise", "null_mean", "null_p95", "leading", "runner_up",
               "loyal", "principal", "n_instructions", "n_axes")


def _two_candidate_note(n: int) -> str | None:
    if n != 2:
        return None
    return ("two candidates: the per-axis robust z is +-0.6745 wherever the pair differs, so "
            "both candidates share one R and the fold cannot name or reject")


def _compare_fold(stored: dict, got: dict) -> dict:
    s = stored["coherence"]
    rows, ok = {}, True
    for f in FOLD_FIELDS:
        a, b = s.get(f), got.get(f)
        same = (abs(a - b) < 1e-9) if isinstance(a, float) and isinstance(b, float) else a == b
        rows[f] = {"stored": a, "got": b, "match": bool(same)}
        ok &= bool(same)
    for f in ("R", "k_chosen"):
        a, b = s.get(f, {}), got.get(f, {})
        same = set(a) == set(b) and all(abs(float(a[c]) - float(b[c])) < 1e-9 for c in a)
        rows[f] = {"match": bool(same)}
        ok &= bool(same)
    stored_alpha = s.get("alpha")
    return {"all_match": bool(ok), "stored_alpha": stored_alpha, "fields": rows,
            "stored_seed": stored.get("seed"), "stored_n_permutations": s.get("n_permutations")}


def one_run(run_dict: dict, n_permutations: int, seed: int, alpha: float) -> dict:
    from script.analysis.baseline_free_20261115.pooled_coherence.common import FoldRun
    run = FoldRun(**run_dict)
    t0 = time.perf_counter()
    level = run_level(run)
    target = level_table(run.target, run.axes, level)
    base = level_table(run.base, run.axes, level)

    reg = paired_max_test(target, base, n_permutations=n_permutations, seed=seed, alpha=alpha)
    att = attribute_principal(reg)
    registered = {
        "statistic": reg["statistic"], "p_family_wise": reg["p_family_wise"],
        "null_p95": reg["null_p95"], "loyal": reg["loyal"], "principal": reg["principal"],
        "named": att["named"] if att.get("resolved") else None,
        "n_axes_rejected": reg["n_axes_rejected"], "argmax_candidate":
            reg["top_pairs"][0]["candidate"] if reg["top_pairs"] else None}
    stored_reg = registered_from_store(run)
    reg_check = None
    if stored_reg and stored_reg.get("statistic") is not None:
        reg_check = {
            "stored_statistic": stored_reg["statistic"], "got_statistic": reg["statistic"],
            "stored_p": stored_reg["p_family_wise"], "got_p": reg["p_family_wise"],
            "stored_named": stored_reg.get("named"), "got_named": registered["named"],
            "stored_n_permutations": stored_reg.get("n_permutations"),
            "source": stored_reg["source"],
            "match": bool(abs(stored_reg["statistic"] - reg["statistic"]) < 1e-9
                          and stored_reg["p_family_wise"] == reg["p_family_wise"]
                          and (run.summary is None
                               or stored_reg.get("named") == registered["named"]))}

    fold = paired_coherence_test(target, base, n_permutations=n_permutations, seed=seed,
                                 alpha=alpha)
    fold_check = None
    if run.stored_fold:
        stored = load_json(REPO / run.stored_fold)
        fold_check = {"source": run.stored_fold, **_compare_fold(stored, fold)}
        fold_check["stored_registered"] = stored["registered"]

    n_c = len(fold["candidates"])
    return {
        "run": run.key, "role": run.role, "title": run.title, "level": level,
        "seed": seed, "alpha": alpha, "n_permutations": n_permutations,
        "settings": SETTINGS,
        "inputs": {**asdict(run), "sha256_target": sha256(run.target),
                   "sha256_base": sha256(run.base), "n_target_rows": target.n_responses,
                   "n_base_rows": base.n_responses},
        "registered": registered,
        "registered_reproduces_stored": reg_check,
        "coherence": fold,
        "coherence_reproduces_stored": fold_check,
        "coherence_rejects": bool(fold["p_family_wise"] <= alpha),
        "two_candidate_degenerate": _two_candidate_note(n_c),
        "seconds": time.perf_counter() - t0,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--permutations", type=int, default=N_PERM)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--alpha", type=float, default=ALPHA)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--replace", action="store_true",
                    help="move existing outputs to out/superseded before writing")
    args = ap.parse_args()
    os.environ.setdefault("OMP_NUM_THREADS", "1")

    runs = [r for r in fold_runs() if not args.only or r.key in args.only]
    results = {}
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(one_run, asdict(r), args.permutations, args.seed, args.alpha): r.key
                   for r in runs}
        for fut in as_completed(futures):
            rec = fut.result()
            results[rec["run"]] = rec
            write_json(OUT / "runs" / f"fold__{rec['run']}.json", rec, replace=args.replace)
            reg, coh = rec["registered"], rec["coherence"]
            rc = rec["registered_reproduces_stored"]
            fc = rec["coherence_reproduces_stored"]
            print(f"{rec['run']:40s} L{rec['level']} reg S={reg['statistic']:.3f} "
                  f"p={reg['p_family_wise']:.4f} "
                  f"[{'-' if rc is None else ('MATCH' if rc['match'] else 'MISMATCH')}] | "
                  f"R S={coh['statistic']:.3f} p={coh['p_family_wise']:.4f} "
                  f"lead={coh['leading']} "
                  f"[{'-' if fc is None else ('MATCH' if fc['all_match'] else 'MISMATCH')}] "
                  f"{rec['seconds']:.0f}s", flush=True)

    order = [r.key for r in runs]
    record = {"settings": SETTINGS, "n_runs": len(order),
              "runs": {k: results[k] for k in order}}
    if not args.only:
        write_json(OUT / "paired_coherence_all.json", record, replace=args.replace)
    bad = [k for k, v in results.items()
           if (v["registered_reproduces_stored"] and not v["registered_reproduces_stored"]["match"])
           or (v["coherence_reproduces_stored"] and not v["coherence_reproduces_stored"]["all_match"])]
    print(f"{len(results)} runs; reproduction failures: {bad or 'none'}", flush=True)


if __name__ == "__main__":
    main()
