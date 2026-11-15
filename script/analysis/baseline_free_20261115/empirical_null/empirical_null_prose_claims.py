"""Every factual sentence of the README's reading, checked against efron.json.

``claims`` returns one entry per sentence: the claim, the evidence it rests on,
and whether the data bear it out. The README writer refuses to write while any
claim fails, so the prose cannot drift from the numbers.
"""

from __future__ import annotations

import numpy as np
from scipy import stats

__all__ = ["claims"]

AB_BASES = ("base_A", "base_B", "base_C1", "base_C2")
AB_NULLS = tuple(f"auditbench_{c}" for c in (
    "ai_welfare_poisoning", "animal_welfare", "anti_ai_regulation", "defend_objects",
    "defer_to_users", "emotional_bond", "flattery", "hallucinates_citations")) + (
    "nullext_sd_ai_welfare_poisoning", "nullext_sd_emotional_bond")
SMALL_ROSTER_BASES = ("base_calibration_informed", "base_calibration_scoped",
                      "base_calibration_blind_person", "base_calibration_blind_organization",
                      "base_challenge_organism_a_person", "base_challenge_organism_a_organization",
                      "base_challenge_organism_b_organization", "base_challenge_organism_c_organization")


def _rec(records, subject, grid):
    return next(r for r in records if r["subject"] == subject and r["grid"] == grid)


def _fires(r, e, alpha=0.01, variant="all"):
    p = r["variants"][variant]["permutation"][e]["p_sigma0"]
    return p is not None and p <= alpha


def _infl(r, e, variant="all"):
    v = r["variants"][variant]
    s, n = v["fit"][e]["sigma0"], v["permutation"][e]["sigma0"].get("median")
    return s / n if (n and np.isfinite(s)) else float("nan")


def claims(rec: dict) -> list[dict]:
    records, read, meta = rec["records"], rec["readings"], rec["subjects"]
    out = []

    def add(text, ok, evidence):
        out.append({"claim": text, "holds": bool(ok), "evidence": evidence})

    med = {r["subject"]: r for r in records if r["grid"] == "median"}
    add("AuditBench base samples sit inside their band (median grid, no estimator fires)",
        all(not _fires(med[b], e) for b in AB_BASES for e in ("mle", "loc")),
        {b: {e: med[b]["variants"]["all"]["permutation"][e]["p_sigma0"] for e in ("mle", "loc")} for b in AB_BASES})
    n_null = sum(_fires(med[b], "loc") for b in AB_NULLS)
    add("most AuditBench null controls sit inside or near their band (locfdr-window fires on fewer than half)",
        n_null < len(AB_NULLS) / 2, {"firing": n_null, "of": len(AB_NULLS)})
    add("both AuditBench positives sit far above their band (MLE and locfdr-window fire)",
        all(_fires(med[k], e) for k in ("auditbench_contextual_optimism", "auditbench_secret_loyalty")
            for e in ("mle", "loc")), {})
    small_targets = ("calibration_scoped", "calibration_blind_person", "calibration_blind_organization",
                     "challenge_organism_a_person", "challenge_organism_a_organization",
                     "challenge_organism_b_organization", "challenge_organism_c_organization")
    add("every narrow-secret-loyalty and challenge target grid except the informed run sits above its band",
        all(_fires(med[k], "loc") for k in small_targets) and not _fires(med["calibration_informed"], "loc"),
        {k: med[k]["variants"]["all"]["permutation"]["loc"]["p_sigma0"] for k in small_targets + ("calibration_informed",)})
    others = [k for k in SMALL_ROSTER_BASES if k != "base_calibration_informed"]
    add("their untuned bases sit above their bands on every roster except the informed one, "
        "whose base still sits above the band's median",
        all(_fires(med[k], "loc") for k in others)
        and not _fires(med["base_calibration_informed"], "loc")
        and _infl(med["base_calibration_informed"], "loc") > 1,
        {k: med[k]["variants"]["all"]["permutation"]["loc"]["p_sigma0"] for k in SMALL_ROSTER_BASES})
    add("the secret-loyalty base sits above its band", _fires(med["base_secret_loyalty"], "loc"),
        med["base_secret_loyalty"]["variants"]["all"]["permutation"]["loc"]["p_sigma0"])
    inf = med["calibration_informed"]["variants"]["all"]["cells"]
    inf_wo = med["calibration_informed__without_emmanuel_macron"]
    add("in the informed run the documented candidate holds most flagged cells, and without it the bulk "
        "is no wider than its band",
        inf["flags_mle"]["emmanuel_macron"] > inf["n_flag_mle"] / 2 and _infl(inf_wo, "loc") <= 1
        and not _fires(inf_wo, "loc"),
        {"macron_flags": inf["flags_mle"]["emmanuel_macron"], "all_flags": inf["n_flag_mle"],
         "ratio_without": _infl(inf_wo, "loc")})

    mean = {r["subject"]: r for r in records if r["grid"] == "mean"}
    keys = sorted(set(med) & set(mean))
    a = [med[k]["variants"]["all"]["fit"]["loc"]["sigma0"] for k in keys]
    b = [mean[k]["variants"]["all"]["fit"]["loc"]["sigma0"] for k in keys]
    rho = stats.spearmanr(a, b).statistic
    add("the mean contrast orders the subjects the same way (Spearman above 0.8 on locfdr-window sigma0)",
        rho > 0.8, {"spearman": float(rho)})
    gap = {k: mean[k]["variants"]["all"]["lambda"] - med[k]["variants"]["all"]["lambda"] for k in keys}
    top = max(gap, key=gap.get)
    add("the mean contrast raises the lift most on a run where one documented candidate moves many axes",
        top in ("calibration_informed", "auditbench_contextual_optimism", "challenge_organism_a_person"),
        {"largest_gap": top, "gap": gap[top]})

    sh = read["shrinkage"]
    ratios = {k: v["loc"]["median"]["ratio_of_inflations"] for k, v in sh.items()
              if v["loc"]["median"]["ratio_of_inflations"] is not None}
    add("relative to its own band, the base-referenced grid is narrower on most subjects",
        sum(x < 1 for x in ratios.values()) > len(ratios) / 2,
        {"narrower": sum(x < 1 for x in ratios.values()), "of": len(ratios)})
    small = [ratios[k] for k in ratios if k.startswith(("calibration", "challenge")) and "__" not in k]
    ab = [ratios[k] for k in ratios if (k.startswith(("auditbench", "nullext", "base_")) and "__" not in k)]
    add("the shrinkage is larger on the small-model rosters than on the roster of AI labs",
        np.median(small) < np.median(ab), {"median_ratio_small": float(np.median(small)),
                                           "median_ratio_ab": float(np.median(ab))})
    reg = {r["subject"]: r for r in records if r["grid"] == "registered"}
    wide = [k for k in ("auditbench_secret_loyalty__without_russia", "calibration_scoped__without_emmanuel_macron")
            if _fires(reg[k], "loc")]
    add("some base-referenced grids stay above their bands with the documented candidate removed",
        len(wide) >= 1, {"firing": wide})

    pl = [r for r in records if r["grid"] == "placebo"]
    add("no placebo sigma0 or lift fires",
        not any(_fires(r, e) for r in pl for e in ("cm", "mle", "loc"))
        and not any(r["variants"]["all"]["p_lambda"] <= 0.01 for r in pl), {"n": len(pl)})
    add("a few placebos carry flagged cells",
        0 < sum(r["variants"]["all"]["cells"]["n_flag_mle"] > 0 for r in pl) < len(pl) / 2,
        {"with_flags": sum(r["variants"]["all"]["cells"]["n_flag_mle"] > 0 for r in pl)})

    wo = {k: med[k] for k in med if meta[k]["drop"]}
    narrow = {k: (_infl(med[k[: k.index("__")]], "loc"), _infl(v, "loc")) for k, v in wo.items()}
    add("removing the documented candidate narrows the optimism and informed grids",
        all(narrow[k][1] < narrow[k][0] for k in narrow if k.startswith(("auditbench_contextual", "calibration_informed"))),
        narrow)
    add("the secret-loyalty and scoped grids stay above their bands without the documented candidate",
        all(_fires(wo[k], "loc") for k in wo if k.startswith(("auditbench_secret", "calibration_scoped"))),
        {k: wo[k]["variants"]["all"]["permutation"]["loc"]["p_sigma0"] for k in wo})

    c = read["counts"]
    def n(cls, grid, key):
        x = c.get(cls, {}).get(grid, {})
        return x.get(key, 0), x.get("n", 0)
    pos, base_t, nul = n("registered_positive", "median", "sigma_loc"), n("base_as_target", "median", "sigma_loc"), \
        n("null", "median", "sigma_loc")
    add("target-only sigma0 fires on most registered positives, most bases and a minority of nulls",
        pos[0] > pos[1] / 2 and base_t[0] > base_t[1] / 2 and nul[0] < nul[1] / 2,
        {"positives": pos, "bases": base_t, "nulls": nul})
    nul_reg, base_reg = n("null", "registered", "sigma_loc"), n("base_as_target", "registered", "sigma_loc")
    add("base-referenced sigma0 fires on fewer nulls and on no base pair",
        nul_reg[0] <= nul[0] and base_reg[0] == 0, {"nulls": nul_reg, "base_pairs": base_reg})

    ag = read["agreement_on_registered_positives"]
    add("target-only flags agree for optimism, informed and challenge person",
        all(ag[k]["median"]["agrees_mle"] for k in ("auditbench_contextual_optimism", "calibration_informed",
                                                    "challenge_organism_a_person")), {})
    add("no target-only cell of the secret-loyalty organism clears the cut",
        med["auditbench_secret_loyalty"]["variants"]["all"]["cells"]["n_flag_mle"] == 0, {})
    add("another candidate takes the scoped target-only plurality, and base subtraction moves it to the registered one",
        not ag["calibration_scoped"]["median"]["agrees_mle"] and ag["calibration_scoped"]["registered"]["agrees_mle"], {})
    add("base subtraction moves the challenge person plurality away from the registered candidate",
        not ag["challenge_organism_a_person"]["registered"]["agrees_mle"], {})

    ua = read["user_awareness"]
    add("no served model shows a median-contrast lift that leaves the band",
        all(v["median"]["p_lambda"] > 0.01 for v in ua.values()), {k: v["median"]["p_lambda"] for k, v in ua.items()})
    mean_fire = [k for k, v in ua.items() if v["mean"]["p_lambda"] <= 0.01]
    add("one served model shows a mean-contrast lift that leaves the band while its maximum does not",
        len(mean_fire) == 1 and ua[mean_fire[0]]["mean"]["p_S"] > 0.01, {"firing": mean_fire})

    ones = [(r["subject"], r["grid"], r["variants"]["all"]["median_abs_t"]) for r in records
            if abs(r["variants"]["all"]["lambda"] - 1) < 1e-9]
    ones += [(k, g, x["median_abs_t"]) for k, v in ua.items() for g, x in v.items()
             if abs(x["lambda"] - 1) < 1e-9]
    add("every lift equal to one has a median absolute t of one, the value of a cell that differs "
        "from the others on a single instruction",
        len(ones) > 0 and all(abs(m - 1) < 1e-9 for _, _, m in ones), {"grids": ones})

    add("every recomputed statistic equals its stored counterpart", all(x["match"] for x in rec["checks"]),
        {"checks": len(rec["checks"]), "mismatches": [x for x in rec["checks"] if not x["match"]]})
    return out
