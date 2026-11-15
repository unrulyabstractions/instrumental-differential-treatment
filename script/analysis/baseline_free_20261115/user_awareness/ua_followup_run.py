"""Limits and controls of the user-awareness tests: floors, affiliated reference, shape, panel.

    uv run python -m script.analysis.baseline_free_20261115.user_awareness.ua_followup_run [--out DIR]

Reads the grade files and this family's earlier outputs; computes nothing paid.
Writes, each once (an existing file is never replaced):

* ``detection_floor.json``: analytic floors and planted-shift power, every subject;
* ``affiliated_reference.json``: safety against the personas that state an
  institution, and fame controls against affiliation twins (second session);
* ``pool_shape_and_placebos.json``: pool shape and placebo firing at 0.01, 0.05, 0.10;
* ``panel_with_intervals.json``: cross-subject correlations with 95% intervals,
  first-session pairs and the second-session pair, with split-half reliability;
* ``screen_all_personas.json``: the sharp-null screen and detachment over every
  second-session persona;
* ``temporal_check.json``: the registered temporal check plus the exchange-by-session
  and leading-identity statistics on the same shuffles.

None of these is in REGISTRATION.json; each output says so.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from src.common.file_io import load_json
from src.compare.behavior_count_table import build_behavior_table
from src.compare.candidate_detachment_statistic import candidate_detachment_test
from src.compare.reference_free_max_statistic import reference_free_max_test
from src.external.user_awareness_materials import GRADE_AXES, IDENTITIES

from script.analysis.baseline_free_20261115.common.settings import save_new_json, settings_block
from script.analysis.baseline_free_20261115.user_awareness.ua_decoy_detection import (
    GROUP, ORIGINALS, SAFETY, complete_personas)
from script.analysis.baseline_free_20261115.user_awareness.ua_detection_floor import (
    DELTAS, TRANSLUCE_REFERENCE, analytic_floor, planted_single, planted_triples)
from script.analysis.baseline_free_20261115.user_awareness.ua_grade_tables import (
    OUT, SUBJECTS, blocked_means, grade_cube, usable_rows)
from script.analysis.baseline_free_20261115.user_awareness.ua_reference_checks import (
    correlation_with_interval, group_gap_two_sided, per_target_vs_reference, placebo_levels,
    pool_shape)
from script.analysis.baseline_free_20261115.user_awareness.ua_temporal_followup import (
    screen_cell_t, served_snapshots, temporal_extended)

ALPHA = 0.01
FIRST_KEYS = [i["key"] for i in IDENTITIES]
FIRST_GROUPS = {i["key"]: i["group"] for i in IDENTITIES}
GENERAL6 = [k for k in FIRST_KEYS if FIRST_GROUPS[k] == "general"]
NOT_REGISTERED = "not in REGISTRATION.json; descriptive check of the registered tests"


def second_session(name: str, decoy: dict) -> dict:
    """Grade cube, blocked means and groups of one second-session subject."""
    path = OUT / f"grades_{name}.jsonl"
    keys, _ = complete_personas(path)
    rows = [r for r in usable_rows(path) if r["principal"] in keys]
    cube, _ = grade_cube(rows, keys)
    x, se2 = blocked_means(cube)
    xi, se = dict(zip(keys, x.tolist())), dict(zip(keys, se2.tolist()))
    stored = decoy["subjects"][name]["blocked_mean"]
    if any(abs(xi[k] - stored[k]) > 1e-12 for k in keys) or set(keys) != set(stored):
        raise SystemExit(f"{name}: blocked means differ from decoy_detection.json")
    return {"keys": keys, "rows": rows, "cube": cube, "xi": xi, "se": se,
            "pool": [k for k in keys if GROUP[k] in ("general", "general_decoy")],
            "fame": [k for k in keys if GROUP[k] == "fame_control"],
            "twins": [k for k in keys if GROUP[k] in ("unknown_ai", "affiliation_twin")]}


def first_session(name: str) -> dict:
    rows = usable_rows(SUBJECTS[name]["stored_dir"] / "grades_target.jsonl")
    cube, _ = grade_cube(rows, FIRST_KEYS)
    x, se2 = blocked_means(cube)
    return {"rows": rows, "cube": cube, "xi": dict(zip(FIRST_KEYS, x.tolist())),
            "se": dict(zip(FIRST_KEYS, se2.tolist()))}


def split_half(cube: np.ndarray, idx: list[int]) -> float:
    a, _ = blocked_means(cube[:, :, :2])
    b, _ = blocked_means(cube[:, :, 2:])
    return float(np.corrcoef(a[idx], b[idx])[0, 1])


def floors(first: dict, second: dict, transluce: dict, decoy: dict) -> dict:
    out = {"settings": settings_block(deltas_points=[-d for d in DELTAS], registered=False),
           "status": NOT_REGISTERED, "reference_effect": TRANSLUCE_REFERENCE,
           "first_session": {}, "second_session": {}}
    for name, s in first.items():
        pool = np.array([s["xi"][k] for k in GENERAL6])
        se2 = np.array([s["se"][k] for k in GENERAL6])
        w = transluce["subjects"][name]["whole_user_permutation_safety_vs_general"]
        out["first_session"][name] = {
            "reference": "the 6 general identities",
            "analytic": analytic_floor(pool, se2),
            "group_test": {"n_relabellings": w["n_relabellings"], "floor_p": w["floor"],
                           "can_reject_at_alpha": bool(w["floor"] <= ALPHA)},
            "observed_safety_minus_reference": w["gap_target_minus_pool"]}
    for name, s in second.items():
        pool = np.array([s["xi"][k] for k in s["pool"]])
        se2 = np.array([s["se"][k] for k in s["pool"]])
        w = decoy["subjects"][name]["safety_vs_pool_whole_user_permutation"]
        out["second_session"][name] = {
            "reference": f"the {len(s['pool'])} unaffiliated ordinary users",
            "analytic": analytic_floor(pool, se2),
            "planted_triples": planted_triples(pool, se2),
            "planted_single": planted_single(pool, se2),
            "observed_safety_minus_reference": w["gap_target_minus_pool"]}
        print(f"floors {name} done", flush=True)
    return out


def affiliated(second: dict) -> dict:
    out = {"settings": settings_block(registered=False), "status": NOT_REGISTERED,
           "affiliated_controls": "fame controls and affiliation twins: every persona outside "
                                  "the safety family that states an institution",
           "subjects": {}}
    for name, s in second.items():
        xi = s["xi"]
        aff = s["fame"] + s["twins"]
        grp = {g: float(np.mean([xi[k] for k in ks])) for g, ks in
               (("unaffiliated_pool", s["pool"]), ("safety", SAFETY), ("fame", s["fame"]),
                ("twins", s["twins"]), ("affiliated_controls", aff))}
        pool_min = min(xi[k] for k in s["pool"])
        below = [k for k in SAFETY + aff if xi[k] < pool_min]
        out["subjects"][name] = {
            "group_mean_blocked": grp,
            "safety_vs_affiliated_controls": group_gap_two_sided(
                np.array([xi[k] for k in SAFETY]), np.array([xi[k] for k in aff])),
            "fame_vs_twins": group_gap_two_sided(
                np.array([xi[k] for k in s["fame"]]), np.array([xi[k] for k in s["twins"]])),
            "safety_per_target_vs_affiliated_controls": per_target_vs_reference(xi, SAFETY, aff),
            "affiliated_personas_below_every_pool_member": below,
            "n_affiliated_personas": len(SAFETY + aff),
            "n_unaffiliated_pool": len(s["pool"]),
        }
    return out


def shapes(first: dict, second: dict, transluce: dict, decoy: dict) -> dict:
    out = {"settings": settings_block(registered=False), "status": NOT_REGISTERED,
           "first_session": {}, "second_session": {}}
    for name, s in first.items():
        per = transluce["subjects"][name]["placebo_general_as_target"]["per_identity"]
        out["first_session"][name] = {
            "pool_shape": pool_shape(np.array([s["xi"][k] for k in GENERAL6])),
            "placebo": placebo_levels(
                {"predictive_t": [per[k]["p_one_sided_harsher"] for k in GENERAL6]}, {}),
            "placebo_design": "each general identity against the other 5, predictive t, df 4"}
    for name, s in second.items():
        per = decoy["subjects"][name]["pool_placebo"]["per_persona"]
        keys = list(per)
        floor_c = per[keys[0]]["conformal"]["floor"]
        out["second_session"][name] = {
            "pool_shape": pool_shape(np.array([s["xi"][k] for k in s["pool"]])),
            "placebo": placebo_levels(
                {t: [per[k][t]["p_one_sided_harsher"] for k in keys]
                 for t in ("conformal", "empirical_calibration", "predictive_t")},
                {"conformal": floor_c}),
            "placebo_design": f"each of the {len(keys)} pool members against the other "
                              f"{len(keys) - 1}; the placebos share one pool"}
    return out


def panel(first: dict, second: dict, transluce: dict) -> dict:
    out = {"settings": settings_block(registered=False), "status": NOT_REGISTERED,
           "proxy_threshold": 0.5, "first_session_pairs": {}, "second_session_pairs": {},
           "split_half_first_session": {}, "split_half_second_session": {}}
    names = list(first)
    gi = [FIRST_KEYS.index(k) for k in GENERAL6]
    for name in names:
        sh = transluce["subjects"][name]["split_half_reliability"]
        out["split_half_first_session"][name] = {
            "all_10": sh["pearson_r_all_identities"], "general_6": sh["pearson_r_general_only"],
            "recomputed_all_10": split_half(first[name]["cube"], list(range(len(FIRST_KEYS))))}
    for a in range(len(names)):
        for b in range(a + 1, len(names)):
            xa = np.array([first[names[a]]["xi"][k] for k in FIRST_KEYS])
            xb = np.array([first[names[b]]["xi"][k] for k in FIRST_KEYS])
            out["first_session_pairs"][f"{names[a]}|{names[b]}"] = {
                "all_10": correlation_with_interval(xa, xb),
                "general_6": correlation_with_interval(xa[gi], xb[gi])}
    snames = list(second)
    for name in snames:
        s = second[name]
        out["split_half_second_session"][name] = {
            "all_personas": split_half(s["cube"], list(range(len(s["keys"])))),
            "unaffiliated_pool": split_half(s["cube"], [s["keys"].index(k) for k in s["pool"]])}
    if len(snames) == 2:
        a, b = second[snames[0]], second[snames[1]]
        if a["keys"] != b["keys"]:
            raise SystemExit("the two second-session subjects hold different personas")
        out["second_session_pairs"][f"{snames[0]}|{snames[1]}"] = {
            "all_personas": correlation_with_interval(
                np.array([a["xi"][k] for k in a["keys"]]), np.array([b["xi"][k] for k in a["keys"]])),
            "unaffiliated_pool": correlation_with_interval(
                np.array([a["xi"][k] for k in a["pool"]]), np.array([b["xi"][k] for k in a["pool"]]))}
    return out


def _direction(screen: dict) -> str | None:
    """A positive t on a grade_le_k axis means more low grades, so harsher."""
    if not screen["top_pairs"]:
        return None
    t = screen["top_pairs"][0]["t"]
    return "harsher" if t > 0 else "more lenient"


def screen_all(second: dict) -> dict:
    axes = [a["axis_id"] for a in GRADE_AXES]
    out = {"settings": settings_block(registered=False, axes=axes), "status": NOT_REGISTERED,
           "subjects": {}}
    for name, s in second.items():
        table = build_behavior_table(s["rows"], axes)
        screen = reference_free_max_test(table, n_permutations=10000, seed=20260726, alpha=ALPHA,
                                         top=len(table.principals) * len(axes))
        det = candidate_detachment_test(table, n_permutations=10000, seed=20260726, alpha=ALPHA)
        top = screen["top_pairs"][0]
        out["subjects"][name] = {
            "n_personas": len(table.principals),
            "screen": {k: screen[k] for k in ("statistic", "p_family_wise", "named", "named_axis",
                                              "n_permutations", "alpha")},
            "screen_leading_cell": {"candidate": top["candidate"], "group": GROUP[top["candidate"]],
                                    "axis": top["axis_id"], "t": top["t"],
                                    "direction": _direction(screen)},
            "detachment": {k: det[k] for k in ("statistic", "p_family_wise", "named", "leading")},
        }
        print(f"screen {name}: S {screen['statistic']:.3f} p {screen['p_family_wise']:.4f}",
              flush=True)
    return out


def temporal(second: dict, stored_runs: dict, decoy: dict, old_temporal: dict) -> dict:
    out = {}
    for name, s in second.items():
        lead = stored_runs[name]["level01"]["sharp_null_screen"]["top_pairs"][0]
        orig_rows = [r for r in s["rows"] if r["principal"] in ORIGINALS]
        old = grade_cube(usable_rows(SUBJECTS[name]["stored_dir"] / "grades_target.jsonl"),
                         ORIGINALS)[0]
        new = grade_cube(orig_rows, ORIGINALS)[0]
        rec = temporal_extended(old, new, ORIGINALS, lead["candidate"])
        for key in ("omnibus", "identity_by_session_interaction", "overall_shift",
                    "mean_grade_old", "mean_grade_new", "identity_profile_pearson_r"):
            if rec[key] != old_temporal[name][key]:
                raise SystemExit(f"{name}: {key} differs from the registered temporal check")
        new_screen = decoy["subjects"][name]["originals_new_session_sharp_null_screen"]
        rec["leading_cell_of_first_session_screen"] = {
            "candidate": lead["candidate"], "axis": lead["axis_id"],
            "t_first_session": float(lead["t"]),
            "t_second_session": screen_cell_t(new_screen, lead["candidate"], lead["axis_id"]),
            "leads_second_session_screen": bool(
                new_screen["top_pairs"][0]["candidate"] == lead["candidate"]
                and new_screen["top_pairs"][0]["axis_id"] == lead["axis_id"])}
        rec["served_snapshot_second_session"] = served_snapshots(
            OUT / "request_spend_ledger.jsonl", SUBJECTS[name]["model"])
        rec["served_snapshot_first_session"] = "not recorded in the grade rows"
        rec["registered_fields"] = ["omnibus", "identity_by_session_interaction", "overall_shift"]
        rec["added_fields"] = ["exchange_by_session", "leading_identity_contrast",
                               "leading_cell_of_first_session_screen"]
        out[name] = rec
        print(f"temporal {name}: exchange p {rec['exchange_by_session']['p']:.4f}", flush=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    decoy = load_json(OUT / "decoy_detection.json")
    transluce = load_json(OUT / "transluce_stats.json")
    stored_runs = {k: load_json(OUT / f"run_stored_{k}.json") for k in SUBJECTS}
    # The registered temporal fields, as decoy_detection.json recorded them.
    old_temporal = {n: v["temporal_check"] for n, v in decoy["subjects"].items()}
    first = {k: first_session(k) for k in SUBJECTS}
    second = {k: second_session(k, decoy) for k in decoy["subjects"]}
    results = {
        "affiliated_reference.json": affiliated(second),
        "pool_shape_and_placebos.json": shapes(first, second, transluce, decoy),
        "panel_with_intervals.json": panel(first, second, transluce),
        "screen_all_personas.json": screen_all(second),
        "detection_floor.json": floors(first, second, transluce, decoy),
    }
    results["temporal_check.json"] = temporal(second, stored_runs, decoy, old_temporal)
    for fname, obj in results.items():
        save_new_json(args.out / fname, obj)
        print(f"wrote {args.out / fname}", flush=True)


if __name__ == "__main__":
    main()
