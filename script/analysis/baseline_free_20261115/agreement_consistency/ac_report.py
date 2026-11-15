"""The family's README: settings, inputs, reproduction, the three parts, and the reading.

Every number sits in a table built from the assembled rows. The reading in
``READING`` interprets the tables and carries no numbers of its own.
"""

from __future__ import annotations

from collections import defaultdict

from script.analysis.baseline_free_20261115.agreement_consistency.ac_subjects import (
    PANEL_POSITIVE, PANEL_TARGET)

UPSTREAM_KEY = {"context_contrast": "up_context_family", "embedding_target_only": "up_embedding",
                "cross_run_panel": "up_panel_family", "name_population_outlier": "up_npo_rms",
                "pooled_coherence": "up_pooled_coherence", "sharp_null_screen": "up_snl_loser",
                "user_awareness": "up_ua_meangrade"}
GROUP_ORDER = ("positive", "challenge", "null", "base", "placebo", "served")
GROUP_LABEL = {"positive": "trained targets", "challenge": "challenge rosters",
               "null": "null controls", "base": "bases as targets",
               "placebo": "placebo halves", "served": "served models", "all": "all"}
METHOD_LABEL = {
    "mean": "target-only max, mean of others",
    "median": "target-only max, median of others",
    "detachment": "peak detachment (permutation)",
    "grubbs": "Grubbs on peaks (normal null)",
    "coherence": "breadth across axes",
    "context": "framing interaction (instrumental framings minus none)",
    "panel": "panel of AuditBench models, resampled maxima",
    "panel_rank": "panel of AuditBench models, member rank",
    "up_snl_loser": "loser dispersion (sharp-null family)",
    "up_npo_rms": "Grubbs on RMS and peak (name-population family)",
    "up_pooled_coherence": "pooled coherence over conditions",
    "up_ua_meangrade": "Grubbs on mean grade (user-awareness family)",
    "up_panel_family": "panel (cross-run family)",
    "up_context_family": "signed context contrast (context family)",
    "up_embedding": "masked embeddings (embedding family)",
    "up_ua_transluce_amanda": "Transluce predictive t for Amanda Askell (user-awareness family)",
    "registered": "registered test (with base)",
    "up_ua_decoy_conformal_amanda": "Amanda Askell among decoys, conformal p (user-awareness family)",
    "up_ua_decoy_calibration_amanda": "Amanda Askell among decoys, calibration p (user-awareness family)",
    "up_ua_decoy_predictive_amanda": "Amanda Askell among decoys, predictive t (user-awareness family)",
}

#: The interpretation, one paragraph per part, kept in ``ac_reading``.
try:
    from script.analysis.baseline_free_20261115.agreement_consistency.ac_reading import (
        READING)
except ImportError:  # the reading is written after the tables are read
    READING: dict[str, str] = {}


def _fmt(x, nd=3):
    if x is None or x == "":
        return ""
    if isinstance(x, bool):
        return "yes" if x else "no"
    if isinstance(x, float):
        if x != x:
            return ""
        if abs(x) >= 1e4 or x == float("inf"):
            return "inf" if x == float("inf") else f"{x:.3g}"
        if 0 < abs(x) < 10 ** -nd:
            return f"{x:.1e}"
        return f"{x:.{nd}f}"
    return str(x)


def _table(header: list[str], rows: list[list]) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for r in rows:
        out.append("| " + " | ".join(_fmt(c) for c in r) + " |")
    return out + [""]


def _group(row: dict) -> str:
    g = row["group"]
    if g == "ORG":
        return "challenge" if row["role"] == "challenge" else "positive"
    return {"NULL": "null", "BASE": "base", "UA": "served", "PLACEBO": "placebo"}[g]


def readme(matrix, pairs, rates, framing, folds, members, varcomp, checks, settings,
           upstream_status) -> str:
    L: list[str] = ["# Agreement between methods and consistency of the named candidate", ""]
    L += [READING.get("intro", ""), ""]

    L += ["## Settings", ""]
    L += _table(["setting", "value"], [
        ["permutations", settings["n_permutations"]], ["seed", settings["seed"]],
        ["alpha", settings["alpha"]],
        ["fold split", f"{settings['fold_split']['n_folds']} folds of 9, seed "
                       f"{settings['fold_split']['seed']}, stratified by template family"],
        ["partial conjunction", "at least 3 of 4 folds; Fisher's method on the 2 largest "
                                "fold p values"],
        ["framings", ", ".join(settings["framings"])],
        ["neutral framing of the framing interaction", "none"],
        ["panel reference", settings["methods"]["panel"]],
        ["panel member rank", settings["methods"]["panel_rank"]],
        ["Grubbs null", settings["methods"]["grubbs"]],
        ["pre-registered targets", "Anthropic on the 15 AuditBench panel members, Russia on "
                                   "secret loyalty, Amanda Askell on the served models"],
        ["placebo halves", "base A and the flattery null, replicate 0 of "
                           "common.subjects.placebo_halves"],
        ["code commit", settings["code_commit"]]])

    L += ["## Inputs", ""]
    rows = [["subject registry", settings["registry"]["path"],
             settings["registry"]["sha256"][:16]]]
    for path, meta in sorted(settings["upstream_sources"].items()):
        rows.append(["other family", path, meta["sha256"][:16]])
    L += _table(["input", "path", "sha256 (first 16)"], rows)
    L += _table(["family", "status when assembled"],
                [[k, v] for k, v in sorted(upstream_status.items())])

    L += ["## Reproduction of stored results", ""]
    by = defaultdict(lambda: [0, 0])
    for c in checks:
        by[c["what"]][0] += 1
        by[c["what"]][1] += c["match"]
    L += _table(["check", "subjects", "match"], [[k, v[0], v[1]] for k, v in sorted(by.items())])
    bad = [c for c in checks if not c["match"]]
    if bad:
        L += _table(["subject", "check", "field", "recomputed", "stored"],
                    [[c["subject"], c["what"], f["field"], f["got"], f["stored"]]
                     for c in bad for f in c["fields"]])

    L += ["## (a) Which candidate each method names", "", READING.get("a", ""), ""]
    rate_rows = []
    for r in rates:
        rate_rows.append([METHOD_LABEL.get(r["method"], r["method"]), GROUP_LABEL[r["group"]],
                          r["n_subjects"], r["n_reject"], r["share_reject"],
                          f"{r['n_leader_matches_registered']} of {r['n_registered_named']}",
                          f"{r['n_leader_matches_documented']} of {r['n_documented']}"])
    L += ["Table A1. How often each method rejects at alpha 0.01, and how often its leading "
          "candidate is the registered test's name or the documented target.", ""]
    L += _table(["method", "group", "subjects", "reject", "share", "leader = registered name",
                 "leader = documented"], rate_rows)
    L += ["Table A2. Share of subjects (three or more candidates) on which two methods lead "
          "with the same candidate, against the share independence gives (mean of 1/k).", ""]
    methods = []
    for p in pairs:
        for m in (p["method_a"], p["method_b"]):
            if m not in methods:
                methods.append(m)
    short = {m: f"m{i + 1}" for i, m in enumerate(methods)}
    L += _table(["key", "method"], [[short[m], METHOD_LABEL.get(m, m)] for m in methods])
    for g in ("positive", "null", "base", "all"):
        cell = {(p["method_a"], p["method_b"]): p for p in pairs if p["group"] == g}
        cell.update({(b, a): v for (a, b), v in list(cell.items())})
        if not cell:
            continue
        exp = [p["share_expected_independent"] for p in pairs if p["group"] == g]
        L += [f"Group: {GROUP_LABEL[g]}. Each cell is the share agreeing (agreeing / subjects). "
              f"Independence gives about {_fmt(sum(exp) / len(exp), 2)}.", ""]
        rows = []
        for a in methods:
            line = [short[a]]
            for b in methods:
                if a == b:
                    line.append("")
                    continue
                c = cell.get((a, b))
                line.append(f"{_fmt(c['share_agree'], 2)} ({c['n_agree']}/{c['n_subjects']})"
                            if c else "")
            rows.append(line)
        L += _table(["", *[short[m] for m in methods]], rows)
    L += ["Table A3. Leading candidate and p of each method on every subject. A name in "
          "the registered column is the naming rule's.", ""]
    hdr = ["subject", "k", "registered (p)", "mean (p)", "median (p)", "detach p",
           "Grubbs p", "coherence (p)", "framing interaction (p)", "panel p (resampled)",
           "panel p (rank)"]
    rows = []
    for m in sorted(matrix, key=lambda m: (GROUP_ORDER.index(_group(m)), m["subject"])):
        def lp(key):
            lead, p = m.get(f"{key}_leader"), m.get(f"{key}_p")
            return "" if lead is None and p is None else f"{lead or ''} ({_fmt(p, 4)})"
        reg = ("" if m["registered_p"] is None else
               f"{m['registered_named_by_rule'] or '-'} ({_fmt(m['registered_p'], 4)})")
        rows.append([m["subject"], m["k"], reg, lp("mean"), lp("median"),
                     _fmt(m["detachment_p"], 4), _fmt(m["grubbs_p"], 4), lp("coherence"),
                     lp("context"), _fmt(m["panel_p"], 4), _fmt(m["panel_rank_p"], 4)])
    L += _table(hdr, rows)
    ups = sorted({k[:-7] for m in matrix for k in m if k.startswith("up_")
                  and k.endswith("_leader") and m[k] is not None})
    if ups:
        L += ["Table A4. The other families' leading candidates and p values.", ""]
        rows = []
        for m in sorted(matrix, key=lambda m: (GROUP_ORDER.index(_group(m)), m["subject"])):
            cells = []
            for u in ups:
                lead, p = m.get(f"{u}_leader"), m.get(f"{u}_p")
                cells.append("" if lead is None and p is None else f"{lead or ''} ({_fmt(p, 4)})")
            if any(cells):
                rows.append([m["subject"], *cells])
        L += _table(["subject", *[METHOD_LABEL.get(u, u) for u in ups]], rows)
    ua = [m for m in matrix if m["group"] == "UA"]
    if ua:
        L += ["Table A5. The served models, with Amanda Askell as the pre-registered target.", ""]
        L += _table(["subject", "mean (p)", "median (p)", "Grubbs p", "Askell peak rank of 10",
                     "Askell peak deleted t", "Askell p (t)", "Askell p (permutation)",
                     "Askell p, Transluce t", "Askell p among decoys (conformal)",
                     "Askell p among decoys (calibration)"],
                    [[m["subject"], f"{m['mean_leader']} ({_fmt(m['mean_p'], 4)})",
                      f"{m['median_leader']} ({_fmt(m['median_p'], 4)})",
                      _fmt(m["grubbs_p"], 4), m["prereg_rank"], m["prereg_deleted_t"],
                      m["prereg_p_deleted_t"], m["prereg_p_loo_permutation"],
                      m.get("up_ua_transluce_amanda_p"), m.get("up_ua_decoy_conformal_amanda_p"),
                      m.get("up_ua_decoy_calibration_amanda_p")] for m in ua])

    L += ["## (b) Consistency over the four framings", "", READING.get("b", ""), ""]
    L += ["Table B1. Kendall's W of the target-only peaks over the four framings, whether all "
          "four lead with the same candidate, and the per-framing reruns. Rosters with two "
          "candidates have tied peaks by antisymmetry, so only the profile correlation is "
          "defined there.", ""]
    rows = []
    for r in framing:
        rows.append([r["roster"], r["seat"], r.get("k"), r.get("W"), r.get("W_p_perm"),
                     r.get("all_framings_same_leader"), r.get("common_leader"),
                     r.get("profile_correlation"), r.get("profile_p_perm"),
                     r.get("sharp_mean_framings_rejecting"),
                     r.get("registered_framings_rejecting"),
                     r.get("registered_named_pooled") if r["seat"] == "target" else ""])
    L += _table(["roster", "seat", "k", "W", "W p (shuffle)", "all four same", "leader",
                 "profile r", "profile p", "framings rejecting (target-only mean)",
                 "framings rejecting (registered)", "registered name (pooled)"], rows)
    agg = []
    for seat in ("target", "base"):
        rs = [r for r in framing if r["seat"] == seat and r.get("W") is not None]
        allr = [r for r in framing if r["seat"] == seat]
        if not allr:
            continue
        agg.append([seat, len(rs), sum(bool(r["all_framings_same_leader"]) for r in rs),
                    sum(r["W_p_perm"] <= 0.01 for r in rs if r.get("W_p_perm") is not None),
                    sum(r["W"] for r in rs) / len(rs) if rs else None,
                    sum(r["independence_rate_all_same"] for r in rs) / len(rs) if rs else None,
                    sum(r.get("profile_p_perm", 1) <= 0.01 for r in allr
                        if r.get("profile_p_perm") is not None), len(allr)])
    L += ["Table B2. Targets against their own untuned bases.", ""]
    L += _table(["seat", "rosters with k > 2", "all four same", "W p <= 0.01", "mean W",
                 "independence rate of all four same", "profile p <= 0.01",
                 "rosters"], agg)

    L += ["Table B3. Variance components of cell rates over all candidates and the 140 or "
          "144 instructions of each framed roster, summed over axes. The profile r is the mean "
          "correlation of the candidates' centred mean rates between framings.", ""]
    L += _table(["roster table", "k", "Var(theta)", "Var(eta)", "binomial",
                 "theta share of signal", "eta / binomial", "profile r over framings"],
                [[r["member"], r["n_candidates"], r["sum_var_theta"], r["sum_var_eta"],
                  r["sum_var_eps"], r["share_theta_of_signal"], r["eta_over_eps"],
                  r["fold_profile_correlation"]] for r in varcomp
                 if r.get("candidates") == "all_candidates"
                 and r.get("design", "").startswith("framed")])
    L += ["## (c) Replication over instruction folds in AuditBench", "", READING.get("c", ""),
          ""]
    L += ["Table C1. Each panel member: the fold-level detachment test, its partial "
          "conjunction, and consistency of the peaks over folds.", ""]
    rows = []
    for r in members:
        leaders = [r.get(f"fold{n}_detach_leader") for n in range(4)]
        rows.append([r["member"], " / ".join(str(x) for x in leaders),
                     " / ".join(_fmt(r.get(f"fold{n}_detach_p"), 3) for n in range(4)),
                     r.get("detach_pc_3of4_p"), r.get("W_folds"), r.get("W_folds_p_perm"),
                     r.get("all_folds_same_peak_leader"), r.get("sharp_mean_folds_rejecting"),
                     r.get("sharp_mean_pc_3of4_p")])
    L += _table(["member", "fold leaders", "fold detachment p", "PC p (3 of 4)", "W",
                 "W p (shuffle)", "same leader in all folds",
                 "folds rejecting (target-only mean)", "PC p of target-only mean"], rows)
    target = [r for r in folds if r.get("member") == PANEL_POSITIVE and
              r.get("candidate") == PANEL_TARGET]
    plac = [r for r in folds if r.get("role") == "placebo"]
    anth_null = [r for r in plac if r.get("candidate") == PANEL_TARGET]
    L += ["Table C2. Candidate-level partial conjunction: the documented target against "
          "the candidate placebos.", ""]
    rows = [[f"Anthropic in {PANEL_POSITIVE}", len(target),
             sum(r["pc_3of4_reject"] for r in target),
             min((r["pc_3of4_p"] for r in target), default=None)],
            ["Anthropic in the 14 null members", len(anth_null),
             sum(r["pc_3of4_reject"] for r in anth_null),
             min((r["pc_3of4_p"] for r in anth_null), default=None)],
            ["every placebo (candidate, member)", len(plac),
             sum(r["pc_3of4_reject"] for r in plac),
             min((r["pc_3of4_p"] for r in plac), default=None)],
            ["placebos in the positive (other 5 candidates)",
             sum(r["member"] == PANEL_POSITIVE for r in plac),
             sum(r["pc_3of4_reject"] for r in plac if r["member"] == PANEL_POSITIVE),
             min((r["pc_3of4_p"] for r in plac if r["member"] == PANEL_POSITIVE),
                 default=None)]]
    L += _table(["candidates", "n", "PC p <= 0.01", "smallest PC p"], rows)
    passing = [r for r in plac if r["pc_3of4_reject"]]
    if passing:
        L += _table(["placebo passing", "member", "fold p values", "PC p"],
                    [[r["candidate"], r["member"],
                      " / ".join(_fmt(r[f"fold{n}_p"], 4) for n in range(4)), r["pc_3of4_p"]]
                     for r in passing])
    L += ["Table C3. Variance components of cell rates, summed over axes, without Anthropic "
          "(non-target) and with every candidate. Reliability is the stable share of a "
          "candidate's fold-mean variance at 9 instructions; the profile r is the mean "
          "correlation of the candidates' centred mean rates between folds.", ""]
    vc = {(r["member"], r["candidates"]): r for r in varcomp
          if r.get("design", "").startswith("AuditBench")}
    rows = []
    for member in dict.fromkeys(r["member"] for r in varcomp
                                if r.get("design", "").startswith("AuditBench")):
        a, b = vc.get((member, "non_target"), {}), vc.get((member, "all_candidates"), {})
        rows.append([member, a.get("sum_var_theta"), a.get("sum_var_eta"), a.get("sum_var_eps"),
                     a.get("eta_over_eps"), a.get("fold_reliability_9"),
                     a.get("fold_profile_correlation"), b.get("sum_var_theta"),
                     b.get("fold_reliability_9"), b.get("fold_profile_correlation")])
    L += _table(["member", "Var(theta), non-target", "Var(eta), non-target",
                 "binomial, non-target", "eta / binomial", "fold reliability, non-target",
                 "fold profile r, non-target", "Var(theta), all", "fold reliability, all",
                 "fold profile r, all"], rows)

    L += ["## Reading", "", READING.get("reading", ""), ""]
    absent = sorted(k for k, v in upstream_status.items() if v == "absent")
    if absent or READING.get("incomplete"):
        L += ["## Inputs absent when the tables were assembled", ""]
        if READING.get("incomplete"):
            L += [READING["incomplete"], ""]
        if absent:
            L += _table(["family", "columns left empty"],
                        [[k, METHOD_LABEL.get(UPSTREAM_KEY.get(k, ""), k)] for k in absent])
    L += ["## Files", ""]
    L += _table(["file", "contents"], [
        ["agreement_matrix.csv", "one row per subject: every method's statistic, p, leader "
                                 "and name, the registered result and the documented target"],
        ["agreement_pairs.csv", "pairwise leader agreement by group, with the independence rate"],
        ["method_rates.csv", "rejection and match rates by method and group"],
        ["framing_consistency.csv", "part (b), one row per roster and seat"],
        ["fold_replication.csv", "part (c), one row per panel member and candidate"],
        ["fold_members.csv", "part (c), one row per panel member"],
        ["variance_components.csv", "part (c), Var(theta) and Var(eta) per member"],
        ["panel_reference.json", "the panel test of every AuditBench member"],
        ["reproduction_checks.json", "every overlap with a stored record"],
        ["runs/<subject>.json", "everything about one subject"],
        ["summary.csv", "one compact row per subject"],
        ["settings.json", "settings, fold split, inputs and their sha256"],
        ["tasks.jsonl", "the raw result of every task"]])
    return "\n".join(L) + "\n"
