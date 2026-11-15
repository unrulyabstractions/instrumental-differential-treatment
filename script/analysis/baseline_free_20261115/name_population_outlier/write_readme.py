"""Write README.md for the name-population outlier family from its own outputs.

    PYTHONPATH=. .venv/bin/python \\
        script/analysis/baseline_free_20261115/name_population_outlier/write_readme.py

Every number comes from ``results.json``, ``reproduce_check.json``,
``grubbs_null_k3_k11.json``, ``split_half_many.json``, the two selfcheck files or
a per-run record. The prose holds no numbers. Refuses to overwrite an existing
README.

The run records keep the field name ``p_exact_mc`` (and the method key
``grubbs_exact``) for the normal-theory Monte Carlo p, because other families
read those columns of ``outlier_table.csv``. Every label here calls it
normal-theory.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OUT = REPO / "out/main/baseline_free_20261115/name_population_outlier"
ROLE_ORDER = ("positive", "null", "base", "half", "ua")
ROLE_LABEL = {"positive": "Positives", "null": "Nulls", "base": "Bases as targets",
              "half": "Split halves (one split)", "ua": "User awareness"}
METHOD_LABEL = {
    "grubbs_shuffle_holm": "Grubbs, shuffle null, Holm",
    "grubbs_shuffle_peak": "Grubbs, shuffle null, peak",
    "grubbs_shuffle_rms": "Grubbs, shuffle null, RMS",
    "grubbs_exact_holm": "Grubbs, normal-theory null, Holm",
    "grubbs_exact_peak": "Grubbs, normal-theory null, peak",
    "grubbs_exact_rms": "Grubbs, normal-theory null, RMS",
    "grubbs_bound_holm": "Grubbs, t bound, Holm",
    "mad_detachment_holm": "MAD detachment, Holm",
    "mad_detachment_peak": "MAD detachment, peak",
    "mad_detachment_rms": "MAD detachment, RMS",
    "target_only_max": "Target-only maximum",
    "registered": "Registered test (base model)",
}
PLACEBO_LABEL = {
    "holm_p_t": "deleted residual, t, Holm", "holm_p_shuffle": "deleted residual, shuffle, Holm",
    "holm_rank_p": "rank p, Holm", "peak_p_t": "deleted residual, t, peak", "rms_p_t": "deleted residual, t, RMS",
    "peak_signed_p_t": "deleted residual, t, signed peak",
    "mean_signed_p_t": "deleted residual, t, mean signed t",
}

SUMMARY_PROSE = """
We lead with Grubbs's test against the within-instruction shuffle, Holm over the peak and RMS scalars.
The shuffle calibrates against sampling noise.
The normal-theory rows carry their measured size under that shuffle in the next table.
""".strip()

#: The reading of the tables above. It holds no numbers; the tables hold them.
READING = """
We first ask whether the stored claim that detachment rejects on no run holds on the current data.
The stored records hold the peak form of the MAD detachment.
The peak form rejects on no subject at the registered alpha.
At the looser alpha the peak form rejects on none of the paper's runs and nulls.
The RMS form rejects at the registered alpha on contextual optimism and on one half of base A.
We therefore contend that the claim holds for the peak form at the registered alpha, and that it must name the peak form.

We next read Grubbs's test against the within-instruction shuffle, Holm over the two scalars.
It rejects on contextual optimism and on the informed narrow secret loyalty.
Both rejections name the candidate the registered test names.
Both rejections come from the RMS scalar.
It also rejects on a synthetic-document null.
It rejects on no base read as a target.
The test misses most registered positives.
We therefore contend that every detection this form makes on these data comes from the RMS scalar.

The normal-theory null of Grubbs's G is exact only for normal scalars.
The peak and RMS scalars are skewed under sampling noise.
We measure the size of each normal-theory test under the subject's own shuffle.
On the peak scalar the size exceeds nominal on every subject the size table covers.
The RMS form sits nearer nominal in the median.
Holm over the two scalars sits in between.
The shuffle quantile of G lies above the normal quantile in almost every subject and scalar.
The normal-theory form also fires on a null control and on a placebo half where the shuffle form does not.
The peak scalar drives both extra rejections.
We therefore contend that the normal-theory p is liberal on these tables and that a decision should rest on the shuffle p.

A **placebo target** is a candidate with no hypothesis behind it, read as if pre-registered.
On the null controls the deleted residual rejects on placebo targets of several models.
Every such rejection lies on the contextual-optimism roster.
Stanford holds most of them.
The deleted residual rejects on no placebo target of a base table or of another roster.
Stanford also leads the RMS scalar in most nulls and base draws on that roster.
We read this as one generic name effect that these models share.
The target-only maximum fires on every Qwen base read as a target.
Grubbs's test fires on none of the base tables.
We therefore contend that a Level-1 rejection marks a name that stands out in this model, and that decoy names or a model panel must calibrate it before it supports a verdict.

A single split-half placebo can mislead in either direction.
We draw many random splits of each source.
On every source the normal-theory Grubbs test rejects on the halves above its nominal rate.
The placebo-target rejection rate on the halves also sits above nominal on every source.
On each source one name holds most of those rejections.
We therefore posit that a model's own name effects push the normal-theory forms past their nominal rate.

The pre-registered targets are the documented principals, so they act as an oracle.
The contextual-optimism principal rejects against its normal-theory null.
The secret-loyalty principal falls short of the registered alpha after Holm.
We also refer each principal to the placebo targets of the null and base tables on its roster.
The contextual-optimism principal's RMS residual exceeds every placebo target there.
A null placebo target exceeds its peak residual.
Its rank p still sits above the registered alpha, because the reference holds too few placebo targets.
The secret-loyalty roster has a single base table, so its reference cannot reach the registered alpha at all.
A blind auditor who reads the leader pays a factor of the number of candidates.
The Grubbs bound carries that factor.
We therefore contend that a pre-registered target draws its power from the oracle, and that its normal-theory p needs a calibration these rosters cannot yet supply.

The rank p never rejects, because its floor sits above the registered alpha at every k we hold.
We therefore posit that exchangeability alone cannot carry a decision at this alpha without decoys.

The blind-person tables hold three candidates.
There the deleted residual has a single degree of freedom.
The normal-theory critical G sits at its ceiling.
The counts above also appear without these tables.
We therefore contend that these tables cannot show the test's power.

Our test finds no safety-user effect on any of the three subjects.
The verdict holds against the other nine identities and against the six general identities alone.
On GPT-5 every safety identity's mean signed t exceeds that of every general identity.
The safety family still falls short of the registered alpha there.
On GPT-5 the affiliation twin receives harsher grades than the general identities.
The twin lies outside the pre-registered family, so we read that row as exploratory.
On GPT-4.1 mini a safety identity receives more lenient grades than the general identities.
Holm over the three safety identities removes that result.
On GPT-5 mini the target-only maximum fires on a general-population identity graded more leniently.
The design holds few exchanges and few samples per cell, so it can miss small effects.
We therefore conjecture that this grading task does not reproduce the safety-user effect at a size the design can detect.

Several decisions sit within a few Monte Carlo standard errors of the registered alpha.
The flag table lists each one.
We therefore posit that no reading here should rest on a single flagged decision.

The court runs and three challenge rosters hold two candidates each, so the test is undefined there.
"""


def _p(x) -> str:
    if x is None:
        return "--"
    if isinstance(x, str):
        return x
    if x != x:
        return "nan"
    if x < 1e-4:
        return f"{x:.1e}"
    return f"{x:.4f}"


def _f(x, nd=3) -> str:
    if x is None:
        return "--"
    if isinstance(x, str):
        return x
    if x != x:
        return "nan"
    if x in (float("inf"), float("-inf")):
        return "inf" if x > 0 else "-inf"
    return f"{x:.{nd}f}"


def _ci(ci) -> str:
    return "--" if not ci else f"[{ci[0]:.3f}, {ci[1]:.3f}]"


def table(header: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c).replace("|", "\\|") for c in r) + " |" for r in rows]
    return "\n".join(out)


def _count(v: dict, a: float) -> str:
    """x/n, with the count without the k = 3 tables when it differs."""
    s = f"{v[f'reject_{a}']}/{v['n']}"
    if v.get("n_k4") is not None and v["n_k4"] != v["n"]:
        s += f" (k >= 4: {v[f'reject_k4_{a}']}/{v['n_k4']})"
    return s


def main() -> None:
    path = OUT / "README.md"
    if path.exists():
        raise SystemExit(f"refusing to overwrite {path}")
    res = json.loads((OUT / "results.json").read_text())
    rep = json.loads((OUT / "reproduce_check.json").read_text())
    gnull = json.loads((OUT / "grubbs_null_k3_k11.json").read_text())
    selfcheck = json.loads((OUT / "selfcheck.json").read_text())
    selfrev = json.loads((OUT / "selfcheck_revision.json").read_text())
    split = json.loads((OUT / "split_half_many.json").read_text())
    st, sm = res["settings"], res["summary"]
    runs = {p.stem: json.loads(p.read_text()) for p in sorted((OUT / "runs").glob("*.json"))}
    rb = sm["rejections_by_role"]

    L = []
    L.append("# Name-population outlier test: detachment, Grubbs, deleted residual, rank p")
    L.append("")
    L.append(
        "This family asks a Level-1 question of one model with no base model. "
        "Each audited candidate gets one scalar from the target-only t-grid. "
        "The test asks whether the leading candidate's scalar comes from the same distribution as the other "
        "candidates' scalars. "
        "A rejection claims that the candidate is anomalous among the audited names of this model, under a "
        "shape assumption. "
        "It cannot claim tuning. "
        "A rank p cannot fall below one over the number of candidates.")
    L.append("")

    # ------------------------------------------------------------------ summary
    L.append("## Summary")
    L.append("")
    L.append(SUMMARY_PROSE)
    L.append("")
    rows = []
    for m in ("grubbs_shuffle_holm", "grubbs_exact_holm", "mad_detachment_holm", "mad_detachment_peak",
              "target_only_max", "registered"):
        row = [METHOD_LABEL[m]]
        for role in ROLE_ORDER:
            v = rb.get(role, {}).get(m)
            row.append("--" if not v else _count(v, 0.01))
        rows.append(row)
    L.append("Rejections at alpha 0.01, by role. A count in parentheses leaves out the k = 3 tables.")
    L.append("")
    L.append(table(["Method"] + [ROLE_LABEL[r] for r in ROLE_ORDER], rows))
    L.append("")
    nts = sm["normal_theory_size_under_shuffle"]["by_role_k4"]
    rows = []
    for role in ROLE_ORDER:
        v = nts[role]["0.01"]
        rows.append([ROLE_LABEL[role], nts[role]["n_subjects_k4"]] + [
            f"{v[c]['median']:.4f} [{v[c]['min']:.4f}, {v[c]['max']:.4f}]"
            for c in ("grubbs_normal_peak", "grubbs_normal_rms", "grubbs_normal_holm",
                      "deleted_residual_holm")])
    L.append("Size of the normal-theory tests at nominal 0.01 under each subject's own shuffle, k >= 4 "
             "(median [min, max] over subjects):")
    L.append("")
    L.append(table(["Role", "Subjects", "Grubbs, peak", "Grubbs, RMS", "Grubbs, Holm",
                    "Deleted residual, Holm, mean over candidates"], rows))
    L.append("")
    sh = split["sources"]
    rows = []
    for src, v in sh.items():
        a = v["0.01"]
        rows.append([src, v["n_splits"], v["n_halves"],
                     f"{a['grubbs_normal_holm']['rate']:.4f} {_ci(a['grubbs_normal_holm']['clopper_pearson_95'])}",
                     f"{a['placebo_targets_holm_p_t']['rate']:.4f} "
                     f"{_ci(a['placebo_targets_holm_p_t']['clopper_pearson_95'])}"])
    L.append("Split-half placebo over many random splits, normal-theory forms at nominal 0.01:")
    L.append("")
    L.append(table(["Source", "Splits", "Halves", "Grubbs, Holm, rate", "Placebo targets, deleted residual, "
                    "Holm, rate"], rows))
    L.append("")
    pf = sm["placebo_targets"]
    rows = []
    for g in ("null", "base", "null+base", "null+base, contextual-optimism roster", "null+base, other rosters"):
        x = pf[g]["holm_p_t@0.01"]
        rows.append([g, f"{x['models_with_any']}/{pf[g]['n_models']}",
                     f"{x['rejections']}/{pf[g]['n_tests']}", _ci(x["clopper_pearson_95"])])
    L.append("Placebo targets on whole tables (no subset tables), deleted residual with its t p, Holm over the "
             "two scalars, at 0.01:")
    L.append("")
    L.append(table(["Group", "Models with any", "Placebo targets rejected", "Clopper-Pearson 95%"], rows))
    L.append("")

    # ------------------------------------------------------------------ settings
    L.append("## Settings")
    L.append("")
    gn = st["grubbs_normal_theory_null"]
    L.append(table(["Setting", "Value"], [
        ["Permutations", st["n_permutations"]], ["Seed", st["seed"]], ["Alpha", st["alpha"]],
        ["Monte Carlo SE of a permutation p at alpha", f"{st['monte_carlo_se_at_alpha']:.5f}"],
        ["Contrast", st["contrast"]], ["t-grid", st["t_grid"]], ["Shuffle", st["permutation"]],
        ["Scalars", "; ".join(f"{k}: {v}" for k, v in st["scalars"].items())],
        ["MAD detachment", st["mad_detachment"]], ["Grubbs", st["grubbs"]],
        ["Normal-theory Grubbs null", f"{gn['draws_per_k']} normal draws per k, k = {gn['k'][0]} to "
                                      f"{gn['k'][-1]}, seed {gn['seed']}; p = {gn['p']}; exact only if "
                                      f"{gn['exact_only_if']}"],
        ["Field names", gn["fields"]],
        ["Size under the shuffle", st["normal_theory_size_under_shuffle"]],
        ["Grubbs bound", st["grubbs_bound"] + " (read off the leader's deleted residual, which equals t_G)"],
        ["Deleted residual", st["deleted_residual"]], ["Rank p", st["rank_p"]], ["Holm", st["holm"]],
        ["Pre-registered targets", "; ".join(f"{k}: {', '.join(v)}" for k, v in st["preregistered"].items())],
        ["Pre-registered label", "; ".join(f"{k}: {v}" for k, v in st["preregistered_label"].items())],
        ["User awareness, general reference", st["ua_general_reference"]],
        ["User awareness, paired grades", st["ua_paired_grades"]],
        ["Placebo targets", st["placebo_targets"]],
        ["k = 3", st["k3"]],
        ["Split-half seed (one split)", st["split_half_seed"]],
        ["Split-half placebo, many splits", f"{split['settings']['n_splits_per_source']} splits per source, "
                                            f"split seed {split['settings']['split_seed_of_split_i']}; "
                                            f"{split['settings']['statistics']}"],
    ]))
    L.append("")

    # ------------------------------------------------------------------ selfcheck
    L.append("## Selfcheck")
    L.append("")
    rows = []
    for k, v in selfcheck["identities_and_t_law"]["by_k"].items():
        rows.append([k, f"{v['max_abs_err_G_formula_vs_direct']:.1e}",
                     f"{v['max_abs_err_bound_p_from_G_vs_from_r']:.1e}",
                     _p(v["deleted_residual_ks_vs_t"]["p"]), "pass" if v["passed"] else "FAIL"])
    L.append(table(["k", "G-D identity, max abs error", "bound p from G vs from r, max abs error",
                    "KS p, deleted residual vs t(k-2)", "Result"], rows))
    L.append("")
    rows = []
    for k, v in selfcheck["null_and_report_table"]["report_table"].items():
        rows.append([k] + [f"{v['report'][f]} / {v['got'][f]:.3f}" for f in ("G_max", "G_05", "D_05_top", "D_05_pre")])
    L.append("Operating points of the research report against this Monte Carlo (report / here):")
    L.append("")
    L.append(table(["k", "largest G", "Grubbs 5% G", "D 5%, top chosen", "D 5%, pre-specified"], rows))
    L.append("")
    eng = selfcheck["engine_reproduces_stored_tests"]
    L.append(table(["Engine check on simulated tables", "Result"],
                   [[k, "exact" if v["passed"] else "FAIL"] for k, v in eng["cases"].items()]))
    L.append("")
    rt = selfrev["reference_residual_t_law"]
    rows = [[k, f"KS p {v['ks_p']:.4f}; 0.99 quantile {v['quantiles_got_vs_t']['0.99'][0]:.3f} against "
                f"{v['quantiles_got_vs_t']['0.99'][1]:.3f}", "pass" if v["passed"] else "FAIL"]
            for k, v in rt.items() if k.startswith("m")]
    rows += [[k, f"max abs error {v['max_abs_err']:.1e}", "pass" if v["passed"] else "FAIL"]
             for k, v in rt.items() if k.startswith("equals")]
    rows.append(["vectorized Monte Carlo p", f"{selfrev['mc_tail_p_many']['n_values']} values",
                 "pass" if selfrev["mc_tail_p_many"]["passed"] else "FAIL"])
    for k, v in selfrev["size_under_iid_normal"].items():
        if k == "passed":
            continue
        a = v["0.01"]
        rows.append([f"size at 0.01 under i.i.d. normal scalars, {k}",
                     f"G {a['G_peak']:.4f} / {a['G_rms']:.4f}; deleted residual {a['deleted_residual_peak']:.4f} / "
                     f"{a['deleted_residual_rms']:.4f}; Holm G {a['G_holm']:.4f}, expected {a['holm_expected']:.4f}",
                     "pass" if a["passed"] and v["0.05"]["passed"] else "FAIL"])
    L.append("Reference-set residual and size machinery, on simulated data (seed "
             f"{selfrev['seed']}):")
    L.append("")
    L.append(table(["Check", "Value", "Result"], rows))
    L.append("")
    L.append(f"Selfcheck overall: {'passed' if selfcheck['passed'] and selfrev['passed'] else 'FAILED'}.")
    L.append("")

    # ------------------------------------------------------------------ null
    L.append("## Normal-theory Grubbs null")
    L.append("")
    rows = []
    for k, v in gnull["levels"].items():
        rows.append([k, _f(v["G_max"]), _f(v["G_quantiles"]["0.95"]), _f(v["G_quantiles"]["0.99"]),
                     _f(v["D_top_quantiles"]["0.99"]), _f(v["D_prespecified_quantiles"]["0.99"]),
                     _p(v["mc_p_at_bound_critical"]["0.01"]), _f(v["rank_floor"])])
    L.append(table(["k", "largest G", "G 95%", "G 99%", "D 99%, top chosen", "D 99%, pre-specified",
                    "Monte Carlo p at the bound's 0.01 critical G", "rank floor 1/k"], rows))
    L.append("")

    # ------------------------------------------------------------------ size
    L.append("## Size of the normal-theory tests under the shuffle")
    L.append("")
    L.append("Each subject's 10,000 shuffles carry sampling noise alone. The size is the share of shuffles whose "
             "normal-theory p falls at or below alpha. The table covers the subjects with k >= 4.")
    L.append("")
    rows = []
    for role in ROLE_ORDER:
        for a in ("0.01", "0.05"):
            v = nts[role][a]
            rows.append([ROLE_LABEL[role], nts[role]["n_subjects_k4"], a] + [
                f"{v[c]['median']:.4f} [{v[c]['min']:.4f}, {v[c]['max']:.4f}]"
                for c in ("grubbs_normal_peak", "grubbs_normal_rms", "grubbs_normal_holm",
                          "deleted_residual_peak", "deleted_residual_rms", "deleted_residual_holm")])
    L.append(table(["Role", "Subjects", "Nominal", "Grubbs, peak", "Grubbs, RMS", "Grubbs, Holm",
                    "Deleted residual, peak", "Deleted residual, RMS", "Deleted residual, Holm"], rows))
    L.append("")
    allc = sm["normal_theory_size_under_shuffle"]["shuffle_G99_above_normal_G99_all"]
    rows = [[ROLE_LABEL[r], nts[r]["n_subjects_k4"], nts[r]["shuffle_G99_above_normal_G99"]["peak"],
             nts[r]["shuffle_G99_above_normal_G99"]["rms"]] for r in ROLE_ORDER]
    rows.append(["All subjects, both scalars", "--", f"{allc['above']} of {allc['cells']} cells", ""])
    L.append("Subjects whose shuffle 99th percentile of G lies above the normal-theory 99th percentile:")
    L.append("")
    L.append(table(["Role", "Subjects (k >= 4)", "Peak", "RMS"], rows))
    L.append("")

    # ------------------------------------------------------------------ inputs
    L.append("## Inputs")
    L.append("")
    rows = []
    for k, v in runs.items():
        s, r = v["subject"], v["result"]
        rows.append([k, s["role"], s["model"], s["roster"], s["level"], r["k"], r["n_instructions"],
                     r["n_axes"], r["n_responses"],
                     "; ".join(f"`{f}` ({v['input_sha256'][f][:12]})" for f in s["files"])
                     + (f", samples {s['s_range'][0]} to {s['s_range'][1]}" if s.get("s_range") else "")
                     + (f", half {s['half'][1]} of every cell" if s.get("half") else ""),
                     v.get("subset_of") or "--"])
    rows.sort(key=lambda r: (ROLE_ORDER.index(r[1]), r[0]))
    L.append(table(["Subject", "Role", "Model", "Roster", "Level", "k", "Instructions", "Axes",
                    "Replies", "Verdicts (sha256 prefix)", "Subset of"], rows))
    L.append("")
    L.append("Undefined, k = 2 (no population of other names):")
    L.append("")
    L.append(table(["Table", "k", "Verdicts"], [[u["key"], u["k"], f"`{u['file']}`"]
                                                for u in res["undefined_k2"]]))
    L.append("")

    # ------------------------------------------------------------------ reproduction
    L.append("## Reproduction of stored results")
    L.append("")
    rows = [[kd, v["n"], v["mismatch"]] for kd, v in sm["reproduction"].items()]
    L.append(table(["Stored record", "Checks", "Mismatches"], rows))
    L.append("")
    L.append("Each reference_free.json check compares the target-only maximum (S, p, null mean, null 95th) and "
             "every detachment field (S, p, leading candidate, leading peak, bulk median, null mean, null 95th, "
             "every candidate's peak and leave-one-out value, the stored 0.05 flag) for exact equality. "
             "The partA check compares S, p and the argmax candidate. "
             "The user-awareness check compares both stored tests.")
    regc = OUT / "registry_check.json"
    if regc.exists():
        rc = json.loads(regc.read_text())
        L.append("")
        L.append(table(["Shared subject registry", "Subjects checked", "Mismatches"],
                       [[f"`{rc['registry']}`", rc["n_checked"], rc["n_mismatch"]]]))
        L.append("")
        L.append("The registry check compares the verdict file's sha256, the level, k, the candidates, "
                 "the instructions, the axes and the replies. The split halves have no registry row.")
    gate = split["split0_gate"]
    L.append("")
    L.append(table(["Split-half check", "Tables", "Same table", "Same G, normal p, leader and residuals"],
                   [["split 0 of the many-split placebo against the family's halves", len(gate),
                     sum(v["same_table"] for v in gate.values()), sum(v["same_values"] for v in gate.values())]]))
    bad = [c for c in rep["checks"] if not c["match"]]
    if bad:
        L.append("")
        L.append(table(["Subject", "Stored", "Fields that differ"],
                       [[c["subject"], f"`{c['stored']}`", ", ".join(c.get("mismatches", {}) or ["see json"])]
                        for c in bad]))
    L.append("")

    # ------------------------------------------------------------------ per subject
    L.append("## Per-subject results")
    L.append("")
    L.append("Holm combines peak and RMS. *Named* is the leader of a method that rejects at alpha 0.01. "
             "The size column is the normal-theory Grubbs Holm test's rejection rate under this subject's own "
             "shuffle at nominal 0.01.")
    L.append("")
    flagged = {f["subject"] for f in sm["monte_carlo_flags"]["flags"]}
    rows = []
    for k, v in runs.items():
        s, r, dec, reg = v["subject"], v["result"], v["decisions"], v["registered"]
        pk, rm = r["scalars"]["peak"], r["scalars"]["rms"]
        cal = r["normal_theory_calibration"]["unsigned"]
        note = []
        if r["k"] == 3:
            note.append("defined, no power")
        if k in flagged:
            note.append("Monte Carlo flag")
        rows.append([
            k, s["role"], r["k"],
            "--" if not reg else f"{_f(reg['S'])} / {_p(reg['p'])} / {reg.get('named') or '--'}",
            f"{_f(r['target_only_max']['statistic'])} / {_p(r['target_only_max']['p_family_wise'])}",
            f"{_f(pk['mad_detachment']['statistic'], 2)} / {_p(pk['mad_detachment']['p_family_wise'])}",
            _p(rm["mad_detachment"]["p_family_wise"]),
            f"{_f(pk['grubbs']['G'])} / {_f(rm['grubbs']['G'])} of {_f(pk['grubbs']['G_max'])}",
            f"{_p(pk['grubbs']['p_shuffle_G'])} / {_p(rm['grubbs']['p_shuffle_G'])}",
            _p(min(dec["grubbs_shuffle"]["holm"].values())),
            f"{_p(pk['grubbs']['p_exact_mc'])} / {_p(rm['grubbs']['p_exact_mc'])}",
            _p(min(dec["grubbs_exact"]["holm"].values())),
            _p(pk["grubbs"]["p_bound"]),
            _f(cal["grubbs_normal_holm_size"]["0.01"], 4),
            pk["grubbs"]["leading"] + ("" if pk["grubbs"]["leading"] == rm["grubbs"]["leading"]
                                       else f" (RMS: {rm['grubbs']['leading']})"),
            dec["grubbs_shuffle"]["named"] or "--", dec["grubbs_exact"]["named"] or "--",
            dec["mad_detachment"]["named"] or "--", "; ".join(note) or "--"])
    rows.sort(key=lambda r: (ROLE_ORDER.index(r[1]), r[0]))
    L.append(table(["Subject", "Role", "k", "Registered S / p / named", "Target-only max S / p",
                    "MAD detachment S / p, peak", "MAD p, RMS", "Grubbs G, peak / RMS, of max",
                    "G shuffle p, peak / RMS", "G shuffle Holm p", "G normal-theory p, peak / RMS",
                    "G normal-theory Holm p", "G t bound p, peak", "Size of normal-theory Holm at 0.01",
                    "Leader", "Named, shuffle Holm", "Named, normal-theory Holm", "Named, MAD Holm",
                    "Note"], rows))
    L.append("")

    # ------------------------------------------------------------------ agreement
    L.append("## Agreement with the registered test on positives (alpha 0.01)")
    L.append("")
    pa = sm["positive_agreement"]["by_method"]
    rows = []
    for m, v in pa.items():
        rows.append([METHOD_LABEL[m], v["n"], v["registered_rejects"], v["method_rejects"], len(v["both"]),
                     len(v["both_same_argmax"]), len(v["registered_only"]), len(v["method_only"]),
                     len(v["neither"])])
    L.append(table(["Method", "Positives", "Registered rejects", "Method rejects", "Both",
                    "Both, same candidate", "Registered only", "Method only", "Neither"], rows))
    L.append("")

    # ------------------------------------------------------------------ firing
    L.append("## Firing on nulls, bases as targets, and split halves")
    L.append("")
    L.append("A count in parentheses leaves out the k = 3 tables.")
    L.append("")
    methods = ("grubbs_shuffle_holm", "grubbs_shuffle_peak", "grubbs_shuffle_rms", "grubbs_exact_holm",
               "grubbs_exact_peak", "grubbs_exact_rms", "grubbs_bound_holm", "mad_detachment_holm",
               "mad_detachment_peak", "mad_detachment_rms", "target_only_max", "registered")
    for a in (0.01, 0.05):
        rows = []
        for m in methods:
            row = [METHOD_LABEL[m]]
            for role in ROLE_ORDER:
                v = rb.get(role, {}).get(m)
                row.append("--" if not v else _count(v, a))
            rows.append(row)
        L.append(f"At alpha {a}:")
        L.append("")
        L.append(table(["Method"] + [ROLE_LABEL[r] for r in ROLE_ORDER], rows))
        L.append("")
    rows = []
    for role in ("null", "base", "half"):
        for m in ("grubbs_shuffle_holm", "grubbs_exact_holm", "mad_detachment_holm", "target_only_max"):
            v = rb.get(role, {}).get(m)
            if v:
                rows.append([ROLE_LABEL[role], METHOD_LABEL[m], f"{v['reject_0.01']}/{v['n']}",
                             _ci(v["ci_0.01"]), ", ".join(v["subjects_0.01"]) or "--"])
    L.append(table(["Role", "Method", "Rejections at 0.01", "Clopper-Pearson 95%", "Which"], rows))
    L.append("")
    L.append("Leaders on the AuditBench contextual-optimism roster, counted over the tables that share it:")
    L.append("")
    rows = []
    for role in ("positive", "null", "base", "half"):
        sel = [v for v in runs.values() if v["subject"]["roster"] == "contextual_optimism"
               and v["subject"]["role"] == role]
        if not sel:
            continue
        for n in ("peak", "rms"):
            cnt = Counter(v["result"]["scalars"][n]["grubbs"]["leading"] for v in sel)
            rows.append([ROLE_LABEL[role], len(sel), n, "; ".join(f"{c} {m}" for c, m in cnt.most_common())])
    L.append(table(["Role", "Tables", "Scalar", "Leader counts"], rows))
    L.append("")
    L.append("Shuffle null against normal-theory null for Grubbs's G:")
    L.append("")
    rows = []
    for n in ("peak", "rms"):
        gt = sum(v["result"]["scalars"][n]["grubbs"]["p_shuffle_G"] > v["result"]["scalars"][n]["grubbs"]["p_exact_mc"]
                 for v in runs.values())
        rows.append([n, len(runs), gt])
    L.append(table(["Scalar", "Subjects", "Shuffle p larger than normal-theory p"], rows))
    L.append("")

    # ------------------------------------------------------------------ split halves
    L.append("## Split-half placebo over many random splits")
    L.append("")
    L.append("Split i uses split seed 20260726 + i; split 0 is the family's split. Each half is read alone as a "
             "target. Halves of one split are complements and every split reuses the source's replies, so the "
             "intervals treat dependent halves as independent.")
    L.append("")
    rows = []
    for src, v in sh.items():
        for a in ("0.01", "0.05"):
            x = v[a]
            rows.append([src, a, f"{x['grubbs_normal_holm']['rejections']}/{x['grubbs_normal_holm']['n']}",
                         _ci(x["grubbs_normal_holm"]["clopper_pearson_95"]),
                         f"{x['grubbs_normal_peak']['rate']:.4f}", f"{x['grubbs_normal_rms']['rate']:.4f}",
                         f"{x['splits_with_either_half_rejecting']['rejections']}/"
                         f"{x['splits_with_either_half_rejecting']['n']}",
                         f"{x['placebo_targets_holm_p_t']['rejections']}/{x['placebo_targets_holm_p_t']['n']}",
                         _ci(x["placebo_targets_holm_p_t"]["clopper_pearson_95"]),
                         f"{x['halves_with_any_placebo_target']['rate']:.4f}",
                         "; ".join(f"{c} {m}" for c, m in list(x["grubbs_normal_holm_named"].items())[:3]) or "--",
                         "; ".join(f"{c} {m}" for c, m in list(x["placebo_named"].items())[:3]) or "--"])
    L.append(table(["Source", "Alpha", "Grubbs normal-theory Holm rejections", "Clopper-Pearson 95%",
                    "Rate, peak only", "Rate, RMS only", "Splits with either half rejecting",
                    "Placebo targets rejected", "Clopper-Pearson 95%", "Halves with any placebo target",
                    "Named by Grubbs", "Named placebo targets"], rows))
    L.append("")
    rows = []
    for src, v in sh.items():
        for h, x in v["split0"].items():
            rows.append([src, h, _p(x["grubbs_normal_holm_p"]), x["leader"], _p(x["placebo_min_holm_p_t"])])
    L.append("The family's split (split 0), the worked example:")
    L.append("")
    L.append(table(["Source", "Half", "Grubbs normal-theory Holm p", "Leader",
                    "Smallest placebo-target Holm p"], rows))
    L.append("")

    # ------------------------------------------------------------------ pre-registered
    L.append("## Pre-registered targets")
    L.append("")
    L.append("The organism targets are each organism's documented principal, an oracle a blind auditor lacks. "
             "A blind auditor who reads the leader pays the factor k; the Grubbs t bound carries it.")
    L.append("")
    rows = []
    for k, v in sm["preregistered"].items():
        if v["role"] == "ua":
            continue
        for tgt, t in v["targets"].items():
            for n in v["family"]["scalars"]:
                rows.append([k, f"{tgt} (documented principal, oracle)", n, _f(t[n]["value"]),
                             _f(t[n]["deleted_residual"]), _p(t[n]["p_t"]), _p(t[n]["p_shuffle"]),
                             _p(t[n]["rank_p"]), _p(v["family"]["holm_t"][f"{tgt}|{n}"]),
                             _p(v["family"]["holm_shuffle"][f"{tgt}|{n}"])])
    L.append(table(["Subject", "Target", "Scalar", "Value", "Deleted residual", "p, t(k-2)",
                    "p, shuffle", "Rank p", "Holm p, t", "Holm p, shuffle"], rows))
    L.append("")
    L.append("Each target against the placebo targets of the null and base tables on its roster (no subset "
             "tables). The rank p is (1 + #{reference at least as extreme}) / (1 + n).")
    L.append("")
    rows = []
    for key, v in sm["preregistered_calibration"].items():
        subj, tgt = key.split("|")
        for ref, lab in (("all_placebo_targets", "every candidate of those tables"),
                         ("same_name", f"{tgt} in each of those tables")):
            o = v[ref]
            for n in ("peak", "rms"):
                rows.append([subj, tgt, lab, len(v["reference_tables"]), o["n"], n, _f(o[n]["observed"]),
                             _f(o[n]["reference_max"]), o[n]["n_at_least"], _p(o[n]["rank_p"]),
                             ", ".join(o[n]["exceeded_by"]) or "--"])
            rows.append([subj, tgt, lab, len(v["reference_tables"]), o["n"], "Holm p, t",
                         _p(o["holm_p_t"]["observed"]), "--", o["holm_p_t"]["n_at_most"],
                         _p(o["holm_p_t"]["rank_p"]), "--"])
    L.append(table(["Subject", "Target", "Reference", "Tables", "Reference targets", "Statistic",
                    "Target value", "Largest reference value", "Reference at least as extreme", "Rank p",
                    "Exceeded by"], rows))
    L.append("")

    # ------------------------------------------------------------------ placebo
    L.append("## Placebo targets")
    L.append("")
    L.append("Every candidate of every null, base and half serves in turn as the pre-registered target. "
             "Subset tables (a sample range of C1, the split halves) share replies with their source, so the "
             "pooled rows leave them out and report them on their own. The user-awareness rows use the signed "
             "scalars of the safety family: the seven identities outside the safety group against the other "
             "nine, and each general identity against the other five general identities.")
    L.append("")
    rows = []
    for g in ("null", "base", "null+base", "null+base, contextual-optimism roster", "null+base, other rosters",
              "subsets (sample range, split halves)", "ua, all others", "ua, general others"):
        v = pf[g]
        cols = ("holm_p_t", "holm_p_shuffle", "holm_rank_p") + (
            ("peak_signed_p_t", "mean_signed_p_t") if g.startswith("ua") else ("peak_p_t", "rms_p_t"))
        for c in cols:
            x, y = v[f"{c}@0.01"], v[f"{c}@0.05"]
            rows.append([g, PLACEBO_LABEL[c], f"{x['models_with_any']}/{v['n_models']}",
                         f"{x['rejections']}/{v['n_tests']}", _f(x["rate"]), _ci(x["clopper_pearson_95"]),
                         f"{y['rejections']}/{v['n_tests']}", _ci(y["clopper_pearson_95"])])
    L.append(table(["Group", "p", "Models with any at 0.01", "Rejections at 0.01", "Rate",
                    "Clopper-Pearson 95%", "Rejections at 0.05", "Clopper-Pearson 95% at 0.05"], rows))
    L.append("")
    rows = [[g, ", ".join(pf[g]["holm_p_t@0.01"]["which"]) or "--"]
            for g in ("null+base", "subsets (sample range, split halves)")]
    L.append(table(["Group", "Placebo targets rejected at 0.01, deleted residual, t, Holm"], rows))
    L.append("")
    L.append("Placebo targets within one model share its data, so the interval treats dependent tests as "
             "independent. The model-level column counts models with at least one rejecting placebo target.")
    L.append("")

    # ------------------------------------------------------------------ detachment sentence
    L.append("## The stored sentence on detachment")
    L.append("")
    oc = sm["old_sentence_detachment_rejects_on_none"]
    rows = []
    for name, lab in (("stored_reference_free_seats", "stored records, peak"),
                      ("recomputed_subjects_peak", "every subject, peak"),
                      ("recomputed_subjects_rms", "every subject, RMS"),
                      ("recomputed_subjects_holm", "every subject, Holm over peak and RMS"),
                      ("paper_runs_and_nulls_peak", "paper runs and nulls, peak"),
                      ("paper_runs_and_nulls_rms", "paper runs and nulls, RMS"),
                      ("paper_runs_and_nulls_holm", "paper runs and nulls, Holm")):
        v = oc[name]
        rows.append([lab, v["n"], "; ".join(v["reject_0.01"]) or "none", "; ".join(v["reject_0.05"]) or "none"])
    L.append(table(["Set", "Tables", "MAD detachment p <= 0.01", "MAD detachment p <= 0.05"], rows))
    L.append("")

    # ------------------------------------------------------------------ user awareness
    L.append("## User awareness")
    L.append("")
    ua = sm["user_awareness"]
    rows = []
    for k, v in ua.items():
        rows.append([k, v["subject_model"], v["target_only_max"]["argmax_candidate"],
                     _p(v["target_only_max"]["p_family_wise"]),
                     f"{v['unsigned_leader']['peak']['leader']} "
                     f"({_p(v['unsigned_leader']['peak']['p_normal_theory'])})",
                     f"{v['signed_leader']['peak_signed']['leader']} "
                     f"({_p(v['signed_leader']['peak_signed']['p_normal_theory'])})",
                     f"{v['signed_leader']['mean_signed']['leader']} "
                     f"({_p(v['signed_leader']['mean_signed']['p_normal_theory'])})"])
    L.append(table(["Subject", "Model", "Target-only max argmax", "Target-only max p",
                    "Unsigned leader (G normal-theory p)", "Harshest by signed peak (G normal-theory p)",
                    "Harshest by mean signed t (G normal-theory p)"], rows))
    L.append("")
    rows = []
    for k, v in ua.items():
        fam, gref, pg = v["family_all_others"], v["general_reference"]["safety_family"], v["paired_grades"]
        rows.append([k, _p(min(fam["holm_t"].values())), _p(min(fam["holm_shuffle"].values())),
                     _p(gref["p_t"]["min_holm"]), _p(gref["p_shuffle"]["min_holm"]),
                     _p(gref["p_t_two_sided"]["min_holm"]), _p(gref["p_shuffle_two_sided"]["min_holm"]),
                     _p(pg["safety_min_holm_two_sided"]),
                     "yes" if (fam["reject_t"] or gref["p_t"]["reject"] or gref["p_shuffle"]["reject"]) else "no"])
    L.append("The safety family (three identities, Holm over identities and signed scalars; the paired column is "
             "Holm over the three identities):")
    L.append("")
    L.append(table(["Subject", "Against the other nine, t", "Against the other nine, shuffle",
                    "Against the six general, t, one-sided", "Against the six general, shuffle, one-sided",
                    "Against the six general, t, two-sided", "Against the six general, shuffle, two-sided",
                    "Paired grades, two-sided", "Any one-sided rejection at 0.01"], rows))
    L.append("")
    rows = []
    for k, v in ua.items():
        gref = v["general_reference"]
        for c, row in gref["identities"].items():
            ms, ps = row["mean_signed"], row["peak_signed"]
            rows.append([k, c, row["group"] + (" (exploratory row)" if row["group"] != "safety" else ""),
                         _f(ms["residual"]), _p(ms["p_t"]), _p(ms["p_t_two_sided"]), _p(ms["p_shuffle"]),
                         _f(ps["residual"]), _p(ps["p_t"]), _p(ps["p_t_two_sided"]), _p(ps["p_shuffle"]),
                         _f(ms["rank_p"])])
    L.append(f"Each safety identity and the affiliation twin against the six general identities, t with "
             f"{next(iter(ua.values()))['general_reference']['df']} degrees of freedom, positive toward lower "
             f"grades:")
    L.append("")
    L.append(table(["Subject", "Identity", "Group", "Residual, mean signed t", "p, one-sided", "p, two-sided",
                    "p, shuffle", "Residual, signed peak", "p, one-sided", "p, two-sided", "p, shuffle",
                    "Rank p, mean signed t, among seven"], rows))
    L.append("")
    rows = []
    for k, v in ua.items():
        pg = v["paired_grades"]
        for c, x in pg["identities"].items():
            rows.append([k, c, x["group"] + (" (exploratory row)" if x["group"] != "safety" else ""),
                         pg["n_exchanges"], "/".join(map(str, pg["samples_per_cell"])),
                         _f(x["mean_grade"]), _f(pg["general_mean_grade"]), _f(x["mean_difference"]),
                         _f(x["paired_t"], 2), _p(x["p_two_sided"]),
                         _p(pg["safety_holm_two_sided"].get(c)) if x["group"] == "safety" else "--"])
    L.append("Mean grade against the six general identities, paired over exchanges:")
    L.append("")
    L.append(table(["Subject", "Identity", "Group", "Exchanges", "Samples per cell", "Mean grade",
                    "General mean grade", "Difference", "Paired t", "p, two-sided", "Holm p over the three"],
                   rows))
    L.append("")
    rows = []
    for k, v in ua.items():
        for tgt, t in v["safety_identities_all_others"].items():
            for n in v["family_all_others"]["scalars"]:
                rows.append([k, tgt, n, _f(t[n]["value"]), _f(t[n]["deleted_residual"]), _p(t[n]["p_t"]),
                             _p(t[n]["p_shuffle"]), _p(t[n]["rank_p"]),
                             _p(v["family_all_others"]["holm_t"][f"{tgt}|{n}"])])
    L.append("Each safety identity against the other nine identities, t with 8 degrees of freedom:")
    L.append("")
    L.append(table(["Subject", "Target", "Scalar", "Value", "Deleted residual", "p, t(8)", "p, shuffle",
                    "Rank p", "Holm p, t"], rows))
    L.append("")

    # ------------------------------------------------------------------ Monte Carlo
    L.append("## Monte Carlo error")
    L.append("")
    mf = sm["monte_carlo_flags"]
    L.append(f"Every permutation p within {mf['width_in_se']:g} standard errors of alpha 0.01. A raw p there has "
             f"standard error {mf['se_raw_at_alpha']:.5f}; a Holm p over two scalars has "
             f"{mf['se_holm2_at_alpha']:.5f}. The normal-theory Monte Carlo p has standard error near 0.0001 at "
             f"0.01 and carries no flag.")
    L.append("")
    rows = [[f["subject"], f["what"], _p(f["p"]), f"{f['se']:.5f}", f"{f['z_from_alpha']:+.2f}",
             "reject" if f["rejects_at_alpha"] else "keep"] for f in mf["flags"]]
    L.append(table(["Subject", "p value", "p", "Standard error", "Distance from 0.01 in SE",
                    "Decision at 0.01"], rows))
    L.append("")

    # ------------------------------------------------------------------ reading
    L.append("## Reading")
    L.append("")
    L.append(READING.strip())
    L.append("")
    L.append("## Files")
    L.append("")
    L.append(table(["File", "Holds"], [
        ["`settings.json`", "every setting and convention"],
        ["`selfcheck.json`", "the simulated-data checks of the Grubbs machinery, run before any verdict was read"],
        ["`selfcheck_revision.json`", "the simulated-data checks of the reference-set residual and the size "
                                      "machinery; the run refuses to start without them"],
        ["`grubbs_null_k3_k11.json`", "quantiles of the normal-theory Monte Carlo null and the bound's "
                                      "critical values"],
        ["`runs/<subject>.json`", "one subject: inputs and hashes, the registered result, every statistic, "
                                  "every candidate's deleted residual and rank p, the normal-theory size under "
                                  "the shuffle, decisions; for the user-awareness subjects also the general "
                                  "reference and the paired grades"],
        ["`outlier_table.csv`", "one row per subject"],
        ["`placebo_targets.csv`", "one row per placebo target"],
        ["`split_half_many.json`", "the split-half placebo over many splits, by source"],
        ["`split_half_many.csv`", "one row per half"],
        ["`reproduce_check.json`", "every comparison with a stored record"],
        ["`registry_check.json`", "every subject against the workflow's shared subject registry"],
        ["`results.json`", "the summary every table here is drawn from"],
        ["`run.log`", "the run's console output"],
    ]))
    L.append("")
    path.write_text("\n".join(L) + "\n")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
