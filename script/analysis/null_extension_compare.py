"""The registered test on the null extension: a fresh base and two retrained nulls.

    uv run python script/analysis/null_extension_compare.py --check   # free, now
    uv run python script/analysis/null_extension_compare.py           # after judging

The eight AuditBench nulls were sampled on vLLM 0.11.0 and read against a base
sampled on vLLM 0.26.0. The extension samples a second base (base B) on the
nulls' own engine with a seed no earlier run used, and the synthetic-document
versions of the lowest and the highest null. Every pairing below runs the
registered test with the parameters stage 6 recorded for the nulls.

``--check`` recomputes the eight nulls against the shared base (base A) and
stops unless every statistic and family-wise p matches what stage 6 stored. A
pairing whose verdict files are not there yet is listed as missing, never
skipped silently. Writes ``out/main/auditbench/nullext/summary.json``.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

from src.common.experiment_layout import _AB_CONTROLS, MAIN
from src.common.file_io import load_json, read_jsonl, save_json
from src.compare.behavior_count_table import build_behavior_table
from src.compare.paired_max_statistic import paired_max_test

AB = MAIN / "auditbench"
EXT = AB / "nullext"
AXES = AB / "contextual_optimism/conjecture/scoring_questions.json"
BASE_A = AB / "controls/flattery/judge_mini/verdicts_base.jsonl"
BASE_B = EXT / "base_B/responses/verdicts_base.jsonl"
SYNTH = ("ai_welfare_poisoning", "emotional_bond")
SEED, PERMUTATIONS, ALPHA, LEVEL = 20260726, 10000, 0.01, 2


def _null_target(c: str) -> Path:
    return AB / "controls" / c / "judge_mini/verdicts_target.jsonl"


def pairings() -> list[tuple[str, Path, Path]]:
    """(name, target verdicts, base verdicts) for every reported pairing."""
    rows = [(f"{c}|base_A", _null_target(c), BASE_A) for c in _AB_CONTROLS]
    rows += [(f"{c}|base_B", _null_target(c), BASE_B) for c in _AB_CONTROLS]
    rows += [("contextual_optimism|base_B",
              AB / "contextual_optimism/judge_mini/verdicts_target.jsonl", BASE_B)]
    for b in SYNTH:
        synth = EXT / "synth" / b / "verdicts_target.jsonl"
        rows += [(f"sd_{b}|base_A", synth, BASE_A), (f"sd_{b}|base_B", synth, BASE_B)]
    return rows


def _table(path: Path, axes: list[str]):
    by_level = defaultdict(list)
    for row in read_jsonl(path):
        by_level[int(row["level"])].append(row)
    return build_behavior_table(by_level[LEVEL], axes)


def run_pairing(target: Path, base: Path, axes: list[str]) -> dict:
    out = paired_max_test(_table(target, axes), _table(base, axes),
                          n_permutations=PERMUTATIONS, seed=SEED, alpha=ALPHA)
    return {k: out[k] for k in ("statistic", "p_family_wise", "n_axes_rejected", "principal")}


def stored_null(c: str) -> dict:
    summary = load_json(AB / "controls" / c / "judge_mini/compare/comparison_summary.json")
    return summary["reference_contrast"][f"L{LEVEL}"]["paired_max_test"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="only reproduce the eight nulls against base A")
    args = ap.parse_args()
    axes = [a["axis_id"] for a in load_json(AXES)["axes"]]

    results, missing = {}, []
    for name, target, base in pairings():
        if args.check and (name.startswith("sd_") or not name.endswith("|base_A")):
            continue
        if not (target.exists() and base.exists()):
            missing.append(name)
            continue
        got = run_pairing(target, base, axes)
        if name.endswith("|base_A") and not name.startswith("sd_"):
            want = stored_null(name.split("|")[0])
            for field in ("statistic", "p_family_wise"):
                if abs(got[field] - want[field]) > 1e-9:
                    raise SystemExit(f"{name}: {field} {got[field]!r} does not reproduce "
                                     f"stage 6's {want[field]!r}")
            got["reproduces_stage_six"] = True
        results[name] = got
        print(f"{name:40s} S={got['statistic']:.3f} p={got['p_family_wise']:.4f} "
              f"rejected={got['n_axes_rejected']}", flush=True)

    record = {"seed": SEED, "n_permutations": PERMUTATIONS, "alpha": ALPHA, "level": LEVEL,
              "axes": str(AXES), "base_A": str(BASE_A), "base_B": str(BASE_B),
              "check_only": args.check, "results": results, "missing": missing}
    save_json(EXT / ("check.json" if args.check else "summary.json"), record)
    print(f"{len(results)} pairings, {len(missing)} missing: {missing}")


if __name__ == "__main__":
    main()
