"""Every value the previous build holds, compared with this build.

    .venv/bin/python -m script.analysis.baseline_free_20261115.cross_run_panel.regress_panel \
        out/superseded/baseline_free_20261115/cross_run_panel/<stamp>

The new build adds a pool, panels, members, p types and fields. It must leave
every value the previous build computed unchanged: the gate, every grid, every
permutation test, every panel test in the old pools, the nine-run reference,
every placebo replicate and the user-awareness panel. Leaves are compared
exactly; a key the old build holds and the new one lacks is a failure.
Writes ``verify/regression_vs_superseded.json`` and exits non-zero on any
difference.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from script.analysis.baseline_free_20261115.cross_run_panel import run_panel as rp  # noqa: E402
from src.common.file_io import load_json, read_jsonl  # noqa: E402

IGNORE = {"seconds"}


def subset_diff(old, new, path: str = "") -> list[str]:
    """Leaves of ``old`` that ``new`` lacks or holds with another value."""
    if isinstance(old, dict):
        if not isinstance(new, dict):
            return [f"{path}: type {type(new).__name__}"]
        out = []
        for k in old:
            if k in IGNORE:
                continue
            if k not in new:
                out.append(f"{path}/{k}: missing in new")
                continue
            out += subset_diff(old[k], new[k], f"{path}/{k}")
        return out
    if isinstance(old, list):
        if not isinstance(new, list) or len(old) != len(new):
            return [f"{path}: list differs in length or type"]
        out = []
        for i, (a, b) in enumerate(zip(old, new)):
            out += subset_diff(a, b, f"{path}[{i}]")
        return out
    if isinstance(old, float) and isinstance(new, float) and math.isnan(old) and math.isnan(new):
        return []
    return [] if (old == new and type(old) is type(new)) else [f"{path}: {old!r} != {new!r}"]


def main() -> int:
    old_dir = Path(sys.argv[1])
    new_dir = REPO / rp.OUT
    report: dict = {"old": str(old_dir), "new": str(rp.OUT), "checks": {}}
    diffs: list[str] = []

    def record(name: str, n: int, d: list[str]) -> None:
        report["checks"][name] = {"n_compared": n, "n_differences": len(d)}
        diffs.extend(f"{name}: {x}" for x in d)

    # Gate.
    old, new = load_json(old_dir / "gate/reproduce_gate.json"), load_json(
        new_dir / "gate/reproduce_gate.json")
    record("gate/reproduce_gate.json", 1, subset_diff(old, new))

    # Grids and their index.
    zo, zn = np.load(old_dir / "t_grids_target_only.npz"), np.load(
        new_dir / "t_grids_target_only.npz")
    d = [k for k in zo.files if k not in zn.files or not np.array_equal(zo[k], zn[k],
                                                                         equal_nan=True)]
    record("t_grids_target_only.npz arrays", len(zo.files), d)
    record("t_grids_target_only_index.json",
           1, subset_diff(load_json(old_dir / "t_grids_target_only_index.json"),
                          load_json(new_dir / "t_grids_target_only_index.json")))

    # Permutation tests.
    so, sn = load_json(old_dir / "sharp/sharp_null.json"), load_json(
        new_dir / "sharp/sharp_null.json")
    record("sharp/sharp_null.json results", len(so["results"]),
           subset_diff(so["results"], sn["results"], "/results"))
    record("sharp/sharp_null.json checks", len(so["checks"]),
           subset_diff(so["checks"], sn["checks"], "/checks"))

    # Panel tests: every old panel, member, pool, grid and field; the nine-run reference.
    po, pn = load_json(old_dir / "cross_run_target_only.json"), load_json(
        new_dir / "cross_run_target_only.json")
    n_tests = sum(len(p["results"]) for p in po["panels"].values())
    record("cross_run_target_only.json panels", n_tests,
           subset_diff(po["panels"], pn["panels"], "/panels"))
    record("cross_run_target_only.json family9_target_only", 1,
           subset_diff(po["family9_target_only"], pn["family9_target_only"], "/family9"))

    # Placebo replicates.
    ro = {(r["design"], r["replicate"]): r for r in read_jsonl(
        old_dir / "placebo/placebo_replicates.jsonl")}
    rn = {(r["design"], r["replicate"]): r for r in read_jsonl(
        new_dir / "placebo/placebo_replicates.jsonl")}
    d = []
    for key, r in ro.items():
        if key not in rn:
            d.append(f"{key}: missing in new")
            continue
        d += subset_diff(r, rn[key], f"/{key}")
    record("placebo/placebo_replicates.jsonl", len(ro), d)

    # User awareness.
    record("ua/ua_panel.json", 1, subset_diff(load_json(old_dir / "ua/ua_panel.json"),
                                              load_json(new_dir / "ua/ua_panel.json")))

    # The deep comparison must be able to fail.
    probe = json.loads(json.dumps(po["panels"]["main"]["results"]["flattery"]))
    probe["nulls_all_rows"]["median"]["pooled_max"]["values"]["p_ref"] += 1e-15
    can_fail = bool(subset_diff(probe, pn["panels"]["main"]["results"]["flattery"]))
    report.update({"comparison_can_fail": can_fail, "n_failures": len(diffs) + (not can_fail),
                   "differences": diffs[:200]})
    out = new_dir / "verify" / "regression_vs_superseded.json"
    if out.exists():
        raise SystemExit(f"refusing to overwrite {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1))
    print(json.dumps({k: v for k, v in report.items() if k != "differences"}, indent=1))
    for x in diffs[:20]:
        print("DIFF", x)
    return report["n_failures"]


if __name__ == "__main__":
    raise SystemExit(main())
