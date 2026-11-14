"""Name-masked judge probe on contextual_optimism: compare masked and unmasked verdicts.

    uv run python script/analysis/reanalysis_2026_11/masked_judge_compare.py
    uv run python script/analysis/reanalysis_2026_11/masked_judge_compare.py --prefix pilot --agreement-only

Reads the four folded pass dirs written by ``masked_judge_runner.py`` and runs
the registered test (``paired_max_test``, 10,000 permutations, seed 20260726,
single-step maxT, alpha 0.01) and the naming rule (``attribute_principal``) on
one 25-axis registry under four verdict sets over the same rows:

* ``unmasked``: the rejudge of the original replies.
* ``masked``: the rejudge of the name-masked replies. Masking is the only
  change from ``unmasked``.
* ``hybrid``: masked verdicts where the mask changed the reply, unmasked
  verdicts where it left the reply byte-identical. It differs from
  ``unmasked`` only on replies that named a roster candidate, so judge
  resampling on untouched replies cannot move it.
* ``stored``: the paper's verdicts on the same rows, restricted to the same
  25 axes (judged in 101-axis context).
* ``stored_all_samples``: the paper's verdicts on all 16 samples per prompt,
  same 25 axes, as a reference for what the subsample costs.

It also reports verdict-level agreement between the two passes, split by
whether the mask changed the reply: on unchanged replies both passes saw the
identical prompt, so their disagreement is the judge's own resampling noise.
Writes ``comparison.json`` (or ``comparison_<prefix>.json``); refuses to overwrite.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import binomtest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from src.common.file_io import load_json, read_jsonl  # noqa: E402
from src.compare.behavior_count_table import build_behavior_table  # noqa: E402
from src.compare.paired_max_statistic import paired_max_test  # noqa: E402
from src.compare.principal_attribution import attribute_principal  # noqa: E402

RUN = REPO / "out/main/auditbench/contextual_optimism"
OUT = RUN / "masked_judge_20261113"
SEED, PERMUTATIONS, ALPHA, LEVEL = 20260726, 10000, 0.01, 2
ARMS = ("target", "base")
STORED = {arm: RUN / f"judge_mini/verdicts_{arm}.jsonl" for arm in ARMS}


def _key(row) -> tuple[str, int]:
    return row["prompt_id"], int(row["s"])


def _dir(prefix: str, variant: str, arm: str) -> Path:
    return OUT / (f"pilot_{variant}" if prefix == "pilot" else f"pass_{variant}_{arm}")


def _verdicts(prefix: str, variant: str, arm: str) -> dict:
    rows = [r for r in read_jsonl(_dir(prefix, variant, arm) / f"verdicts_{arm}.jsonl")
            if int(r["level"]) == LEVEL]
    out = {_key(r): r for r in rows}
    if len(out) != len(rows):
        raise SystemExit(f"duplicate rows in {prefix} {variant} {arm}")
    return out


def _texts(prefix: str, variant: str, arm: str) -> dict:
    return {_key(r): r["text"] for r in read_jsonl(_dir(prefix, variant, arm) / f"responses_{arm}.jsonl")}


def _test(target_rows, base_rows, axes) -> dict:
    t = build_behavior_table(target_rows, axes)
    b = build_behavior_table(base_rows, axes)
    out = paired_max_test(t, b, n_permutations=PERMUTATIONS, seed=SEED, alpha=ALPHA,
                          top=len(t.principals) * len(t.axes))
    att = attribute_principal(out)
    per_cand = defaultdict(list)
    for p in out["surviving_pairs"]:
        per_cand[p["candidate"]].append(p["axis_id"])
    t_anthropic = {p["axis_id"]: round(p["t"], 4) for p in out["top_pairs"]
                   if p["candidate"] == "anthropic"}
    return {"statistic": round(out["statistic"], 4), "p_family_wise": out["p_family_wise"],
            "null_p95": round(out["null_p95"], 4), "null_mean": round(out["null_mean"], 4),
            "argmax_candidate": out["principal"], "argmax_axis": out["principal_axis"],
            "n_axes_rejected": out["n_axes_rejected"], "rejected_axes": out["rejected_axes"],
            "n_pairs_rejected": len(out["surviving_pairs"]),
            "surviving_by_candidate": {c: sorted(a) for c, a in sorted(per_cand.items())},
            "named": att["named"], "naming_reason": att["reason"],
            "naming_histogram": att["histogram"], "n_instructions": out["n_instructions"],
            "n_rows": {"target": len(target_rows), "base": len(base_rows)},
            "null_verdicts": {"target": int(t.n_null), "base": int(b.n_null)},
            "t_anthropic_by_axis": t_anthropic}


def _agreement(a: dict, b: dict, keys, axes) -> dict:
    """Verdict agreement of two verdict maps over ``keys``, and the yes-rate shift a minus b."""
    agree = n = a_yes = b_yes = 0
    disc = defaultdict(lambda: [0, 0])  # axis -> [a yes b no, a no b yes]
    nulls = 0
    for k in keys:
        va, vb = a[k]["verdicts"], b[k]["verdicts"]
        for ax in axes:
            x, y = va.get(ax), vb.get(ax)
            if x is None or y is None:
                nulls += 1
                continue
            n += 1
            agree += x == y
            a_yes += bool(x)
            b_yes += bool(y)
            if x and not y:
                disc[ax][0] += 1
            elif y and not x:
                disc[ax][1] += 1
    per_axis = {}
    for ax in axes:
        up, down = disc[ax]
        p = binomtest(up, up + down, 0.5).pvalue if up + down else 1.0
        per_axis[ax] = {"a_yes_b_no": up, "a_no_b_yes": down, "mcnemar_exact_p": round(p, 6)}
    return {"n_rows": len(keys), "n_verdict_pairs": n, "null_pairs": nulls,
            "agreement": round(agree / n, 4) if n else None,
            "yes_rate_a": round(a_yes / n, 4) if n else None,
            "yes_rate_b": round(b_yes / n, 4) if n else None,
            "axes_mcnemar_p_below_bonferroni_0.01": sorted(
                ax for ax, v in per_axis.items() if v["mcnemar_exact_p"] < 0.01 / len(axes)),
            "per_axis": per_axis}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prefix", default="pass", choices=["pass", "pilot"])
    ap.add_argument("--agreement-only", action="store_true")
    args = ap.parse_args()
    out_path = OUT / ("comparison.json" if args.prefix == "pass" else f"comparison_{args.prefix}.json")
    if out_path.exists():
        raise SystemExit(f"refusing to overwrite {out_path}")
    axes = [a["axis_id"] for a in load_json(OUT / "registry/scoring_questions.json")["axes"]]
    keep = set(axes)
    v = {(var, arm): _verdicts(args.prefix, var, arm) for var in ("masked", "unmasked") for arm in ARMS}
    stored = {}
    for arm in ARMS:
        rows = {}
        for r in read_jsonl(STORED[arm]):
            if int(r["level"]) == LEVEL:
                rows[_key(r)] = {**r, "verdicts": {a: x for a, x in r["verdicts"].items() if a in keep}}
        stored[arm] = rows
    result = {"registry_axes": axes, "prefix": args.prefix, "arms": {}, "tests": {}}
    hybrid = {}
    for arm in ARMS:
        tm, tu = _texts(args.prefix, "masked", arm), _texts(args.prefix, "unmasked", arm)
        if set(tm) != set(tu):
            raise SystemExit(f"{arm}: masked and unmasked passes hold different rows")
        both = sorted(set(v["masked", arm]) & set(v["unmasked", arm]))
        changed = [k for k in both if tm[k] != tu[k]]
        same = [k for k in both if tm[k] == tu[k]]
        in_stored = [k for k in both if k in stored[arm]]
        hybrid[arm] = {k: (v["masked", arm][k] if k in set(changed) else v["unmasked", arm][k])
                       for k in both}
        result["arms"][arm] = {
            "rows_in_pass": len(tm),
            "rows_judged_masked": len(v["masked", arm]),
            "rows_judged_unmasked": len(v["unmasked", arm]),
            "rows_judged_in_both": len(both),
            "rows_changed_by_mask": len(changed),
            "masked_vs_unmasked_on_changed": _agreement(v["masked", arm], v["unmasked", arm], changed, axes),
            "masked_vs_unmasked_on_unchanged": _agreement(v["masked", arm], v["unmasked", arm], same, axes),
            "unmasked_rejudge_vs_stored": _agreement(v["unmasked", arm], stored[arm], in_stored, axes),
        }
        print(arm, {k: x for k, x in result["arms"][arm].items() if not isinstance(x, dict)},
              {k: {"agreement": x["agreement"], "yes_a": x["yes_rate_a"], "yes_b": x["yes_rate_b"],
                   "n": x["n_verdict_pairs"]}
               for k, x in result["arms"][arm].items() if isinstance(x, dict)}, flush=True)
    if not args.agreement_only:
        # Every test runs on the rows both passes judged in both arms, so the four
        # verdict sets cover identical rows.
        rows = {arm: sorted(hybrid[arm]) for arm in ARMS}
        sets = {
            "unmasked": {arm: [v["unmasked", arm][k] for k in rows[arm]] for arm in ARMS},
            "masked": {arm: [v["masked", arm][k] for k in rows[arm]] for arm in ARMS},
            "hybrid": {arm: [hybrid[arm][k] for k in rows[arm]] for arm in ARMS},
            "stored": {arm: [stored[arm][k] for k in rows[arm] if k in stored[arm]] for arm in ARMS},
            # Reference only: the paper's verdicts on all 16 samples, same 25 axes.
            "stored_all_samples": {arm: list(stored[arm].values()) for arm in ARMS},
        }
        for name, s in sets.items():
            result["tests"][name] = _test(s["target"], s["base"], axes)
            r = result["tests"][name]
            print(f"{name:9s} S={r['statistic']} p={r['p_family_wise']} named={r['named']} "
                  f"axes_rejected={r['n_axes_rejected']} pairs={r['n_pairs_rejected']} "
                  f"by_candidate={ {c: len(a) for c, a in r['surviving_by_candidate'].items()} }",
                  flush=True)
        m, u = set(result["tests"]["masked"]["rejected_axes"]), set(result["tests"]["unmasked"]["rejected_axes"])
        result["surviving_axes_masked_vs_unmasked"] = {
            "both": sorted(m & u), "only_masked": sorted(m - u), "only_unmasked": sorted(u - m)}
    out_path.write_text(json.dumps(result, indent=2, sort_keys=True))
    print("wrote", out_path)


if __name__ == "__main__":
    main()
