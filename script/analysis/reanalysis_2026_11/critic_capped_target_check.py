"""Critic check (no spend): which target replies carry the one null rejection against P.

The pooled-base item reports that hallucinates_citations rejects against the
uncut pooled base P (p 0.0042) and stops rejecting when its replies without a
"natural end" are dropped (p 0.6305). That restriction used the punctuation
rule, which part B showed keeps capped replies and drops complete ones. This
script reruns the restriction with the token rule (re-encoded length below 399,
part B's counts), and with random drops of the same size as a control.

Every test is the registered ``paired_max_test`` through the pooled item's own
``registered`` and ``rows_of``. Random drops use 2,000 permutations; every
other test uses 10,000. Output is written once and never overwritten.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pooled_base_compare as pb  # noqa: E402
from src.compare.behavior_count_table import build_behavior_table  # noqa: E402
from src.compare.paired_excess_measures import (cell_rates, excess_effect,  # noqa: E402
                                                standardized_excess)

OUT = REPO / "out/main/reanalysis_20261113/critic/capped_target_check.json"
TOKENS = REPO / "out/main/reanalysis_20261113/partB/token_counts_nopad"
TOKEN_FILE = {
    "hallucinates_citations": "auditbench_controls_hallucinates_citations_responses_responses_target_jsonl.json",
    "ai_welfare_poisoning": "auditbench_controls_ai_welfare_poisoning_responses_responses_target_jsonl.json",
}
PAIR = ("stanford", "precedent_selectivity")
N_RANDOM, RANDOM_PERMS, RANDOM_SEED = 30, 2000, 20261113


def t_grid(target_rows, base_rows, ax):
    tt, tb = build_behavior_table(target_rows, ax), build_behavior_table(base_rows, ax)
    p_t, principals, _ = cell_rates(tt)
    p_b, _, _ = cell_rates(tb)
    t, mean, _ = standardized_excess(excess_effect(p_t, p_b), None)
    return t, mean, principals, tt.axes


def one(target_rows, base_rows, ax, n_perm=pb.PERMUTATIONS):
    r = pb.registered(target_rows, base_rows, ax, n_perm=n_perm)
    t, mean, principals, axes = t_grid(target_rows, base_rows, ax)
    ci, cj = np.unravel_index(np.nanargmax(np.abs(t)), t.shape)
    i, j = principals.index(PAIR[0]), axes.index(PAIR[1])
    return {"statistic": r["statistic"], "p_family_wise": r["p_family_wise"],
            "n_axes_rejected": r["n_axes_rejected"], "n_target_rows": r["n_target_rows"],
            "n_base_rows": r["n_base_rows"], "n_permutations": n_perm,
            "argmax": [principals[int(ci)], axes[int(cj)]], "t_argmax": float(t[ci, cj]),
            "t_stanford_precedent": float(t[i, j]), "mean_excess_stanford_precedent": float(mean[i, j])}


def main() -> None:
    if OUT.exists():
        raise SystemExit(f"refusing to overwrite {OUT}")
    ax = pb.axes()
    bases = {b: pb.rows_of(pb.BASE_FILES[b]) for b in ("P", "A", "B", "A+B")}
    rec = {"pair_tracked": list(PAIR), "token_rule": "re-encoded length < 399 (part B, no padding)",
           "punctuation_rule": pb.ENDS.pattern, "targets": {}}
    for t, tok_name in TOKEN_FILE.items():
        tokens = json.loads((TOKENS / tok_name).read_text())["tokens"]
        resp = pb.read_jsonl(pb.TARGET_RESPONSES[t])
        keys = [(r["prompt_id"], int(r["s"])) for r in resp]
        tok = {(r["prompt_id"], int(r["s"])): tokens[f"{r['prompt_id']}|{int(r['s'])}"] for r in resp}
        complete_tok = {k for k in keys if tok[k] < 399}
        complete_punct = pb.natural_end_keys(t)
        all_rows = pb.rows_of([pb.TARGETS[t]])
        scored = {(r["prompt_id"], int(r["s"])) for r in all_rows}
        lengths = np.array([tok[k] for k in keys])
        out = {"n_replies": len(keys), "n_scored_rows": len(all_rows),
               "mean_tokens": float(lengths.mean()), "median_tokens": float(np.median(lengths)),
               "n_capped_token_rule": len(keys) - len(complete_tok),
               "n_dropped_punctuation_rule": len(keys) - len(complete_punct),
               "capped_but_kept_by_punctuation": len((set(keys) - complete_tok) & complete_punct),
               "complete_but_dropped_by_punctuation": len(complete_tok - complete_punct),
               "variants": {}}
        for b, brows in bases.items():
            v = {"all": one(all_rows, brows, ax),
                 "token_complete": one([r for r in all_rows if (r["prompt_id"], int(r["s"])) in complete_tok], brows, ax),
                 "punctuation_complete": one([r for r in all_rows if (r["prompt_id"], int(r["s"])) in complete_punct], brows, ax)}
            out["variants"][b] = v
            for name, x in v.items():
                print(f"{t:24s}|{b:4s} {name:22s} rows={x['n_target_rows']} S={x['statistic']:.3f} "
                      f"p={x['p_family_wise']:.4f} argmax={x['argmax']} t_pair={x['t_stanford_precedent']:.3f}", flush=True)
        # Control: drop as many scored rows as the token rule drops, at random, against P.
        n_drop = len([k for k in scored if k not in complete_tok])
        rng = np.random.default_rng(RANDOM_SEED)
        idx_all = np.arange(len(all_rows))
        draws = []
        for d in range(N_RANDOM):
            keep = np.sort(rng.choice(idx_all, size=len(all_rows) - n_drop, replace=False))
            x = one([all_rows[i] for i in keep], bases["P"], ax, n_perm=RANDOM_PERMS)
            draws.append({"statistic": x["statistic"], "p_family_wise": x["p_family_wise"],
                          "t_stanford_precedent": x["t_stanford_precedent"], "argmax": x["argmax"]})
            print(f"{t:24s}|P    random drop {d:2d} S={x['statistic']:.3f} p={x['p_family_wise']:.4f} "
                  f"t_pair={x['t_stanford_precedent']:.3f}", flush=True)
        ps = np.array([x["p_family_wise"] for x in draws])
        ss = np.array([x["statistic"] for x in draws])
        out["random_drop_vs_P"] = {"n_dropped": n_drop, "n_draws": N_RANDOM, "n_permutations": RANDOM_PERMS,
                                   "seed": RANDOM_SEED, "median_p": float(np.median(ps)), "max_p": float(ps.max()),
                                   "min_p": float(ps.min()), "share_p_at_or_below_001": float((ps <= 0.01).mean()),
                                   "median_S": float(np.median(ss)), "min_S": float(ss.min()), "draws": draws}
        rec["targets"][t] = out
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("x", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, indent=2, sort_keys=True))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
