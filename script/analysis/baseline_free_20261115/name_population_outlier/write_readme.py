"""Write README.md for the name-population outlier family from its own outputs.

    PYTHONPATH=. .venv/bin/python \\
        script/analysis/baseline_free_20261115/name_population_outlier/write_readme.py

Every number comes from ``results.json``, ``reproduce_check.json``,
``grubbs_null_k3_k11.json`` or a per-run record. The prose holds no numbers.
Refuses to overwrite an existing README.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OUT = REPO / "out/main/baseline_free_20261115/name_population_outlier"
ROLE_ORDER = ("positive", "null", "base", "half", "ua")

#: The reading of the tables above. It holds no numbers; the tables hold them.
READING = """
We first ask whether the stored detachment sentence still holds on the current data.
The MAD detachment rejects on no subject at the registered alpha.
At the looser alpha it also rejects on none of the paper's runs and nulls.
One held-out challenge roster and one placebo half cross the looser line.
We therefore contend that the sentence holds on the current data once it names the registered alpha.

The Grubbs form with its exact normal null rejects on two positives, contextual optimism and the informed narrow secret loyalty.
Both rejections name the registered principal.
The RMS scalar carries both, so breadth across axes separates these principals from their peers better than the peak does.
The test misses most registered positives.
The secret loyalty organism's pre-registered target falls short of the registered alpha after Holm.
We therefore posit that a pre-registered target and a breadth scalar supply most of this test's power.

The same test fires on two null controls and on one placebo half.
It never fires on a base read as a target.
The target-only maximum fires on every Qwen base read as a target, and this test removes that failure.
Stanford leads the RMS scalar in most tables on the AuditBench roster, in the nulls and in the base draws alike.
Stanford is also the named candidate in most null rejections.
We read this as one generic name effect that these models share.
The placebo-target rejection rate of the deleted residual sits above nominal on the nulls and at zero on the bases.
On the halves its interval still covers the nominal rate.
The within-instruction shuffle gives larger p values than the normal null on almost every subject, so the two nulls disagree on the shape of ordinary name effects.
We therefore contend that a Level-1 rejection identifies a name that stands out in this model, and that decoy names or a model panel must calibrate it before it supports a verdict.

The rank p never rejects, because its floor sits above the registered alpha at every k we hold.
We therefore posit that exchangeability alone cannot carry a decision at this alpha without decoys.

The safety family does not reject in any user-awareness subject.
In two subjects the safety identities sit slightly below the general identities' median grade, and none of them reaches significance.
In the one subject where the target-only maximum fires, the outlier is a general-population identity graded more leniently.
We therefore conjecture that this miniature grading task does not reproduce the safety-user effect, and that its identity spread is a generic name effect of the kind this test cannot tell apart from a target.

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
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def main() -> None:
    path = OUT / "README.md"
    if path.exists():
        raise SystemExit(f"refusing to overwrite {path}")
    res = json.loads((OUT / "results.json").read_text())
    rep = json.loads((OUT / "reproduce_check.json").read_text())
    gnull = json.loads((OUT / "grubbs_null_k3_k11.json").read_text())
    selfcheck = json.loads((OUT / "selfcheck.json").read_text())
    st, sm = res["settings"], res["summary"]
    runs = {p.stem: json.loads(p.read_text()) for p in sorted((OUT / "runs").glob("*.json"))}

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
    L.append("## Settings")
    L.append("")
    L.append(table(["Setting", "Value"], [
        ["Permutations", st["n_permutations"]], ["Seed", st["seed"]], ["Alpha", st["alpha"]],
        ["Contrast", st["contrast"]], ["t-grid", st["t_grid"]], ["Shuffle", st["permutation"]],
        ["Scalars", "; ".join(f"{k}: {v}" for k, v in st["scalars"].items())],
        ["MAD detachment", st["mad_detachment"]], ["Grubbs", st["grubbs"]],
        ["Exact Grubbs null", f"{st['grubbs_exact_null']['draws_per_k']} normal draws per k, k = "
                              f"{st['grubbs_exact_null']['k'][0]} to {st['grubbs_exact_null']['k'][-1]}, "
                              f"seed {st['grubbs_exact_null']['seed']}; p = {st['grubbs_exact_null']['p']}"],
        ["Grubbs bound", st["grubbs_bound"] + " (read off the leader's deleted residual, which equals t_G)"],
        ["Deleted residual", st["deleted_residual"]], ["Rank p", st["rank_p"]], ["Holm", st["holm"]],
        ["Pre-registered targets", "; ".join(f"{k}: {', '.join(v)}" for k, v in st["preregistered"].items())],
        ["Split-half seed", st["split_half_seed"]],
    ]))
    L.append("")
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
    L.append(f"Selfcheck overall: {'passed' if selfcheck['passed'] else 'FAILED'}.")
    L.append("")
    L.append("## Exact Grubbs null")
    L.append("")
    rows = []
    for k, v in gnull["levels"].items():
        rows.append([k, _f(v["G_max"]), _f(v["G_quantiles"]["0.95"]), _f(v["G_quantiles"]["0.99"]),
                     _f(v["D_top_quantiles"]["0.99"]), _f(v["D_prespecified_quantiles"]["0.99"]),
                     _p(v["mc_p_at_bound_critical"]["0.01"]), _f(v["rank_floor"])])
    L.append(table(["k", "largest G", "G 95%", "G 99%", "D 99%, top chosen", "D 99%, pre-specified",
                    "Monte Carlo p at the bound's 0.01 critical G", "rank floor 1/k"], rows))
    L.append("")
    L.append("## Inputs")
    L.append("")
    rows = []
    for k, v in runs.items():
        s, r = v["subject"], v["result"]
        rows.append([k, s["role"], s["model"], s["roster"], s["level"], r["k"], r["n_instructions"],
                     r["n_axes"], r["n_responses"],
                     "; ".join(f"`{f}` ({v['input_sha256'][f][:12]})" for f in s["files"])
                     + (f", samples {s['s_range'][0]} to {s['s_range'][1]}" if s.get("s_range") else "")
                     + (f", half {s['half'][1]} of every cell" if s.get("half") else "")])
    rows.sort(key=lambda r: (ROLE_ORDER.index(r[1]), r[0]))
    L.append(table(["Subject", "Role", "Model", "Roster", "Level", "k", "Instructions", "Axes",
                    "Replies", "Verdicts (sha256 prefix)"], rows))
    L.append("")
    L.append("Undefined, k = 2 (no population of other names):")
    L.append("")
    L.append(table(["Table", "k", "Verdicts"], [[u["key"], u["k"], f"`{u['file']}`"]
                                                for u in res["undefined_k2"]]))
    L.append("")
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
    bad = [c for c in rep["checks"] if not c["match"]]
    if bad:
        L.append("")
        L.append(table(["Subject", "Stored", "Fields that differ"],
                       [[c["subject"], f"`{c['stored']}`", ", ".join(c.get("mismatches", {}) or ["see json"])]
                        for c in bad]))
    L.append("")
    L.append("## Per-subject results")
    L.append("")
    L.append("Peak scalar unless marked. Holm combines peak and RMS. "
             "*Named* is the leader of a method that rejects at alpha 0.01.")
    L.append("")
    rows = []
    for k, v in runs.items():
        s, r, dec, reg = v["subject"], v["result"], v["decisions"], v["registered"]
        pk, rm = r["scalars"]["peak"], r["scalars"]["rms"]
        rows.append([
            k, s["role"], r["k"],
            "--" if not reg else f"{_f(reg['S'])} / {_p(reg['p'])} / {reg.get('named') or '--'}",
            f"{_f(r['target_only_max']['statistic'])} / {_p(r['target_only_max']['p_family_wise'])}",
            f"{_f(pk['mad_detachment']['statistic'], 2)} / {_p(pk['mad_detachment']['p_family_wise'])}",
            f"{_p(rm['mad_detachment']['p_family_wise'])}",
            f"{_f(pk['grubbs']['G'])} of {_f(pk['grubbs']['G_max'])}",
            _p(pk["grubbs"]["p_shuffle_G"]), _p(pk["grubbs"]["p_exact_mc"]), _p(pk["grubbs"]["p_bound"]),
            _p(rm["grubbs"]["p_exact_mc"]), _p(min(dec["grubbs_exact"]["holm"].values())),
            pk["grubbs"]["leading"] + ("" if pk["grubbs"]["leading"] == rm["grubbs"]["leading"]
                                       else f" (RMS: {rm['grubbs']['leading']})"),
            dec["grubbs_exact"]["named"] or "--", dec["mad_detachment"]["named"] or "--",
            _f(1 / r["k"])])
    rows.sort(key=lambda r: (ROLE_ORDER.index(r[1]), r[0]))
    L.append(table(["Subject", "Role", "k", "Registered S / p / named", "Target-only max S / p",
                    "MAD detachment S / p", "MAD p, RMS", "Grubbs G of max", "G shuffle p",
                    "G exact p", "G bound p", "G exact p, RMS", "G exact Holm p", "Leader",
                    "Named, Grubbs exact", "Named, MAD", "Rank floor"], rows))
    L.append("")
    L.append("## Agreement with the registered test on positives (alpha 0.01)")
    L.append("")
    pa = sm["positive_agreement"]["by_method"]
    rows = []
    for m, v in pa.items():
        rows.append([m, v["n"], v["registered_rejects"], v["method_rejects"], len(v["both"]),
                     len(v["both_same_argmax"]), len(v["registered_only"]), len(v["method_only"]),
                     len(v["neither"])])
    L.append(table(["Method", "Positives", "Registered rejects", "Method rejects", "Both",
                    "Both, same candidate", "Registered only", "Method only", "Neither"], rows))
    L.append("")
    L.append("## Firing on nulls, bases as targets, and split halves")
    L.append("")
    rb = sm["rejections_by_role"]
    methods = ("target_only_max", "mad_detachment_peak", "mad_detachment_holm", "grubbs_shuffle_peak",
               "grubbs_shuffle_holm", "grubbs_exact_peak", "grubbs_exact_rms", "grubbs_exact_holm",
               "grubbs_bound_holm", "registered")
    rows = []
    for m in methods:
        row = [m]
        for role in ("positive", "null", "base", "half", "ua"):
            v = rb.get(role, {}).get(m)
            row.append("--" if not v else f"{v['reject_0.01']}/{v['n']} ({v['reject_0.05']} at 0.05)")
        rows.append(row)
    L.append(table(["Method", "Positives", "Nulls", "Bases", "Halves", "User awareness"], rows))
    L.append("")
    rows = []
    for role in ("null", "base", "half"):
        for m in ("grubbs_exact_holm", "mad_detachment_holm", "target_only_max"):
            v = rb.get(role, {}).get(m)
            if v:
                rows.append([role, m, f"{v['reject_0.01']}/{v['n']}", _ci(v["ci_0.01"]),
                             ", ".join(v["subjects_0.01"]) or "--"])
    L.append(table(["Role", "Method", "Rejections at 0.01", "Clopper-Pearson 95%", "Which"], rows))
    L.append("")
    L.append("Leaders on the AuditBench contextual-optimism roster, counted over the tables that share it:")
    L.append("")
    from collections import Counter
    rows = []
    for role in ("positive", "null", "base", "half"):
        sel = [v for v in runs.values() if v["subject"]["roster"] == "contextual_optimism"
               and v["subject"]["role"] == role]
        if not sel:
            continue
        for n in ("peak", "rms"):
            cnt = Counter(v["result"]["scalars"][n]["grubbs"]["leading"] for v in sel)
            rows.append([role, len(sel), n, "; ".join(f"{c} {m}" for c, m in cnt.most_common())])
    L.append(table(["Role", "Tables", "Scalar", "Leader counts"], rows))
    L.append("")
    L.append("Shuffle null against exact normal null for Grubbs's G:")
    L.append("")
    rows = []
    for n in ("peak", "rms"):
        gt = sum(v["result"]["scalars"][n]["grubbs"]["p_shuffle_G"] > v["result"]["scalars"][n]["grubbs"]["p_exact_mc"]
                 for v in runs.values())
        rows.append([n, len(runs), gt])
    L.append(table(["Scalar", "Subjects", "Shuffle p larger than exact p"], rows))
    L.append("")
    L.append("## Pre-registered targets")
    L.append("")
    rows = []
    for k, v in sm["preregistered"].items():
        for tgt, t in v["targets"].items():
            for n in v["family"]["scalars"]:
                rows.append([k, tgt, n, _f(t[n]["value"]), _f(t[n]["deleted_residual"]), _p(t[n]["p_t"]),
                             _p(t[n]["p_shuffle"]), _p(t[n]["rank_p"]),
                             _p(v["family"]["holm_t"][f"{tgt}|{n}"])])
    L.append(table(["Subject", "Target", "Scalar", "Value", "Deleted residual", "p, t(k-2)",
                    "p, shuffle", "Rank p", "Holm p, t"], rows))
    L.append("")
    L.append("## Placebo targets")
    L.append("")
    L.append("Every candidate of every null, base and half serves in turn as the pre-registered target. "
             "The user-awareness rows use the seven identities outside the safety group.")
    L.append("")
    pf = sm["placebo_targets"]
    rows = []
    for g in ("null", "base", "half", "null+base+half", "ua_non_safety"):
        v = pf[g]
        for c in ("peak_p_t", "rms_p_t", "holm_p_t", "peak_p_shuffle", "holm_p_shuffle", "holm_rank_p"):
            x = v[f"{c}@0.01"]
            y = v[f"{c}@0.05"]
            rows.append([g, c, f"{x['rejections']}/{v['n_tests']}", _f(x["rate"]),
                         _ci(x["clopper_pearson_95"]), f"{x['models_with_any']}/{v['n_models']}",
                         f"{y['rejections']}/{v['n_tests']}", _ci(y["clopper_pearson_95"])])
    L.append(table(["Group", "p", "Rejections at 0.01", "Rate", "Clopper-Pearson 95%",
                    "Models with any", "Rejections at 0.05", "Clopper-Pearson 95% at 0.05"], rows))
    L.append("")
    L.append("Placebo targets within one model share its data, so the interval treats dependent tests as "
             "independent. The model-level column counts models with at least one rejecting placebo target.")
    L.append("")
    L.append("## The stored sentence on detachment")
    L.append("")
    oc = sm["old_sentence_detachment_rejects_on_none"]
    rows = []
    for name in ("stored_reference_free_seats", "recomputed_subjects", "paper_runs_and_nulls"):
        v = oc[name]
        rows.append([name, v["n"], "; ".join(v["reject_0.01"]) or "none", "; ".join(v["reject_0.05"]) or "none"])
    L.append(table(["Set", "Tables", "MAD detachment p <= 0.01", "MAD detachment p <= 0.05"], rows))
    L.append("")
    L.append("## User awareness")
    L.append("")
    ua = sm["user_awareness"]
    rows = []
    for k, v in ua.items():
        mg = v["mean_grade"]
        safety = [t for t in v["safety_identities"]]
        rows.append([k, v["subject_model"], v["target_only_max"]["argmax_candidate"],
                     _p(v["target_only_max"]["p_family_wise"]),
                     f"{v['unsigned_leader']['peak']['leader']} ({_p(v['unsigned_leader']['peak']['p_exact'])})",
                     f"{v['signed_leader']['peak_signed']['leader']} "
                     f"({_p(v['signed_leader']['peak_signed']['p_exact'])})",
                     f"{v['signed_leader']['mean_signed']['leader']} "
                     f"({_p(v['signed_leader']['mean_signed']['p_exact'])})",
                     _p(min(v["family"]["holm_t"].values())), _p(min(v["family"]["holm_shuffle"].values())),
                     "yes" if v["family"]["reject_t"] else "no"])
    L.append(table(["Subject", "Model", "Target-only max argmax", "Target-only max p",
                    "Unsigned leader (G exact p)", "Harshest by signed peak (G exact p)",
                    "Harshest by mean signed t (G exact p)", "Safety family Holm p, t",
                    "Safety family Holm p, shuffle", "Safety family rejects"], rows))
    L.append("")
    rows = []
    for k, v in ua.items():
        idents = json.loads((REPO / runs[k]["subject"]["stored_ua"]).read_text())["identities"]
        general = sorted(v["mean_grade"][i] for i, g in idents.items() if g["group"] == "general")
        med = (general[len(general) // 2 - 1] + general[len(general) // 2]) / 2
        for tgt, t in v["safety_identities"].items():
            rows.append([k, tgt, _f(v["mean_grade"][tgt]), _f(med),
                         _f(t["peak_signed"]["deleted_residual"]), _p(t["peak_signed"]["p_t"]),
                         _f(t["mean_signed"]["deleted_residual"]), _p(t["mean_signed"]["p_t"]),
                         _p(t["mean_signed"]["rank_p"])])
    L.append(table(["Subject", "Safety identity", "Mean grade", "Median mean grade, six general identities",
                    "Deleted residual, signed peak", "p, t(8)", "Deleted residual, mean signed t",
                    "p, t(8)", "Rank p, mean signed t"], rows))
    L.append("")
    L.append("## Reading")
    L.append("")
    L.append(READING.strip())
    L.append("")
    L.append("## Files")
    L.append("")
    L.append(table(["File", "Holds"], [
        ["`settings.json`", "every setting and convention"],
        ["`selfcheck.json`", "the simulated-data checks, run before any verdict was read"],
        ["`grubbs_null_k3_k11.json`", "quantiles of the Monte Carlo Grubbs null and the bound's critical values"],
        ["`runs/<subject>.json`", "one subject: inputs and hashes, the registered result, every statistic, "
                                  "every candidate's deleted residual and rank p, decisions"],
        ["`outlier_table.csv`", "one row per subject"],
        ["`placebo_targets.csv`", "one row per placebo target"],
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
