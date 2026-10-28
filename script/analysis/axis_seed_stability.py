"""Axis-subset and permutation-seed stability of the registered test (B46, D).

    .venv/bin/python -m script.analysis.axis_seed_stability run --workers 10
    .venv/bin/python -m script.analysis.axis_seed_stability summarize

For each run: the registered test, unchanged, on ``N_SUBSETS`` random halves of
the axis registry (the paper's permutation seed held fixed, so only the axes
move), and on the full data under ``N_SEEDS`` other permutation seeds (so only
the Monte Carlo draw moves). Seeds and subsets derive from ``ROOT_SEED``.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import numpy as np

from script.analysis.placebo_calibration import RUNS, _tables
from script.analysis.zero_compute_runner import OUT, require_reproduced, run_tasks
from src.common.file_io import load_json, read_jsonl, save_json

DIR = OUT / "axis_seed_stability"
ROOT_SEED = 2026102848
N_SUBSETS = 50
N_SEEDS = 20
SUBSET_SHARE = 0.5


def build_tasks() -> list[dict]:
    require_reproduced([s.key for s in RUNS])
    tasks = []
    for r_idx, spec in enumerate(RUNS):
        n_axes = len(_tables(spec)[0].axes)
        size = int(round(SUBSET_SHARE * n_axes))
        for s in range(N_SUBSETS):
            rng = np.random.default_rng(np.random.SeedSequence([ROOT_SEED, r_idx, s]))
            axes = np.sort(rng.choice(n_axes, size=size, replace=False))
            tasks.append({"id": f"{spec.key}|axes|{s}", "key": spec.key, "axes": axes.tolist(),
                          "meta": {"kind": "axis_subset", "index": s, "n_kept": size,
                                   "n_axes_total": n_axes}})
        seeds = np.random.SeedSequence([ROOT_SEED, r_idx, 10**6]).generate_state(N_SEEDS)
        for j, seed in enumerate(seeds):
            tasks.append({"id": f"{spec.key}|seed|{j}", "key": spec.key, "seed": int(seed),
                          "meta": {"kind": "seed", "index": j, "n_kept": n_axes,
                                   "n_axes_total": n_axes}})
    return tasks


def _fold(sel: list[dict], ref: dict) -> dict:
    p = np.array([r["p"] for r in sel])
    return {"n": len(sel), "p_quantiles": {q: float(np.quantile(p, float(q)))
                                           for q in ("0", "0.25", "0.5", "0.75", "1")},
            "share_le_01": float(np.mean(p <= 0.01)), "share_le_05": float(np.mean(p <= 0.05)),
            "named": dict(Counter(str(r["named"]) for r in sel).most_common()),
            "argmax": dict(Counter(str(r["argmax"]) for r in sel).most_common()),
            "share_named_same": float(np.mean([r["named"] == ref["named"] for r in sel])),
            "share_max_axis_same": float(np.mean([r["max_axis"] == ref["max_axis"]
                                                  for r in sel])),
            # A half that keeps the full run's top axis has the same S; the max-axis
            # match marks exactly those halves.
            "reject_share_top_kept": _share([r["loyal"] for r in sel
                                             if r["max_axis"] == ref["max_axis"]]),
            "reject_share_top_dropped": _share([r["loyal"] for r in sel
                                                if r["max_axis"] != ref["max_axis"]])}


def _share(flags: list) -> float | None:
    return float(np.mean(flags)) if flags else None


def _fmt(x) -> str:
    return "n/a" if x is None else f"{x:.2f}"


def _counts_text(counts: dict) -> str:
    return ", ".join(f"{k} {v}" for k, v in counts.items())


def summarize(folder: Path = DIR) -> dict:
    ref = {r["key"]: r["full"] for r in load_json(OUT / "reproduction.json")["runs"]}
    rows = list(read_jsonl(folder / "replicates.jsonl"))
    out = {}
    for key in ref:
        mine = [r for r in rows if r["key"] == key]
        out[key] = {"reference": ref[key],
                    "axis_subsets": _fold([r for r in mine if r["meta"]["kind"] == "axis_subset"],
                                          ref[key]),
                    "seeds": _fold([r for r in mine if r["meta"]["kind"] == "seed"], ref[key]),
                    "cpu_seconds": float(sum(r["seconds"] for r in mine))}
    save_json(folder / "summary.json", out)
    lines = ["# Axis-subset and seed stability (B46 D)", "",
             f"{N_SUBSETS} random halves of the axis registry (paper seed) and {N_SEEDS} "
             "permutation seeds (all axes), registered test at 10,000 permutations.", "",
             "A half rejects or not almost entirely by whether it keeps the full run's top "
             "axis: then S is unchanged and only the max-null shrinks to about half the "
             "axes. The halves overlap and share the data and the seed, so their shares are "
             "not independent estimates; third_party_politics (8 axes) has repeated halves.",
             "",
             "| Run | ref p | ref named | subsets: p median [min, max] | share p<=0.01 | "
             "share keeping top axis | p<=0.01 if kept / if dropped | "
             "named (count) | seeds: p [min, max] | share p<=0.01 | named (count) |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for key, e in out.items():
        a, s = e["axis_subsets"], e["seeds"]
        q, qs = a["p_quantiles"], s["p_quantiles"]
        lines.append(f"| {key} | {e['reference']['p']:.4f} | {e['reference']['named']} | "
                     f"{q['0.5']:.4f} [{q['0']:.4f}, {q['1']:.4f}] | {a['share_le_01']:.2f} | "
                     f"{a['share_max_axis_same']:.2f} | {_fmt(a['reject_share_top_kept'])} / "
                     f"{_fmt(a['reject_share_top_dropped'])} | "
                     f"{_counts_text(a['named'])} | [{qs['0']:.4f}, {qs['1']:.4f}] | "
                     f"{s['share_le_01']:.2f} | {_counts_text(s['named'])} |")
    (folder / "summary.md").write_text("\n".join(lines) + "\n")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--workers", type=int, default=10)
    sub.add_parser("summarize")
    args = ap.parse_args()
    if args.cmd == "run":
        run_tasks(build_tasks(), DIR / "replicates.jsonl", args.workers)
    summarize()


if __name__ == "__main__":
    main()
