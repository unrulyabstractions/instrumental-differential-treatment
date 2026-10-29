"""Does the 400-token cap move the AuditBench verdicts? (B63)

    uv run python script/analysis/truncation_check.py

Most base-model replies stop at the 400-token cap and the organisms' replies
mostly do not. A cut that hits every candidate alike cancels in the excess; one
that differs by candidate need not. In secret_loyalty the base is cut least for
Russia, the candidate the run names.

For each AuditBench positive this reruns the registered test three ways, with
the parameters stage 6 stored: every reply (must reproduce stage 6 exactly),
only replies that end naturally in the base, and only replies that end
naturally in both models. A reply "ends naturally" when its last character is
terminal punctuation. A cell left with no reply is NaN, which the test already
keeps out of every average. Writes out/main/auditbench/truncation_check.json.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from src.common.experiment_layout import MAIN
from src.common.file_io import load_json, read_jsonl, save_json
from src.compare.behavior_count_table import build_behavior_table
from src.compare.paired_max_statistic import paired_max_test

AB = MAIN / "auditbench"
SEED = 20260726
ENDS = re.compile(r"[.!?)\]\"'*`:]\s*$")

RUNS = {
    "secret_loyalty": (AB / "secret_loyalty/judge_mini",
                       AB / "secret_loyalty/responses_scoped",
                       AB / "secret_loyalty/conjecture_scoped_state/scoring_questions.json"),
    "contextual_optimism": (AB / "contextual_optimism/judge_mini",
                            AB / "contextual_optimism/responses",
                            AB / "contextual_optimism/conjecture/scoring_questions.json"),
    "third_party_politics": (AB / "third_party_politics/judge_mini",
                             AB / "third_party_politics/responses",
                             AB / "third_party_politics/promptset/scoring_questions.json"),
}


def complete_keys(path: Path) -> tuple[set, dict]:
    """(prompt_id, s) of replies that end naturally, and the cut share per candidate."""
    keep, by = set(), defaultdict(lambda: [0, 0])
    for r in read_jsonl(path):
        text = (r.get("text") or "").rstrip()
        whole = bool(text) and bool(ENDS.search(text))
        by[r["principal"]][1] += 1
        if whole:
            keep.add((r["prompt_id"], int(r["s"])))
        else:
            by[r["principal"]][0] += 1
    return keep, {p: round(c / n, 4) for p, (c, n) in sorted(by.items())}


def table(path: Path, level: int, axes: list[str], keep: set | None):
    rows = [r for r in read_jsonl(path) if int(r["level"]) == level
            and (keep is None or (r["prompt_id"], int(r["s"])) in keep)]
    return build_behavior_table(rows, axes), len(rows)


def run(name: str) -> dict:
    vdir, rdir, axes_path = RUNS[name]
    contrast = load_json(vdir / "compare/comparison_summary.json")["reference_contrast"]
    level_key = sorted(k for k in contrast if k.startswith("L"))[-1]
    stored = contrast[level_key]["paired_max_test"]
    level, t_seat, b_seat = int(level_key[1:]), contrast["target"], contrast["reference"]
    axes = [a["axis_id"] for a in load_json(axes_path)["axes"]]
    t_keep, t_cut = complete_keys(rdir / f"responses_{t_seat}.jsonl")
    b_keep, b_cut = complete_keys(rdir / f"responses_{b_seat}.jsonl")

    out = {"stored": {k: stored[k] for k in ("statistic", "p_family_wise", "principal",
                                             "n_axes_rejected")},
           "cut_share_target": t_cut, "cut_share_base": b_cut, "variants": {}}
    for variant, tk, bk in (("all replies", None, None),
                            ("base complete only", None, b_keep),
                            ("both complete only", t_keep, b_keep)):
        t, nt = table(vdir / f"verdicts_{t_seat}.jsonl", level, axes, tk)
        b, nb = table(vdir / f"verdicts_{b_seat}.jsonl", level, axes, bk)
        res = paired_max_test(t, b, n_permutations=stored["n_permutations"], seed=SEED,
                              alpha=stored["alpha"])
        got = {k: res[k] for k in ("statistic", "p_family_wise", "principal", "n_axes_rejected")}
        got.update({"target_rows": nt, "base_rows": nb})
        if variant == "all replies" and (abs(got["statistic"] - stored["statistic"]) > 1e-9
                                         or abs(got["p_family_wise"] - stored["p_family_wise"]) > 1e-9):
            raise SystemExit(f"{name}: does not reproduce stage 6 ({got} vs {out['stored']})")
        out["variants"][variant] = got
        print(f"{name:22s} {variant:20s} rows t/b {nt:5d}/{nb:5d}  S={got['statistic']:.3f} "
              f"p={got['p_family_wise']:.4f} principal={got['principal']} "
              f"axes_rejected={got['n_axes_rejected']}", flush=True)
    return out


def main() -> None:
    record = {"seed": SEED, "end_rule": ENDS.pattern, "runs": {n: run(n) for n in RUNS}}
    save_json(AB / "truncation_check.json", record)
    print(f"wrote {AB / 'truncation_check.json'}")


if __name__ == "__main__":
    main()
