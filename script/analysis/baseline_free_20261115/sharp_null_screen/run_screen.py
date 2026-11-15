"""Target-only screen at the sharp null, on every subject. No spend.

    uv run python -m script.analysis.baseline_free_20261115.sharp_null_screen.run_screen plan
    uv run python -m script.analysis.baseline_free_20261115.sharp_null_screen.run_screen run --workers 12 [--reuse DIR]
    uv run python -m script.analysis.baseline_free_20261115.sharp_null_screen.run_screen precision --workers 12
    uv run python -m script.analysis.baseline_free_20261115.sharp_null_screen.run_screen finalize

Copied from ``partA_baseline_role.py`` and ``compute_reference_free_detector.py``
with the outputs redirected and the subject list extended (``sharp_null_subjects``).
Each subject runs on the full registry and, where its registry carries all three
guaranteed axes with identical wording, on those three. ``run`` appends one line
per finished task to ``tasks.jsonl`` and resumes from it. With ``--reuse DIR`` it
takes a task's line from ``DIR/tasks.jsonl`` (and its grid file from
``DIR/task_grids``) when every input field of the line equals the planned task's,
and runs every other task; the new lines are written first, then the reused lines.
``precision`` reruns every decision that lies within Monte Carlo error of alpha at
100,000 permutations (same seed) into ``mc_precision.jsonl``. ``finalize`` writes
the merged outputs and refuses to overwrite any of them.

Writes only under ``out/main/baseline_free_20261115/sharp_null_screen/``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path

from script.analysis.baseline_free_20261115.sharp_null_screen.sharp_null_finalize import (
    INPUT_KEYS, finalize, load_task_log)
from script.analysis.baseline_free_20261115.sharp_null_screen.sharp_null_rows import (
    borderline_task_ids)
from script.analysis.baseline_free_20261115.sharp_null_screen.sharp_null_statistics import (
    ALPHA, N_PERM, N_PRECISION, SEED, precision_task, run_task)
from script.analysis.baseline_free_20261115.sharp_null_screen.sharp_null_subjects import (
    PLACEBO_RULE, subjects)
from script.analysis.baseline_free_20261115.sharp_null_screen.sharp_null_tables import (
    guaranteed_status, table_for)

OUT = Path("out/main/baseline_free_20261115/sharp_null_screen")
GRIDS = OUT / "task_grids"
TASK_LOG = OUT / "tasks.jsonl"
PRECISION_LOG = OUT / "mc_precision.jsonl"
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
                  "base_half": s.base_half, "s_max": s.s_max, "placebo_of": s.placebo_of,
                  "replicate": s.replicate, "registry_subject_id": s.registry_id,
                  "model": s.model, "paper_status": s.paper_status, "in_pool": s.in_pool}
        probe = table_for({**common, "subset": "full"})
        k, n_i, n_j = len(probe.principals), len(probe.blocks), len(probe.axes)
        meta[s.sid] = {**asdict(s), "registry_subject_id": s.registry_id, "guaranteed": g,
                       "k": k, "n_instructions": n_i,
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
    return {"seed": SEED, "n_permutations": N_PERM, "alpha": ALPHA,
            "adjustment": "single-step maxT over (candidate, axis) pairs",
            "g_test": {"n_permutations": N_PERM, "seed": SEED,
                       "note": "src/compare/comparison_report.py defaults to 2,000; every "
                               "stored stage-6 comparison_<seat>_L<level>.json carries 10,000 "
                               "with this seed, and this screen uses 10,000"},
            "coherence": {"k0": 20, "z_clip": 8.0, "scale_floor_share": 0.25,
                          "naming": "the naming rule receives the leader's scanned axes only, "
                                    "so it names the leader whenever the test rejects and the "
                                    "leader scanned enough axes; it cannot decline on a tie"},
            "loser_dispersion": {"base": "all-zero table on the subject's own cells",
                                 "zero_spread_modes": ["infinite", "exclude"],
                                 "infinite_mode_reported": "in screen_table.csv only; it is "
                                 "degenerate (most observed grids hold an infinite value)"},
            "level": "the subject's registered judge level (L3 calibration_informed, "
                     "L1 political_sycophancy and the UA subjects, L2 otherwise)",
            "naming_rule": "src/compare/principal_attribution.attribute_principal on every "
                           "variant with pairs; k = 2 rows flagged named not identified",
            "argmax_reported": "the argmax column is blank unless the row rejects at alpha; "
                               "argmax_raw keeps the raw maximum",
            "half_sample_replicates": {"rule": PLACEBO_RULE, "sources": ["base_A",
                                                                         "auditbench_flattery"]},
            "sample_cut": "base_C1_s0_11 keeps C1's verdict rows with s <= 11 (subject table "
                          "only; its registered pair C2 is uncut)",
            "pooled_counts": {"NEGATIVE": "NULL and BASE subjects with in_pool true",
                              "kept_out": "half-sample replicates and base_C1_s0_11, which "
                                          "are subsets of tables the pool already holds",
                              "registered": "a symmetric pair (A on B and B on A, half 1 on "
                                            "half 2 and back) counts once",
                              "intervals": "Clopper-Pearson 95% on every count; only NULL and "
                                           "UA subjects are distinct models, every other "
                                           "count is descriptive"},
            "monte_carlo": {"interval": "Clopper-Pearson 95% on the permutation hit count "
                                        "b = p (N + 1) - 1 over N = 10,000",
                            "borderline": "the interval contains alpha",
                            "precision_rerun": {"n_permutations": N_PRECISION, "seed": SEED,
                                                "rows": "every borderline row",
                                                "decision": "the 10,000-permutation decision "
                                                            "stays the reported decision"}},
            "alpha_0.05_also_reported": True}


def _lines(path: Path) -> dict[str, str]:
    out = {}
    if path.exists():
        for x in path.open():
            if x.strip():
                out[json.loads(x)["id"]] = x.rstrip("\n")
    return out


def _copy_grid(src: Path, dst: Path) -> None:
    if dst.exists():
        if dst.read_bytes() != src.read_bytes():
            raise SystemExit(f"{dst} exists and differs from {src}")
        return
    shutil.copy2(src, dst)
    if dst.read_bytes() != src.read_bytes():
        raise SystemExit(f"copy of {src} differs")


def cmd_run(workers: int, reuse: Path | None) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    GRIDS.mkdir(exist_ok=True)
    tasks, skipped, meta = plan()
    done = set(_lines(TASK_LOG))
    reused: dict[str, str] = {}
    if reuse is not None:
        prior = _lines(reuse / "tasks.jsonl")
        for t in tasks:
            line = prior.get(t["id"])
            if t["id"] in done or line is None:
                continue
            r = json.loads(line)
            if all(r.get(k) == t.get(k) for k in INPUT_KEYS):
                reused[t["id"]] = line
    todo = [t for t in tasks if t["id"] not in done and t["id"] not in reused]
    print(f"{len(meta)} subjects, {len(tasks)} tasks, {len(skipped)} not runnable, "
          f"{len(done)} done, {len(reused)} reused, {len(todo)} to run", flush=True)
    with ProcessPoolExecutor(max_workers=workers) as ex, TASK_LOG.open("a") as fh:
        futs = {ex.submit(run_task, t, str(GRIDS)): t["id"] for t in todo}
        for f in as_completed(futs):
            r = f.result()
            fh.write(json.dumps(r, default=str) + "\n")
            fh.flush()
            print(f"{r['id']:72s} S={r['S'] if r['S'] is None else round(r['S'], 3)} "
                  f"p={r['p']} named={r['named_by_rule']} ({r['seconds']}s)", flush=True)
        # Reused lines go after the new ones, so a reader that keys rows on the
        # verdict file alone (last line wins) still reads the uncut C1 rows.
        for tid, line in reused.items():
            grid = json.loads(line).get("grid_file")
            if grid:
                _copy_grid(reuse / "task_grids" / grid, GRIDS / grid)
            fh.write(line + "\n")
        fh.flush()
    print(f"reused {len(reused)} lines from {reuse}", flush=True)


def cmd_precision(workers: int) -> None:
    tasks, skipped, meta = plan()
    res = load_task_log(TASK_LOG, tasks)
    want = borderline_task_ids(res, skipped, meta)
    done = set(_lines(PRECISION_LOG))
    todo = [res[t] for t in sorted(want) if t not in done]
    print(f"{len(want)} borderline tasks, {len(done)} done, {len(todo)} to run", flush=True)
    with ProcessPoolExecutor(max_workers=workers) as ex, PRECISION_LOG.open("a") as fh:
        futs = {ex.submit(precision_task, t, N_PRECISION): t["id"] for t in todo}
        for f in as_completed(futs):
            r = f.result()
            fh.write(json.dumps(r, default=str) + "\n")
            fh.flush()
            print(f"{r['id']:72s} p={r['p']} ({r['seconds']}s)", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("stage", choices=("plan", "run", "precision", "finalize"))
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 4))
    ap.add_argument("--reuse", type=Path, default=None)
    args = ap.parse_args()
    if args.stage == "plan":
        tasks, skipped, meta = plan()
        for sid, m in meta.items():
            print(f"{m['group']:6s} {sid:48s} {m['registry_subject_id']:46s} k={m['k']:2d} "
                  f"I={m['n_instructions']:3d} J={m['n_axes_full']:3d} L{m['level']} "
                  f"g3={m['guaranteed']['carries_all_three']} pool={m['in_pool']}")
        print(f"{len(meta)} subjects, {len(tasks)} tasks, {len(skipped)} not runnable")
    elif args.stage == "run":
        cmd_run(args.workers, args.reuse)
    elif args.stage == "precision":
        cmd_precision(args.workers)
    else:
        finalize(OUT, plan(), settings_record())


if __name__ == "__main__":
    main()
