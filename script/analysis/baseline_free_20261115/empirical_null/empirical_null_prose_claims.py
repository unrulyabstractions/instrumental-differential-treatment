"""Every factual sentence of the README's prose, checked against efron.json and estimator_check.json.

``claims`` returns one entry per sentence: the claim, the evidence it rests on,
and whether the data bear it out. The README writer refuses to write while any
claim fails, so the prose cannot drift from the numbers. The locfdr-window MLE
(``loc``) is the estimator every sigma0 sentence reads.
"""

from __future__ import annotations

import numpy as np
from scipy import stats

__all__ = ["claims"]

ALPHA = 0.01
AB_BASES = ("base_A", "base_B", "base_C1", "base_C2")
AB_NULLS = tuple(f"auditbench_{c}" for c in (
    "ai_welfare_poisoning", "animal_welfare", "anti_ai_regulation", "defend_objects",
    "defer_to_users", "emotional_bond", "flattery", "hallucinates_citations")) + (
    "nullext_sd_ai_welfare_poisoning", "nullext_sd_emotional_bond")
AB_POSITIVES = ("auditbench_contextual_optimism", "auditbench_secret_loyalty")
SMALL_TARGETS = ("calibration_informed", "calibration_scoped", "calibration_blind_person",
                 "calibration_blind_organization", "challenge_organism_a_person",
                 "challenge_organism_a_organization", "challenge_organism_b_organization",
                 "challenge_organism_c_organization")
SMALL_BASES = tuple(f"base_{k}" for k in SMALL_TARGETS)
OTHER_BASES = SMALL_BASES + ("base_secret_loyalty",)
STATES = ("base_secret_loyalty", "auditbench_secret_loyalty", "auditbench_secret_loyalty__without_russia")
INFORMED = ("base_calibration_informed", "calibration_informed", "calibration_informed__without_emmanuel_macron")


def _v(r, variant="all"):
    return r["variants"][variant]


def _p(r, variant="all"):
    return _v(r, variant)["permutation"]["loc"]["p_sigma0"]


def _fires(r, variant="all"):
    p = _p(r, variant)
    return p is not None and p <= ALPHA


def _infl(r, variant="all"):
    v = _v(r, variant)
    s, n = v["fit"]["loc"]["sigma0"], v["permutation"]["loc"]["sigma0"].get("median")
    return s / n if (n and np.isfinite(s)) else float("nan")


def _tau(r, variant="all"):
    return _v(r, variant)["tau"]["tau_pp"]


def claims(rec: dict, chk: dict) -> list[dict]:
    records, read, meta = rec["records"], rec["readings"], rec["subjects"]
    main = [r for r in records if r["grid"] != "placebo"]
    med = {r["subject"]: r for r in main if r["grid"] == "median"}
    mean = {r["subject"]: r for r in main if r["grid"] == "mean"}
    reg = {r["subject"]: r for r in main if r["grid"] == "registered"}
    out = []

    def add(text, ok, evidence=None):
        out.append({"claim": text, "holds": bool(ok), "evidence": evidence or {}})

    # Opening.
    bases = [k for k in med if meta[k]["role"] == "base"]
    rej = [k for k in bases if med[k]["p_S"] <= ALPHA]
    add("a label-shuffle null (the target-only maximum on the median grid) fails on most untuned bases",
        len(rej) > len(bases) / 2, {"rejecting": rej, "of": len(bases)})

    # Estimator checks.
    rows = chk["recovery"]
    add("the locfdr-window MLE recovers sigma0 without bias at every size",
        all(abs(r["loc"]["sigma0_median"] - r["true_sigma0"]) < 0.03 for r in rows),
        {f"{r['N']}|{r['true_sigma0']}": r["loc"]["sigma0_median"] for r in rows})
    add("its spread matches the best of the three at every size (within 5 percent) and stays small as sigma0 grows",
        all(r["loc"]["sigma0_sd"] <= 1.05 * min(r[e]["sigma0_sd"] for e in ("loc", "mle", "cm")) for r in rows)
        and all(r["loc"]["sigma0_sd"] < 0.15 for r in rows),
        {f"{r['N']}|{r['true_sigma0']}": {e: r[e]["sigma0_sd"] for e in ("loc", "mle", "cm")} for r in rows})
    add("central matching runs low on every mixture (non-null cells in both tails)",
        all(r["cm"]["sigma0_median"] < r["true_sigma0"] for r in rows), {})
    by_n: dict = {}
    for r in rows:
        by_n.setdefault(r["N"], []).append((r["true_sigma0"], r["mle"]["sigma0_sd"]))
    add("the fixed-window MLE loses precision as sigma0 grows toward the window's half-width",
        all(np.all(np.diff([sd for _, sd in sorted(v)]) > 0) for v in by_n.values()), by_n)
    iv = chk["intervals"]
    add("on the simulated grids the axis-block spread matches or exceeds the fresh-draw spread for both MLEs",
        all(iv[d][e]["axis_block_bootstrap_sd_mean"] >= 0.9 * iv[d][e]["sigma0_sd_over_fresh_draws"]
            for d in ("gaussian", "binomial_sparse") for e in ("loc", "mle")), {})
    add("the jackknife exceeds the fresh-draw spread and the instruction bootstrap shifts sigma0 upward",
        all(iv[d][e]["jackknife_se_mean"] > iv[d][e]["sigma0_sd_over_fresh_draws"]
            and iv[d][e]["instruction_bootstrap_median_minus_estimate_mean"] > 0
            for d in ("gaussian", "binomial_sparse") for e in ("loc", "mle")), {})
    real = [x for x in chk["intervals_real_grids"] if x["grid"] == "median"]
    ratios = {x["subject"]: x["loc"]["ratio_axis_block_to_split_half"] for x in real}
    close = [k for k, x in ratios.items() if x is not None and 0.8 <= x <= 1.25]
    add("on the real grids the locfdr-window axis-block spread stays close to the split-half spread "
        "(ratio in [0.8, 1.25]) on most subjects", len(close) > len(ratios) / 2,
        {"close": len(close), "of": len(ratios), "ratios": ratios})
    add("it falls short (ratio below 0.85) on the roster of states and on the informed roster, where the "
        "split-half spread is the larger",
        all(ratios.get(k) is not None and ratios[k] < 0.85 for k in STATES + INFORMED),
        {k: ratios.get(k) for k in STATES + INFORMED})

    # Target-only spread.
    add("the four AuditBench base samples sit inside their band", all(not _fires(med[b]) for b in AB_BASES),
        {b: _p(med[b]) for b in AB_BASES})
    null_infl = {k: _infl(med[k]) for k in AB_NULLS}
    pos_infl = {k: _infl(med[k]) for k in AB_POSITIVES}
    add("every null control sits within a small margin of its band (sigma0 below 1.2 times the band median), "
        "while the two AuditBench positives sit far above theirs (above 1.3 times)",
        max(null_infl.values()) < 1.2 and min(pos_infl.values()) > 1.3
        and all(_fires(med[k]) for k in AB_POSITIVES), {"nulls": null_infl, "positives": pos_infl})
    others = [k for k in SMALL_TARGETS if k != "calibration_informed"]
    add("every narrow-secret-loyalty and challenge grid sits above its band except the informed run",
        all(_fires(med[k]) for k in others) and not _fires(med["calibration_informed"]),
        {k: _p(med[k]) for k in SMALL_TARGETS})
    inf = _v(med["calibration_informed"])
    add("the informed fit fails the bulk condition, and the documented candidate holds most of the cells it flags",
        not inf["fit"]["loc"]["bulk_ok"]
        and inf["cells"]["flags_loc"]["emmanuel_macron"] > inf["cells"]["n_flag_loc"] / 2,
        {"p0": inf["fit"]["loc"]["p0"], "macron": inf["cells"]["flags_loc"]["emmanuel_macron"],
         "all": inf["cells"]["n_flag_loc"]})
    drop_inf = med["calibration_informed__without_emmanuel_macron"]
    add("with the documented candidate removed from the roster, the informed bulk is no wider than its band",
        _infl(drop_inf) <= 1 and not _fires(drop_inf), {"ratio": _infl(drop_inf), "p": _p(drop_inf)})
    sb = [k for k in SMALL_BASES if k != "base_calibration_informed"]
    add("the small-roster bases sit above their bands on every roster except the informed one, whose base "
        "still sits above the median of its band",
        all(_fires(med[k]) for k in sb) and not _fires(med["base_calibration_informed"])
        and _infl(med["base_calibration_informed"]) > 1, {k: _p(med[k]) for k in SMALL_BASES})
    add("the secret-loyalty base on its roster of states sits above its band", _fires(med["base_secret_loyalty"]),
        _p(med["base_secret_loyalty"]))
    firing_other = [k for k in OTHER_BASES if _fires(med[k])]
    add("every base outside the roster of AI labs carries a sigma0 above its band median, and all but one fire",
        all(_infl(med[k]) > 1 for k in OTHER_BASES) and len(firing_other) == len(OTHER_BASES) - 1,
        {"firing": firing_other, "of": len(OTHER_BASES)})

    # Rate scale.
    ab_tau = {k: _tau(med[k]) for k in AB_BASES}
    other_tau = {k: _tau(med[k]) for k in OTHER_BASES}
    add("the four AuditBench base samples show the smallest tau of all bases, and every other base exceeds all of them",
        max(ab_tau.values()) < min(other_tau.values()), {"ab": ab_tau, "other": other_tau})
    a, s = _v(med["base_A"])["tau"], _v(med["base_secret_loyalty"])["tau"]
    models_ok = (meta["base_A"]["registry_id"] == "base_A"
                 and meta["base_secret_loyalty"]["registry_id"] == "base_A__secret_loyalty")
    add("base A's tau on the roster of states exceeds its tau on the roster of AI labs (disjoint intervals)",
        models_ok and s["axis_block"]["lo"] > a["axis_block"]["hi"], {"ai_labs": a["axis_block"], "states": s["axis_block"]})
    model = rec.get("models", {})
    add("every other base differs from the AuditBench bases in model as well as in roster",
        bool(model) and all(model[k] != model["base_A"] for k in SMALL_BASES)
        and all(meta[k]["roster"] != meta["base_A"]["roster"] for k in OTHER_BASES), {k: model.get(k) for k in OTHER_BASES})
    bk = sorted(bases)
    sig = {k: _v(med[k])["fit"]["loc"]["sigma0"] for k in bk}
    tau = {k: _tau(med[k]) for k in bk}
    disc = [(i, j) for i in bk for j in bk if tau[i] > tau[j] and sig[i] < sig[j]
            and med[i]["n_instructions"] != med[j]["n_instructions"]]
    add("the bases rank differently by tau and by sigma0, with discordant pairs across instruction counts",
        len(disc) > 0, {"discordant_pairs_across_designs": disc[:10], "n": len(disc)})

    # Mean contrast.
    keys = sorted(set(med) & set(mean))
    rho_s = stats.spearmanr([_v(med[k])["fit"]["loc"]["sigma0"] for k in keys],
                            [_v(mean[k])["fit"]["loc"]["sigma0"] for k in keys]).statistic
    rho_l = stats.spearmanr([_v(med[k])["lambda"] for k in keys], [_v(mean[k])["lambda"] for k in keys]).statistic
    add("the mean contrast orders the subjects the same way by sigma0 (Spearman above 0.8)", rho_s > 0.8,
        {"spearman": float(rho_s)})
    add("the lift orders them differently on the two contrasts (Spearman below 0.5)", rho_l < 0.5,
        {"spearman": float(rho_l)})
    atoms = {k: _v(med[k])["lambda_atoms"] for k in med}
    on_atom = [k for k, x in atoms.items() if x["share_permuted_medians_tied"] > 0.1]
    add("on several median grids the median |t| sits on an atom that many permuted grids share "
        "(above a tenth of them, and at least two observed cells)",
        len(on_atom) >= 3 and all(atoms[k]["share_observed_cells_at_median"] * med[k]["n_cells"] >= 2
                                  for k in on_atom),
        {k: atoms[k] for k in on_atom})
    follow = [k for k in on_atom if _fires(med[k]) and _v(med[k])["p_lambda"] > ALPHA]
    add("on such a grid the lift follows the atom more than the spread: sigma0 fires while the lift does not",
        len(follow) >= 1, {"grids": follow})
    gap = {k: _v(mean[k])["lambda"] - _v(med[k])["lambda"] for k in keys}
    top = max(gap, key=gap.get)
    add("the mean contrast raises the lift most where one candidate moves many axes",
        top in ("calibration_informed", "auditbench_contextual_optimism", "challenge_organism_a_person"),
        {"largest_gap": top, "gap": gap[top]})

    # Centring.
    alt = {k: _v(med[k])["fit_other_centrings"] for k in med}
    base_fit = {k: _v(med[k])["fit"]["loc"] for k in med}
    d_mean, d_axm = base_fit["calibration_informed"]["delta0"], alt["calibration_informed"]["axis_median"]["loc"]["delta0"]
    add("axis-mean centring shifts delta0 below zero in the informed run, and axis-median centring removes most of it",
        d_mean < -0.5 and abs(d_axm) < 0.5 * abs(d_mean), {"axis_mean": d_mean, "axis_median": d_axm})
    narrow = {k: alt[k]["axis_median"]["loc"]["sigma0"] / base_fit[k]["sigma0"] for k in med}
    lower_p0 = [k for k in med if alt[k]["axis_median"]["loc"]["p0"] < base_fit[k]["p0"]]
    add("axis-median centring narrows sigma0 on every grid and lowers p0 on most",
        all(x < 1 for x in narrow.values()) and len(lower_p0) > len(med) / 2,
        {"max_ratio": max(narrow.values()), "lower_p0": len(lower_p0), "of": len(med)})
    odd = [narrow[k] for k in med if med[k]["n_candidates"] % 2 == 1]
    even = [narrow[k] for k in med if med[k]["n_candidates"] % 2 == 0]
    add("it narrows sigma0 most on the rosters with odd k", np.median(odd) < np.median(even),
        {"median_ratio_odd": float(np.median(odd)), "median_ratio_even": float(np.median(even))})
    add("centring on the other candidates' median widens sigma0 on every grid",
        all(alt[k]["others_median"]["loc"]["sigma0"] > base_fit[k]["sigma0"] for k in med), {})

    # Instruction-level intervals.
    jk = {e: np.median([_v(med[k])["jackknife_instructions"][e]["sigma0"]["se"] for k in med
                        if _v(med[k])["jackknife_instructions"][e]["sigma0"]["se"] is not None])
          for e in ("loc", "mle", "cm")}
    add("the jackknife standard errors are wider for the fixed-window MLE and central matching than for the locfdr-window MLE",
        jk["mle"] > jk["loc"] and jk["cm"] > jk["loc"], {e: float(x) for e, x in jk.items()})

    # Shrinkage.
    sh = read["shrinkage"]
    inf_ratio = {k: v["loc"]["median"]["ratio_of_inflations"] for k, v in sh.items()
                 if v["loc"]["median"]["ratio_of_inflations"] is not None}
    add("relative to its own band, the base-referenced grid is narrower on most subjects",
        sum(x < 1 for x in inf_ratio.values()) > len(inf_ratio) / 2,
        {"narrower": sum(x < 1 for x in inf_ratio.values()), "of": len(inf_ratio)})
    small = [inf_ratio[k] for k in inf_ratio if k.startswith(("calibration", "challenge")) and "__" not in k]
    ab = [inf_ratio[k] for k in inf_ratio if k.startswith(("auditbench", "nullext", "base_")) and "__" not in k
          and k not in OTHER_BASES]
    add("the shrinkage is larger on the small-model rosters than on the roster of AI labs",
        np.median(small) < np.median(ab), {"small": float(np.median(small)), "ai_labs": float(np.median(ab))})
    tr = {k: sh[k]["tau"]["ratio_registered_to_target_only"] for k in SMALL_TARGETS}
    add("base subtraction shrinks tau on every narrow-secret-loyalty and challenge target",
        all(x is not None and x < 1 for x in tr.values()), tr)
    tp = {k: sh[k]["tau"]["ratio_registered_to_target_only"] for k in AB_POSITIVES}
    base_tau = {k: _tau(med[meta_base]) for k, meta_base in (("auditbench_contextual_optimism", "base_A"),
                                                            ("auditbench_secret_loyalty", "base_secret_loyalty"))}
    add("it leaves tau almost unchanged (within 10 percent) on the two AuditBench positives",
        all(0.9 <= x <= 1.1 for x in tp.values()), {"ratios": tp, "base_tau": base_tau})
    wide = [k for k in ("auditbench_secret_loyalty__without_russia", "calibration_scoped__without_emmanuel_macron")
            if _fires(reg[k])]
    add("some base-referenced grids stay above their bands with the documented candidate removed", len(wide) >= 1,
        {"firing": wide})

    # Placebos.
    pl = read["placebo"]
    for grp in ("all", "base"):
        f = pl[grp]["fires"]
        add(f"placebo ({grp}): the locfdr-window sigma0, the lift and the maximum fire no more often than "
            "alpha allows (each Clopper-Pearson interval reaches alpha)",
            all(f[k]["lo"] <= ALPHA for k in ("sigma_loc", "lambda"))
            and pl[grp]["max_fires"]["lo"] <= ALPHA,
            {k: f[k] for k in ("sigma_loc", "lambda")} | {"max": pl[grp]["max_fires"]})
        add(f"placebo ({grp}): the fixed-window sigma0 fires more often than alpha allows "
            "(its Clopper-Pearson interval lies above alpha)",
            f["sigma_mle"]["lo"] > ALPHA, {"sigma_mle": f["sigma_mle"]})
    ks = pl["all"]["ks_uniform"]
    excess = {}
    for k in ("p_sigma0_loc", "p_lambda", "p_S"):
        n, share = ks[k]["n"], ks[k]["share_below_0.05"]
        excess[k] = float(stats.binomtest(int(round(share * n)), n, 0.05, alternative="greater").pvalue)
    add("placebo p values sit at or above uniform: no excess of p values at or below 0.05 (one-sided binomial p above alpha)",
        all(x > ALPHA for x in excess.values()), excess)
    nflag = pl["all"]["fires"]["flags_loc"]
    add("a few placebo splits carry flags under the bulk condition", 0 < nflag["k"] < nflag["n"] / 2, nflag)
    add("the median placebo tau stays below the tau of every base outside the roster of AI labs",
        pl["all"]["tau_pp"]["median"] < min(other_tau.values()),
        {"placebo_median": pl["all"]["tau_pp"]["median"], "other_base_min": min(other_tau.values())})
    pl_tau = [r["variants"]["all"]["tau"]["tau_pp"] for r in records if r["grid"] == "placebo"]
    reach = sum(x is not None and x >= min(other_tau.values()) for x in pl_tau)
    add("only a few placebo splits (under 5 percent) reach the smallest tau of those bases",
        reach < 0.05 * len(pl_tau), {"reach": reach, "n": len(pl_tau),
                                     "other_base_min": min(other_tau.values())})

    # Documented candidate.
    ranks = [(r["subject"], r["grid"], _v(r).get("documented_rank", {}).get("flags_loc")) for r in main
             if r.get("documented")]
    add("the documented candidate's rank p reaches the rank floor at best",
        all(x is None or x["p_rank"] >= x["floor"] - 1e-12 for _, _, x in ranks)
        and any(x and abs(x["p_rank"] - x["floor"]) < 1e-12 for _, _, x in ranks), {"ranks": ranks})
    drops = {k: (_infl(med[k[: k.index("__")]]), _infl(med[k])) for k in med if meta[k]["drop"]}
    add("removing the documented candidate narrows the optimism and informed grids toward their bands",
        all(drops[k][1] < drops[k][0] for k in drops if k.startswith(("auditbench_contextual", "calibration_informed"))),
        drops)
    add("the secret-loyalty and scoped grids stay above their bands without the documented candidate",
        all(_fires(med[k]) for k in drops if k.startswith(("auditbench_secret", "calibration_scoped"))),
        {k: _p(med[k]) for k in drops})

    # Counts.
    c = read["counts"]

    def n(cls, grid):
        x = c.get(cls, {}).get(grid, {})
        return x.get("sigma_loc", 0), x.get("n", 0)
    pos, base_t, nul = n("registered_positive", "median"), n("base_as_target", "median"), n("null", "median")
    add("target-only sigma0 fires on most registered positives, most bases and a minority of nulls",
        pos[0] > pos[1] / 2 and base_t[0] > base_t[1] / 2 and nul[0] < nul[1] / 2,
        {"positives": pos, "bases": base_t, "nulls": nul})
    nul_reg, base_reg = n("null", "registered"), n("base_as_target", "registered")
    add("base-referenced sigma0 fires on fewer nulls and on no base pair (mirror counted once)",
        nul_reg[0] < nul[0] and base_reg[0] == 0 and base_reg[1] == 3, {"nulls": nul_reg, "base_pairs": base_reg})

    # Agreement.
    ag = read["agreement_on_registered_positives"]
    add("under the bulk condition the target-only flags name the registered candidate for optimism, "
        "secret loyalty and challenge person",
        all(ag[k]["median"]["agrees_loc"] for k in ("auditbench_contextual_optimism", "auditbench_secret_loyalty",
                                                    "challenge_organism_a_person")), {})
    add("the informed and scoped fits fail the bulk condition, and most informed flags fall on the registered candidate",
        not ag["calibration_informed"]["median"]["bulk_ok_loc"] and not ag["calibration_scoped"]["median"]["bulk_ok_loc"]
        and ag["calibration_informed"]["median"]["plurality_loc_any_fit"] == [ag["calibration_informed"]["registered_candidate"]],
        {})
    bp = ag["calibration_blind_person"]["median"]
    add("on the blind person roster another candidate takes the plurality",
        bp["plurality_loc"] and not bp["agrees_loc"], {"plurality": bp["plurality_loc"],
                                                       "registered": ag["calibration_blind_person"]["registered_candidate"]})
    add("base subtraction brings the scoped and blind person pluralities to the registered candidate",
        ag["calibration_scoped"]["registered"]["agrees_loc"] and ag["calibration_blind_person"]["registered"]["agrees_loc"], {})
    add("base subtraction moves the challenge person plurality away from the registered candidate",
        not ag["challenge_organism_a_person"]["registered"]["agrees_loc"], {})
    add("the agreement table covers every registered positive", len(ag) == pos[1], {"rows": sorted(ag)})

    # User awareness and atoms.
    ua = read["user_awareness"]
    ones = [(r["subject"], r["grid"], _v(r)["lambda_atoms"]) for r in main if abs(_v(r)["lambda"] - 1) < 1e-6]
    ones_ua = [(k, g, x["lambda_atoms"]) for k, v in ua.items() for g, x in v.items() if abs(x["lambda"] - 1) < 1e-6]
    add("several lifts on the user-awareness and larger grids equal one, each on an atom that the observed and "
        "permuted medians share",
        len(ones) > 0 and len(ones_ua) > 0
        and all(x["share_permuted_medians_tied"] > 0.05 for _, _, x in ones + ones_ua), {"grids": ones + ones_ua})
    add("no served model shows a median-contrast lift that leaves the band",
        all(v["median"]["p_lambda"] > ALPHA for v in ua.values()), {k: v["median"]["p_lambda"] for k, v in ua.items()})
    mean_fire = sorted(k for k, v in ua.items() if v["mean"]["p_lambda"] <= ALPHA)
    add("exactly one served model shows a mean-contrast lift that leaves the band while its maximum does not",
        len(mean_fire) == 1 and ua[mean_fire[0]]["mean"]["p_S"] > ALPHA, {"firing": mean_fire})

    add("every recomputed statistic equals its stored counterpart", all(x["match"] for x in rec["checks"]),
        {"checks": len(rec["checks"]), "mismatches": [x for x in rec["checks"] if not x["match"]]})
    add("every listed grid completed", not rec["missing_grids"], {"missing": rec["missing_grids"]})
    return out
