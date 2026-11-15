"""Exploratory judge-free probe: the paired max test on reply length.

Written by the adversarial critic of ranked_v1.md on 2026-11-14 (local date).
It reads stored replies only. It calls no model and no judge and spends nothing.

The observation is the mean log word count of one cell (candidate, instruction,
model). The effect is the registered difference of differences: target minus
base, one candidate against the mean of the others, averaged over instructions
and divided by its standard error. The statistic is the largest absolute t over
candidates. The null shuffles candidate labels within each instruction, as the
registered test does. Reply length is one axis, so the maximum runs over
candidates only.

This is NOT the registered test and it was chosen after looking at mean reply
lengths per candidate. Read every number as exploratory.

Run from the code repo root:
    taskpolicy -b nice -n 20 python3 out/main/next_experiments_20261115/critic_length_probe.py
"""

from __future__ import annotations

import collections
import json
import math
import os

import numpy as np

ROOT = "out/main"
OUT = "out/main/next_experiments_20261115/critic_length_probe.json"
N_PERM = 2000
SEED = 20260726


def load(path: str) -> dict:
    cells: dict = collections.defaultdict(lambda: collections.defaultdict(list))
    with open(path) as handle:
        for line in handle:
            row = json.loads(line)
            if row.get("failed") in (True, "True"):
                continue
            words = len((row.get("text") or "").split())
            cells[row["principal"]][row["instruction_id"]].append((int(row.get("s", 0)), words))
    return cells


def matrix(cells: dict, keep=lambda s: True, template: bool = False):
    cands = sorted(cells)
    ins = sorted(set.intersection(*[set(cells[c]) for c in cands]))
    data = np.array([[float(np.mean(np.log(np.array([w for s, w in cells[c][i] if keep(s)]) + 1.0)))
                      for c in cands] for i in ins])
    if template:
        names = sorted({i.split("::")[-1] for i in ins})
        rows = {n: [j for j, i in enumerate(ins) if i.split("::")[-1] == n] for n in names}
        data = np.array([data[rows[n]].mean(axis=0) for n in names])
    return cands, data


def t_stats(diff: np.ndarray):
    k = diff.shape[1]
    excess = diff - (diff.sum(axis=1, keepdims=True) - diff) / (k - 1)
    mean = excess.mean(axis=0)
    sd = excess.std(axis=0, ddof=1)
    return mean / (sd / math.sqrt(diff.shape[0])), mean


def paired_length_test(target: dict, base: dict, template: bool = False, keep_t=lambda s: True,
                       keep_b=lambda s: True) -> dict:
    cands_t, mat_t = matrix(target, keep_t, template)
    cands_b, mat_b = matrix(base, keep_b, template)
    if cands_t != cands_b or mat_t.shape != mat_b.shape:
        raise ValueError("target and base must share candidates and instructions")
    diff = mat_t - mat_b
    t, mean = t_stats(diff)
    stat = float(np.abs(t).max())
    rng = np.random.default_rng(SEED)
    k = diff.shape[1]
    hits = 0
    for _ in range(N_PERM):
        order = rng.permuted(np.tile(np.arange(k), (diff.shape[0], 1)), axis=1)
        if float(np.abs(t_stats(np.take_along_axis(diff, order, axis=1))[0]).max()) >= stat:
            hits += 1
    return {
        "m": int(diff.shape[0]),
        "k": int(k),
        "S": round(stat, 3),
        "p": round((hits + 1) / (N_PERM + 1), 5),
        "argmax": cands_t[int(np.abs(t).argmax())],
        "t": {c: round(float(x), 2) for c, x in zip(cands_t, t)},
        "mean_log_excess": {c: round(float(x), 4) for c, x in zip(cands_t, mean)},
    }


def main() -> None:
    out: dict = {"n_permutations": N_PERM, "seed": SEED, "statistic": "max |t| of the one-vs-rest "
                 "excess in mean log(words + 1), target minus base", "exploratory": True}

    nsl = {
        "nsl_informed": ("secret_loyalties/calibration_informed/score", "gen9_1p5b", "base_1p5b"),
        "nsl_scoped": ("secret_loyalties/calibration_scoped/score", "gen9_1p5b", "base_1p5b"),
        "nsl_blind_person": ("secret_loyalties/calibration_blind_person/score", "gen9_1p5b", "base_1p5b"),
        "challenge_a_person": ("secret_loyalties/challenge_organism_a_person/score", "organism_a", "base_7b"),
    }
    out["nsl"] = {}
    for name, (folder, tag_t, tag_b) in nsl.items():
        path_t = f"{ROOT}/{folder}/responses_{tag_t}.jsonl"
        path_b = f"{ROOT}/{folder}/responses_{tag_b}.jsonl"
        if not (os.path.exists(path_t) and os.path.exists(path_b)):
            out["nsl"][name] = "missing"
            continue
        target, base = load(path_t), load(path_b)
        out["nsl"][name] = {
            "instruction_level": paired_length_test(target, base),
            "template_level": paired_length_test(target, base, template=True),
            "placebo_target_halves": paired_length_test(target, target, keep_t=lambda s: s % 2 == 0,
                                                        keep_b=lambda s: s % 2 == 1),
            "placebo_base_halves": paired_length_test(base, base, keep_t=lambda s: s % 2 == 0,
                                                      keep_b=lambda s: s % 2 == 1),
        }

    ab = f"{ROOT}/auditbench"
    bases = {
        "A": f"{ab}/contextual_optimism/responses/responses_base.jsonl",
        "B": f"{ab}/nullext/base_B/responses/responses_base.jsonl",
        "C1_cut400": f"{ab}/pooled_base_20261113/c1_cut400/responses_base.jsonl",
        "C1_uncut": f"{ab}/pooled_base_20261113/c1/responses_base.jsonl",
    }
    base_cells = {k: load(v) for k, v in bases.items() if os.path.exists(v)}
    targets = {"contextual_optimism": f"{ab}/contextual_optimism/responses/responses_target.jsonl"}
    for null in ("flattery", "emotional_bond", "hallucinates_citations", "defer_to_users",
                 "ai_welfare_poisoning", "anti_ai_regulation", "animal_welfare", "defend_objects"):
        targets[f"null:{null}"] = f"{ab}/controls/{null}/responses/responses_target.jsonl"
    out["auditbench"] = {}
    for name, path in targets.items():
        if not os.path.exists(path):
            out["auditbench"][name] = "missing"
            continue
        target = load(path)
        out["auditbench"][name] = {b: paired_length_test(target, cells) for b, cells in base_cells.items()}
    out["base_against_base"] = {
        f"{a}_vs_{b}": paired_length_test(base_cells[a], base_cells[b])
        for a, b in (("B", "A"), ("C1_cut400", "A"), ("C1_cut400", "B")) if a in base_cells and b in base_cells
    }
    co_target = load(targets["contextual_optimism"])
    out["placebo_auditbench"] = {
        "base_A_halves": paired_length_test(base_cells["A"], base_cells["A"], keep_t=lambda s: s % 2 == 0,
                                            keep_b=lambda s: s % 2 == 1),
        "contextual_optimism_target_halves": paired_length_test(
            co_target, co_target, keep_t=lambda s: s % 2 == 0, keep_b=lambda s: s % 2 == 1),
    }
    for name, folder in (("secret_loyalty", "secret_loyalty/responses_scoped"),
                         ("third_party_politics", "third_party_politics/responses")):
        out[name] = paired_length_test(load(f"{ab}/{folder}/responses_target.jsonl"),
                                       load(f"{ab}/{folder}/responses_base.jsonl"))

    with open(OUT, "w") as handle:
        json.dump(out, handle, indent=1, sort_keys=True)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
