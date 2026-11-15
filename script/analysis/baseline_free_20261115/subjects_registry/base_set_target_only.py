"""The target-only median test on the three fresh base draws that partA never ran. No spend.

    .venv/bin/python -m script.analysis.baseline_free_20261115.subjects_registry.base_set_target_only

partA ran its base-only median test once per distinct base file. The fresh API
draws C1, C1 restricted to samples 0-11, and C2 are not partA runs, so the
registry had no target-only row for them. This runs the same task on each:
``reference_free_max_test`` (one candidate against the median of the others, no
base) with the registered settings (10,000 permutations, seed 20260726, alpha
0.01, every cell reported), formatted with partA's own ``_digest``, on the full
axis registry and, where the registry carries the three guaranteed axes
verbatim, on those three. Each table is read through ``load_subject_table``, so
a moved verdict or axis file stops the script.

Writes ``base_set_target_only.json`` once and refuses to overwrite it.
"""

from __future__ import annotations

import time

from script.analysis.baseline_free_20261115.common.settings import (ALPHA, N_PERM,
                                                                   REGISTRY_DIR, SEED,
                                                                   SUBJECTS_JSON,
                                                                   save_new_json,
                                                                   settings_block)
from script.analysis.baseline_free_20261115.common.subjects import (load_subject_table,
                                                                   sha256,
                                                                   subject_record)
from script.analysis.baseline_free_20261115.subjects_registry.reproduce_partA import (
    guaranteed_status)
from script.analysis.reanalysis_2026_11.partA_baseline_role import _digest as partA_digest
from src.compare.reference_free_max_statistic import reference_free_max_test

OUT = REGISTRY_DIR / "base_set_target_only.json"
SUBJECTS = ("base_C1", "base_C1_s0_11", "base_C2")


def main() -> None:
    if OUT.exists():
        raise SystemExit(f"{OUT} exists; never overwritten")
    reg_sha = sha256(SUBJECTS_JSON)
    results = {}
    for sid in SUBJECTS:
        rec = subject_record(sid)
        g = guaranteed_status(rec["axes"])
        for subset in ["full"] + (["guaranteed3"] if g["carries_all_three"] else []):
            t0 = time.time()
            t = load_subject_table(sid, subset)
            n_cells = len(t.principals) * len(t.axes)
            res = reference_free_max_test(t, n_permutations=N_PERM, seed=SEED, alpha=ALPHA,
                                          top=n_cells)
            row = {"subject_id": sid, "subset": subset, "kind": "median", "seat": "base",
                   "table": rec["verdicts"], "s_max": rec["s_max"],
                   "table_sha256": rec["sha256"]["verdicts"], "axes": rec["axes"],
                   "level": rec["level"], "n_rows": int(t.n_responses),
                   **partA_digest(res, "median", len(t.axes)),
                   "seconds": round(time.time() - t0, 1)}
            results[f"{sid}|target_only_median|{subset}"] = row
            print(f"{sid:16s} {subset:12s} S={row['S']:.4f} p={row['p']:.4f} "
                  f"argmax={row['argmax_candidate']} reject={row['reject_0.01']}", flush=True)
    if sha256(SUBJECTS_JSON) != reg_sha:
        raise SystemExit("subjects.json changed during the run; stop")
    save_new_json(OUT, {
        "what": "target-only median test on the fresh base draws C1, C1 s0-11 and C2",
        "settings": settings_block(top="every (candidate, axis) cell"),
        "registry": {"path": "out/main/baseline_free_20261115/subjects_registry/subjects.json",
                     "sha256": reg_sha},
        "test": "src.compare.reference_free_max_statistic.reference_free_max_test",
        "format": "script.analysis.reanalysis_2026_11.partA_baseline_role._digest",
        "results": results})
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
