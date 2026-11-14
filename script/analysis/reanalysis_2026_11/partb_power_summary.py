"""(b) Summary of the power curve: rejection rate per run and subset size.

    uv run python script/analysis/reanalysis_2026_11/partb_power_summary.py

Reads ``partB/power_curve_subsets.jsonl`` and, for the full instruction set,
``partB/reproduce_check.json`` and ``partB/mirror_naming.json``. Per run and
size it reports the subsets drawn, the share rejecting at alpha 0.01 with a 95%
Wilson interval, the median statistic, the share of all subsets that the
registered naming rule names the full-data name on, and the share of
rejecting subsets whose maximum sits on the full-data group at the maximum.
Only sizes where every run holds the same subset count are compared. Writes
``partB/power_curve_summary_n<count>.json``.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict

import numpy as np

from partb_power_curve import FRACTIONS, ROWS, RUNS
from partb_run_sources import OUT
from src.common.file_io import load_json, save_json


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (round(centre - half, 4), round(centre + half, 4))


def main() -> None:
    rows = [json.loads(x) for x in ROWS.read_text().splitlines()]
    full = {r["key"]: r for r in load_json(OUT / "reproduce_check.json")["rows"]}
    mirror = {r["run"]: r for r in load_json(OUT / "mirror_naming.json")["runs"]}
    cells = defaultdict(list)
    for r in rows:
        cells[(r["run"], r["fraction"])].append(r)
    count = min(len(cells[(k, f)]) for k in RUNS for f in FRACTIONS)
    out = {}
    for key in RUNS:
        name = full[key].get("attribution_named") if key in full else None
        argmax_full = mirror[key]["registered_rule"]["argmax"] if key in mirror else None
        per = {"1.0": {"k": full[key]["m"], "n_subsets": 1,
                       "reject_rate": float(full[key]["p_family_wise"] <= 0.01),
                       "median_statistic": full[key]["statistic"],
                       "p_full": full[key]["p_family_wise"], "named_full": name}}
        for f in FRACTIONS:
            group = sorted(cells[(key, f)], key=lambda r: r["subset_index"])[:count]
            rej = [r for r in group if r["reject"]]
            per[str(f)] = {
                "k": group[0]["k"], "n_subsets": len(group),
                "reject_rate": round(len(rej) / len(group), 4),
                "reject_ci95": wilson(len(rej), len(group)),
                "median_statistic": float(np.median([min(r["statistic"], 1e6) for r in group])),
                "named_full_name_rate": (round(sum(r.get("named") == name for r in rej)
                                               / len(group), 4) if name else None),
                "argmax_on_full_group_among_rejections": (
                    round(sum(r.get("argmax") == argmax_full for r in rej) / len(rej), 4)
                    if rej and argmax_full else None),
                # Rejecting subsets by the name the registered rule gives them.
                "names_given": {(n or "none named"): sum(r.get("named") == n for r in rej)
                                for n in {r.get("named") for r in rej}},
            }
        out[key] = {"full_data_name": name, "full_data_argmax": argmax_full, "sizes": per}
        print(f"{key:30s} " + "  ".join(
            f"k={v['k']:3d}: {v['reject_rate']:.2f}" for v in per.values()), flush=True)
    path = OUT / f"power_curve_summary_n{count}.json"
    if path.exists():
        raise SystemExit(f"{path} exists; part B never overwrites")
    save_json(path, {"subsets_per_size": count, "alpha": 0.01, "rows_file": str(ROWS),
                     "note": "median_statistic caps a near-degenerate t at 1e6 before the median",
                     "runs": out})
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
