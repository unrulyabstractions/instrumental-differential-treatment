"""Fold the independent-base-slice replicates into a summary (B46, section A).

The shared-base p-values are read from the reproduction gate, which reran the
stored test exactly, never typed in. Within one partition the ``8x2`` nulls use
disjoint base rows and distinct targets, so their eight p-values are
independent draws apart from the shared prompts and the shared permutation
seed; the KS test is reported for that arm only. ``4x4`` pairs share a slice,
and the ``-shared`` arms share one slice across all eight. Across partitions
every arm reuses the same data, so pooled shares are not independent draws.

Co-movement is the mean over the 28 null pairs of the Spearman correlation of
their p-values across partitions: near zero when nulls do not share a base
draw, positive when one base draw moves them together.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy import stats

from script.analysis.placebo_calibration import CONTROLS
from script.analysis.zero_compute_runner import OUT
from src.common.file_io import load_json, read_jsonl, save_json

NULLS = tuple(f"auditbench_{c}" for c in CONTROLS)
POSITIVE = "auditbench_contextual_optimism"
SCHEMES = ("8x2", "4x4", "8x2-shared", "4x4-shared")
INDEPENDENT = "8x2"


def _counts(p) -> dict:
    p = np.asarray(p, dtype=float)
    return {"median": float(np.median(p)), "n_le_05": int(np.sum(p <= 0.05)),
            "n_le_01": int(np.sum(p <= 0.01)), "min": float(p.min()), "n": int(p.size)}


def _co_movement(by: dict, parts: list[int]) -> float:
    rhos = []
    for i, a in enumerate(NULLS):
        for b in NULLS[i + 1:]:
            rhos.append(stats.spearmanr([by[(q, a)]["p"] for q in parts],
                                        [by[(q, b)]["p"] for q in parts]).statistic)
    return float(np.mean(rhos))


def _positive(by: dict, parts: list[int]) -> dict | None:
    if (0, POSITIVE) not in by:
        return None
    pos = [by[(q, POSITIVE)] for q in parts]
    return {"p_partition0": by[(0, POSITIVE)]["p"],
            "median_p": float(np.median([r["p"] for r in pos])),
            "share_reject_01": float(np.mean([r["loyal"] for r in pos])),
            "share_named_anthropic": float(np.mean([r["named"] == "anthropic" for r in pos]))}


def summarize(folder: Path) -> dict:
    gate = {r["key"]: r for r in load_json(OUT / "reproduction.json")["runs"]}
    rows = list(read_jsonl(folder / "replicates.jsonl"))
    shared = {k: gate[k]["stored_p"] for k in [*NULLS, POSITIVE]}
    out = {"shared_base": {"p": {k: shared[k] for k in NULLS}, **_counts(
        [shared[k] for k in NULLS])}, "positive_shared_p": shared[POSITIVE], "schemes": {}}
    for scheme in SCHEMES:
        for version in ("full", "matched"):
            sel = [r for r in rows if r["meta"]["scheme"] == scheme
                   and r["meta"]["target"] == version]
            parts = sorted({r["meta"]["partition"] for r in sel})
            by = {(r["meta"]["partition"], r["key"]): r for r in sel}
            head = [by[(0, k)]["p"] for k in NULLS]
            per_part = [_counts([by[(q, k)]["p"] for k in NULLS]) for q in parts]
            pooled = [by[(q, k)]["p"] for q in parts for k in NULLS]
            out["schemes"][f"{scheme}/{version}"] = {
                "partition0": {"p": dict(zip(NULLS, head)), **_counts(head),
                               "ks_p_uniform": (float(stats.kstest(head, "uniform").pvalue)
                                                if scheme == INDEPENDENT else None),
                               "base_rows": {k: by[(0, k)]["meta"]["base_rows"] for k in NULLS},
                               "target_rows": {k: by[(0, k)]["meta"]["target_rows"]
                                               for k in NULLS}},
                "partitions": len(parts),
                "median_of_medians": float(np.median([c["median"] for c in per_part])),
                "mean_n_le_05": float(np.mean([c["n_le_05"] for c in per_part])),
                "mean_n_le_01": float(np.mean([c["n_le_01"] for c in per_part])),
                "range_n_le_05": [min(c["n_le_05"] for c in per_part),
                                  max(c["n_le_05"] for c in per_part)],
                "pooled_share_le_05": float(np.mean(np.asarray(pooled) <= 0.05)),
                "pooled_share_le_01": float(np.mean(np.asarray(pooled) <= 0.01)),
                "sd_partition_median": float(np.std([c["median"] for c in per_part])),
                "co_movement_spearman": _co_movement(by, parts),
                "per_null_median_p": {k: float(np.median([by[(q, k)]["p"] for q in parts]))
                                      for k in NULLS},
                "positive": _positive(by, parts),
                "cpu_seconds": float(sum(r["seconds"] for r in sel)),
            }
    save_json(folder / "summary.json", out)
    _write_markdown(folder, out)
    return out


def _write_markdown(folder: Path, s: dict) -> None:
    keys = list(s["schemes"])
    lines = ["# Independent base slices for the AuditBench null controls (B46 A)", "",
             "Partition 0 p-values (registered test, 10,000 permutations, paper seed).", "",
             "| Null | shared base | " + " | ".join(keys) + " |",
             "|---|---|" + "---|" * len(keys)]
    for k in NULLS:
        cells = [f"{s['schemes'][x]['partition0']['p'][k]:.4f}" for x in keys]
        lines.append(f"| {k.removeprefix('auditbench_')} | {s['shared_base']['p'][k]:.4f} | "
                     + " | ".join(cells) + " |")
    for label, f in (("median", "median"), ("n <= 0.05", "n_le_05"), ("n <= 0.01", "n_le_01")):
        lines.append(f"| **{label}** | {s['shared_base'][f]:.4g} | " + " | ".join(
            f"{s['schemes'][x]['partition0'][f]:.4g}" for x in keys) + " |")
    lines += ["", f"Over {s['schemes'][keys[0]]['partitions']} random partitions:", "",
              "| Scheme | median of medians | mean n<=0.05 (range) | mean n<=0.01 | "
              "pooled share <=0.05 | pooled share <=0.01 | co-movement | KS p (partition 0) | "
              "optimism median p | optimism reject share | optimism named share |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    for x in keys:
        v = s["schemes"][x]
        pos = v["positive"]
        opt = ("n/a | n/a | n/a" if pos is None else
               f"{pos['median_p']:.4f} | {pos['share_reject_01']:.2f} | "
               f"{pos['share_named_anthropic']:.2f}")
        ks = v["partition0"]["ks_p_uniform"]
        lines.append(
            f"| {x} | {v['median_of_medians']:.4f} | {v['mean_n_le_05']:.2f} "
            f"({v['range_n_le_05'][0]}-{v['range_n_le_05'][1]}) | {v['mean_n_le_01']:.2f} | "
            f"{v['pooled_share_le_05']:.3f} | {v['pooled_share_le_01']:.3f} | "
            f"{v['co_movement_spearman']:+.3f} | "
            f"{'n/a (dependent)' if ks is None else f'{ks:.3f}'} | {opt} |")
    lines += ["", f"Shared-base optimism p: {s['positive_shared_p']:.4g}."]
    (folder / "summary.md").write_text("\n".join(lines) + "\n")
