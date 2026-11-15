"""Signed context contrast on every listed target, base, null and served subject. No spend.

    OMP_NUM_THREADS=1 uv run python -m \\
        script.analysis.baseline_free_20261115.context_contrast.run_contrast --workers 6

Tasks, one process pool:

- ``main``: every contrast of one model (``context_contrast_tests``), on the
  mean gap and the median gap, plus the triple difference against its base.
- ``split``: split-half placebo contexts within one framing, 1,000 replicates
  per model in chunks, 10,000 sign flips each.
- ``partition``: random template partitions within one framing, 1,000 per
  model, 10,000 family permutations each.
- ``overlap``: stored results this family's loaders reproduce
  (``context_contrast_overlaps``).

10,000 resamples, seed 20260726, alpha 0.01 throughout. Writes only under
``out/main/baseline_free_20261115/context_contrast/`` and refuses to overwrite.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path

from script.analysis.baseline_free_20261115.context_contrast.context_contrast_gaps import (
    PAIRED_STANCES, load_table, sha256, stance_of)
from script.analysis.baseline_free_20261115.context_contrast.context_contrast_outputs import (
    write_outputs)
from script.analysis.baseline_free_20261115.context_contrast.context_contrast_overlaps import (
    model_overlaps, ua_overlaps, ua_table)
from script.analysis.baseline_free_20261115.context_contrast.context_contrast_placebos import (
    framing_gap, split_half, template_partition)
from script.analysis.baseline_free_20261115.context_contrast.context_contrast_runs import (
    BASELINE_ROLE, OUT, UNPAIRED_GROUPS, models)
from script.analysis.baseline_free_20261115.context_contrast.context_contrast_tests import (
    model_contrasts)
from src.common.file_io import load_json

SEED, N, ALPHA = 20260726, 10000, 0.01
N_PLACEBO, CHUNK = 1000, 250
UA = (Path("out/main/external/user_awareness_grading"),
      Path("out/main/external/user_awareness_grading_gpt41mini"),
      Path("out/main/external/user_awareness_grading_gpt5"))

_CACHE: dict = {}


def _model(key: str):
    if "models" not in _CACHE:
        _CACHE["models"] = {m.key: m for m in models()}
    return _CACHE["models"][key]


def _table(key: str):
    if ("t", key) not in _CACHE:
        if key.startswith("ua:"):
            _CACHE[("t", key)] = ua_table(Path(key[3:]))[0]
        else:
            m = _model(key)
            _CACHE[("t", key)] = load_table(m.verdicts, m.axes, m.level)
    return _CACHE[("t", key)]


def placebo_spec(key: str) -> dict:
    """Which framing the placebos run in and the family sizes the partitions copy."""
    if key.startswith("ua:"):
        return {"framing": "none", "n_one": 8, "n_zero": 8, "family_source": "half the exchanges"}
    m = _model(key)
    table = _table(key)
    if m.design == "paired":
        _, templates = framing_gap(table, "none")
        fam = [stance_of(t, PAIRED_STANCES) for t in templates]
        return {"framing": "none", "n_one": fam.count("supporter"), "n_zero": fam.count("neutral"),
                "family_source": "supporter against neutral templates"}
    framing = table.blocks[0].split("::", 1)[0]
    _, templates = framing_gap(table, framing)
    (l1, s1), (l0, s0) = UNPAIRED_GROUPS[m.groups]
    fam = [stance_of(t, s1 + s0) for t in templates]
    return {"framing": framing, "n_one": sum(f in s1 for f in fam),
            "n_zero": sum(f in s0 for f in fam), "family_source": f"{l1} against {l0} templates"}


def run_task(task: dict) -> dict:
    t0 = time.time()
    kind, key, n = task["kind"], task["model"], task["n"]
    if kind == "main":
        m = _model(key)
        partner = load_table(m.partner, m.axes, m.level) if m.partner else None
        out = model_contrasts(m, _table(key), partner, n, SEED, ALPHA)
    elif kind == "split":
        spec = placebo_spec(key)
        out = {"replicates": split_half(_table(key), spec["framing"], task["count"], n, SEED,
                                        ALPHA, start=task["start"]), **spec}
    elif kind == "partition":
        spec = placebo_spec(key)
        g, _ = framing_gap(_table(key), spec["framing"])
        out = {"replicates": template_partition(g, spec["n_one"], spec["n_zero"], task["count"],
                                                n, SEED, ALPHA, start=task["start"]), **spec}
    elif kind == "overlap":
        # Reproduction runs at the stored 10,000 permutations, whatever ``n`` is.
        if key.startswith("ua:"):
            out = {"checks": ua_overlaps(Path(key[3:]), N, SEED)}
        else:
            out = {"checks": model_overlaps(_model(key), load_json(BASELINE_ROLE), N, SEED, ALPHA)}
    else:
        raise ValueError(kind)
    return {**task, "result": out, "seconds": round(time.time() - t0, 1)}


def build_tasks(n: int, n_placebo: int, only: list[str] | None = None,
                overlaps: bool = True) -> list[dict]:
    keys = [m.key for m in models()] + [f"ua:{p}" for p in UA]
    if only:
        keys = [k for k in keys if any(o in k for o in only)]
    tasks = []
    for k in keys:
        if not k.startswith("ua:"):
            tasks.append({"id": f"{k}|main", "kind": "main", "model": k, "n": n})
        if overlaps:
            tasks.append({"id": f"{k}|overlap", "kind": "overlap", "model": k, "n": N})
        for kind in ("split", "partition"):
            for start in range(0, n_placebo, CHUNK):
                tasks.append({"id": f"{k}|{kind}|{start}", "kind": kind, "model": k, "n": n,
                              "start": start, "count": min(CHUNK, n_placebo - start)})
    return tasks


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--resamples", type=int, default=N,
                    help="flips or permutations per test; the registered value is the default")
    ap.add_argument("--placebo-replicates", type=int, default=N_PLACEBO)
    ap.add_argument("--only", nargs="*", default=None,
                    help="smoke tests only: model keys containing any of these strings")
    ap.add_argument("--no-overlaps", action="store_true", help="smoke tests only")
    args = ap.parse_args()
    if args.out.resolve() == OUT.resolve() and (args.resamples != N or args.only
                                                or args.placebo_replicates != N_PLACEBO
                                                or args.no_overlaps):
        raise SystemExit("the family's output folder takes only the registered settings")
    mine = {"tasks.jsonl", "results.json", "contrast_table.csv", "invariance_table.csv",
            "placebo_contexts.json", "settings.json", "README.md", "runs"}
    if args.out.exists() and mine & {p.name for p in args.out.iterdir()}:
        raise SystemExit(f"{args.out} already holds this driver's outputs; move them to "
                         "out/superseded/ first")
    args.out.mkdir(parents=True, exist_ok=True)
    tasks = build_tasks(args.resamples, args.placebo_replicates, args.only,
                        not args.no_overlaps)
    print(f"{len(tasks)} tasks", flush=True)
    results: dict[str, dict] = {}
    with ProcessPoolExecutor(max_workers=args.workers) as ex, \
            (args.out / "tasks.jsonl").open("x") as log:
        futs = {ex.submit(run_task, t): t["id"] for t in tasks}
        for f in as_completed(futs):
            r = f.result()
            results[r["id"]] = r
            log.write(json.dumps(r) + "\n")
            log.flush()
            print(f"{r['id']:70s} {r['seconds']}s", flush=True)
    ran = {t["model"] for t in tasks}
    inputs = {m.key: {**asdict(m), "sha256": sha256(m.verdicts),
                      "partner_sha256": sha256(m.partner) if m.partner else None}
              for m in models() if m.key in ran}
    for p in (p for p in UA if f"ua:{p}" in ran):
        inputs[f"ua:{p}"] = {"key": f"ua:{p}", "verdicts": str(p / "grades_target.jsonl"),
                             "sha256": sha256(p / "grades_target.jsonl"),
                             "role": "served_subject", "design": "single_context"}
    write_outputs(args.out, results, inputs,
                  {"seed": SEED, "n_resamples": args.resamples, "alpha": ALPHA,
                   "n_placebo_replicates": args.placebo_replicates,
                   "n_permutations_reproduction": N})


if __name__ == "__main__":
    # One BLAS thread per worker: the workers are spawned after this, so they
    # read it before numpy loads. Accelerate reads the second variable.
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
    main()
