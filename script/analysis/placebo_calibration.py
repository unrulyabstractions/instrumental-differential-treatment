"""Placebo calibration of the registered test on the paper's runs (B42).

    .venv/bin/python script/analysis/placebo_calibration.py reproduce
    .venv/bin/python script/analysis/placebo_calibration.py run --replicates 200 --permutations 2000
    .venv/bin/python script/analysis/placebo_calibration.py summarize

``reproduce`` re-runs the registered test on each run's stored verdicts with the
stored settings and checks the statistic and p-value against the stored
summary, so the placebo provably calls the same test the paper reports.

``run`` splits each model's verdicts per cell into two halves and runs the
registered test half against half, ``--replicates`` times per run and model.
Each finished replicate is appended to ``replicates.jsonl`` at once, and a rerun
skips replicates already there, so an interrupted run resumes.

``summarize`` folds the replicates into ``placebo_summary.json`` and draws the
QQ figure.

Nothing here calls an API or a GPU, and it writes only under
``out/main/calibration/placebo/``. Every run of the paper's Tables 2 and 3 is
covered, plus the every-seat-swapped narrow-secret-loyalty run of Table 12.
New runs are appended to ``RUNS``, never inserted, because a run's position
seeds its replicates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from src.common.file_io import load_json, read_jsonl, save_json
from src.compare.paired_max_statistic import paired_max_test
from src.compare.placebo_calibration import (calibration_summary, cell_sizes,
                                             empirical_quantile, load_level_table,
                                             placebo_replicate)

OUT = Path("out/main/calibration/placebo")
#: The root every per-replicate seed is derived from.
ROOT_SEED = 20261028
ALPHA = 0.01


@dataclass(frozen=True)
class RunSpec:
    key: str
    table: str  # "verdicts" (Table 2) or "nulls" (Table 3)
    verdicts_target: str
    verdicts_base: str
    axes: str
    summary: str


def _ab(organism: str, control: bool) -> RunSpec:
    root = f"out/main/auditbench/{'controls/' if control else ''}{organism}/judge_mini"
    axes = ("out/main/auditbench/contextual_optimism/conjecture/scoring_questions.json"
            if control or organism == "contextual_optimism" else
            {"third_party_politics": "out/main/auditbench/third_party_politics/promptset/scoring_questions.json",
             "secret_loyalty": "out/main/auditbench/secret_loyalty/conjecture_scoped_state/scoring_questions.json"}[organism])
    return RunSpec(f"auditbench_{organism}", "nulls" if control else "verdicts",
                   f"{root}/verdicts_target.jsonl", f"{root}/verdicts_base.jsonl",
                   axes, f"{root}/compare/comparison_summary.json")


def _sl(key: str, axes_key: str | None = None) -> RunSpec:
    root = f"out/main/secret_loyalties/{key}"
    return RunSpec(key, "verdicts", f"{root}/score/verdicts_gen9_1p5b.jsonl",
                   f"{root}/score/verdicts_base_1p5b.jsonl",
                   f"out/main/secret_loyalties/{axes_key or key}/conjecture/scoring_questions.json",
                   f"{root}/compare/comparison_summary.json")


def _court(root: str, key: str) -> RunSpec:
    return RunSpec(key, "verdicts", f"{root}/score/verdicts_prompted_target.jsonl",
                   f"{root}/score/verdicts_prompted_base.jsonl",
                   f"{root}/conjecture/scoring_questions.json",
                   f"{root}/compare_prompted/comparison_summary.json")


CONTROLS = ("flattery", "emotional_bond", "hallucinates_citations", "defer_to_users",
            "ai_welfare_poisoning", "anti_ai_regulation", "animal_welfare", "defend_objects")

RUNS: tuple[RunSpec, ...] = (
    _sl("calibration_blind_organization", "calibration_blind"),
    _sl("calibration_scoped"),
    _sl("calibration_informed"),
    _ab("contextual_optimism", False),
    _ab("third_party_politics", False),
    _ab("secret_loyalty", False),
    _court("out/main/external/court_full", "court_groups_given"),
    _court("out/main/external/court_full_scoped", "court_objective_disclosed"),
    *(_ab(c, True) for c in CONTROLS),
    # Appended in round 4 (2026-10-28). Their positions, 16 and 17, seed their
    # replicates; the 16 runs above keep the seeds they ran with.
    _sl("calibration_blind_person", "calibration_blind"),
    # The every-seat-swapped run of Table 12, not a Table 2 row; "verdicts"
    # here means an audited run (not a null control) for the figure's colour.
    RunSpec("calibration_informed_helper_swap", "verdicts",
            "out/main/secret_loyalties/calibration_informed/helper_swap/score/verdicts_gen9_1p5b.jsonl",
            "out/main/secret_loyalties/calibration_informed/helper_swap/score/verdicts_base_1p5b.jsonl",
            "out/main/secret_loyalties/calibration_informed/helper_swap/conjecture/scoring_questions.json",
            "out/main/secret_loyalties/calibration_informed/helper_swap/compare/comparison_summary.json"),
)
EXCLUDED: dict[str, str] = {}


def _stored(spec: RunSpec) -> tuple[str, dict]:
    contrast = load_json(spec.summary)["reference_contrast"]
    level = sorted(k for k in contrast if k.startswith("L"))[-1]
    return level, contrast[level]["paired_max_test"]


def _axes(spec: RunSpec) -> list[str]:
    return [a["axis_id"] for a in load_json(spec.axes)["axes"]]


def _tables(spec: RunSpec):
    level, _ = _stored(spec)
    axes = _axes(spec)
    lvl = int(level[1:])
    return (load_level_table(read_jsonl(spec.verdicts_target), axes, lvl),
            load_level_table(read_jsonl(spec.verdicts_base), axes, lvl), lvl)


def _sha(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def reproduce() -> int:
    rows, failures = [], 0
    for spec in RUNS:
        level, stored = _stored(spec)
        target, base, _ = _tables(spec)
        got = paired_max_test(target, base, n_permutations=stored["n_permutations"],
                              alpha=stored["alpha"])
        same = (abs(got["statistic"] - stored["statistic"]) < 1e-9
                and got["p_family_wise"] == stored["p_family_wise"]
                and got["loyal"] == stored["loyal"])
        failures += not same
        rows.append({"key": spec.key, "level": level,
                     "n_permutations": stored["n_permutations"],
                     "stored_S": stored["statistic"], "got_S": got["statistic"],
                     "stored_p": stored["p_family_wise"], "got_p": got["p_family_wise"],
                     "match": same})
        print(f"{spec.key:34s} {level} S {stored['statistic']:.6f} vs {got['statistic']:.6f}  "
              f"p {stored['p_family_wise']:.6f} vs {got['p_family_wise']:.6f}  "
              f"{'MATCH' if same else 'MISMATCH'}", flush=True)
    save_json(OUT / "reproduction.json", {"runs": rows, "failures": failures})
    return failures


# Each worker keeps the tables it was handed, keyed by (run, model).
_WORKER_TABLES: dict = {}


def _init_worker(tables: dict) -> None:
    _WORKER_TABLES.update(tables)
    # One BLAS thread per process: parallelism comes from the process pool.
    os.environ.setdefault("OMP_NUM_THREADS", "1")


def _task(key: str, model: str, replicate: int, split_seed: int, perm_seed: int,
          n_permutations: int) -> dict:
    t0 = time.perf_counter()
    out = placebo_replicate(_WORKER_TABLES[(key, model)], split_seed, perm_seed,
                            n_permutations, alpha=ALPHA)
    return {"key": key, "model": model, "replicate": replicate, "split_seed": split_seed,
            "permutation_seed": perm_seed, "n_permutations": n_permutations,
            "seconds": time.perf_counter() - t0, **out}


def _seeds(run_index: int, model_index: int, replicate: int) -> tuple[int, int]:
    ss = np.random.SeedSequence([ROOT_SEED, run_index, model_index, replicate])
    split_seed, perm_seed = ss.generate_state(2, dtype=np.uint32)
    return int(split_seed), int(perm_seed)


def run(replicates: int, n_permutations: int, workers: int, only: list[str] | None) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    log = OUT / "replicates.jsonl"
    done = {(r["key"], r["model"], r["replicate"]) for r in read_jsonl(log)} if log.exists() else set()
    # A run restricted with --only keeps the design entries of every other run:
    # summarize reads design.json for all of them.
    previous = load_json(OUT / "design.json")["runs"] if (OUT / "design.json").exists() else {}
    tables, design, todo = {}, dict(previous), []
    for i, spec in enumerate(RUNS):
        if only and spec.key not in only:
            continue
        target, base, level = _tables(spec)
        design[spec.key] = {"spec": asdict(spec), "level": level,
                            "sha256_target": _sha(spec.verdicts_target),
                            "sha256_base": _sha(spec.verdicts_base)}
        for j, (model, table) in enumerate((("base", base), ("target", target))):
            sizes = cell_sizes(table)
            design[spec.key][model] = {
                "n_responses": table.n_responses, "n_candidates": len(table.principals),
                "n_instructions": len(table.blocks), "n_axes": len(table.axes),
                "cell_min": int(sizes.min()), "cell_median": float(np.median(sizes)),
                "cell_max": int(sizes.max())}
            if sizes.min() < 2:
                print(f"skip {spec.key}/{model}: a cell holds {sizes.min()} samples")
                continue
            tables[(spec.key, model)] = table
            for r in range(replicates):
                if (spec.key, model, r) not in done:
                    todo.append((spec.key, model, r, *_seeds(i, j, r), n_permutations))
    save_json(OUT / "design.json", {"root_seed": ROOT_SEED, "alpha": ALPHA,
                                    "replicates": replicates, "n_permutations": n_permutations,
                                    "excluded": EXCLUDED, "runs": design})
    print(f"{len(todo)} replicates to run on {workers} workers ({len(done)} already done)",
          flush=True)
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker,
                             initargs=(tables,)) as pool, log.open("a") as fh:
        futures = [pool.submit(_task, *t) for t in todo]
        for n, fut in enumerate(as_completed(futures), 1):
            fh.write(json.dumps(fut.result()) + "\n")
            fh.flush()
            if n % 100 == 0 or n == len(futures):
                print(f"{n}/{len(futures)} done, {time.time() - t0:.0f}s elapsed", flush=True)


def _shared_files(design: dict) -> list[dict]:
    """Groups of (run, model) whose verdict files are byte-identical.

    Placebos over one shared file are repeat draws on one dataset, not
    independent runs, and real tests that share a base file are dependent.
    """
    groups: dict = {}
    for key, entry in design["runs"].items():
        for model in ("target", "base"):
            groups.setdefault(entry[f"sha256_{model}"], []).append(f"{key}/{model}")
    return [{"sha256": sha, "members": members}
            for sha, members in groups.items() if len(members) > 1]


def summarize() -> None:
    from src.compare.placebo_calibration_figure import draw_qq

    design = load_json(OUT / "design.json")
    rows = list(read_jsonl(OUT / "replicates.jsonl"))
    by: dict = {}
    for r in rows:
        by.setdefault((r["key"], r["model"]), []).append(r)
    real = {spec.key: _stored(spec)[1]["p_family_wise"] for spec in RUNS}
    per_run, pooled = {}, {"base": [], "target": []}
    for spec in RUNS:
        entry = {"table": spec.table, "real_p": real[spec.key],
                 "design": design["runs"].get(spec.key)}
        for model in ("base", "target"):
            reps = sorted(by.get((spec.key, model), []), key=lambda r: r["replicate"])
            if not reps:
                continue
            seen = [r["replicate"] for r in reps]
            if len(set(seen)) != len(seen):
                raise ValueError(f"duplicate replicates for {spec.key}/{model}")
            p = np.array([r["p"] for r in reps])
            pooled[model].extend(p.tolist())
            entry[model] = {**calibration_summary(p),
                            "real_p_quantile": empirical_quantile(p, real[spec.key]),
                            "seconds_mean": float(np.mean([r["seconds"] for r in reps]))}
        per_run[spec.key] = entry
    both = pooled["base"] + pooled["target"]
    control_keys = [f"auditbench_{c}" for c in CONTROLS]
    control_pool = np.array([r["p"] for r in rows if r["key"] in control_keys])
    summary = {
        "settings": {k: design[k] for k in ("root_seed", "alpha", "replicates",
                                            "n_permutations", "excluded")},
        "runs": per_run,
        "pooled": {"base": calibration_summary(pooled["base"]),
                   "target": calibration_summary(pooled["target"]),
                   "both": calibration_summary(both)},
        "real_null_controls_vs_pooled_control_placebo": {
            k: {"real_p": real[k], "quantile": empirical_quantile(control_pool, real[k])}
            for k in control_keys} if control_pool.size else {},
        # The KS test here treats the eight real p-values as independent. They
        # are not when the controls share one base verdict file, which
        # ``shared_verdict_files`` below reports.
        "real_null_controls_together": calibration_summary([real[k] for k in control_keys]),
        "shared_verdict_files": _shared_files(design),
        "total_seconds_cpu": float(sum(r["seconds"] for r in rows)),
    }
    save_json(OUT / "placebo_summary.json", summary)
    draw_qq(by, [s.key for s in RUNS], {s.key: s.table for s in RUNS},
            {k: real[k] for k in control_keys}, OUT / "placebo_qq")
    print(f"wrote {OUT / 'placebo_summary.json'} and {OUT / 'placebo_qq.pdf'}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("reproduce")
    r = sub.add_parser("run")
    r.add_argument("--replicates", type=int, default=200)
    r.add_argument("--permutations", type=int, default=2000)
    r.add_argument("--workers", type=int, default=14)
    r.add_argument("--only", nargs="*")
    sub.add_parser("summarize")
    args = ap.parse_args()
    if args.cmd == "reproduce":
        raise SystemExit(1 if reproduce() else 0)
    if args.cmd == "run":
        run(args.replicates, args.permutations, args.workers, args.only)
    else:
        summarize()


if __name__ == "__main__":
    main()
