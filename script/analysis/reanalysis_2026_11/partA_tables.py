"""Part A: fold baseline_role.json into two CSV tables. No computation.

    .venv/bin/python -m script.analysis.reanalysis_2026_11.partA_tables

Writes ``baseline_role_table.csv`` (registered vs target-only vs base-only, full
registry) and ``guaranteed_axes_table.csv`` (full registry vs the three
guaranteed axes) under ``out/main/reanalysis_20261113/partA/``. Never overwrites.
"""

from __future__ import annotations

import csv
from pathlib import Path

from src.common.file_io import load_json

OUT = Path("out/main/reanalysis_20261113/partA")


def _base_row(results: dict, meta: dict, key: str, subset: str) -> dict | None:
    m = meta[key]
    if not m["sha256_base"]:
        return None
    for v in results.values():
        if (v["kind"] == "median" and v.get("seat") == "base" and v["subset"] == subset
                and v["axes"] == m["axes"] and v["level"] == m["level"]
                and v.get("base_sha256") == m["sha256_base"]):
            return v
    return None


def _f(x, nd=4):
    return "" if x is None else (f"{x:.{nd}f}" if isinstance(x, float) else x)


def main() -> None:
    rec = load_json(OUT / "baseline_role.json")
    res, meta = rec["results"], rec["runs"]
    t1, t2 = OUT / "baseline_role_table.csv", OUT / "guaranteed_axes_table.csv"
    for p in (t1, t2):
        if p.exists():
            raise SystemExit(f"{p} exists; never overwritten")

    rows1, rows2 = [], []
    for key, m in meta.items():
        reg = res.get(f"{key}|registered|full")
        tmed = res[f"{key}|target_only_median|full"]
        tmean = res[f"{key}|target_only_mean|full"]
        bmed = _base_row(res, meta, key, "full")
        rows1.append({
            "run": key, "role": m["role"], "note": m["note"], "level": m["level"],
            "m": tmed["n_instructions"], "n_candidates": len(tmed["candidates"]),
            "n_axes": tmed["n_axes"],
            "registered_S": _f(reg and reg["S"], 3), "registered_p": _f(reg and reg["p"]),
            "registered_reject": reg and reg["reject_0.01"],
            "registered_argmax": reg and reg["argmax_candidate"],
            "registered_named": reg and reg["named_by_rule"],
            "target_only_median_S": _f(tmed["S"], 3), "target_only_median_p": _f(tmed["p"]),
            "target_only_median_reject": tmed["reject_0.01"],
            "target_only_median_argmax": tmed["argmax_candidate"],
            "target_only_median_named": tmed["named_by_rule"],
            "target_only_median_surviving": tmed["surviving_axes_by_candidate"],
            "target_only_mean_S": _f(tmean["S"], 3), "target_only_mean_p": _f(tmean["p"]),
            "target_only_mean_reject": tmean["reject_0.01"],
            "target_only_mean_argmax": tmean["argmax_candidate"],
            "target_only_mean_named": tmean["named_by_rule"],
            "base_only_median_S": _f(bmed and bmed["S"], 3),
            "base_only_median_p": _f(bmed and bmed["p"]),
            "base_only_median_reject": bmed and bmed["reject_0.01"],
            "base_only_median_argmax": bmed and bmed["argmax_candidate"],
        })
        if f"{key}|target_only_median|guaranteed3" not in res:
            continue
        reg3 = res.get(f"{key}|registered|guaranteed3")
        tmed3 = res[f"{key}|target_only_median|guaranteed3"]
        tmean3 = res[f"{key}|target_only_mean|guaranteed3"]
        bmed3 = _base_row(res, meta, key, "guaranteed3")
        best_g = (sorted(reg["guaranteed_axis_best_pairs"], key=lambda r: -abs(r["t"]))[0]
                  if reg and reg["guaranteed_axis_best_pairs"] else None)
        rows2.append({
            "run": key, "note": m["note"], "n_axes_full": m["guaranteed"]["n_axes"],
            "registered_full_S": _f(reg and reg["S"], 3),
            "registered_full_p": _f(reg and reg["p"]),
            "registered_full_named": reg and reg["named_by_rule"],
            "full_best_g_axis": best_g and best_g["axis_id"],
            "full_best_g_candidate": best_g and best_g["candidate"],
            "full_best_g_t": _f(best_g and best_g["t"], 3),
            "full_best_g_p_adjusted": _f(best_g and best_g["p_adjusted"]),
            "registered_g3_S": _f(reg3 and reg3["S"], 3),
            "registered_g3_p": _f(reg3 and reg3["p"]),
            "registered_g3_reject": reg3 and reg3["reject_0.01"],
            "registered_g3_argmax": reg3 and reg3["argmax_candidate"],
            "registered_g3_argmax_axis": reg3 and reg3["argmax_axis"],
            "registered_g3_named": reg3 and reg3["named_by_rule"],
            "target_only_median_g3_p": _f(tmed3["p"]),
            "target_only_median_g3_argmax": tmed3["argmax_candidate"],
            "target_only_mean_g3_p": _f(tmean3["p"]),
            "target_only_mean_g3_argmax": tmean3["argmax_candidate"],
            "base_only_median_g3_p": _f(bmed3 and bmed3["p"]),
            "base_only_median_g3_argmax": bmed3 and bmed3["argmax_candidate"],
        })
    for path, rows in ((t1, rows1), (t2, rows2)):
        with path.open("x", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print(f"wrote {path} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
