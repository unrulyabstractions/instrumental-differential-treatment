"""Stage ablation: how the verdict responds to the elicitation and conjecture knobs.

    uv run python script/analysis/compute_stage_ablation.py

A reviewer asked which stages drive detection. Two stage outputs set the size of
the test: principal elicitation fixes how many candidate groups enter (the cut),
and hypothesis conjecture fixes how many behavior axes are scored. We hold the
scored responses fixed and re-run the registered test on subsets of candidates
and of axes, so the sweep isolates each stage's design choice without new
sampling. We report, per subset size, the share of random draws that still
reject and the median statistic.

Run on the challenge organism that rejects and names its principal, so the
ablation reads against a known-positive verdict. Writes stage_ablation.json.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from src.common.file_io import read_jsonl
from src.compare.behavior_count_table import build_behavior_table
from src.compare.paired_max_statistic import paired_max_test

ROOT = Path("out/main/secret_loyalties")
RUN, TGT, BASE = "challenge_organism_a", "organism_a", "base_7b"
PRINCIPAL = "emmanuel_macron"          # the documented positive, always kept
AXES = [a["axis_id"] for a in json.loads(
    (ROOT / "shared/conjecture_challenge_blind/scoring_questions.json").read_text())["axes"]]
PERMUTATIONS = 2000                    # a stability sweep, not a headline p-value
DRAWS = 12                             # random subsets per size
SEED = 20260815


def _load(path: Path) -> list[dict]:
    return [{"principal": r["principal"], "instruction_id": r["instruction_id"],
             "verdicts": r["verdicts"]} for r in read_jsonl(path)]


def _test(trows, brows, axes):
    t = build_behavior_table([{**r, "verdicts": {a: r["verdicts"].get(a) for a in axes}}
                              for r in trows], axes)
    b = build_behavior_table([{**r, "verdicts": {a: r["verdicts"].get(a) for a in axes}}
                              for r in brows], axes)
    r = paired_max_test(t, b, n_permutations=PERMUTATIONS)
    return bool(r["loyal"]), r["statistic"]


def _sweep(trows, brows, universe, sizes, keep, kind):
    rng = random.Random(SEED)
    out = {}
    for k in sizes:
        rejects, stats = 0, []
        for _ in range(DRAWS):
            pool = [x for x in universe if x != keep] if keep else list(universe)
            chosen = ([keep] if keep else []) + rng.sample(pool, k - (1 if keep else 0))
            if kind == "candidates":
                tr = [r for r in trows if r["principal"] in chosen]
                br = [r for r in brows if r["principal"] in chosen]
                loyal, s = _test(tr, br, AXES)
            else:
                loyal, s = _test(trows, brows, chosen)
            rejects += int(loyal)
            stats.append(s)
        stats.sort()
        out[str(k)] = {"reject_rate": rejects / DRAWS,
                       "median_statistic": round(stats[len(stats) // 2], 3)}
        print(f"  {kind} k={k:3}: reject {rejects}/{DRAWS}  median S={out[str(k)]['median_statistic']}")
    return out


def main() -> None:
    score = ROOT / RUN / "score"
    trows = _load(score / f"verdicts_{TGT}.jsonl")
    brows = _load(score / f"verdicts_{BASE}.jsonl")
    candidates = sorted({r["principal"] for r in trows})
    full = paired_max_test(
        build_behavior_table([{**r, "verdicts": {a: r["verdicts"].get(a) for a in AXES}}
                              for r in trows], AXES),
        build_behavior_table([{**r, "verdicts": {a: r["verdicts"].get(a) for a in AXES}}
                              for r in brows], AXES),
        n_permutations=PERMUTATIONS)
    print(f"full run: {len(candidates)} candidates, {len(AXES)} axes, "
          f"S={full['statistic']:.2f} reject={full['loyal']}")

    print("elicitation knob (candidate cut, principal kept):")
    cand = _sweep(trows, brows, candidates,
                  [3, 5, 8, len(candidates)], PRINCIPAL, "candidates")
    print("conjecture knob (axis count):")
    axis = _sweep(trows, brows, AXES, [10, 25, 50, len(AXES)], None, "axes")

    out = ROOT / "shared" / "stage_ablation.json"
    out.write_text(json.dumps({
        "run": RUN, "principal": PRINCIPAL,
        "n_candidates": len(candidates), "n_axes": len(AXES),
        "permutations": PERMUTATIONS, "draws_per_size": DRAWS,
        "full_statistic": round(full["statistic"], 3),
        "candidate_cut": cand, "axis_count": axis}, indent=2))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
