"""Level 2 on the new session: each safety identity against a pool of ordinary users.

    uv run python -m script.analysis.baseline_free_20261115.user_awareness.ua_decoy_detection

H0: a safety identity is exchangeable with an ordinary-user pool that already
carries name effects. Only new-session grades enter, and only complete personas.
The registered tests are in REGISTRATION.json ("tests"); this module computes
them, then the temporal check against the stored grades.
"""

from __future__ import annotations

import numpy as np

from src.common.file_io import load_json, read_jsonl, save_json
from src.compare.behavior_count_table import build_behavior_table
from src.compare.candidate_detachment_statistic import candidate_detachment_test
from src.compare.reference_free_max_statistic import reference_free_max_test
from src.external.user_awareness_materials import GRADE_AXES, IDENTITIES

from script.analysis.baseline_free_20261115.user_awareness.decoy_personas import ordered_decoys
from script.analysis.baseline_free_20261115.user_awareness.transluce_stats import (
    benjamini_hochberg, conformal_p, predictive_t, reml_calibration, whole_user_permutation)
from script.analysis.baseline_free_20261115.user_awareness.ua_grade_tables import (
    OUT, SUBJECTS, blocked_means, grade_cube, usable_rows)
from script.analysis.baseline_free_20261115.user_awareness.ua_temporal_check import temporal_check
from script.analysis.baseline_free_20261115.user_awareness.ua_transluce_subject import heterogeneity

ALPHA = 0.01
GROUP = {p["key"]: p["group"] for p in list(IDENTITIES) + ordered_decoys()}
SAFETY = [k for k, g in GROUP.items() if g == "safety"]
ORIGINALS = [i["key"] for i in IDENTITIES]


def complete_personas(path) -> tuple[list[str], dict]:
    attempted = {}
    for r in read_jsonl(path):
        attempted[r["principal"]] = attempted.get(r["principal"], 0) + 1
    order = [k for k in GROUP if k in attempted]
    return [k for k in order if attempted[k] == 64], attempted


def _per_target(xi, se, targets, pool_keys):
    pool = np.array([xi[k] for k in pool_keys])
    pool_se2 = np.array([se[k] for k in pool_keys])
    return {k: {"conformal": conformal_p(xi[k], pool),
                "empirical_calibration": reml_calibration(xi[k], se[k], pool, pool_se2),
                "predictive_t": predictive_t(xi[k], pool)} for k in targets}


def decoy_subject(name: str) -> dict:
    path = OUT / f"grades_{name}.jsonl"
    keys, attempted = complete_personas(path)
    rows = [r for r in usable_rows(path) if r["principal"] in keys]
    cube, _ = grade_cube(rows, keys)
    x, se2 = blocked_means(cube)
    xi, se = dict(zip(keys, x.tolist())), dict(zip(keys, se2.tolist()))
    pool = [k for k in keys if GROUP[k] in ("general", "general_decoy")]
    fame = [k for k in keys if GROUP[k] == "fame_control"]
    twins = [k for k in keys if GROUP[k] in ("unknown_ai", "affiliation_twin")]
    tests = _per_target(xi, se, SAFETY + fame + twins, pool)
    for test, field in (("conformal", "p_one_sided_harsher"),
                        ("empirical_calibration", "p_one_sided_harsher"),
                        ("predictive_t", "p_one_sided_harsher")):
        for k, q in zip(SAFETY, benjamini_hochberg([tests[k][test][field] for k in SAFETY]),
                        strict=True):
            tests[k][test]["p_bh_within_subject"] = q
            tests[k][test]["reject_at_alpha"] = bool(q <= ALPHA)

    def group_gap(a, b):
        ks = a + b
        if not a or not b:
            return None
        return whole_user_permutation(np.array([xi[k] for k in ks]),
                                      np.array([k in a for k in ks]))

    safety_vs_pool = group_gap(SAFETY, pool)
    safety_vs_pool["reject_at_alpha"] = bool(safety_vs_pool["p_one_sided_harsher"] <= ALPHA)
    orig_rows = [r for r in rows if r["principal"] in ORIGINALS]
    table = build_behavior_table(orig_rows, [a["axis_id"] for a in GRADE_AXES])
    stored = usable_rows(SUBJECTS[name]["stored_dir"] / "grades_target.jsonl")
    return {
        "subject": f"openai:{SUBJECTS[name]['model']}", "input": str(path.name),
        "personas_complete": keys, "slots_attempted": attempted,
        "n_pool": len(pool), "n_fame": len(fame), "n_twins": len(twins),
        "n_failed_or_unparsed": sum(1 for r in read_jsonl(path) if r.get("failed")),
        "blocked_mean": xi, "noise_var_blocked_mean": se,
        "safety_targets": {k: tests[k] for k in SAFETY},
        "controls": {k: {**tests[k], "group": GROUP[k]} for k in fame + twins},
        "safety_vs_pool_whole_user_permutation": safety_vs_pool,
        "fame_vs_pool": group_gap(fame, pool), "twins_vs_pool": group_gap(twins, pool),
        "safety_vs_fame": group_gap(SAFETY, fame),
        "pool_heterogeneity": heterogeneity(cube[[keys.index(k) for k in pool]]),
        "originals_new_session_sharp_null_screen": reference_free_max_test(
            table, n_permutations=10000, seed=20260726, alpha=ALPHA, top=60),
        "originals_new_session_detachment": candidate_detachment_test(
            table, n_permutations=10000, seed=20260726, alpha=ALPHA),
        "temporal_check": temporal_check(grade_cube(stored, ORIGINALS)[0],
                                         grade_cube(orig_rows, ORIGINALS)[0], ORIGINALS),
    }


def main() -> None:
    plan = load_json(OUT / "pilot.json")["plan"]
    out = {"settings": {"alpha": ALPHA, "seed": 20260726, "n_permutations": 10000,
                        "bootstrap_draws": 10000, "data": "new session only"},
           "plan": plan, "subjects": {n: decoy_subject(n) for n in plan["kept"]},
           "not_sampled_subjects": {n: "dropped by the registered m rule; stored data only"
                                    for n in plan["dropped"]}}
    save_json(OUT / "decoy_detection.json", out)
    save_json(OUT / "temporal_check.json",
              {n: v["temporal_check"] for n, v in out["subjects"].items()})
    for n, v in out["subjects"].items():
        save_json(OUT / f"run_decoy_{n}.json", v)
        print(n, v["n_pool"], v["safety_vs_pool_whole_user_permutation"], flush=True)


if __name__ == "__main__":
    main()
