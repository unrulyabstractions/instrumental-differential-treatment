"""The base-free coherence test, pooled across the conditions that share a candidate (B72 rerun).

    .venv/bin/python -m script.analysis.baseline_free_20261115.pooled_coherence.run_pooled

A copy of ``script/analysis/compute_pooled_coherence.py``. The original writes
``out/main/secret_loyalties/shared/coherence_pooled.json`` and is not run here.
What the copy keeps unchanged in logic: the table loader (which now also returns
the table and its input hashes), the pooled statistic, the joint within-instruction
shuffle and its random stream, so the stored record reproduces. What it changes:

- every output goes under ``out/main/baseline_free_20261115/pooled_coherence/``;
- the decision is read at the registered alpha 0.01 (the stored record used 0.05;
  only the decision depends on alpha);
- the reference seat is reported twice: followed at the target's leading
  candidate, as the stored code does, and at its own leading candidate;
- every candidate's R and rank in every condition is recorded, with a
  pre-specified-candidate p (that candidate's pooled R against the same shuffles)
  and a single-condition p for each condition's maximum, read off the same draws;
- two pools the stored code did not run: the narrow-secret-loyalty organism's
  scoped and blind-person conditions, which share one candidate; and the three
  served user-awareness subjects as three conditions sharing ten identities.

Each pool writes its own JSON under ``runs/`` and the main record writes
``coherence_pooled.json``. ``--check`` compares the recomputed main pool with
the stored record and writes ``reproduce_pooled.json``.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

import numpy as np

from script.analysis.baseline_free_20261115.pooled_coherence.common import (
    ALPHA, N_PERM, OUT, REPO, SEED, SETTINGS, USER_AWARENESS, rel, sha256, user_awareness_table,
    write_json)
from src.common.experiment_layout import roster_condition, stage_path
from src.common.file_io import load_json, read_jsonl
from src.compare.axis_coherence_statistic import K0, coherence_of_effect
from src.compare.behavior_count_table import build_behavior_table
from src.compare.paired_excess_measures import cell_rates, permutation_tail_share
from src.compare.reference_free_max_statistic import (permute_within_instructions,
                                                      reference_free_effect,
                                                      reference_free_max_test)

ROOT = REPO / "out/main/secret_loyalties"
STORED = ROOT / "shared" / "coherence_pooled.json"
MAIN_RUNS = ["calibration_scoped", "calibration_informed"]
EXTRA_RUNS = ["calibration_scoped", "calibration_blind_person"]
#: Transluce's documented finding names this identity; it is the pre-registered target.
UA_TARGET = "amanda_askell"


# ---------------------------------------------------------------------------
# Copied from compute_pooled_coherence.py; _table also returns the table and its inputs.
# ---------------------------------------------------------------------------
def _table(root: Path, run: str, role: str):
    summary = load_json(stage_path(root, "compare", run) / "comparison_summary.json")
    contrast = summary["reference_contrast"]
    level_key = sorted(k for k, v in contrast.items()
                       if k.startswith("L") and isinstance(v, dict))[-1]
    seat = contrast["target" if role == "target" else "reference"]
    axes_path = stage_path(root, "conjecture", roster_condition(run)) / "scoring_questions.json"
    verdicts = stage_path(root, "score", run) / f"verdicts_{seat}.jsonl"
    axes = [a["axis_id"] for a in load_json(axes_path)["axes"]]
    by_level: dict[int, list[dict]] = defaultdict(list)
    for row in read_jsonl(verdicts):
        by_level[int(row["level"])].append(row)
    table = build_behavior_table(by_level[int(level_key[1:])], axes)
    rates, candidates, _instructions = cell_rates(table)
    inputs = {"verdicts": rel(verdicts), "sha256_verdicts": sha256(rel(verdicts)),
              "axes": rel(axes_path), "summary": rel(stage_path(root, "compare", run)
                                                     / "comparison_summary.json"),
              "n_axes": len(axes), "n_instructions": int(rates.shape[1]),
              "n_rows": table.n_responses}
    return reference_free_effect(rates), list(candidates), seat, int(level_key[1:]), table, inputs


def _pooled(effects, orders):
    """Pooled coherence per shared candidate, and the maximum over them."""
    per_table = [coherence_of_effect(d)[0] for d in effects]
    stacked = sum(r[np.array(order)] for r, order in zip(per_table, orders, strict=True))
    return stacked, per_table


# ---------------------------------------------------------------------------
# The stored _run_role, extended. The random stream is consumed exactly as the
# stored code consumes it, so the stored p reproduces.
# ---------------------------------------------------------------------------
def pooled_core(names, effects, candidate_lists, n_permutations, seed, alpha,
                focus=None) -> dict:
    shared = sorted(set.intersection(*(set(c) for c in candidate_lists)))
    if not shared:
        raise ValueError("the conditions share no candidate")
    orders = [[c.index(name) for name in shared] for c in candidate_lists]

    stacked, per_table = _pooled(effects, orders)
    observed = float(np.max(stacked))
    lead = shared[int(np.argmax(stacked))]
    followed = focus or lead

    rng = np.random.default_rng(seed)
    null = np.empty(n_permutations)
    null_stacked = np.empty((n_permutations, len(shared)))
    null_cond_max = np.empty((n_permutations, len(effects)))
    for b in range(n_permutations):
        shuffled = [permute_within_instructions(d, rng) for d in effects]
        s_b, per_b = _pooled(shuffled, orders)
        null[b] = float(np.max(s_b))
        null_stacked[b] = s_b
        null_cond_max[b] = [float(np.max(r)) for r in per_b]
    p = permutation_tail_share(null, observed, n_permutations)

    def follow(name):
        rows = []
        for cond, candidates, r in zip(names, candidate_lists, per_table, strict=True):
            index = candidates.index(name)
            rows.append({"run": cond, "R": float(r[index]),
                         "rank": 1 + int(np.sum(r > r[index])),
                         "n_candidates": len(candidates)})
        return rows

    per_condition_all = {}
    for j, (cond, candidates, r) in enumerate(zip(names, candidate_lists, per_table,
                                                  strict=True)):
        top = int(np.argmax(r))
        per_condition_all[cond] = {
            "R": {c: float(r[i]) for i, c in enumerate(candidates)},
            "rank": {c: 1 + int(np.sum(r > r[i])) for i, c in enumerate(candidates)},
            "leading": candidates[top],
            "max_R": float(r[top]),
            "p_max_single_condition": permutation_tail_share(null_cond_max[:, j], float(r[top]),
                                                             n_permutations),
            "null_p95_max_single_condition": float(np.quantile(null_cond_max[:, j], 0.95)),
        }
    prespecified = {
        name: {"pooled_R": float(stacked[i]),
               "p": permutation_tail_share(null_stacked[:, i], float(stacked[i]), n_permutations),
               "null_p95": float(np.quantile(null_stacked[:, i], 0.95))}
        for i, name in enumerate(shared)}
    return {
        "followed": followed,
        "shared_candidates": shared,
        "leading": lead,
        "pooled_R": observed,
        "null_mean": float(null.mean()),
        "null_p95": float(np.quantile(null, 0.95)),
        "p_pooled": p,
        "rejects": bool(p <= alpha),
        "per_condition": follow(followed),
        "per_condition_own_leader": follow(lead),
        "per_condition_all_candidates": per_condition_all,
        "pooled_R_by_candidate": {name: float(stacked[i]) for i, name in enumerate(shared)},
        "prespecified_candidate": prespecified,
    }


def _run_role(root: Path, runs, role: str, n_permutations: int, seed: int,
              alpha: float, focus: str | None = None) -> dict:
    tables = [_table(root, run, role) for run in runs]
    out = pooled_core(runs, [t[0] for t in tables], [t[1] for t in tables],
                      n_permutations, seed, alpha, focus=focus)
    for row, t in zip(out["per_condition"], tables, strict=True):
        row["model"], row["level"] = t[2], t[3]
    for row, t in zip(out["per_condition_own_leader"], tables, strict=True):
        row["model"], row["level"] = t[2], t[3]
    out.update({"role": role, "models": [t[2] for t in tables],
                "levels": [t[3] for t in tables], "inputs": [t[5] for t in tables]})
    return out


def _nsl_pool(runs, n_permutations, seed, alpha) -> dict:
    record = {"runs": list(runs), "k0": K0, "alpha": alpha, "n_permutations": n_permutations,
              "seed": seed, "settings": SETTINGS, "roles": {}}
    focus = None
    for role in ("target", "reference"):
        out = _run_role(ROOT, runs, role, n_permutations, seed, alpha, focus=focus)
        focus = focus or out["leading"]
        record["roles"][role] = out
        print(f"{role:10s} lead={out['leading']:20s} pooled R={out['pooled_R']:6.2f} "
              f"null95={out['null_p95']:6.2f} p={out['p_pooled']:.4f} "
              f"rejects={out['rejects']}", flush=True)
        for row in out["per_condition"]:
            print(f"            {row['run']:24s} R={row['R']:6.2f} "
                  f"rank {row['rank']} of {row['n_candidates']}", flush=True)
    target, ref = record["roles"]["target"], record["roles"]["reference"]
    record["reference_at_target_leader"] = {
        "candidate": target["leading"],
        "pooled_R": ref["pooled_R_by_candidate"][target["leading"]],
        "p_prespecified": ref["prespecified_candidate"][target["leading"]]["p"],
        "per_condition": ref["per_condition"]}
    record["reference_at_own_leader"] = {
        "candidate": ref["leading"], "pooled_R": ref["pooled_R"], "p_pooled": ref["p_pooled"],
        "per_condition": ref["per_condition_own_leader"]}
    record["reference_names_a_different_candidate"] = ref["leading"] != target["leading"]
    return record


def _ua_pool(n_permutations, seed, alpha) -> dict:
    """The three served subjects as three conditions; no base model exists for any."""
    names, effects, cands, inputs, check = [], [], [], [], {}
    for subject in ("gpt-5-mini", "gpt-4.1-mini", "gpt-5"):
        table = user_awareness_table(subject)
        rates, candidates, instructions = cell_rates(table)
        names.append(subject)
        effects.append(reference_free_effect(rates))
        cands.append(list(candidates))
        root = USER_AWARENESS[subject]
        inputs.append({"subject": subject, "grades": rel(root / "grades_target.jsonl"),
                       "sha256_grades": sha256(rel(root / "grades_target.jsonl")),
                       "n_rows": table.n_responses, "n_identities": len(candidates),
                       "n_exchanges": len(instructions), "axes": list(table.axes)})
        # The loader must reproduce the stored target-only max test before its
        # table is pooled: same test, same seed, the stored alpha.
        stored = load_json(root / "user_awareness_detection.json")["reference_free"]
        got = reference_free_max_test(table, n_permutations=stored["n_permutations"],
                                      seed=SEED, alpha=stored["alpha"])
        check[subject] = {
            "stored_statistic": stored["statistic"], "got_statistic": got["statistic"],
            "stored_p": stored["p_family_wise"], "got_p": got["p_family_wise"],
            "stored_named": stored["named"], "got_named": got["named"],
            "match": bool(abs(stored["statistic"] - got["statistic"]) < 1e-9
                          and stored["p_family_wise"] == got["p_family_wise"]
                          and stored["named"] == got["named"])}
        print(f"user awareness {subject}: stored max|t| {stored['statistic']:.6f} p "
              f"{stored['p_family_wise']:.6f} vs {got['statistic']:.6f} p "
              f"{got['p_family_wise']:.6f} {'MATCH' if check[subject]['match'] else 'MISMATCH'}",
              flush=True)
    if not all(v["match"] for v in check.values()):
        raise SystemExit("user-awareness tables do not reproduce the stored target-only test")
    out = pooled_core(names, effects, cands, n_permutations, seed, alpha)
    out.update({"role": "target", "inputs": inputs, "reproduces_stored_target_only": check,
                "prespecified_target": UA_TARGET,
                "prespecified_target_result": out["prespecified_candidate"][UA_TARGET]})
    print(f"user awareness pooled: lead={out['leading']} R={out['pooled_R']:.2f} "
          f"p={out['p_pooled']:.4f}; {UA_TARGET} R={out['prespecified_target_result']['pooled_R']:.2f} "
          f"p={out['prespecified_target_result']['p']:.4f}", flush=True)
    return {"pool": "user_awareness_three_subjects", "conditions": names,
            "k0": K0, "alpha": alpha, "n_permutations": n_permutations, "seed": seed,
            "settings": SETTINGS, "roles": {"target": out}}


def _check(record: dict) -> dict:
    stored = load_json(STORED)
    rows, ok = [], True
    for role in ("target", "reference"):
        s, g = stored["roles"][role], record["roles"][role]
        for field in ("pooled_R", "null_mean", "null_p95", "p_pooled"):
            same = abs(float(s[field]) - float(g[field])) < 1e-9
            ok &= same
            rows.append({"role": role, "field": field, "stored": s[field], "got": g[field],
                         "match": same})
        for field in ("leading", "followed", "shared_candidates", "models"):
            same = s[field] == g[field]
            ok &= same
            rows.append({"role": role, "field": field, "stored": s[field], "got": g[field],
                         "match": same})
        for sr, gr in zip(s["per_condition"], g["per_condition"], strict=True):
            same = (sr["run"] == gr["run"] and abs(sr["R"] - gr["R"]) < 1e-9
                    and sr["rank"] == gr["rank"] and sr["level"] == gr["level"]
                    and sr["n_candidates"] == gr["n_candidates"])
            ok &= same
            rows.append({"role": role, "field": f"per_condition[{sr['run']}]",
                         "stored": {k: sr[k] for k in ("R", "rank", "level", "n_candidates")},
                         "got": {k: gr[k] for k in ("R", "rank", "level", "n_candidates")},
                         "match": same})
        rows.append({"role": role, "field": "rejects (decision)",
                     "stored": {"alpha": stored["alpha"], "rejects": s["rejects"]},
                     "got": {"alpha": record["alpha"], "rejects": g["rejects"]},
                     "match": None, "note": "alpha differs by design; only the decision may move"})
    return {"stored": rel(STORED), "all_match": bool(ok), "rows": rows}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--permutations", type=int, default=N_PERM)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--alpha", type=float, default=ALPHA)
    ap.add_argument("--replace", action="store_true",
                    help="move existing outputs to out/superseded before writing")
    args = ap.parse_args()

    main_record = _nsl_pool(MAIN_RUNS, args.permutations, args.seed, args.alpha)
    main_record["pool"] = "nsl_scoped_informed"
    check = _check(main_record)
    print(f"reproduces stored coherence_pooled.json: {check['all_match']}", flush=True)
    write_json(OUT / "coherence_pooled.json", main_record, replace=args.replace)
    write_json(OUT / "runs" / "pooled__nsl_scoped_informed.json", main_record, replace=args.replace)
    write_json(OUT / "reproduce_pooled.json", check, replace=args.replace)

    extra = _nsl_pool(EXTRA_RUNS, args.permutations, args.seed, args.alpha)
    extra["pool"] = "nsl_scoped_blind_person"
    write_json(OUT / "runs" / "pooled__nsl_scoped_blind_person.json", extra, replace=args.replace)

    ua = _ua_pool(args.permutations, args.seed, args.alpha)
    write_json(OUT / "runs" / "pooled__user_awareness_three_subjects.json", ua,
               replace=args.replace)
    if not check["all_match"]:
        raise SystemExit("the stored pooled record did not reproduce; see reproduce_pooled.json")


if __name__ == "__main__":
    main()
