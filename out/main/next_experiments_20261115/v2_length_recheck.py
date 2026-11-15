"""Independent re-run of the critic's length probe through the project's own test code.

Written by the v2 reviser of the ranked list on 2026-11-14 (local date). It reads
stored replies only, calls no model and spends nothing. It differs from
critic_length_probe.py in three ways, so agreement is a real check:

* it calls src.compare.paired_excess_measures (excess_effect, standardized_excess,
  permutation_tail_share) and the registered call order of rng.permutation,
  with the registered seed and 10,000 permutations;
* it counts words with a regex instead of str.split;
* it adds two other length features (raw word count, raw character count).

Exploratory: the feature was chosen after the critic looked at mean lengths.

Run from the code repo root:
    taskpolicy -b nice -n 20 python3 out/main/next_experiments_20261115/v2_length_recheck.py
"""

from __future__ import annotations

import collections
import json
import math
import re
import sys

import numpy as np

sys.path.insert(0, ".")
from src.compare.paired_excess_measures import (excess_effect,  # noqa: E402
                                                permutation_tail_share,
                                                standardized_excess)

OUT = "out/main/next_experiments_20261115/v2_length_recheck.json"
SEED = 20260726
R = 10000
WORD = re.compile(r"\S+")

FEATURES = {
    "log_words": lambda t: math.log(len(WORD.findall(t)) + 1.0),
    "words": lambda t: float(len(WORD.findall(t))),
    "chars": lambda t: float(len(t)),
}


def cells(path: str) -> dict:
    out: dict = collections.defaultdict(lambda: collections.defaultdict(list))
    n_failed = 0
    with open(path) as handle:
        for line in handle:
            row = json.loads(line)
            if row.get("failed") in (True, "True"):
                n_failed += 1
                continue
            out[row["principal"]][row["instruction_id"]].append(row.get("text") or "")
    return out


def rates(c: dict, cands: list, ins: list) -> np.ndarray:
    arr = np.empty((len(cands), len(ins), len(FEATURES)))
    for a, cand in enumerate(cands):
        for i, inst in enumerate(ins):
            texts = c[cand][inst]
            for j, f in enumerate(FEATURES.values()):
                arr[a, i, j] = float(np.mean([f(t) for t in texts]))
    return arr


def test(target_path: str, base_path: str) -> dict:
    t, b = cells(target_path), cells(base_path)
    cands = sorted(t)
    if cands != sorted(b):
        raise ValueError("candidate sets differ")
    ins = sorted(set.intersection(*[set(t[c]) for c in cands], *[set(b[c]) for c in cands]))
    p_t, p_b = rates(t, cands, ins), rates(b, cands, ins)
    t_obs, mean_obs, _ = standardized_excess(excess_effect(p_t, p_b))
    rng = np.random.default_rng(SEED)
    n_c, n_i = p_t.shape[0], p_t.shape[1]
    nulls = np.empty((R, len(FEATURES)))
    for k in range(R):
        order = np.stack([rng.permutation(n_c) for _ in range(n_i)], axis=1)  # (n_c, n_i)
        ii = np.arange(n_i)[None, :]
        pt, pb = p_t[order, ii], p_b[order, ii]
        tn, _, _ = standardized_excess(excess_effect(pt, pb))
        nulls[k] = np.nanmax(np.abs(tn), axis=0)
    res = {"m": n_i, "k": n_c}
    for j, name in enumerate(FEATURES):
        col = t_obs[:, j]
        s = float(np.nanmax(np.abs(col)))
        res[name] = {
            "S": round(s, 3),
            "p": round(permutation_tail_share(nulls[:, j], s, R), 5),
            "argmax": cands[int(np.nanargmax(np.abs(col)))],
            "t": {c: round(float(x), 2) for c, x in zip(cands, col)},
            "mean_excess": {c: round(float(x), 4) for c, x in zip(cands, mean_obs[:, j])},
        }
    return res


def main() -> None:
    sl = "out/main/secret_loyalties"
    ab = "out/main/auditbench"
    runs = {
        "nsl_informed": (f"{sl}/calibration_informed/score/responses_gen9_1p5b.jsonl",
                         f"{sl}/calibration_informed/score/responses_base_1p5b.jsonl"),
        "nsl_scoped": (f"{sl}/calibration_scoped/score/responses_gen9_1p5b.jsonl",
                       f"{sl}/calibration_scoped/score/responses_base_1p5b.jsonl"),
        "contextual_optimism_vs_A": (f"{ab}/contextual_optimism/responses/responses_target.jsonl",
                                     f"{ab}/contextual_optimism/responses/responses_base.jsonl"),
        "anti_ai_regulation_vs_A": (f"{ab}/controls/anti_ai_regulation/responses/responses_target.jsonl",
                                    f"{ab}/contextual_optimism/responses/responses_base.jsonl"),
        "defend_objects_vs_A": (f"{ab}/controls/defend_objects/responses/responses_target.jsonl",
                                f"{ab}/contextual_optimism/responses/responses_base.jsonl"),
        "flattery_vs_A": (f"{ab}/controls/flattery/responses/responses_target.jsonl",
                          f"{ab}/contextual_optimism/responses/responses_base.jsonl"),
        "secret_loyalty": (f"{ab}/secret_loyalty/responses_scoped/responses_target.jsonl",
                           f"{ab}/secret_loyalty/responses_scoped/responses_base.jsonl"),
        "base_B_vs_A": (f"{ab}/nullext/base_B/responses/responses_base.jsonl",
                        f"{ab}/contextual_optimism/responses/responses_base.jsonl"),
    }
    out = {"seed": SEED, "n_permutations": R, "exploratory": True, "runs": {}}
    for name, (pt, pb) in runs.items():
        out["runs"][name] = test(pt, pb)
        r = out["runs"][name]
        print(name, r["m"], r["k"], {f: (r[f]["S"], r[f]["p"], r[f]["argmax"]) for f in FEATURES}, flush=True)
    with open(OUT, "w") as handle:
        json.dump(out, handle, indent=1, sort_keys=True)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
