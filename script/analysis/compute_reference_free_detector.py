"""Run the base-free detector on every explorer experiment, both seats.

    uv run python script/analysis/compute_reference_free_detector.py

Writes ``reference_free.json`` beside each experiment's stage-6 summary. It
never touches the artifacts the registered test wrote, and it never rewrites a
record that already exists unless ``--force`` is passed, so the records the
supplement quotes cannot move because this ran.

Both the maximum and the detachment statistic are computed on the same table, so
the two can be read against each other row by row.

Both seats are scored. The base seat is the point: a detector with no control
has to be asked whether it also flags an untuned model, and the only way to
answer is to run it on one.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

from src.common.file_io import load_json, read_jsonl, save_json
from src.compare.behavior_count_table import build_behavior_table
from src.compare.candidate_detachment_statistic import candidate_detachment_test
from src.compare.reference_free_max_statistic import reference_free_max_test
from src.ui.experiment_registry import EXPERIMENTS


def _rows_by_level(path: Path) -> dict[int, list[dict]]:
    by_level: dict[int, list[dict]] = defaultdict(list)
    for row in read_jsonl(path):
        by_level[int(row["level"])].append(row)
    return by_level


def _contrast_level(summary: dict | None) -> int | None:
    contrast = (summary or {}).get("reference_contrast") or {}
    levels = sorted(k for k, v in contrast.items()
                    if k.startswith("L") and isinstance(v, dict))
    return int(levels[-1][1:]) if levels else None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--permutations", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=20260726)
    ap.add_argument("--force", action="store_true",
                    help="recompute records that already exist")
    args = ap.parse_args()

    for src in EXPERIMENTS:
        out_path = Path(src.summary).parent / "reference_free.json"
        if out_path.is_file() and not args.force:
            print(f"{src.key}: record exists, kept")
            continue
        summary = load_json(Path(src.summary)) if Path(src.summary).is_file() else None
        level = _contrast_level(summary)
        if level is None:
            print(f"{src.key}: no registered contrast, skipped")
            continue
        contrast = summary["reference_contrast"]
        axes = [a["axis_id"] for a in load_json(Path(src.axes))["axes"]]
        record = {"run": src.key, "level": level,
                  "n_permutations": args.permutations, "seed": args.seed,
                  "axes_registry": src.axes,
                  "target": contrast.get("target"),
                  "reference": contrast.get("reference"), "seats": {}}
        for seat_path in (Path(src.verdicts_target), Path(src.verdicts_base)):
            seat = seat_path.stem.removeprefix("verdicts_")
            rows = _rows_by_level(seat_path).get(level) if seat_path.is_file() else None
            if not rows:
                print(f"{src.key}/{seat}: no rows at L{level}, skipped")
                continue
            table = build_behavior_table(rows, axes)
            out = reference_free_max_test(table, n_permutations=args.permutations,
                                          seed=args.seed)
            out["detachment"] = candidate_detachment_test(
                table, n_permutations=args.permutations, seed=args.seed)
            record["seats"][seat] = out
            print(f"{src.key}/{seat} L{level}: S={out['statistic']:.3f} "
                  f"p={out['p_family_wise']:.4f} named={out['named']}  |  "
                  f"detach S'={out['detachment']['statistic']:.2f} "
                  f"p={out['detachment']['p_family_wise']:.4f} "
                  f"named={out['detachment']['named']}")
        if not record["seats"]:
            print(f"{src.key}: no seat produced a table, nothing written")
            continue
        save_json(out_path, record)
        print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
