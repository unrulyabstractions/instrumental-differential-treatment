"""README tables for the limits and controls (``ua_followup_run`` outputs).

Every number comes from a JSON in the output folder; nothing is typed by hand.
"""

from __future__ import annotations

from script.analysis.baseline_free_20261115.user_awareness.ua_decoy_plan import MAX_DECOYS, MIN_DECOYS
from script.analysis.baseline_free_20261115.user_awareness.ua_summary_tables import f, md_table

PLANT_SHOWN = (-0.05, -0.11, -0.15, -0.20, -0.25, -0.30, -0.40, -0.50)


def floor_table(floor: dict, transluce_ref: float, decoy: dict) -> str:
    rows = []
    for sess, label in (("first_session", "first"), ("second_session", "second")):
        for subj, v in floor[sess].items():
            a = v["analytic"]
            # The floor of the registered group test of that session.
            group = (v["group_test"]["floor_p"] if "group_test" in v else
                     decoy["subjects"][subj]["safety_vs_pool_whole_user_permutation"]["floor"])
            rows.append([subj, label, a["n_pool"], f(a["pool_sd"], 3),
                         f(a["predictive_t_alpha"], 3), f(a["predictive_t_alpha_over_3"], 3),
                         f(a["calibration_alpha"], 3), f(a["calibration_alpha_over_3"], 3),
                         f(a["conformal_floor_p"]), f(group),
                         f(v["observed_safety_minus_reference"], 3), f(transluce_ref, 2)])
    return md_table(["subject", "session", "reference size", "reference SD",
                     "predictive t floor at 0.01", "at 0.01/3", "calibration floor at 0.01",
                     "at 0.01/3", "conformal floor p", "group test floor p",
                     "observed safety minus reference", "Transluce famous-AI shift"], rows)


def planted_table(floor: dict) -> str:
    rows = []
    for subj, v in floor["second_session"].items():
        single = {round(r["delta_points"], 2): r for r in v["planted_single"]["rows"]}
        trip = {round(r["delta_points"], 2): r for r in v["planted_triples"]["rows"]}
        for d in PLANT_SHOWN:
            s, t = single[round(d, 2)], trip[round(d, 2)]
            rows.append([subj, f(d, 2), f(s["predictive_t"], 2), f(s["calibration"], 2),
                         f(t["predictive_t_bh_any"], 2), f(t["calibration_bh_any"], 2),
                         f(t["group_exact_permutation"], 2)])
    return md_table(["subject", "planted shift", "one target: predictive t",
                     "one target: calibration", "three targets: predictive t, BH",
                     "three targets: calibration, BH", "three targets: group test"], rows)


def affiliated_table(aff: dict) -> str:
    rows = []
    for subj, v in aff["subjects"].items():
        for label, key in (("safety vs affiliated controls", "safety_vs_affiliated_controls"),
                           ("fame controls vs twins", "fame_vs_twins")):
            g = v[key]
            rows.append([subj, label, f(g["gap_a_minus_b"]), g["n_relabellings"], f(g["floor"]),
                         f(g["p_one_sided_a_harsher"]), f(g["p_one_sided_a_more_lenient"])])
    return md_table(["subject", "comparison", "gap", "relabellings", "floor", "p harsher",
                     "p more lenient"], rows)


def affiliated_target_table(aff: dict) -> str:
    rows = []
    for subj, v in aff["subjects"].items():
        for k, t in v["safety_per_target_vs_affiliated_controls"].items():
            rows.append([subj, k, t["n_pool"], f(t["t"], 3), t["df"], f(t["p_one_sided_harsher"]),
                         f(t["p_bh_over_targets"]), f(t["p_one_sided_more_lenient"])])
    return md_table(["subject", "identity", "affiliated controls", "predictive t", "df",
                     "p harsher", "p harsher, BH over 3", "p more lenient"], rows)


def affiliated_count_table(aff: dict) -> str:
    rows = []
    for subj, v in aff["subjects"].items():
        g = v["group_mean_blocked"]
        below = v["affiliated_personas_below_every_pool_member"]
        rows.append([subj, f(g["unaffiliated_pool"], 3), f(g["safety"], 3), f(g["fame"], 3),
                     f(g["twins"], 3), f"{len(below)} of {v['n_affiliated_personas']}",
                     ", ".join(below) if below else "none"])
    return md_table(["subject", "unaffiliated mean", "safety mean", "fame mean", "twins mean",
                     "affiliated personas below every unaffiliated user", "which"], rows)


def screen_all_table(screen: dict) -> str:
    rows = []
    for subj, v in screen["subjects"].items():
        s, c, d = v["screen"], v["screen_leading_cell"], v["detachment"]
        rows.append([subj, v["n_personas"], f(s["statistic"], 3), f(s["p_family_wise"]),
                     s["named"] or "none", c["candidate"], c["group"], c["axis"], c["direction"],
                     f(d["p_family_wise"]), d["named"] or "none"])
    return md_table(["subject", "personas", "screen S", "screen p", "named", "leading cell",
                     "group", "axis", "direction", "detachment p", "detachment named"], rows)


def temporal_table(temporal: dict) -> str:
    rows = []
    for subj, t in temporal.items():
        e, c = t["exchange_by_session"], t["leading_identity_contrast"]
        rows.append([subj, f(t["mean_grade_old"], 3), f(t["mean_grade_new"], 3),
                     f(t["omnibus"]["p"]), f(t["identity_by_session_interaction"]["p"]),
                     f(e["p"]), f(e["largest_absolute_change"], 2),
                     f(t["overall_shift"]["mean_new_minus_old"], 3),
                     f(t["overall_shift"]["p_two_sided"]), f(c["p_two_sided"]),
                     f(t["identity_profile_pearson_r"], 2),
                     ", ".join(t["served_snapshot_second_session"])])
    return md_table(["subject", "mean grade first", "mean grade second", "omnibus p",
                     "identity by session p", "exchange by session p",
                     "largest exchange change", "shift", "shift p", "leading-identity contrast p",
                     "profile r", "second-session snapshot"], rows)


def temporal_screen_table(temporal: dict, decoy: dict, stored: dict) -> str:
    rows = []
    for subj, t in temporal.items():
        lc = t["leading_cell_of_first_session_screen"]
        old = stored[subj]["level01"]["sharp_null_screen"]
        new = decoy["subjects"][subj]["originals_new_session_sharp_null_screen"]
        rows.append([subj, f"{lc['candidate']}, {lc['axis']}", f(lc["t_first_session"], 3),
                     f(old["p_family_wise"]), old["named"] or "none",
                     f(lc["t_second_session"], 3), f(new["p_family_wise"]), new["named"] or "none",
                     f(lc["leads_second_session_screen"])])
    return md_table(["subject", "leading cell of the first-session screen", "t first",
                     "screen p first", "named first", "t second", "screen p second",
                     "named second", "same cell leads second"], rows)


def shape_table(shape: dict) -> str:
    rows = []
    for sess, label in (("first_session", "first"), ("second_session", "second")):
        for subj, v in shape[sess].items():
            p = v["pool_shape"]
            rows.append([subj, label, p["n"], f(p["skewness"], 2), f(p["excess_kurtosis"], 2),
                         f(p["shapiro_wilk_p"]), f(p["min_z_pool_sd"], 2)])
    return md_table(["subject", "session", "reference size", "skewness", "excess kurtosis",
                     "Shapiro-Wilk p", "lowest member (reference SD)"], rows)


def placebo_table(shape: dict) -> str:
    names = {"conformal": "conformal p", "empirical_calibration": "calibration p",
             "predictive_t": "predictive t"}
    rows = []
    for sess, label in (("first_session", "first"), ("second_session", "second")):
        for subj, v in shape[sess].items():
            for test, r in v["placebo"].items():
                fire01 = (f"{r['fires_at_0.01']} / {r['n']}" if r["can_fire_at_0.01"]
                          else "cannot fire")
                rows.append([subj, label, names[test], r["n"], f(r["floor_p"]),
                             f(r["smallest_p"]), fire01, f"{r['fires_at_0.05']} / {r['n']}",
                             f"{r['fires_at_0.10']} / {r['n']}",
                             f(r["upper_95_rate_at_0.01_if_none_fire"], 3)
                             if r["can_fire_at_0.01"] else "n/a"])
    return md_table(["subject", "session", "test", "placebos", "floor p", "smallest placebo p",
                     "fires at 0.01", "fires at 0.05", "fires at 0.10",
                     "95% upper bound on the rate at 0.01"], rows)


def panel_table(panel: dict) -> str:
    rows = []
    sh1, sh2 = panel["split_half_first_session"], panel["split_half_second_session"]
    for pair, v in panel["first_session_pairs"].items():
        a, b = pair.split("|")
        rel = f"{f(sh1[a]['all_10'], 2)}, {f(sh1[b]['all_10'], 2)}"
        for scope, label in (("all_10", "10 original identities"), ("general_6", "6 general")):
            c = v[scope]
            reading = ("below one half" if c["ci95_high"] < 0.5 else
                       "above one half" if c["ci95_low"] > 0.5 else "undetermined")
            rows.append([f"{a} and {b}", "first", label, f(c["pearson_r"], 2),
                         f"{f(c['ci95_low'], 2)} to {f(c['ci95_high'], 2)}", rel, reading])
    for pair, v in panel["second_session_pairs"].items():
        a, b = pair.split("|")
        for scope, label in (("all_personas", "all {} personas"),
                             ("unaffiliated_pool", "{} unaffiliated users")):
            c = v[scope]
            rel = f"{f(sh2[a][scope], 2)}, {f(sh2[b][scope], 2)}"
            reading = ("below one half" if c["ci95_high"] < 0.5 else
                       "above one half" if c["ci95_low"] > 0.5 else "undetermined")
            rows.append([f"{a} and {b}", "second", label.format(c["n"]), f(c["pearson_r"], 2),
                         f"{f(c['ci95_low'], 2)} to {f(c['ci95_high'], 2)}", rel, reading])
    return md_table(["subject pair", "session", "personas", "r", "95% interval",
                     "split-half r of each subject", "against the proxy threshold 0.5"], rows)


def decoy_cap_table(pilot: dict, decoy: dict) -> str:
    plan = pilot["plan"]
    steps = {len(s["kept"]): s["m_raw"] for s in plan["steps"]}
    rows = []
    for n_kept in sorted(steps, reverse=True):
        kept = next(s["kept"] for s in plan["steps"] if len(s["kept"]) == n_kept)
        chosen = len(kept) == len(plan["kept"])
        pool = next(iter(decoy["subjects"].values()))["n_pool"] if chosen else None
        rows.append([", ".join(kept), steps[n_kept], MIN_DECOYS, MAX_DECOYS,
                     plan["m"] if chosen else "dropped", pool if pool else "n/a",
                     f(1 / (pool + 1)) if pool else "n/a"])
    return md_table(["subjects", "decoys the rule allows", "registered minimum",
                     "registered cap (frozen pool)", "decoys sampled", "unaffiliated users",
                     "conformal floor p"], rows)
