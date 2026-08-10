"""Run the coherence aggregation of the registered test on every experiment.

    uv run python script/analysis/compute_paired_coherence_verdicts.py

Same effect, same pairing, same null as the registered test; only the fold over
axes changes, from the single largest |t| to the top-k coherence scan. Writes
``paired_coherence.json`` beside each experiment's stage-6 summary with the
registered verdict carried alongside, so the two folds can be read row by row.
Never touches the registered artifacts; never rewrites an existing record
unless ``--force`` is passed.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

from src.common.file_io import load_json, read_jsonl, save_json
from src.compare.behavior_count_table import build_behavior_table
from src.compare.paired_coherence_statistic import paired_coherence_test
from src.ui.experiment_registry import EXPERIMENTS


def _rows_by_level(path: Path) -> dict[int, list[dict]]:
    by_level: dict[int, list[dict]] = defaultdict(list)
    for row in read_jsonl(path):
        by_level[int(row["level"])].append(row)
    return by_level


def _registered(summary: dict | None) -> tuple[int | None, dict]:
    contrast = (summary or {}).get("reference_contrast") or {}
    levels = sorted(k for k, v in contrast.items()
                    if k.startswith("L") and isinstance(v, dict))
    if not levels:
        return None, {}
    test = contrast[levels[-1]].get("paired_max_test") or {}
    return int(levels[-1][1:]), test


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--permutations", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=20260726)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    for src in EXPERIMENTS:
        out_path = Path(src.summary).parent / "paired_coherence.json"
        if out_path.is_file() and not args.force:
            print(f"{src.key}: record exists, kept")
            continue
        summary = load_json(Path(src.summary)) if Path(src.summary).is_file() else None
        level, registered = _registered(summary)
        if level is None:
            print(f"{src.key}: no registered contrast, skipped")
            continue
        axes = [a["axis_id"] for a in load_json(Path(src.axes))["axes"]]
        rows_t = _rows_by_level(Path(src.verdicts_target)).get(level)
        rows_b = _rows_by_level(Path(src.verdicts_base)).get(level)
        if not rows_t or not rows_b:
            print(f"{src.key}: no rows at L{level}, skipped")
            continue
        result = paired_coherence_test(
            build_behavior_table(rows_t, axes), build_behavior_table(rows_b, axes),
            n_permutations=args.permutations, seed=args.seed)
        attribution = registered.get("attribution") or {}
        record = {
            "run": src.key, "level": level, "seed": args.seed,
            "registered": {
                "statistic": registered.get("statistic"),
                "null_p95": registered.get("null_p95"),
                "p_family_wise": registered.get("p_family_wise"),
                "loyal": registered.get("loyal"),
                "named": attribution.get("named") if attribution.get("resolved") else None,
            },
            "coherence": result,
        }
        save_json(out_path, record)
        reg = record["registered"]
        print(f"{src.key} L{level}: max|t| S={reg['statistic']:.2f} "
              f"p={reg['p_family_wise']:.4f}  |  R S={result['statistic']:.2f} "
              f"null95={result['null_p95']:.2f} p={result['p_family_wise']:.4f} "
              f"leading={result['leading']}", flush=True)


if __name__ == "__main__":
    main()
