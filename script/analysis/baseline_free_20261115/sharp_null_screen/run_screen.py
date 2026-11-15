"""Target-only screen at the sharp null, on every subject. No spend.

    uv run python -m script.analysis.baseline_free_20261115.sharp_null_screen.run_screen plan
    uv run python -m script.analysis.baseline_free_20261115.sharp_null_screen.run_screen run --workers 12
    uv run python -m script.analysis.baseline_free_20261115.sharp_null_screen.run_screen finalize

Copied from ``partA_baseline_role.py`` and ``compute_reference_free_detector.py``
with the outputs redirected and the subject list extended (``sharp_null_subjects``).
Each subject runs on the full registry and, where its registry carries all three
guaranteed axes with identical wording, on those three. ``run`` appends one line
per finished task to ``tasks.jsonl`` and resumes from it; ``finalize`` writes the
merged outputs and refuses to overwrite any of them.

Writes only under ``out/main/baseline_free_20261115/sharp_null_screen/``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path

from script.analysis.baseline_free_20261115.sharp_null_screen.sharp_null_finalize import finalize
from script.analysis.baseline_free_20261115.sharp_null_screen.sharp_null_statistics import (
    ALPHA, N_PERM, SEED, run_task)
from script.analysis.baseline_free_20261115.sharp_null_screen.sharp_null_subjects import (
    SPLIT_SEED, subjects)
from script.analysis.baseline_free_20261115.sharp_null_screen.sharp_null_tables import (
    guaranteed_status, table_for)

OUT = Path("out/main/baseline_free_20261115/sharp_null_screen")
GRIDS = OUT / "task_grids"
TASK_LOG = OUT / "tasks.jsonl"
KINDS = ("registered", "mean", "median", "g_test", "coherence", "loser")


def _sha(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def plan() -> tuple[list[dict], list[dict], dict]:
    """(tasks to run, manifest rows that cannot run, subject metadata)."""
    tasks, skipped, meta = [], [], {}
    for s in subjects():
        g = guaranteed_status(s.axes)
        common = {"sid": s.sid, "group": s.group, "table": s.verdicts, "base": s.base,
                  "axes": s.axes, "level": s.level, "half": s.half,
                  "base_half": s.base_half, "split_seed": SPLIT_SEED if s.half is not None
                  else None}
        probe = table_for({**common, "subset": "full"})
        k, n_i, n_j = len(probe.principals), len(probe.blocks), len(probe.axes)
        meta[s.sid] = {**asdict(s), "guaranteed": g, "k": k, "n_instructions": n_i,
                       "n_axes_full": n_j, "candidates": list(probe.principals),
                       "n_responses": int(probe.n_responses),
                       "sha256_verdicts": _sha(s.verdicts),
                       "sha256_base": _sha(s.base) if s.base else None}
        for subset in ("full", "guaranteed3") if g["carries_all_three"] else ("full",):
            for kind in KINDS:
                tid = f"{s.sid}|{kind}|{subset}"
                row = {**common, "id": tid, "kind": kind, "subset": subset,
                       "cost": k * n_i * (n_j if subset == "full" else 3)}
                if kind == "registered" and s.base is None and s.half is None:
                    skipped.append({**row, "status": "no pair: no base or second draw exists"})
                elif kind in ("coherence", "loser") and k < 3:
                    skipped.append({**row, "status": f"not computable: k = {k} < 3"})
                else:
                    tasks.append(row)
    tasks.sort(key=lambda t: -t["cost"])
    return tasks, skipped, meta


def settings_record() -> dict:
    return {"seed": SEED, "n_permutations": N_PERM, "alpha": ALPHA, "split_seed": SPLIT_SEED,
            "adjustment": "single-step maxT over (candidate, axis) pairs",
            "g_test": {"n_permutations": N_PERM, "seed": SEED,
                       "note": "src/compare/comparison_report.py defaults to 2,000; every "
                               "stored stage-6 comparison_<seat>_L<level>.json carries 10,000 "
                               "with this seed, and this screen uses 10,000"},
            "coherence": {"k0": 20, "z_clip": 8.0, "scale_floor_share": 0.25},
            "loser_dispersion": {"base": "all-zero table on the subject's own cells",
                                 "zero_spread_modes": ["infinite", "exclude"]},
            "level": "the subject's registered judge level (L3 calibration_informed, "
                     "L1 political_sycophancy and the UA subjects, L2 otherwise)",
            "naming_rule": "src/compare/principal_attribution.attribute_principal on every "
                           "variant with pairs; k = 2 rows flagged named not identified",
            "alpha_0.05_also_reported": True}


def cmd_run(workers: int) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    GRIDS.mkdir(exist_ok=True)
    tasks, skipped, meta = plan()
    done = set()
    if TASK_LOG.exists():
        done = {json.loads(x)["id"] for x in TASK_LOG.open() if x.strip()}
    todo = [t for t in tasks if t["id"] not in done]
    print(f"{len(meta)} subjects, {len(tasks)} tasks, {len(skipped)} not runnable, "
          f"{len(done)} done, {len(todo)} to run", flush=True)
    with ProcessPoolExecutor(max_workers=workers) as ex, TASK_LOG.open("a") as fh:
        futs = {ex.submit(run_task, t, str(GRIDS)): t["id"] for t in todo}
        for f in as_completed(futs):
            r = f.result()
            fh.write(json.dumps(r, default=str) + "\n")
            fh.flush()
            print(f"{r['id']:72s} S={r['S'] if r['S'] is None else round(r['S'], 3)} "
                  f"p={r['p']} named={r['named_by_rule']} ({r['seconds']}s)", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("stage", choices=("plan", "run", "finalize"))
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 4))
    args = ap.parse_args()
    if args.stage == "plan":
        tasks, skipped, meta = plan()
        for sid, m in meta.items():
            print(f"{m['group']:8s} {sid:48s} k={m['k']:2d} I={m['n_instructions']:3d} "
                  f"J={m['n_axes_full']:3d} L{m['level']} g3={m['guaranteed']['carries_all_three']}")
        print(f"{len(meta)} subjects, {len(tasks)} tasks, {len(skipped)} not runnable")
    elif args.stage == "run":
        cmd_run(args.workers)
    else:
        finalize(OUT, plan(), settings_record())


if __name__ == "__main__":
    main()
