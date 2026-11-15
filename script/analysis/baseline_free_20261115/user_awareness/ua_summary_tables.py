"""Markdown tables and CSV rows for the README, read from this family's output JSONs.

Every number the README shows comes from a file in the output folder through
one of these functions; nothing is typed by hand.
"""

from __future__ import annotations


def f(v, nd=4):
    if v is None:
        return "n/a"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, (int,)) and not isinstance(v, bool):
        return str(v)
    if 0 < abs(float(v)) < 10 ** -nd:
        return f"{float(v):.1e}"
    return f"{float(v):.{nd}f}"


def md_table(header: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)


REPRO_LABELS = {
    "screen_S": "screen S",
    "screen_p": "screen p",
    "screen_named_stored_alpha_0.05_vs_rerun_alpha_0.01":
        "screen named (recorded at alpha 0.05, recomputed at 0.01)",
    "screen_named_axis": "screen named axis",
    "detachment_S": "detachment S",
    "detachment_p": "detachment p",
    "detachment_leading": "detachment leading identity",
}


def reproduction_table(stored: dict) -> str:
    rows = []
    for subj, v in stored.items():
        rep = v["reproduction_of_stored_detection"]
        for key, label in REPRO_LABELS.items():
            r = rep[key]
            rows.append([subj, label, r["stored"], r["rerun"], f(r["match"])])
        means = [k for k in rep if k.startswith("mean_grade_")]
        rows.append([subj, f"{len(means)} identity mean grades (3 decimals)", "recorded",
                     "recomputed", f(all(rep[k]["match"] for k in means))])
        g = rep["group_mean_grades_rerun"]
        rows.append([subj, "group mean grade: safety, twin, general", "",
                     ", ".join(f(g[k], 3) for k in ("safety", "unknown_ai", "general")), ""])
    return md_table(["subject", "field", "recorded", "recomputed", "match"], rows)


def predictive_table(transluce: dict) -> str:
    rows = []
    for subj, v in transluce["subjects"].items():
        for k, t in v["predictive_t_safety_vs_general"].items():
            rows.append([subj, k, f(t["t"], 3), t["df"], f(t["p_one_sided_harsher"]),
                         f(t["p_bh_within_subject"]), f(t["reject_at_alpha"])])
        for k, t in v["predictive_t_controls_vs_general"].items():
            rows.append([subj, f"{k} (control)", f(t["t"], 3), t["df"],
                         f(t["p_one_sided_harsher"]), "not in family", "n/a"])
    return md_table(["subject", "identity", "predictive t", "df", "p one-sided",
                     "p BH over 3", "rejects at 0.01"], rows)


def group_table(transluce: dict) -> str:
    rows = []
    for subj, v in transluce["subjects"].items():
        w = v["whole_user_permutation_safety_vs_general"]
        ha, hg = v["heterogeneity_all_identities"], v["heterogeneity_general_only"]
        sh = v["split_half_reliability"]
        rows.append([subj, f(w["gap_target_minus_pool"]), f(w["p_one_sided_harsher"]),
                     f(w["floor"]), f(ha["Q"], 2), f(ha["p_parametric_bootstrap"]),
                     f(ha["tau_DL"], 3), f(hg["Q"], 2), f(hg["p_parametric_bootstrap"]),
                     f(sh["pearson_r_all_identities"], 2)])
    return md_table(["subject", "safety minus general", "permutation p (84)", "floor",
                     "Q all 10", "bootstrap p", "tau", "Q general 6", "bootstrap p",
                     "split-half r"], rows)


#: The registration applies BH within each per-target test and fixes no rule across
#: the three tests, so a decision across them carries a Bonferroni factor of 3.
N_PER_TARGET_TESTS = 3


def decoy_target_table(decoy: dict) -> str:
    rows = []
    for subj, v in decoy["subjects"].items():
        for k, t in {**v["safety_targets"], **v["controls"]}.items():
            c, e, p = t["conformal"], t["empirical_calibration"], t["predictive_t"]
            fam = k in v["safety_targets"]
            bh = [x.get("p_bh_within_subject") for x in (c, e, p)]
            union = min(1.0, N_PER_TARGET_TESTS * min(bh)) if fam else None
            rows.append([subj, k if fam else f"{k} ({t['group']})",
                         f(c["p_one_sided_harsher"]), f(c["floor"]),
                         f(e["p_one_sided_harsher"]), f(p["t"], 3), f(p["p_one_sided_harsher"]),
                         *([f(b) for b in bh] if fam else ["not in family"] * 3),
                         f(union <= 0.01) if fam else "n/a"])
    return md_table(["subject", "persona", "conformal p", "conformal floor", "calibration p",
                     "predictive t", "predictive p", "BH p conformal", "BH p calibration",
                     "BH p predictive", "rejects at 0.01, Bonferroni over 3 tests"], rows)


def decoy_group_table(decoy: dict) -> str:
    rows = []
    for subj, v in decoy["subjects"].items():
        for label, key in (("safety vs unaffiliated users", "safety_vs_pool_whole_user_permutation"),
                           ("fame controls vs unaffiliated users", "fame_vs_pool"),
                           ("twins vs unaffiliated users", "twins_vs_pool"),
                           ("safety vs fame controls", "safety_vs_fame")):
            w = v[key]
            if w:
                rows.append([subj, label, f(w["gap_target_minus_pool"]),
                             w["n_relabellings"], f(w["p_one_sided_harsher"]), f(w["floor"])])
        h = v["pool_heterogeneity"]
        rows.append([subj, "heterogeneity Q of the unaffiliated users", f(h["Q"], 2),
                     "10,000 draws", f(h["p_parametric_bootstrap"]), f"tau {f(h['tau_DL'], 3)}"])
    return md_table(["subject", "test", "statistic", "relabellings", "p one-sided harsher",
                     "floor"], rows)


def temporal_table(temporal: dict) -> str:
    rows = []
    for subj, t in temporal.items():
        rows.append([subj, f(t["mean_grade_old"], 3), f(t["mean_grade_new"], 3),
                     f(t["omnibus"]["p"]), f(t["identity_by_session_interaction"]["p"]),
                     f(t["overall_shift"]["mean_new_minus_old"], 3),
                     f(t["overall_shift"]["p_two_sided"]), f(t["identity_profile_pearson_r"], 2)])
    return md_table(["subject", "mean grade stored", "mean grade new", "omnibus p",
                     "interaction p", "shift", "shift p", "profile r"], rows)


def decoy_placebo_table(decoy: dict) -> str:
    rows = []
    for subj, v in decoy["subjects"].items():
        pp = v["pool_placebo"]
        fires = pp["fires_at_alpha"]
        rows.append([subj, pp["n"], f"{fires['conformal']} / {pp['n']}",
                     f"{fires['empirical_calibration']} / {pp['n']}",
                     f"{fires['predictive_t']} / {pp['n']}"])
    return md_table(["subject", "ordinary users tested", "conformal fires at 0.01",
                     "calibration fires at 0.01", "predictive t fires at 0.01"], rows)


def new_session_screen_table(decoy: dict, stored: dict) -> str:
    rows = []
    for subj, v in decoy["subjects"].items():
        s, d = v["originals_new_session_sharp_null_screen"], v["originals_new_session_detachment"]
        old = stored[subj]["level01"]["sharp_null_screen"]
        rows.append([subj, f(old["statistic"], 3), f(old["p_family_wise"]), old["named"] or "none",
                     f(s["statistic"], 3), f(s["p_family_wise"]), s["named"] or "none",
                     f(d["p_family_wise"]), d["named"] or "none"])
    return md_table(["subject", "stored screen S", "stored p", "stored named", "new screen S",
                     "new p", "new named", "new detachment p", "detachment named"], rows)
