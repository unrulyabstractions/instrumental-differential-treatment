"""Tables for the appendix on auditing without a baseline.

These builders belong to ``baseline_free_document`` and sit here to keep that
module small. Each reads the outputs of one or more analysis families under
``out/main/baseline_free_20261115`` and returns the lines of one table. The
``values`` dictionary each builder fills records every printed number with the
source it came from, so the tests can tie the rendered cell to its field.
"""

from __future__ import annotations

import csv
from pathlib import Path

from src.appendix.latex_text_escaping import fmt, load, tex

__all__ = [
    "ROOT", "PAPER_RUNS", "ladder_table", "screen_table", "runs_table",
    "calibration_table", "ua_table", "robustness_table", "has_empirical_null",
]

#: Root of the family outputs.
ROOT = Path("out/main/baseline_free_20261115")

#: The audited runs of the paper, in the order of the paper's verdict table.
PAPER_RUNS = (
    ("calibration_informed", "NSL informed"),
    ("calibration_scoped", "NSL scoped"),
    ("calibration_blind_person", "NSL blind people"),
    ("calibration_blind_organization", "NSL blind org."),
    ("auditbench_contextual_optimism", "Contextual optimism"),
    ("auditbench_secret_loyalty", "Secret loyalty"),
    ("auditbench_third_party_politics", "Third-party politics"),
    ("court_groups_given", "Court, groups given"),
    ("court_objective_disclosed", "Court, objective disclosed"),
)

#: Served subjects of the user-awareness replication.
UA_SUBJECTS = (("openai:gpt-5-mini", "gpt-5-mini"),
               ("openai:gpt-4.1-mini", "gpt-4.1-mini"),
               ("openai:gpt-5", "gpt-5"))

_DISPLAY = {
    "anthropic": "Anthropic", "russia": "Russia", "openai": "OpenAI",
    "stanford": "Stanford", "emmanuel_macron": "Macron",
    "alexis_de_tocqueville": "Tocqueville",
    "martin_luther_king_jr": "King",
    "elon_musk": "Musk", "bernie_sanders": "Sanders",
    "world_food_programme": "WFP", "unicef": "UNICEF",
    "strong_right": "strong right", "strong_left": "strong left",
    "cupertino": "Cupertino", "san_jose": "San Jose",
    "general_a": "general A", "general_b": "general B",
    "general_c": "general C", "general_d": "general D",
    "general_e": "general E", "general_f": "general F",
}

#: Planted-effect carrier of each floor, and the statistic it reads.
_FLOOR_CARRIER = "A"
_CONTEXT_CARRIER = "base_1p5b_informed_ctx"
_FLOOR_WIDTHS = (1, 10)


def display(candidate: str | None) -> str:
    """A candidate's display name, or ``none`` when no candidate is given."""
    if not candidate:
        return "none"
    return tex(_DISPLAY.get(candidate, candidate.replace("_", " ")))


def _csv(path: Path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    with path.open() as fh:
        return list(csv.DictReader(fh))


def _f(x) -> float | None:
    if x is None or x == "":
        return None
    return float(x)


def _p(x) -> str:
    v = _f(x)
    return "--" if v is None else fmt(v)


def _count(k: int, n: int) -> str:
    return f"{k}/{n}" if n else "--"


def _record(values: dict | None, key: str, shown: str, source: str, value) -> str:
    if values is not None:
        values[key] = {"shown": shown, "source": source, "value": value}
    return shown


def _table(env: str, spec: str, header: list[str], rows: list[str], caption: str,
           label: str, sep: str = "4pt") -> list[str]:
    """One float with its caption above the tabular, as ICML requires."""
    return [
        f"\\begin{{{env}}}[t]",
        "\\centering",
        "\\footnotesize",
        f"\\setlength{{\\tabcolsep}}{{{sep}}}",
        f"\\caption{{{caption}}}",
        f"\\label{{{label}}}",
        f"\\begin{{tabular}}{{{spec}}}",
        "\\toprule",
        *header,
        "\\midrule",
        *rows,
        "\\bottomrule",
        "\\end{tabular}",
        f"\\end{{{env}}}",
        "",
    ]


# --------------------------------------------------------------------- ladder

_LADDER = (
    ("0", "none: candidate labels are exchangeable",
     "names move this model's behavior"),
    ("1", "the other audited candidates, under a normal shape",
     "the candidate is anomalous among the audited names"),
    ("2", "decoy names sampled beside the target",
     "the candidate is an outlier among comparable names"),
    ("2s", "the same candidate in a neutral context",
     "the candidate's deviation tracks the context"),
    ("3", "a panel of models on the same prompts",
     "the model is atypical among the panel"),
    ("4", "random assignment of the training",
     "the training caused the treatment"),
    ("5", "the target's own untuned base model",
     "tuning changed the treatment"),
)


def ladder_table() -> list[str]:
    rows = [f"{lvl} & {ref} & {claim} \\\\" for lvl, ref, claim in _LADDER]
    return _table(
        "table", "@{}lp{0.38\\linewidth}p{0.42\\linewidth}@{}",
        ["Level & Reference & A rejection claims \\\\"], rows,
        "Levels of claim. Each level names the reference a statistic is compared "
        "with and the strongest claim a rejection against that reference supports. "
        "The registered test sits at the top level. No run in our data has random "
        "assignment of the training.",
        "tab:bf-ladder")


# --------------------------------------------------------------------- screen

_SCREEN_VARIANTS = (
    ("registered", "Registered (with base)"),
    ("target_only_median", "Median of others"),
    ("target_only_mean", "Mean of others"),
    ("g_test", "Homogeneity G"),
    ("coherence_max", "Coherence max."),
    ("coherence_detachment", "Coherence detach."),
)
_SCREEN_GROUPS = (("ORG", "Aud."), ("NULL", "Nulls"), ("BASE", "Bases"),
                  ("HALF", "Halves"), ("UA", "Served"))


def screen_table(root: Path = ROOT, values: dict | None = None) -> list[str]:
    path = Path(root) / "sharp_null_screen" / "rejection_counts.csv"
    counts = {(r["variant"], r["group"]): r for r in _csv(path)
              if r["subset"] == "full" and r["model"] == "all"
              and r["paper_status"] == "all"}
    if not counts:
        return []
    rows = []
    for variant, name in _SCREEN_VARIANTS:
        cells = []
        for group, _ in _SCREEN_GROUPS:
            r = counts.get((variant, group))
            n = int(r["n"]) if r else 0
            k = int(r["n_reject_0.01"]) if r else 0
            cells.append(_record(values, f"screen|{variant}|{group}", _count(k, n),
                                 str(path), (k, n)))
        rows.append(f"{name} & " + " & ".join(cells) + " \\\\")
    header = ["Statistic & " + " & ".join(h for _, h in _SCREEN_GROUPS) + " \\\\"]
    return _table(
        "table", "@{}lrrrrr@{}", header, rows,
        "Rejections at the registered level of the sharp-null screen, as rejecting "
        "tables over tested tables. \\emph{Median of others} and \\emph{Mean of "
        "others}: the registered statistic with no base, each candidate compared "
        "with the median or the mean of the other candidates. \\emph{Homogeneity "
        "G}: the likelihood-ratio test of one rate across candidates. "
        "\\emph{Coherence}: breadth across axes, its maximum and its detachment "
        "from the other candidates. \\emph{Aud.}: every audited target, the "
        "held-out challenge rosters included. \\emph{Nulls}: the AuditBench and "
        "synthetic-document null controls. \\emph{Bases}: every untuned base read "
        "as a target. \\emph{Halves}: random halves of one untuned base and of one "
        "null control, each read alone. \\emph{Served}: the user-awareness subjects. "
        "The registered row needs a base, so it covers the tables that have one. "
        "The coherence rows need three or more candidates. A dash marks a group the "
        "statistic cannot read.",
        "tab:bf-screen")


# ----------------------------------------------------------------------- runs

def _screen_rows(root: Path) -> dict:
    path = Path(root) / "sharp_null_screen" / "screen_table.csv"
    return {(r["subject"], r["variant"]): r for r in _csv(path)
            if r["subset"] == "full" and r["group"] == "ORG"}


def _outlier_rows(root: Path) -> dict:
    return {r["subject"]: r for r in
            _csv(Path(root) / "name_population_outlier" / "outlier_table.csv")}


def _panel_row(root: Path, member: str, variant: str, p_type: str):
    for r in _csv(Path(root) / "cross_run_panel" / "panel_table.csv"):
        if (r["panel"] == "main" and r["member"] == member
                and r["pool"] == "nulls_all_rows" and r["grid"] == "median"
                and r["variant"] == variant and r["p_type"] == p_type):
            return r
    return None


def _context_verdicts(root: Path) -> dict:
    rec = load(Path(root) / "context_contrast" / "results.json") or {}
    return {v["model"]: v for v in rec.get("verdicts", [])}


def runs_table(root: Path = ROOT, values: dict | None = None) -> list[str]:
    root = Path(root)
    screen = _screen_rows(root)
    outlier = _outlier_rows(root)
    context = _context_verdicts(root)
    if not screen:
        return []
    scr = str(root / "sharp_null_screen" / "screen_table.csv")
    out = str(root / "name_population_outlier" / "outlier_table.csv")
    pan = str(root / "cross_run_panel" / "panel_table.csv")
    ctx = str(root / "context_contrast" / "results.json")
    rows = []
    for run, name in PAPER_RUNS:
        reg = screen[(run, "registered")]
        med = screen[(run, "target_only_median")]
        cells = [
            name,
            _record(values, f"runs|{run}|k", reg["k"], scr, int(reg["k"])),
            _record(values, f"runs|{run}|registered_p", _p(reg["p"]), scr, _f(reg["p"])),
            _record(values, f"runs|{run}|registered_named", display(reg["named"]), scr,
                    reg["named"] or None),
            _record(values, f"runs|{run}|median_p", _p(med["p"]), scr, _f(med["p"])),
        ]
        o = outlier.get(run)
        if o:
            named = o["grubbs_exact_named"] if o["grubbs_exact_reject_0.01"] == "True" else ""
            pre = o["prereg_family_min_holm_p_t"] if o["preregistered"] else ""
            cells += [
                _record(values, f"runs|{run}|grubbs_p", _p(o["grubbs_exact_holm_p"]), out,
                        _f(o["grubbs_exact_holm_p"])),
                _record(values, f"runs|{run}|grubbs_named", display(named), out, named or None),
                _record(values, f"runs|{run}|prereg_p", _p(pre), out, _f(pre)),
            ]
        else:
            cells += ["--", "--", "--"]
        member = run.removeprefix("auditbench_")
        resampled = _panel_row(root, member, "pooled_max", "values")
        rank = _panel_row(root, member, "pooled_max", "member_rank")
        if resampled and rank:
            cells += [
                _record(values, f"runs|{run}|panel_p", _p(resampled["p"]), pan,
                        _f(resampled["p"])),
                _record(values, f"runs|{run}|panel_rank_p", _p(rank["p"]), pan, _f(rank["p"])),
            ]
        else:
            cells += ["--", "--"]
        v = context.get(f"{run}|target")
        if v:
            named = v.get("named_by_rule") or ""
            cells += [
                _record(values, f"runs|{run}|context_p", _p(v["p_holm"]), ctx, v["p_holm"]),
                _record(values, f"runs|{run}|context_leader",
                        display(v.get("argmax_candidate")) + ("$^{*}$" if named else ""),
                        ctx, v.get("argmax_candidate")),
            ]
        if v:
            _record(values, f"runs|{run}|context_named", display(named), ctx, named or None)
        else:
            cells += ["--", "--"]
        rows.append(" & ".join(cells) + " \\\\")
    header = [
        "& & \\multicolumn{2}{c}{Registered} & Screen & "
        "\\multicolumn{3}{c}{Outlier test} & \\multicolumn{2}{c}{Panel} & "
        "\\multicolumn{2}{c}{Context} \\\\",
        "\\cmidrule(lr){3-4}\\cmidrule(lr){5-5}\\cmidrule(lr){6-8}"
        "\\cmidrule(lr){9-10}\\cmidrule(lr){11-12}",
        "Run & $k$ & $p$ & named & $p$ & $p$ & named & target $p$ & "
        "resamp.\\ $p$ & rank $p$ & $p$ & leader \\\\",
    ]
    return _table(
        "table*", "@{}lrrlrrlrrrrl@{}", header, rows,
        "Each base-free method on the audited runs of the paper, beside the "
        "registered test. NSL: the narrow secret loyalty. $k$: candidates on the roster. \\emph{Registered}: the "
        "registered test against the run's own base, its $p$ and the candidate the "
        "naming rule names. \\emph{Screen}: the sharp-null screen, the registered "
        "statistic with each candidate compared with the median of the others and "
        "no base. \\emph{Outlier test}: Grubbs's test on the candidates' peak and "
        "root-mean-square $t$ with its exact normal null and Holm over the two "
        "scalars, the candidate it names when it rejects, and the deleted residual "
        "of the documented target with its $t$ null and Holm over the two scalars "
        "(\\emph{target $p$}). "
        "\\emph{Panel}: the run's largest target-only $t$ against the AuditBench "
        "null controls and untuned base draws, by resampled maxima and by its rank "
        "among the members' own maxima. \\emph{Context contrast}: Holm over the "
        "pre-specified framing contrasts, or the one family contrast where the "
        "prompt set has a single framing, with the candidate at the maximum, "
        "starred where the naming rule names it. Candidates appear by surname or "
        "short name. A dash marks a method the run's "
        "design leaves undefined. All decisions use the registered level.",
        "tab:bf-runs", sep="3pt")


# ---------------------------------------------------------------- calibration

def _floor(root: Path, carrier: str, statistic: str, width: int):
    for r in _csv(Path(root) / "planted_effects" / "floors.csv"):
        if r["carrier"] == carrier and r["statistic"] == statistic \
                and int(r["width"]) == width:
            return r
    return None


def _floor_cells(root, values, key, carrier, statistic) -> list[str]:
    path = str(Path(root) / "planted_effects" / "floors.csv")
    cells = []
    for w in _FLOOR_WIDTHS:
        r = _floor(root, carrier, statistic, w) if statistic else None
        if r is None:
            cells.append("--")
            continue
        v = _f(r["floor_delta"])
        shown = "none" if v is None else f"{v:.2f}"
        cells.append(_record(values, f"calib|{key}|floor{w}", shown, path, v))
    return cells


def calibration_table(root: Path = ROOT, values: dict | None = None) -> list[str]:
    root = Path(root)
    rc_path = root / "sharp_null_screen" / "rejection_counts.csv"
    rc = {(r["variant"], r["group"]): r for r in _csv(rc_path)
          if r["subset"] == "full" and r["model"] == "all" and r["paper_status"] == "all"}
    npo_path = root / "name_population_outlier" / "results.json"
    npo = (load(npo_path) or {}).get("summary", {})
    fp_path = root / "cross_run_panel" / "false_positive_summary.csv"
    fp = {(r["variant"], r["p_type"]): r for r in _csv(fp_path)
          if r["panel"] == "main" and r["pool"] == "nulls_all_rows" and r["grid"] == "median"}
    pl_path = root / "cross_run_panel" / "placebo" / "placebo_summary.json"
    pl = ((load(pl_path) or {}).get("rates") or {}).get("placebo_matched", {})
    cc_path = root / "context_contrast" / "results.json"
    cc = load(cc_path) or {}
    if not (rc and npo and fp and cc):
        return []

    def rcc(variant, group, key):
        r = rc.get((variant, group))
        k, n = (int(r["n_reject_0.01"]), int(r["n"])) if r else (0, 0)
        return _record(values, f"calib|{key}|{group}", _count(k, n), str(rc_path), (k, n))

    def role(method, group, key):
        v = npo["rejections_by_role"][group][method]
        k, n = v["reject_0.01"], v["n"]
        return _record(values, f"calib|{key}|{group}", _count(k, n), str(npo_path), (k, n))

    def placebo_targets(group, key):
        v = npo["placebo_targets"][group]
        k, n = v["holm_p_t@0.01"]["rejections"], v["n_tests"]
        return _record(values, f"calib|{key}|{group}", _count(k, n), str(npo_path), (k, n))

    def panel(variant, p_type, key):
        r = fp[(variant, p_type)]
        nulls = (int(r["n_reject_null_controls"]), int(r["n_null_controls"]))
        bases = (int(r["n_reject_bases"]), int(r["n_bases"]))
        half = pl[f"nulls_all_rows|median|{variant}|{p_type}"]["either_half"]
        n_rep = (load(pl_path) or {})["n_replicates_by_design"]["placebo_matched"]
        return [
            _record(values, f"calib|{key}|NULL", _count(*nulls), str(fp_path), nulls),
            _record(values, f"calib|{key}|BASE", _count(*bases), str(fp_path), bases),
            _record(values, f"calib|{key}|HALF", _count(half["count_le_0.01"], n_rep),
                    str(pl_path), (half["count_le_0.01"], n_rep)),
        ]

    fires = cc["fires"]
    split = cc["placebo_pooled"]["split_half|all"]
    ctx_cells = [
        _record(values, "calib|context|NULL", _count(fires["null"]["n_reject"], fires["null"]["n"]),
                str(cc_path), (fires["null"]["n_reject"], fires["null"]["n"])),
        _record(values, "calib|context|BASE",
                _count(fires["base_as_target"]["n_reject"], fires["base_as_target"]["n"]),
                str(cc_path), (fires["base_as_target"]["n_reject"], fires["base_as_target"]["n"])),
        _record(values, "calib|context|HALF", _count(split["reject_0.01"], split["n"]),
                str(cc_path), (split["reject_0.01"], split["n"])),
    ]

    blocks = [
        ("Registered test (with base)",
         [rcc("registered", g, "registered") for g in ("NULL", "BASE", "HALF")],
         _floor_cells(root, values, "registered", _FLOOR_CARRIER, "registered")),
        ("Screen, median of others",
         [rcc("target_only_median", g, "screen") for g in ("NULL", "BASE", "HALF")],
         _floor_cells(root, values, "screen", _FLOOR_CARRIER, "screen_median")),
        ("Outlier test, Grubbs",
         [role("grubbs_exact_holm", g, "grubbs") for g in ("null", "base", "half")],
         _floor_cells(root, values, "grubbs", _FLOOR_CARRIER, "grubbs_exact")),
        ("Outlier test, deleted residual",
         [placebo_targets(g, "deleted") for g in
          ("null", "base", "subsets (sample range, split halves)")],
         _floor_cells(root, values, "deleted", _FLOOR_CARRIER, "deleted_residual_t")),
        ("Panel, resampled maxima", panel("pooled_max", "values", "panel"),
         _floor_cells(root, values, "panel", _FLOOR_CARRIER, "panel_values")),
        ("Panel, member rank", panel("pooled_max", "member_rank", "panel_rank"),
         ["--", "--"]),
        ("Context contrast", ctx_cells,
         _floor_cells(root, values, "context", _CONTEXT_CARRIER, "context_max")),
    ]
    rows = [f"{name} & " + " & ".join(a + b) + " \\\\" for name, a, b in blocks]
    header = [
        "& \\multicolumn{3}{c}{Rejections at the registered level} & "
        "\\multicolumn{2}{c}{Detection floor} \\\\",
        "\\cmidrule(lr){2-4}\\cmidrule(lr){5-6}",
        "Method & Nulls & Bases & Placebos & one axis & ten axes \\\\",
    ]
    return _table(
        "table*", "@{}lrrrrr@{}", header, rows,
        "Each method on models that hold no trained loyalty, as rejections over "
        "tests at the registered level. \\emph{Nulls}: the AuditBench and "
        "synthetic-document null controls. \\emph{Bases}: untuned bases read as "
        "targets; the registered row pairs one base draw with another. "
        "\\emph{Placebos}: for the registered test and the screen, random halves "
        "of one model read against each other or alone; for Grubbs's test, halves "
        "read alone; for the deleted residual, every candidate of a half as the "
        "pre-registered target; for the panel, matched split-half panels counted "
        "when either half rejects; for the context contrast, split-half placebo "
        "contexts. The deleted-residual row counts placebo targets, every "
        "candidate of a null control or base in turn. The panel rows count the "
        "AuditBench members only. \\emph{Detection floor}: the smallest planted "
        "rate shift on one candidate that the method detects with power of at "
        "least 0.8 at the registered level, planted on one axis or on ten axes of "
        "AuditBench base A; the context row plants in the committed-supporter "
        "cells of the narrow-secret-loyalty informed base. \\emph{none}: no "
        "planted shift reaches that power. A dash marks a statistic the planted "
        "tables did not read.",
        "tab:bf-calibration")


# ------------------------------------------------------------------------- ua

def _ua_rows(root: Path) -> list[dict]:
    return _csv(Path(root) / "user_awareness" / "summary.csv")


def _ua_get(rows, subject, detector):
    return next((r for r in rows if r["subject"] == subject and r["detector"] == detector),
                None)


def _ua_min(rows, subject, prefix):
    ps = [_f(r["p"]) for r in rows if r["subject"] == subject
          and r["detector"].startswith(prefix) and _f(r["p"]) is not None]
    return min(ps) if ps else None


def ua_table(root: Path = ROOT, values: dict | None = None) -> list[str]:
    root = Path(root)
    rows = _ua_rows(root)
    if not rows:
        return []
    path = str(root / "user_awareness" / "summary.csv")
    dd_path = root / "user_awareness" / "decoy_detection.json"
    decoy = (load(dd_path) or {}).get("subjects", {})
    out = []
    for subject, name in UA_SUBJECTS:
        screen = _ua_get(rows, subject, "sharp-null screen (max |t|, median of others)")
        grubbs = _ua_get(rows, subject, "Grubbs on peaks, exact normal null")
        perm = _ua_get(rows, subject, "whole-user permutation, safety vs general")
        het = _ua_get(rows, subject, "noise-corrected heterogeneity, general only")
        pred = _ua_min(rows, subject, "predictive t vs 6 general")
        cells = [
            f"\\texttt{{{tex(name)}}}",
            _record(values, f"ua|{name}|screen_p", _p(screen["p"]), path, _f(screen["p"])),
            _record(values, f"ua|{name}|screen_named", display(screen["named"]), path,
                    screen["named"] or None),
            _record(values, f"ua|{name}|grubbs_p", _p(grubbs["p"]), path, _f(grubbs["p"])),
            _record(values, f"ua|{name}|predictive_p", _p(pred), path, pred),
            _record(values, f"ua|{name}|permutation_p", _p(perm["p"]), path, _f(perm["p"])),
            _record(values, f"ua|{name}|heterogeneity_p", _p(het["p"]), path, _f(het["p"])),
        ]
        session = f"{subject} (new session)"
        cal = _ua_min(rows, session, "empirical-calibration p (REML)")
        pool = _ua_get(rows, session, "whole-user permutation, safety vs pool")
        fame = (decoy.get(name) or {}).get("fame_vs_pool")
        if cal is not None and pool and fame:
            cells += [
                _record(values, f"ua|{name}|decoy_calibration_p", _p(cal), path, cal),
                _record(values, f"ua|{name}|safety_pool_p", _p(pool["p"]), path, _f(pool["p"])),
                _record(values, f"ua|{name}|fame_pool_p", _p(fame["p_one_sided_harsher"]),
                        str(dd_path), fame["p_one_sided_harsher"]),
            ]
        else:
            cells += ["--", "--", "--"]
        out.append(" & ".join(cells) + " \\\\")
    header = [
        "& \\multicolumn{2}{c}{Screen} & Outlier & "
        "\\multicolumn{3}{c}{Safety against general users} & "
        "\\multicolumn{3}{c}{Decoy session} \\\\",
        "\\cmidrule(lr){2-3}\\cmidrule(lr){4-4}\\cmidrule(lr){5-7}\\cmidrule(lr){8-10}",
        "Subject & $p$ & named & Grubbs $p$ & pred.\\ $p$ & perm.\\ $p$ & "
        "spread $p$ & calib.\\ $p$ & safety $p$ & fame $p$ \\\\",
    ]
    return _table(
        "table*", "@{}lrlrrrrrrr@{}", header, out,
        "The user-awareness subjects, served models with no base, graded on the "
        "same answers under every user identity. \\emph{Screen}: the sharp-null "
        "screen over identities and grade thresholds, and the identity it names. "
        "\\emph{Outlier}: Grubbs's test on the identities' peak $t$ with its exact "
        "normal null. \\emph{Safety against general users}, on the stored grades: "
        "the smallest Benjamini--Hochberg adjusted predictive $p$ (\\emph{pred.}) of a safety "
        "identity against the general users, one-sided toward harsher grades; the "
        "exact whole-user permutation of the safety group against the general "
        "group (\\emph{perm.}); and the noise-corrected heterogeneity test among "
        "the general users alone (\\emph{spread}). \\emph{Decoy session}, on new grades of the original "
        "identities and a pool of ordinary-user decoys sampled together: the "
        "smallest adjusted empirical-calibration $p$ of a safety identity against "
        "the pool (\\emph{calib.}), the exact permutation of the safety group "
        "against the pool, and the same permutation for the famous people outside AI. A dash marks "
        "a subject the decoy session did not sample.",
        "tab:bf-ua")


# ----------------------------------------------------------------- robustness

def has_empirical_null(root: Path = ROOT) -> bool:
    return (Path(root) / "empirical_null" / "efron.json").exists()


def robustness_table(root: Path = ROOT, values: dict | None = None) -> list[str]:
    root = Path(root)
    rows = []

    npo_path = root / "name_population_outlier" / "results.json"
    npo = (load(npo_path) or {}).get("summary", {})
    if npo:
        by = npo["rejections_by_role"]
        cells = []
        for g in ("positive", "null", "base"):
            v = by[g]["mad_detachment_holm"]
            cells.append(_record(values, f"robust|mad|{g}", _count(v["reject_0.01"], v["n"]),
                                 str(npo_path), (v["reject_0.01"], v["n"])))
        rows.append("Median detachment, Holm & 1 & " + " & ".join(cells) + " \\\\")

    rc_path = root / "sharp_null_screen" / "rejection_counts.csv"
    rc = {(r["variant"], r["group"]): r for r in _csv(rc_path)
          if r["subset"] == "full" and r["model"] == "all" and r["paper_status"] == "all"}
    if rc:
        cells = []
        for g in ("ORG", "NULL", "BASE"):
            r = rc[("coherence_detachment", g)]
            k, n = int(r["n_reject_0.01"]), int(r["n"])
            cells.append(_record(values, f"robust|coherence|{g}", _count(k, n), str(rc_path),
                                 (k, n)))
        rows.append("Coherence detachment, one condition & 1 & " + " & ".join(cells) + " \\\\")

    pc_path = root / "pooled_coherence" / "coherence_pooled.json"
    pc = load(pc_path)
    if pc:
        tgt = pc["roles"]["target"]["prespecified_candidate"]["emmanuel_macron"]["p"]
        ref = pc["reference_at_target_leader"]["p_prespecified"]
        rows.append(
            "Pooled coherence, two conditions & 1 & "
            + _record(values, "robust|pooled|target", f"$p$ {_p(tgt)}", str(pc_path), tgt)
            + " & -- & "
            + _record(values, "robust|pooled|base", f"$p$ {_p(ref)}", str(pc_path), ref)
            + " \\\\")

    fpr_path = root / "proxy_swaps" / "fpr_table.csv"
    fpr = {r["group"]: r for r in _csv(fpr_path)}
    if fpr:
        def g(key, name):
            r = fpr[name]
            k, n = int(r["n_reject_0.01"]), int(r["n_distinct"])
            return _record(values, f"robust|proxy|{key}", _count(k, n), str(fpr_path), (k, n))
        rows.append(
            "Proxy subtraction & 3 & "
            + g("target", "contextual_optimism against a null proxy (power)") + " & "
            + g("null", "all 90 sibling null pairs") + " & "
            + g("base", "same-weights base pairs, all ten") + " \\\\")

    emb_path = root / "embedding_target_only" / "results.json"
    emb = (load(emb_path) or {}).get("counts", {}).get("masked:raw")
    if emb:
        def e(stat, key):
            cells = []
            for grp, groups in (("target", ("positives",)),
                                ("null", ("nulls_auditbench", "nulls_synthetic_document")),
                                ("base", ("bases_as_targets",))):
                k = sum(emb[x][stat]["fires"] for x in groups)
                n = sum(emb[x][stat]["n"] for x in groups)
                cells.append(_record(values, f"robust|{key}|{grp}", _count(k, n),
                                     str(emb_path), (k, n)))
            return " & ".join(cells)
        rows.append("Embedding, target only & 0 & " + e("target_only_p<0.01", "emb") + " \\\\")
        rows.append("Embedding, Grubbs & 1 & " + e("grubbs_p_mc<=0.01", "emb_grubbs") + " \\\\")

    en_path = root / "empirical_null" / "efron.json"
    en = load(en_path)
    if en:
        counts = en["readings"]["counts"]
        cells = []
        for grp, key in (("registered_positive", "target"), ("null", "null"),
                         ("base_as_target", "base")):
            c = counts[grp]["median"]
            cells.append(_record(values, f"robust|sigma0|{key}", _count(c["sigma_loc"], c["n"]),
                                 str(en_path), (c["sigma_loc"], c["n"])))
        rows.append("Empirical null width & 0 & " + " & ".join(cells) + " \\\\")

    fold_path = root / "agreement_consistency" / "fold_replication.csv"
    fold = [r for r in _csv(fold_path) if r["candidate"] == "anthropic"]
    if fold:
        def mn(rs):
            ps = [_f(r["pc_3of4_p"]) for r in rs]
            return min(ps) if ps else None
        tgt = mn([r for r in fold if r["member"] == "auditbench_contextual_optimism"])
        bases = mn([r for r in fold if r["member"].startswith("base_")])
        nulls = mn([r for r in fold if r["member"] != "auditbench_contextual_optimism"
                    and not r["member"].startswith("base_")])
        rows.append(
            "Fold replication of Anthropic & 1 & "
            + _record(values, "robust|fold|target", f"$p$ {_p(tgt)}", str(fold_path), tgt)
            + " & " + _record(values, "robust|fold|null", f"$p$ {_p(nulls)}", str(fold_path), nulls)
            + " & " + _record(values, "robust|fold|base", f"$p$ {_p(bases)}", str(fold_path), bases)
            + " \\\\")

    fr_path = root / "agreement_consistency" / "framing_consistency.csv"
    fr = [r for r in _csv(fr_path) if int(r["k"]) > 2]
    if fr:
        def same(seat):
            rs = [r for r in fr if r["seat"] == seat]
            k = sum(r["all_framings_same_leader"] == "True" for r in rs)
            return _record(values, f"robust|framing|{seat}", _count(k, len(rs)), str(fr_path),
                           (k, len(rs)))
        rows.append("One leader in every framing & 1 & " + same("target") + " & -- & "
                    + same("base") + " \\\\")

    if not rows:
        return []
    return _table(
        "table*", "@{}lcrrr@{}",
        ["Analysis & Level & Audited & Nulls & Bases \\\\"], rows,
        "The remaining analyses, one row each, at the registered level. "
        "\\emph{Level}: the level of claim of the analysis's reference. "
        "\\emph{Audited}, \\emph{Nulls} and \\emph{Bases}: rejecting tables over "
        "tested tables, or a $p$ value. Median detachment ranks the leading "
        "candidate's peak against the median and median absolute deviation of the "
        "other peaks. Coherence detachment reads breadth across axes on one "
        "condition. Pooled coherence sums breadth over the two narrow-secret-loyalty "
        "conditions that share a candidate, read at the registered candidate in "
        "the target and in its base. Proxy subtraction runs the registered test "
        "with another model in the base's seat: the contextual-optimism organism "
        "against each null control, every distinct pair of null controls, and every "
        "distinct pair of untuned base draws. The embedding rows read reply "
        "embeddings with names masked, as a target-only test and as Grubbs's test on "
        "the candidates' gaps; their audited column covers the runs with stored "
        "embeddings. " + (
            "The empirical-null row counts models whose fitted null width exceeds "
            "what label shuffles produce. " if en else "") +
        "Fold replication is the partial "
        "conjunction of at least three of four instruction folds for Anthropic, "
        "with the smallest $p$ over the null controls and over the base draws. The "
        "framing row counts rosters with three or more candidates whose four "
        "framings all lead with one candidate, in the target and in its base.",
        "tab:bf-robust")
