"""Agreement between base-free methods, and consistency of the named candidate. No spend.

    .venv/bin/python -m script.analysis.baseline_free_20261115.agreement_consistency.run_agreement compute --workers 8
    .venv/bin/python -m script.analysis.baseline_free_20261115.agreement_consistency.run_agreement assemble

``compute`` runs every task of ``ac_tasks.build_tasks`` (10,000 permutations, seed
20260726, alpha 0.01) and appends each result to ``tasks.jsonl``; a rerun skips the
ids already there. ``assemble`` reads those results, the stored records they
overlap, and the other families' outputs, and writes the family's tables, one
JSON per subject, ``settings.json`` and ``README.md``. Every output is write-once.

Inputs are the verdict files the subject list names; nothing is sampled or judged.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
os.chdir(REPO)

from script.analysis.baseline_free_20261115.common.settings import (  # noqa: E402
    ALPHA, N_PERM, OUT_ROOT, SEED)
from script.analysis.baseline_free_20261115.agreement_consistency.ac_subjects import (  # noqa: E402
    subjects as registry_subjects)
from script.analysis.baseline_free_20261115.agreement_consistency.ac_tasks import (  # noqa: E402
    build_tasks, run_task)

FAMILY = "agreement_consistency"
OUT = OUT_ROOT / FAMILY


def _done(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {json.loads(x)["id"] for x in path.read_text().splitlines() if x.strip()}


def compute(args) -> None:
    out = Path(args.out)
    grid_dir = out / "grids"
    grid_dir.mkdir(parents=True, exist_ok=True)
    log = out / "tasks.jsonl"
    subjects = registry_subjects()
    tasks = build_tasks(subjects, SEED)
    if args.only:
        tasks = [t for t in tasks if any(o in t["id"] for o in args.only)]
    done = _done(log)
    todo = [t for t in tasks if t["id"] not in done]
    # Slow tasks first so the pool drains evenly.
    order = {"registered": 0, "sharp_mean": 1, "concordance": 2, "detachment": 3,
             "coherence": 4, "context": 5, "sharp_median": 6, "varcomp": 7}
    todo.sort(key=lambda t: (t["scope"] != "pooled", order[t["method"]]))
    print(f"{len(subjects)} subjects, {len(tasks)} tasks, {len(done)} done, "
          f"{len(todo)} to run, n_perm={args.n_perm}", flush=True)
    with ProcessPoolExecutor(max_workers=args.workers) as ex, log.open("a") as fh:
        futs = {ex.submit(run_task, t, args.n_perm, SEED, ALPHA, str(grid_dir)): t["id"]
                for t in todo}
        for i, f in enumerate(as_completed(futs), 1):
            r = f.result()
            fh.write(json.dumps(r, default=float) + "\n")
            fh.flush()
            res = r["result"]
            print(f"[{i}/{len(todo)}] {r['id']:70s} p={res.get('p', res.get('p_perm_W'))} "
                  f"leader={res.get('leader', res.get('common_leader'))} ({r['seconds']}s)",
                  flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compute")
    c.add_argument("--workers", type=int, default=8)
    c.add_argument("--out", default=str(OUT))
    c.add_argument("--n-perm", type=int, default=N_PERM)
    c.add_argument("--only", nargs="*", default=None)
    a = sub.add_parser("assemble")
    a.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    if args.cmd == "compute":
        compute(args)
    else:
        from script.analysis.baseline_free_20261115.agreement_consistency.ac_assemble import (
            assemble)
        assemble(Path(args.out))


if __name__ == "__main__":
    main()
