"""The "look at the losers" statistic on the paper's runs (B44), exploratory.

    .venv/bin/python -m script.analysis.losers_statistic run
    .venv/bin/python -m script.analysis.losers_statistic placebo --replicates 200 --permutations 2000
    .venv/bin/python -m script.analysis.losers_statistic summarize

``run`` computes the dispersion statistic of
``src/compare/loser_dispersion_statistic.py`` on every run of the placebo run
list (Tables 2 and 3, plus the informed helper swap of Table 12), at each run's
registered level, with the registered permutation count and seed. It recomputes
the registered statistic on the same permutations and refuses to write unless
S and p match the stored summary exactly.

``placebo`` reuses the B42 placebo splits: the same run positions and
``SeedSequence`` seeds, so replicate r here splits the cells exactly as B42's
replicate r did. Each replicate also recomputes the registered p on the same
split and permutations, and ``summarize`` checks it against B42's stored
``replicates.jsonl`` value.

Nothing here calls an API or a GPU. It writes only under
``out/main/calibration/losers_statistic/``.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from scipy import stats

from script.analysis.placebo_calibration import (ALPHA, CONTROLS, OUT as PLACEBO_OUT,
                                                 RUNS, _seeds, _sha, _stored, _tables)
from src.common.file_io import load_json, read_jsonl, save_json
from src.compare.loser_dispersion_statistic import (ZERO_SPREAD_MODES,
                                                    loser_dispersion_test,
                                                    loser_dispersion_test_tables)
from src.compare.paired_excess_measures import cell_rates
from src.compare.placebo_calibration import (calibration_summary, cell_sizes,
                                             split_cell_indices, subset_table)

OUT = Path("out/main/calibration/losers_statistic")
POSITIVES = ("calibration_blind_person", "calibration_blind_organization",
             "calibration_scoped", "calibration_informed",
             "auditbench_contextual_optimism", "auditbench_third_party_politics",
             "auditbench_secret_loyalty", "court_groups_given",
             "court_objective_disclosed")
NULLS = tuple(f"auditbench_{c}" for c in CONTROLS)


def run_all() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows, failures = {}, 0
    for spec in RUNS:
        level, stored = _stored(spec)
        target, base, _ = _tables(spec)
        t0 = time.perf_counter()
        got = loser_dispersion_test_tables(target, base,
                                           n_permutations=stored["n_permutations"],
                                           alpha=stored["alpha"])
        seconds = time.perf_counter() - t0
        same = (got["registered_S_recomputed"] == stored["statistic"]
                and got["registered_p_recomputed"] == stored["p_family_wise"])
        failures += not same
        att = stored.get("attribution") or {}
        rows[spec.key] = {
            "table": spec.table, "level": level, "seconds": seconds,
            "sha256_target": _sha(spec.verdicts_target),
            "sha256_base": _sha(spec.verdicts_base),
            "registered": {"S": stored["statistic"], "p": stored["p_family_wise"],
                           "loyal": stored["loyal"], "named": att.get("named"),
                           "plurality": att.get("plurality"),
                           "argmax": att.get("argmax"),
                           "reproduced_exactly": same},
            **got}
        line = " ".join(
            f"{mode}: Z={got[mode]['Z']} p={got[mode]['p']} named={got[mode]['named']}"
            for mode in ZERO_SPREAD_MODES)
        print(f"{spec.key:34s} N={got['n_candidates']} reg S {stored['statistic']:.3f} "
              f"p {stored['p_family_wise']:.4f} {'MATCH' if same else 'MISMATCH'} | "
              f"{line} | {seconds:.0f}s", flush=True)
    if failures:
        print(f"{failures} runs did not reproduce the registered test; nothing written")
        return failures
    save_json(OUT / "results.json", {"alpha": ALPHA, "runs": rows})
    print(f"wrote {OUT / 'results.json'}")
    return 0


_WORKER_TABLES: dict = {}


def _init_worker(tables: dict) -> None:
    _WORKER_TABLES.update(tables)
    os.environ.setdefault("OMP_NUM_THREADS", "1")


def placebo_replicate(table, split_seed: int, perm_seed: int, n_permutations: int) -> dict:
    """One B42 split, both zero-spread modes and the registered p on one null."""
    a, b = split_cell_indices(table, np.random.default_rng(split_seed))
    ta, tb = subset_table(table, a), subset_table(table, b)
    p_t, principals, _ = cell_rates(ta)
    p_b, _, _ = cell_rates(tb)
    got = loser_dispersion_test(p_t, p_b, principals, list(table.axes),
                                n_permutations=n_permutations, seed=perm_seed,
                                alpha=ALPHA, details=False)
    return {"registered_p": got["registered_p_recomputed"],
            **{f"p_{mode}": got[mode]["p"] for mode in ZERO_SPREAD_MODES},
            **{f"p_signed_{mode}": got[mode]["p_signed"] for mode in ZERO_SPREAD_MODES}}


def _task(key, model, replicate, split_seed, perm_seed, n_permutations) -> dict:
    t0 = time.perf_counter()
    out = placebo_replicate(_WORKER_TABLES[(key, model)], split_seed, perm_seed,
                            n_permutations)
    return {"key": key, "model": model, "replicate": replicate,
            "split_seed": split_seed, "permutation_seed": perm_seed,
            "n_permutations": n_permutations,
            "seconds": time.perf_counter() - t0, **out}


def placebo(replicates: int, n_permutations: int, workers: int) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    log = OUT / "placebo_replicates.jsonl"
    done = ({(r["key"], r["model"], r["replicate"]) for r in read_jsonl(log)}
            if log.exists() else set())
    tables, todo, skipped = {}, [], {}
    for i, spec in enumerate(RUNS):
        target, base, _ = _tables(spec)
        if len(target.principals) < 3:
            skipped[spec.key] = "two candidates: the statistic is not computable"
            continue
        for j, (model, table) in enumerate((("base", base), ("target", target))):
            if cell_sizes(table).min() < 2:
                skipped[f"{spec.key}/{model}"] = "a cell holds fewer than two samples"
                continue
            tables[(spec.key, model)] = table
            for r in range(replicates):
                if (spec.key, model, r) not in done:
                    todo.append((spec.key, model, r, *_seeds(i, j, r), n_permutations))
    save_json(OUT / "placebo_design.json",
              {"replicates": replicates, "n_permutations": n_permutations,
               "alpha": ALPHA, "seeds": "B42: SeedSequence([20261028, run_index, "
               "model_index, replicate]), run_index = position in RUNS",
               "skipped": skipped})
    print(f"{len(todo)} replicates to run on {workers} workers ({len(done)} done); "
          f"skipped {skipped}", flush=True)
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker,
                             initargs=(tables,)) as pool, log.open("a") as fh:
        futures = [pool.submit(_task, *t) for t in todo]
        for n, fut in enumerate(as_completed(futures), 1):
            fh.write(json.dumps(fut.result()) + "\n")
            fh.flush()
            if n % 100 == 0 or n == len(futures):
                print(f"{n}/{len(futures)} done, {time.time() - t0:.0f}s elapsed",
                      flush=True)


def _rank_against_nulls(p: float | None, null_ps: list[float]) -> int | None:
    """How many null controls have a p at or below this run's p."""
    if p is None:
        return None
    return int(sum(q <= p for q in null_ps))


def summarize() -> None:
    results = load_json(OUT / "results.json")["runs"]
    out: dict = {"alpha": ALPHA, "comparison": {}, "nulls": {}, "placebo": {}}

    # Real runs, side by side.
    for key, r in results.items():
        row = {"table": r["table"], "n_candidates": r["n_candidates"],
               "roster_flag": r["roster_flag"], "registered": r["registered"]}
        for mode in ZERO_SPREAD_MODES:
            v = r[mode]
            row[mode] = {k: v.get(k) for k in ("computable", "Z", "p", "Z_signed",
                                               "p_signed", "loyal", "named",
                                               "top_pair", "n_pairs_rejected",
                                               "n_infinite_observed",
                                               "share_null_max_infinite",
                                               "n_pairs_scored")}
            att = v.get("attribution") or {}
            row[mode]["plurality"] = att.get("plurality")
            row[mode]["histogram"] = att.get("histogram")
        out["comparison"][key] = row

    def null_block(getter) -> dict:
        ps = [getter(results[k]) for k in NULLS]
        ps_ok = [p for p in ps if p is not None]
        block = {"p": dict(zip(NULLS, ps)),
                 "n_reject_01": int(sum(p <= 0.01 for p in ps_ok)),
                 "n_reject_05": int(sum(p <= 0.05 for p in ps_ok)),
                 "min_p": min(ps_ok) if ps_ok else None,
                 "median_p": float(np.median(ps_ok)) if ps_ok else None}
        if len(ps_ok) >= 2:
            ks = stats.kstest(ps_ok, "uniform")
            block["ks_statistic"], block["ks_p"] = float(ks.statistic), float(ks.pvalue)
        block["positives_rank"] = {
            k: {"p": getter(results[k]),
                "nulls_at_or_below": _rank_against_nulls(getter(results[k]), ps_ok)}
            for k in POSITIVES}
        return block

    out["nulls"]["registered"] = null_block(lambda r: r["registered"]["p"])
    for mode in ZERO_SPREAD_MODES:
        out["nulls"][mode] = null_block(lambda r, m=mode: r[m]["p"])
        out["nulls"][f"{mode}_signed"] = null_block(lambda r, m=mode: r[m]["p_signed"])

    # Placebo.
    reps = list(read_jsonl(OUT / "placebo_replicates.jsonl"))
    b42 = {(r["key"], r["model"], r["replicate"]): r["p"]
           for r in read_jsonl(PLACEBO_OUT / "replicates.jsonl")}
    mismatches = [(r["key"], r["model"], r["replicate"]) for r in reps
                  if b42.get((r["key"], r["model"], r["replicate"])) != r["registered_p"]]
    by: dict = {}
    for r in reps:
        by.setdefault((r["key"], r["model"]), []).append(r)
    for (key, model), rs in by.items():
        seen = [r["replicate"] for r in rs]
        if len(set(seen)) != len(seen):
            raise ValueError(f"duplicate replicates for {key}/{model}")
    columns = ["registered_p"] + [f"p_{m}" for m in ZERO_SPREAD_MODES] + \
              [f"p_signed_{m}" for m in ZERO_SPREAD_MODES]
    per_run: dict = {}
    for spec in RUNS:
        entry = {}
        for model in ("base", "target"):
            rs = by.get((spec.key, model))
            if not rs:
                continue
            entry[model] = {c: calibration_summary([r[c] for r in rs]) for c in columns}
        if entry:
            per_run[spec.key] = entry
    pooled = {c: calibration_summary([r[c] for r in reps]) for c in columns}
    pooled_nulls = {c: calibration_summary([r[c] for r in reps if r["key"] in NULLS])
                    for c in columns}
    out["placebo"] = {
        "n_replicates": len(reps),
        "registered_p_matches_B42": len(reps) - len(mismatches),
        "registered_p_mismatches": mismatches[:20],
        "pooled": pooled, "pooled_null_controls": pooled_nulls, "per_run": per_run,
        "total_seconds_cpu": float(sum(r["seconds"] for r in reps)),
    }
    save_json(OUT / "summary.json", out)
    (OUT / "comparison.md").write_text(_markdown(out))
    print(f"wrote {OUT / 'summary.json'} and {OUT / 'comparison.md'}")


def _fmt_p(p) -> str:
    if p is None:
        return "n/a"
    return "<0.0001" if p <= 1.0001e-4 else f"{p:.4f}"


def _fmt_z(z) -> str:
    return "n/a" if z is None else ("inf" if np.isinf(z) else f"{z:.2f}")


def _markdown(out: dict) -> str:
    lines = ["# Look-at-the-losers statistic beside the registered test (B44, exploratory)",
             "", "alpha 0.01. `inf`: literal statistic, zero spread is a signed "
             "infinity (registered convention). `excl`: zero-spread pairs not scored.",
             "",
             "| Run | Table | N | S | p (reg) | named (reg) | Z inf | p inf | named inf "
             "| Z excl | p excl | top pair excl (z) | named excl | p+ excl |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for key, r in out["comparison"].items():
        reg, a, b = r["registered"], r["infinite"], r["exclude"]
        tp = b.get("top_pair") or {}
        top = (f"{tp.get('candidate')}, {tp.get('axis_id')} ({_fmt_z(tp.get('z'))})"
               if tp else "n/a")
        def name(v):
            if not v.get("computable"):
                return "n/a"
            if not v.get("loyal"):
                return ""
            return v.get("named") or f"none (plurality {v.get('plurality')})"
        reg_name = (reg["named"] or (f"none (plurality {reg['plurality']})"
                                     if reg["loyal"] else ""))
        flag = " (3, unstable)" if r["n_candidates"] == 3 else ""
        lines.append(
            f"| {key} | {r['table']} | {r['n_candidates']}{flag} | {reg['S']:.2f} | "
            f"{_fmt_p(reg['p'])}{'*' if reg['loyal'] else ''} | {reg_name} | "
            f"{_fmt_z(a.get('Z'))} | {_fmt_p(a.get('p'))}{'*' if a.get('loyal') else ''} | "
            f"{name(a)} | {_fmt_z(b.get('Z'))} | "
            f"{_fmt_p(b.get('p'))}{'*' if b.get('loyal') else ''} | {top} | {name(b)} | "
            f"{_fmt_p(b.get('p_signed'))} |")
    lines += ["", "## Null controls", "",
              "| Statistic | reject at 0.01 | reject at 0.05 | min p | median p | KS p |",
              "|---|---|---|---|---|---|"]
    for k, v in out["nulls"].items():
        lines.append(f"| {k} | {v['n_reject_01']}/8 | {v['n_reject_05']}/8 | "
                     f"{_fmt_p(v['min_p'])} | {_fmt_p(v['median_p'])} | "
                     f"{v.get('ks_p', float('nan')):.3f} |")
    lines += ["", "Nulls with p at or below each positive's p:", "",
              "| Run | " + " | ".join(out["nulls"]) + " |",
              "|---|" + "---|" * len(out["nulls"])]
    for key in POSITIVES:
        cells = []
        for v in out["nulls"].values():
            pr = v["positives_rank"][key]
            cells.append("n/a" if pr["nulls_at_or_below"] is None
                         else f"{pr['nulls_at_or_below']} (p {_fmt_p(pr['p'])})")
        lines.append(f"| {key} | " + " | ".join(cells) + " |")
    pl = out["placebo"]
    lines += ["", "## Placebo (within-model half splits, B42 seeds)", "",
              f"{pl['n_replicates']} replicates; registered p equal to B42's on "
              f"{pl['registered_p_matches_B42']}.", "",
              "| Statistic | pool | n | share <= 0.05 | share <= 0.01 | KS p |",
              "|---|---|---|---|---|---|"]
    for pool_name in ("pooled", "pooled_null_controls"):
        for c, v in pl[pool_name].items():
            lines.append(f"| {c} | {pool_name} | {v['n']} | {v['share_le_05']:.3f} | "
                         f"{v['share_le_01']:.3f} | {v['ks_p']:.3g} |")
    lines += ["", "Per-run KS p against uniform (base / target):", "",
              "| Run | " + " | ".join(next(iter(pl["per_run"].values()))["base"]) + " |",
              "|---|" + "---|" * len(next(iter(pl["per_run"].values()))["base"])]
    for key, e in pl["per_run"].items():
        cells = [f"{e['base'][c]['ks_p']:.3g} / {e['target'][c]['ks_p']:.3g}"
                 for c in e["base"]]
        lines.append(f"| {key} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run")
    p = sub.add_parser("placebo")
    p.add_argument("--replicates", type=int, default=200)
    p.add_argument("--permutations", type=int, default=2000)
    p.add_argument("--workers", type=int, default=12)
    sub.add_parser("summarize")
    args = ap.parse_args()
    if args.cmd == "run":
        raise SystemExit(1 if run_all() else 0)
    if args.cmd == "placebo":
        placebo(args.replicates, args.permutations, args.workers)
    else:
        summarize()


if __name__ == "__main__":
    main()
