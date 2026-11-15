"""Gate: the copies' outputs equal the stored judge-free and calibration files.

    uv run python <this file>

Compares, file by file, what ``run_reproduce_gate.sh`` wrote under
``reproduce/`` with the stored originals:

* ``semantic_bridge_masked.json`` of the 15 embedded runs (every field);
* the ``group_test`` of each run's ``semantic_bridge.json`` (unmasked; every field
  the stored test wrote, the display name aside);
* ``out/main/judge_free_masked/calibration.json``;
* the 2026-11-14 calibration's ``reproduce_base_A.json``, ``grid.json``, the six
  ``placebo_*.json`` and ``summary.json``.

A file matches when its parsed JSON is equal value for value (floats compared
exactly); byte equality is reported beside it. Writes ``reproduce_check.json`` and
exits non-zero on any mismatch or missing file.
"""

from __future__ import annotations

import json
import sys

from emb_target_only_sources import OUT, REPO, REPRO_DIR, STORED_RUNS
from script.analysis.baseline_free_20261115.common.settings import save_new_json
from src.common.experiment_layout import geometry_dir

CAL = REPO / "out/main/auditbench/nullext/embedding_calibration_20261114/results"
MINE_CAL = REPRO_DIR / "embedding_calibration_20261114/results"
MINE_JF = REPRO_DIR / "judge_free_masked"
PLACEBOS = [f"placebo_{s}_{v}.json" for s in ("A", "B", "auditbench_flattery")
            for v in ("masked", "unmasked")]


def _diff(a, b, path="", out=None, limit=5):
    out = [] if out is None else out
    if len(out) >= limit:
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append(f"{path}/{k}: present on one side only")
            else:
                _diff(a[k], b[k], f"{path}/{k}", out, limit)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{path}: length {len(a)} vs {len(b)}")
        for j, (x, y) in enumerate(zip(a, b)):
            _diff(x, y, f"{path}[{j}]", out, limit)
    elif a != b:
        out.append(f"{path}: {a!r} vs {b!r}")
    return out


def _compare(mine, stored, select=None) -> dict:
    if not mine.exists():
        return {"mine": str(mine.relative_to(REPO)), "match": False, "error": "missing"}
    a, b = json.loads(mine.read_text()), json.loads(stored.read_text())
    if select:
        a, b = select(a, "mine"), select(b, "stored")
    diffs = _diff(a, b)
    out = {"mine": str(mine.relative_to(REPO)), "stored": str(stored.relative_to(REPO)),
           "match": not diffs, "bytes_equal": mine.read_bytes() == stored.read_bytes(),
           "first_differences": diffs}
    if diffs:
        all_diffs = _diff(a, b, limit=10**6)
        out["n_differences"] = len(all_diffs)
        out["max_abs_numeric_difference"] = _max_numeric(a, b)
        if isinstance(a, dict) and "statistic" in a:
            out["decision_fields_match"] = all(a.get(k) == b.get(k) for k in
                                               ("statistic", "p", "named", "null_p95", "rejects"))
    return out


def _max_numeric(a, b) -> float:
    if isinstance(a, dict) and isinstance(b, dict):
        return max([_max_numeric(a[k], b[k]) for k in a if k in b] or [0.0])
    if isinstance(a, list) and isinstance(b, list):
        return max([_max_numeric(x, y) for x, y in zip(a, b)] or [0.0])
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return abs(float(a) - float(b))
    return 0.0 if a == b else float("inf")


def main():
    rows = {}
    for key in STORED_RUNS:
        gd = REPO / geometry_dir(key)
        rows[f"semantic_bridge_masked:{key}"] = _compare(
            MINE_JF / "semantic_bridge_masked" / f"{key}.json", gd / "semantic_bridge_masked.json")

        def pick(d, side):
            g = d["group_test"]
            return {k: v for k, v in g.items() if k != "named_display"}
        r = _compare(MINE_JF / "semantic_bridge_unmasked" / f"{key}.json",
                     gd / "semantic_bridge.json", select=pick)
        r.pop("bytes_equal", None)
        rows[f"semantic_bridge_unmasked_group_test:{key}"] = r
    rows["judge_free_masked/calibration.json"] = _compare(
        MINE_JF / "calibration.json", REPO / "out/main/judge_free_masked/calibration.json")
    for name in ["reproduce_base_A.json", "grid.json", *PLACEBOS, "summary.json"]:
        rows[f"embedding_calibration_20261114/{name}"] = _compare(MINE_CAL / name, CAL / name)
    bad = [k for k, v in rows.items() if not v["match"]]
    out = {"all_match": not bad, "n_files": len(rows), "n_match": len(rows) - len(bad),
           "mismatches": bad,
           "mismatches_with_equal_decision_fields": [k for k in bad
                                                     if rows[k].get("decision_fields_match")],
           "files": rows,
           "rule": "parsed JSON equal value for value, floats compared exactly; a mismatch "
                   "reports its largest numeric difference and whether statistic, p, named, "
                   "null_p95 and rejects still match"}
    save_new_json(OUT / "reproduce_check.json", out)
    print(json.dumps({k: out[k] for k in ("all_match", "n_files", "n_match", "mismatches")}))
    if bad:
        sys.exit(1)


if __name__ == "__main__":
    main()
