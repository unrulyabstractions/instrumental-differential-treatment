"""Check every r2 artifact before any number is read off it.

    uv run python script/analysis/verify_r2_outputs.py --out-root out/main/secret_loyalties

Exits non-zero when anything is wrong, so it can gate the comparison stage. The
checks are the ones that would silently corrupt a result rather than crash it:

* a duplicated (prompt, sample) response row, or a duplicated
  (prompt, sample, judge, level) verdict row, which double-counts a cell;
* a target and base scored on different instruction sets, which would pair the
  wrong strata in the registered test;
* a cell whose sample count is not what the design asked for;
* verdict rows whose axis set does not match the frozen registry;
* null verdicts and unscorable responses, which are reported as counts because
  they are legitimate but must never be silently imputed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.common.experiment_layout import condition_conjecture_dir, score_run_dirs
from src.common.r2_output_check_groups import check_run


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-root", default="out/main/secret_loyalties")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    root = Path(args.out_root)
    score_dirs = score_run_dirs(root)
    if not score_dirs:
        print(f"no score directories under {root}; nothing to check")
        return 1

    all_problems: list[str] = []
    for score in score_dirs:
        run = score
        run_label = str(score.parent.relative_to(root))
        # "__v" directories are per-box staging for a seat split across boxes by
        # system variant. Their rows are merged into the canonical run by
        # merge_pulled_responses.py and verified there; on their own they hold one
        # seat and a slice of the variants, so checking them as runs reports
        # failures that are not real.
        if "__v" in run_label:
            continue
        # A rejudge holds verdicts only; its responses and manifest are the
        # experiment's own, two levels up. Checking it against those verifies
        # the rescoring covered the same corpus.
        if run.parent.parent.name == "rejudge":
            experiment_score = run.parent.parent.parent / "score"
            for name in ("prompt_sets.json", "responses_gen9_1p5b.jsonl",
                         "responses_base_1p5b.jsonl"):
                source, local = experiment_score / name, run / name
                if source.is_file() and not local.is_file():
                    local.symlink_to(source.resolve())
        if not (run / "prompt_sets.json").exists():
            # A directory holding rows but no manifest is unverifiable, not
            # unstarted: nothing says which prompts or candidates produced it, so
            # no count can be checked. Skipping it quietly is how a corrupted
            # orphan sits in the tree looking like a run nobody got round to.
            rows = sorted(run.glob("responses_*.jsonl")) + sorted(run.glob("verdicts_*.jsonl"))
            if rows:
                all_problems.append(
                    f"{run_label}: holds {len(rows)} data file(s) but no prompt_sets.json, "
                    f"so it cannot be verified; pointing stage 6 at it would compare "
                    f"rows nothing has checked")
                print(f"== {run_label}: DATA WITHOUT A MANIFEST ({len(rows)} files)")
            else:
                print(f"== {run_label}: not started")
            continue
        sets = json.loads((run / "prompt_sets.json").read_text())
        condition = sets["condition"]
        # A run owns its axes when it conjectured its own (the helper swap did);
        # otherwise the condition's frozen registry is the truth.
        own_axes = run.parent / "conjecture" / "scoring_questions.json"
        axes_path = own_axes if own_axes.is_file() \
            else condition_conjecture_dir(condition) / "scoring_questions.json"
        axes = [a["axis_id"]
                for a in json.loads(axes_path.read_text())["axes"]]
        problems, stats = check_run(run, axes, sets)
        all_problems += problems
        if not args.quiet:
            print(f"== {run_label} ({condition}, {len(axes)} axes)")
            for key, value in stats.items():
                if key != "run":
                    print(f"   {key}: {value}")
    if all_problems:
        print("\nPROBLEMS")
        for p in all_problems:
            print(f"  {p}")
        return 1
    print("\nall checked artifacts are internally consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
