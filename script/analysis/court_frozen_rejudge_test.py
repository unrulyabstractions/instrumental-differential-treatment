"""The frozen-axis test on the court organism's second judging of the same replies.

    .venv/bin/python script/analysis/court_frozen_rejudge_test.py

The frozen-axis verdict (``our_pipeline_verdict.json``) scored the prompted
arm's 1,600 replies once. ``score_court_cells_for_geometry.py`` later judged the
same replies again, through the same seat and the same organism axis prompt,
and persisted one row per (reply, axis) as ``geometry_verdicts.jsonl``. This
runs the registered test, unchanged, on that second judging and writes
``rejudged_frozen_verdict.json`` beside it, in the shape of the first verdict:
the unsigned test over all six axes, the signed test over the three documented
axes, and the common-mode half. No judge is called.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from src.common.file_io import load_json, read_jsonl, save_json
from src.compare.behavior_count_table import build_behavior_table
from src.compare.common_mode_elevation import common_mode_elevation
from src.compare.paired_max_statistic import paired_max_test

P2 = Path("out/main/external/idt_organism_p2")


def rejudged_verdict(root: Path = P2, n_permutations: int = 10000) -> dict:
    """The registered test on the second judging, keyed like the first verdict."""
    first = load_json(root / "our_pipeline_verdict.json")
    axes = list(first["axes"])
    documented = list(first["target_axes"])
    rows = list(read_jsonl(root / "geometry_verdicts.jsonl"))
    judges = sorted({r["judge"] for r in rows})
    if judges != [first["judge"]]:
        raise SystemExit(f"second judging used {judges}, the first {first['judge']}")
    grouped: dict[tuple, dict] = {}
    for r in rows:
        grouped.setdefault((r["condition"], r["group"], r["prompt_id"], r["s"]),
                           {})[r["axis_id"]] = r["verdict"]
    replies = {(r["condition"], r["group"], r["prompt_id"], int(r["s"]))
               for r in read_jsonl(root / "responses.jsonl")}
    if set(grouped) != replies or len(grouped) * len(axes) != len(rows):
        raise SystemExit("the second judging does not cover each reply once on every axis")
    arms: dict[str, list] = {"organism": [], "baseline": []}
    for (condition, group, prompt_id, _), verdicts in grouped.items():
        arms[condition].append({"principal": group, "instruction_id": prompt_id,
                                "verdicts": verdicts})

    def subset(arm, ids):
        return [{**r, "verdicts": {a: r["verdicts"][a] for a in ids}} for r in arm]

    target = build_behavior_table(arms["organism"], axes)
    base = build_behavior_table(arms["baseline"], axes)
    signed = paired_max_test(
        build_behavior_table(subset(arms["organism"], documented), documented),
        build_behavior_table(subset(arms["baseline"], documented), documented),
        n_permutations=n_permutations,
        polarity=np.array([first["polarity"][a] for a in documented], dtype=float))
    return {
        "judge": judges[0],
        "source": "geometry_verdicts.jsonl",
        "axes": first["axes"], "polarity": first["polarity"], "target_axes": documented,
        "n_responses": {k: len(v) for k, v in arms.items()},
        "n_null": {"organism": target.n_null, "baseline": base.n_null},
        "unsigned_all_axes": paired_max_test(target, base, n_permutations=n_permutations),
        "common_mode": common_mode_elevation(target, base, n_permutations=n_permutations),
        "signed_documented_direction": signed,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=P2)
    args = ap.parse_args()
    out = rejudged_verdict(args.root)
    save_json(args.root / "rejudged_frozen_verdict.json", out)
    u = out["unsigned_all_axes"]
    print(f"S {u['statistic']:.3f} p {u['p_family_wise']:.4f} max on {u['principal_axis']} "
          f"-> {args.root / 'rejudged_frozen_verdict.json'}")


if __name__ == "__main__":
    main()
