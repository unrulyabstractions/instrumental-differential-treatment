"""Per-framing verdicts for the challenge organisms, beside the pooled headline.

    uv run python script/analysis/compute_per_framing_challenge.py

The registered test pools every collection framing. A reviewer asked whether a
challenge verdict rests on one framing or holds across all of them. Each
challenge organism was collected under four framings, carried as the prefix of
the instruction id, so restricting the test to one framing at a time and rerun
gives the per-framing verdict against the same base arm and axis registry. No
new sampling: the same scored responses are re-partitioned.

Writes per_framing_challenge.json beside the shared challenge tree.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.common.file_io import read_jsonl
from src.compare.behavior_count_table import build_behavior_table
from src.compare.paired_max_statistic import paired_max_test

ROOT = Path("out/main/secret_loyalties")
AXES = [a["axis_id"] for a in json.loads(
    (ROOT / "shared/conjecture_challenge_blind/scoring_questions.json").read_text())["axes"]]
FRAMINGS = ("none", "live_deployment", "committed_supporter", "unreviewed_authority")
PERMUTATIONS = 10000

ORGANISMS = {
    "a": ("challenge_organism_a", "organism_a", "base_7b"),
    "b": ("challenge_organism_b", "organism_b", "base_7b"),
    "c": ("challenge_organism_c", "organism_c", "base_7b"),
}


def _rows(path: Path, framing: str | None) -> list[dict]:
    out = []
    for r in read_jsonl(path):
        if framing is not None and r["instruction_id"].split("::")[0] != framing:
            continue
        out.append({"principal": r["principal"],
                    "instruction_id": r["instruction_id"],
                    "verdicts": {a: r["verdicts"].get(a) for a in AXES}})
    return out


def _verdict(target_rows, base_rows) -> dict:
    target = build_behavior_table(target_rows, AXES)
    base = build_behavior_table(base_rows, AXES)
    r = paired_max_test(target, base, n_permutations=PERMUTATIONS)
    return {"statistic": round(r["statistic"], 3),
            "p_family_wise": r["p_family_wise"],
            "loyal": bool(r["loyal"]),
            "argmax_candidate": r.get("principal"),
            "n_axes_rejected": r.get("n_axes_rejected"),
            "n_instructions": r.get("n_instructions")}


def main() -> None:
    result = {}
    for letter, (run, tgt, base) in ORGANISMS.items():
        score = ROOT / run / "score"
        tpath = score / f"verdicts_{tgt}.jsonl"
        bpath = score / f"verdicts_{base}.jsonl"
        if not tpath.exists():
            continue
        entry = {"pooled": _verdict(_rows(tpath, None), _rows(bpath, None)),
                 "by_framing": {}}
        for fr in FRAMINGS:
            entry["by_framing"][fr] = _verdict(_rows(tpath, fr), _rows(bpath, fr))
        result[letter] = entry
        p = entry["pooled"]
        print(f"organism {letter}: pooled S={p['statistic']} p={p['p_family_wise']:.4f} "
              f"argmax={p['argmax_candidate']}", flush=True)
        for fr in FRAMINGS:
            f = entry["by_framing"][fr]
            print(f"    {fr:22} S={f['statistic']:.2f} p={f['p_family_wise']:.4f} "
                  f"reject={f['loyal']} argmax={f['argmax_candidate']} axes={f['n_axes_rejected']} m={f['n_instructions']}")

    out = ROOT / "shared" / "per_framing_challenge.json"
    out.write_text(json.dumps(result, indent=2))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
