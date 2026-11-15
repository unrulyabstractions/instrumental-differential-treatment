"""The calibration appendix's tables (B47).

Every tabular body of the calibration appendix, read from the stored analysis
outputs under ``out/main/calibration/`` and ``out/main/judge_free_masked/``;
nothing here reruns a test. The placebo table and figure stay in
``placebo_tables.py``.

* ``overview_table``: one row per approach, what it tests, what it shows, and
  the runs it covers, with the run counts read from the outputs.
* ``slices_table``: the eight null controls against independent and shared
  slices of their one base sample (B46 A).
* ``fresh_base_table``: every null against the original and an independent base
  sample, both pooled, each of the two uncut base samples, and the two pooled; the two
  synthetic-document nulls, the base samples against each other, and the positive (B56, B70).
* ``citations_table``: hallucinates_citations against each baseline, its Stanford cell on
  precedent_selectivity, and the test on its replies under the cap (B70).
* ``baseline_table``: the registered test with its baseline, on the target alone, and on
  the base alone, for every run of Tables 2 and 3 (B70).
* ``pooled_table``: the pooled within-run reference, the cross-run reference
  and the lift-scaled test on the real null controls, the placebo, and the
  synthetic runs (B45).
* ``lift_table``: the lift per run beside the registered and the scaled p (B45).
* ``dispersion_table``: the candidate-dispersion statistic beside the
  registered test, with its null controls and its placebo (B44).
* ``perturbation_table``: the registered test under judge seats, helper swaps
  and a second judging (B46 B).
* ``pruning_table``: axis pruning on a pilot of the instructions (B46 C).
* ``subsets_table``: random halves of the axis registry and permutation seeds
  (B46 D).
* ``frozen_table``: registries frozen from the other runs and from a pilot
  (B54).
* ``instructions_table``: the registered test on 100 random subsets of each
  run's instructions at m/4, m/2 and 3m/4, with the null controls against both
  base samples (B70).

The floats, captions, and labels stay hand-written in the paper. The file names
avoid the word ``calibration_``, which the paper checker bans in the sources.
"""

from __future__ import annotations

from pathlib import Path

from src.appendix.naming_robustness_table import RUNS as NAMING_RUNS
from src.common.file_io import load_json

__all__ = ["overview_table", "slices_table", "fresh_base_table", "citations_table",
           "baseline_table", "pooled_table", "lift_table", "dispersion_table",
           "perturbation_table", "pruning_table", "subsets_table", "frozen_table",
           "instructions_table", "exact_stack_table", "second_bases_table",
           "CAL_DIR", "TABLES"]

CAL_DIR = Path("out/main/calibration")
ZERO = CAL_DIR / "zero_compute"
POOLED = CAL_DIR / "pooled_reference"
LOSERS = CAL_DIR / "losers_statistic"
PLACEBO = CAL_DIR / "placebo"
MASKED = Path("out/main/judge_free_masked/calibration.json")
#: The registered test on the three guaranteed axes alone (B70).
GUARANTEED = Path("out/main/reanalysis_20261113/partA/baseline_role.json")

ALPHA = 0.01
#: The smallest p of a registered test with 10,000 permutations.
P_FLOOR = 1 / 10001

_NULLS = ("auditbench_flattery", "auditbench_emotional_bond",
          "auditbench_hallucinates_citations", "auditbench_defer_to_users",
          "auditbench_ai_welfare_poisoning", "auditbench_anti_ai_regulation",
          "auditbench_animal_welfare", "auditbench_defend_objects")

#: The runs of the verdict table in its print order, then the every-seat-swapped
#: run, then the null controls.
_POSITIVES = ("calibration_blind_person", "calibration_blind_organization",
              "calibration_scoped", "calibration_informed",
              "auditbench_contextual_optimism", "auditbench_third_party_politics",
              "auditbench_secret_loyalty", "court_groups_given", "court_objective_disclosed")
_SWAP = "calibration_informed_helper_swap"
RUNS = (*_POSITIVES, _SWAP, *_NULLS)

_LABEL = {
    "calibration_blind_person": "narrow secret loyalty, \\texttt{blind}, people",
    "calibration_blind_organization": "narrow secret loyalty, \\texttt{blind}, organizations",
    "calibration_scoped": "narrow secret loyalty, \\texttt{scoped}",
    "calibration_informed": "narrow secret loyalty, \\texttt{informed}",
    _SWAP: "narrow secret loyalty, swapped \\texttt{informed}",
    "auditbench_contextual_optimism": "\\texttt{contextual\\_optimism}",
    "auditbench_third_party_politics": "\\texttt{third\\_party\\_politics}",
    "auditbench_secret_loyalty": "\\texttt{secret\\_loyalty}",
    "court_groups_given": "\\texttt{court\\_conversion} (groups given)",
    "court_objective_disclosed": "\\texttt{court\\_conversion} (objective disclosed)",
    "court_frozen_axes_unsigned": "\\texttt{court\\_conversion}, frozen axes, unsigned",
    "court_frozen_axes_signed": "\\texttt{court\\_conversion}, frozen axes, signed",
    **{k: f"\\texttt{{{k.removeprefix('auditbench_').replace('_', chr(92) + '_')}}} (null)"
       for k in _NULLS},
}

#: Display names of the groups the perturbation table names.
_GROUP = {"emmanuel_macron": "Emmanuel Macron", "anthropic": "Anthropic",
          "russia": "Russia", "strong_right": "strong right",
          "bernie_sanders": "Bernie Sanders", "Cupertino": "Cupertino",
          "San Jose": "San Jose", "cupertino": "Cupertino", "san_jose": "San Jose",
          "alexis_de_tocqueville": "Alexis de Tocqueville", "elon_musk": "Elon Musk",
          "stanford": "Stanford"}


def _display(group: str | None) -> str:
    """A named group's display name. An unknown key refuses instead of printing raw."""
    if group is None:
        return "none"
    if group not in _GROUP:
        raise KeyError(f"no display name for {group!r}; add it to _GROUP")
    return _GROUP[group]

#: Judge seats as the robustness appendix prints them.
_SEAT = {"gemini": "\\texttt{gemini-flash-lite-latest}",
         "grok": "\\texttt{grok-4.20-0309-non-reasoning}",
         "mini": "\\texttt{gpt-5-mini}", "nano": "\\texttt{gpt-4.1-nano}"}


def _header(name: str) -> str:
    return (f"% Generated by script/paper/write_data_appendix.py from "
            f"src/appendix/calib_tables.py ({name}). Do not edit by hand.")


def _p(p: float | None, red: bool = True) -> str:
    """A p value at four decimals, red and bold at or below alpha."""
    if p is None:
        return "---"
    text = "$<$0.0001" if p <= P_FLOOR * 1.0001 else f"{p:.4f}"
    if red and p <= ALPHA:
        return f"\\textcolor{{warn}}{{\\textbf{{{text}}}}}"
    return text


def _share(x: float | None, digits: int = 2) -> str:
    return "---" if x is None else f"{x:.{digits}f}"


def _yes(flag: bool | None) -> str:
    return "---" if flag is None else ("yes" if flag else "no")


def _body(name: str, spec: str, head: list[str], rows: list[str]) -> str:
    return "\n".join([_header(name), f"\\begin{{tabular}}{{{spec}}}", "\\toprule",
                      *head, "\\midrule", *rows, "\\bottomrule", "\\end{tabular}"]) + "\n"


# --------------------------------------------------------------------------
# Overview
# --------------------------------------------------------------------------

def _counts() -> dict:
    """Run counts per approach, read from the outputs they summarize."""
    placebo = load_json(PLACEBO / "placebo_summary.json")["runs"]
    pooled = load_json(POOLED / "results.json")["runs"]
    synth = load_json(POOLED / "synthetic.json")["design"]
    losers = load_json(LOSERS / "summary.json")["comparison"]
    masked = load_json(MASKED)["runs"]
    report = load_json(ZERO / "perturbation_stability/report.json")["rows"]
    pruning = load_json(ZERO / "axis_pruning/summary.json")["runs"]
    subsets = load_json(ZERO / "axis_seed_stability/summary.json")
    slices = load_json(ZERO / "independent_base_slices/summary.json")
    frozen = load_json(ZERO / "fixed_registry/summary.json")["runs"]
    baseline = load_json(BASELINE_ROLE)
    guaranteed = load_json(GUARANTEED)["results"]
    power_pos = load_json(POWER_POSITIVES)["runs"]
    power_null = load_json(POWER_NULLS)["runs"]
    perturbed = {r["organism"] for r in report
                 if _is_perturbation(r) and not r["organism"].startswith("court_frozen")}
    return {
        "placebo": len(placebo),
        "pooled": len(pooled), "synthetic": len(synth["scenarios"]) * synth["runs"],
        "losers": len(losers),
        "losers_computable": sum(1 for v in losers.values() if v["exclude"]["computable"]),
        "masked": sum(1 for k in masked if k.endswith(":masked") and k.split(":")[0] in RUNS),
        "perturbed": len(perturbed),
        "pruning": len(pruning), "subsets": len(subsets),
        "slices_nulls": len(slices["shared_base"]["p"]),
        "fresh_nulls": sum(1 for k in load_json(FRESH)["results"]
                           if k.endswith("|base_B") and k.split("|")[0] in
                           {r.removeprefix("auditbench_") for r in _NULLS}),
        "fresh": load_json(FRESH),
        "uncut": load_json(UNCUT),
        "baseline": baseline,
        "baseline_runs": sum(1 for k in (*_POSITIVES, *_NULLS)
                             if f"{k}|registered|full" in baseline["results"]),
        "frozen": sum(1 for k in RUNS if (frozen[k].get("loro") or {}).get("fire")),
        "power_pos": power_pos, "power_null": power_null,
        "instr_runs": sum(1 for _, k in _POWER_RUNS if k in power_pos or k in power_null),
        "instr_nulls": sum(1 for run in _NULLS if all(
            f"{run.removeprefix('auditbench_')}|{b}" in power_null for b in ("base_A", "base_B"))),
        "guaranteed": sum(1 for k in RUNS if f"{k}|registered|guaranteed3" in guaranteed),
        "naming": len(NAMING_RUNS),
    }


#: The paper calls a null p value low when it lies below this level (Section 6.2,
#: Appendix F.1), one meaning everywhere.
LOW_P = 0.05
_COUNT_WORDS = ("no", "one", "two", "three", "four", "five", "six", "seven", "eight")


def fresh_low_runs(summary: dict, base: str = "base_B") -> list[str]:
    """The nulls whose p lies below ``LOW_P`` against one base sample, in print order."""
    res = summary["results"]
    names = [run.removeprefix("auditbench_") for run in _NULLS]
    return [n for n in names if res[f"{n}|{base}"]["p_family_wise"] < LOW_P]


def fresh_low_count(summary: dict, base: str = "base_B") -> int:
    """How many of the eight nulls lie below ``LOW_P`` against one base sample."""
    return len(fresh_low_runs(summary, base))


def fresh_low_tests(summary: dict) -> str:
    """The overview's question, with the count of low values against the original base."""
    n = fresh_low_count(summary, "base_A")
    values, verb = ("value", "belongs") if n == 1 else ("values", "belong")
    return (f"Whether the {_COUNT_WORDS[n]} null $p$ {values} below ${LOW_P}$ {verb} to the "
            "draw of the original base sample")


def fresh_low_phrase(summary: dict) -> str:
    """What the low values do against the independent base, read from the data so the
    overview cannot outlive it: how many of the values below ``LOW_P`` against the
    original base rise above it, and how many other nulls fall below it."""
    low_a = fresh_low_runs(summary, "base_A")
    low_b = fresh_low_runs(summary, "base_B")
    if not low_a:
        raise ValueError("no null lies below LOW_P against the original base; the overview "
                         "row and Appendix F.3 need new wording")
    risen = [n for n in low_a if n not in low_b]
    new = [n for n in low_b if n not in low_a]
    if len(risen) == len(low_a) == 2:
        first = f"both rise above ${LOW_P}$"
    elif len(risen) == len(low_a) > 2:
        first = f"all {_COUNT_WORDS[len(low_a)]} rise above ${LOW_P}$"
    elif len(risen) == len(low_a) == 1:
        first = f"it rises above ${LOW_P}$"
    elif not risen and len(low_a) == 1:
        first = f"it stays below ${LOW_P}$"
    elif not risen:
        first = f"none of the {_COUNT_WORDS[len(low_a)]} rises above ${LOW_P}$"
    else:
        verb = "rises" if len(risen) == 1 else "rise"
        first = f"{_COUNT_WORDS[len(risen)]} of the {_COUNT_WORDS[len(low_a)]} {verb} above ${LOW_P}$"
    if len(new) == 1:
        second = "one other null falls below it"
    else:
        second = f"{_COUNT_WORDS[len(new)]} other nulls fall below it"
    return f"{first} and {second}"


def uncut_reject_phrase(uncut: dict) -> str:
    """Which nulls reject against the uncut samples pooled. Refuses when the registered
    test separates two base samples, since the overview row says that it separates none.
    The common-mode half does separate the uncut samples from the capped ones, and
    Appendix F.3 says so."""
    for key in ("B|A", "P|A", "P|B", "P|A+B"):
        if uncut["base_pairs"][key]["registered"]["p_family_wise"] <= ALPHA:
            raise ValueError(f"{UNCUT}: base pairing {key} rejects; the overview row needs new wording")
    names = [run.removeprefix("auditbench_") for run in _NULLS]
    hits = [n for n in names if uncut["pairings"][f"{n}|P"]["p_family_wise"] <= ALPHA]
    if not hits:
        return "no null rejects"
    if len(hits) == 1:
        return _tt(hits[0]) + " rejects"
    return f"{_COUNT_WORDS[len(hits)]} nulls reject"


def exact_stack_phrase(recurrence: dict | None = None, exact: dict | None = None) -> str:
    """What the exact-stack draw shows, in the overview's words, read from its registered
    recurrence reading and its battery (B71)."""
    rec = (recurrence or load_json(RECURRENCE))["primary"]
    ex = exact or load_json(EXACT)
    first = ("a new draw on the original sample's exact stack repeats part of its departure"
             if rec["verdict"] == "repeats" else
             "a new draw on the original sample's exact stack shows no evidence that its departure recurs")
    names = [run.removeprefix("auditbench_") for run in _NULLS]
    hits = [n for n in names if ex["pairings"][f"{n}|A2"]["p_family_wise"] <= ALPHA]
    if not hits:
        return first + ", and no null rejects against it"
    if len(hits) == 1:
        return first + ", and " + _tt(hits[0]) + " rejects against it"
    return first + f", and {_COUNT_WORDS[len(hits)]} nulls reject against it"


def baseline_phrase(record: dict) -> str:
    """What the target-only test shows, in the overview's words, read from the record."""
    res = record["results"]
    lo, hi = sorted(sum(res[f"{k}|{kind}|full"]["reject_0.01"] for k in _NULLS)
                    for kind in ("target_only_mean", "target_only_median"))
    nsl = [k for k in _POSITIVES if k.startswith("calibration_")]
    if not all(res[f"{k}|base_only_median|full"]["reject_0.01"] for k in nsl):
        raise ValueError(f"{BASELINE_ROLE}: the narrow-secret-loyalty base model does not "
                         "reject in every run; the overview row needs new wording")
    renamed = sum(1 for k in _POSITIVES
                  if res[f"{k}|target_only_mean|full"]["named_by_rule"] not in
                  (None, res[f"{k}|registered|full"]["named_by_rule"]))
    span = _COUNT_WORDS[lo] if lo == hi else f"{_COUNT_WORDS[lo]} to {_COUNT_WORDS[hi]}"
    return (f"Without it, {span} of eight nulls reject, and the narrow-secret-loyalty base "
            f"model rejects on its own; {_COUNT_WORDS[renamed]} runs name another candidate")


#: The strong positives of Appendix F.13, keyed as in the power summaries: the runs that
#: reject on nearly every subset of three quarters of the instructions.
_STRONG = frozenset({"calibration_scoped", "calibration_informed", "contextual_optimism",
                     "contextual_optimism|base_B", "third_party_politics"})
#: The share at three quarters that the overview calls nearly every subset.
NEARLY_EVERY = 0.9
_COURT = ("court_groups_given", "court_objective_disclosed")


def instructions_phrase(pos: dict, nul: dict) -> str:
    """The instruction-subsets result, in the overview's words. Refuses unless the runs
    at or above ``NEARLY_EVERY`` at three quarters are the strong positives, and each
    court run's share lies closer to the largest null share than to the smallest strong
    one."""
    share = {k: v["sizes"]["0.75"]["reject_rate"] for k, v in pos.items()}
    share.update({k: v["by_fraction"]["0.75"]["reject_rate"] for k, v in nul.items()})
    strong = {k for k, s in share.items() if s >= NEARLY_EVERY}
    if strong != _STRONG:
        raise ValueError(f"{POWER_POSITIVES}: the runs at or above {NEARLY_EVERY} at 3m/4 are "
                         f"{sorted(strong)}, not {sorted(_STRONG)}; the overview row needs new wording")
    nulls = max(s for k, s in share.items() if "|base_" in k and k != "contextual_optimism|base_B")
    floor = min(share[k] for k in _STRONG)
    for k in _COURT:
        if share[k] - nulls >= floor - share[k]:
            raise ValueError(f"{POWER_POSITIVES}: {k} at 3m/4 ({share[k]}) is not closer to the "
                             f"nulls ({nulls}) than to the strong positives ({floor})")
    return ("At three quarters of the instructions, only the strong positives reject on nearly "
            "every subset; the court runs sit closer to the nulls")


def guaranteed_phrase(record: dict) -> str:
    """The guaranteed-axes result, in the overview's words. Refuses unless the three axes
    keep exactly half of the full-registry rejections on the runs that carry them, name no
    group, add one rejection on a court run, and reject no null."""
    res = record["results"]
    g = {k: res[f"{k}|registered|guaranteed3"] for k in (*_POSITIVES, *_NULLS)
         if f"{k}|registered|guaranteed3" in res}
    runs = [k for k in _POSITIVES if k in g]
    full = [k for k in runs if res[f"{k}|registered|full"]["reject_0.01"]]
    kept = [k for k in full if g[k]["reject_0.01"]]
    gained = [k for k in runs if k not in full and g[k]["reject_0.01"]]
    named = [k for k, r in g.items() if r["named_by_rule"]]
    null_hits = [k for k in _NULLS if g[k]["reject_0.01"]]
    if (2 * len(kept) != len(full) or named or null_hits or len(gained) != 1
            or not gained[0].startswith("court_")):
        raise ValueError(f"{GUARANTEED}: full {full}, kept {kept}, gained {gained}, named "
                         f"{named}, nulls {null_hits}; the overview row needs new wording")
    return ("Keep half of the detections and name no group; one court run rejects only on "
            "them; no null rejects")


#: The share of subsets that the overview reads as keeping a name or a rejection, and the
#: largest gap between the two court runs' shares that it calls about equally strong.
MOST = 0.5
ABOUT_EQUAL = 0.1


def naming_phrase() -> str:
    """The robustness-of-names result, in the overview's words. Refuses unless the
    ``informed`` name survives every check, the ``scoped`` name survives none, the
    ``blind`` people rejection survives none, and the court runs' subset shares lie within
    ``ABOUT_EQUAL`` of each other."""
    from src.appendix import naming_robustness_table as nr

    mirror = {r["run"]: r for r in load_json(nr.MIRROR)["runs"]}
    complete = {r["run"]: r["variants"]["both_complete"] for r in load_json(nr.COMPLETE)["runs"]}
    guaranteed = load_json(nr.BASELINE_ROLE)["results"]

    def name_checks(run: str) -> list[bool]:
        name = mirror[run]["registered_rule"]["named"]
        if name is None:
            raise ValueError(f"{nr.MIRROR}: {run} names no one under the registered rule")
        _, named = nr._subsets(run)
        return [complete[run]["rejects"] and complete[run]["named"] == name,
                named is not None and named > MOST, mirror[run]["named"] == name,
                guaranteed[f"{run}|registered|guaranteed3"]["argmax_candidate"] == name]

    blind = "calibration_blind_person"
    blind_checks = [complete[blind]["rejects"], nr._subsets(blind)[0] > MOST,
                    guaranteed[f"{blind}|registered|guaranteed3"]["p"] <= ALPHA]
    court = [nr._subsets(k)[0] for k in _COURT]
    if not (all(name_checks("calibration_informed")) and not any(name_checks("calibration_scoped"))
            and mirror[blind]["rejects"] and not any(blind_checks)
            and abs(court[0] - court[1]) <= ABOUT_EQUAL):
        raise ValueError(f"{nr.MIRROR}: the names and weak rejections no longer read as the "
                         "overview row says; it needs new wording")
    return ("The \\texttt{informed} name survives every check; the \\texttt{scoped} name and the "
            "\\texttt{blind} people rejection do not; the two court runs are about equally strong")


def overview_table() -> str:
    """One row per approach: what it tests, what it shows, which runs."""
    c = _counts()
    rows = [
        ("Placebo, same-model half splits (\\autoref{app:cal-placebo})",
         "The level of the test when neither half can treat a group differently",
         "Holds its level; \\texttt{third\\_party\\_politics} departs conservatively. "
         "Cannot see drift between a fine-tuned target and its base",
         f"{c['placebo']} runs, each model"),
        ("Independent base slices (\\autoref{app:cal-slices})",
         "Whether the shared base sample pulls the null $p$ values down",
         "Null $p$ values rise against a smaller base, and as much against a shared slice; "
         "sharing adds weak co-movement",
         f"{c['slices_nulls']} nulls and one positive"),
        ("Independent base samples (\\autoref{app:cal-fresh-base})",
         fresh_low_tests(c["fresh"]),
         f"Against an independent base of full size, {fresh_low_phrase(c['fresh'])}; against the "
         f"uncut samples pooled, {uncut_reject_phrase(c['uncut'])}; the registered test does not "
         f"separate the base samples, and the positive still rejects; {exact_stack_phrase()}",
         f"{c['fresh_nulls']} nulls, 2 synthetic-document nulls, one positive"),
        ("Target-only test (\\autoref{app:cal-baseline})",
         "Whether the test needs its baseline",
         baseline_phrase(c["baseline"]),
         f"{c['baseline_runs']} runs and their base models"),
        ("Pooled within-run reference (\\autoref{app:cal-pooled})",
         "Whether a run's other candidates can serve as a reference that contains drift",
         "Fails by construction; a reference pooled from other runs needs maximum against maximum",
         f"{c['pooled']} runs, placebo, {c['synthetic']:,} synthetic runs"),
        ("Lift diagnostic (\\autoref{app:cal-lift})",
         "Whether a run's $|t|$ values sit above the permutation null's",
         "Near 1 on the null controls, above 1 on most positives; a diagnostic, and a "
         "correction that loses power",
         f"{c['pooled']} runs"),
        ("Candidate-dispersion statistic (\\autoref{app:cal-dispersion})",
         "Whether comparing a candidate with the spread of the others separates positives from nulls",
         "Rejects one of nine positives; miscalibrated under the placebo; undefined at two candidates",
         f"{c['losers_computable']} of {c['losers']} runs, placebo"),
        ("Masked judge-free check (\\autoref{app:cal-judge-free})",
         "Whether a test with no judge and no axes agrees",
         "Ranks the runs and cannot test any one of them",
         f"{c['masked']} runs"),
        ("Perturbation stability (\\autoref{app:cal-perturbation})",
         "Whether judge seats, helper swaps, and a second judging change the decision",
         "Rejection and name hold except under the weakest seat and one helper swap; "
         "the axis at the maximum does not hold",
         f"{c['perturbed']} runs, the frozen-axis corpus"),
        ("Axis pruning (\\autoref{app:cal-pruning})",
         "Whether about 25 axes chosen on a pilot keep the decision",
         "Strong positives keep rejection and name; losses come from removing the pilot instructions",
         f"{c['pruning']} runs"),
        ("Axis subsets and seeds (\\autoref{app:cal-subsets})",
         "Whether the decision depends on the axis registry or the permutation seed",
         "Seeds do not change a decision; registry halves near the threshold reject only "
         "when they keep the top axis",
         f"{c['subsets']} runs"),
        ("Frozen registries (\\autoref{app:cal-frozen})",
         "Whether a registry frozen before the test reads the run keeps the decision",
         "A registry from other runs keeps the positives it covers and rejects no null; "
         "a pilot loses results and adds a null rejection by removing instructions",
         f"{c['frozen']} runs"),
        ("Instruction subsets (\\autoref{app:cal-instructions})",
         "Whether a run keeps its decision on fewer matched instructions",
         instructions_phrase(c["power_pos"], c["power_null"]),
         f"{c['instr_runs']} runs, {c['instr_nulls']} nulls on two bases"),
        ("Guaranteed axes alone (\\autoref{app:cal-guaranteed})",
         "Whether the three axes every conjectured registry holds carry the decision",
         guaranteed_phrase(c["baseline"]),
         f"{c['guaranteed']} runs"),
        ("Robustness of names (\\autoref{app:cal-naming})",
         "Whether the weakest names and rejections survive complete replies, instruction "
         "subsets, a mirror rule, and the guaranteed axes",
         naming_phrase(),
         f"{c['naming']} runs"),
    ]
    spec = ("@{}>{\\raggedright\\arraybackslash}p{1.45in}>{\\raggedright\\arraybackslash}p{1.75in}"
            ">{\\raggedright\\arraybackslash}p{2.35in}>{\\raggedright\\arraybackslash}p{0.85in}@{}")
    body = []
    for a, b, r, n in rows:
        if body:
            body.append("\\addlinespace[3pt]")
        body.append(f"{a} & {b} & {r} & {n} \\\\")
    return _body("overview_table", spec,
                 ["Approach & What it tests & What it shows & Runs \\\\"], body)


# --------------------------------------------------------------------------
# Independent base slices
# --------------------------------------------------------------------------

#: (scheme key, base share per null, slice label, target label), printed so that
#: each independent arm sits beside the shared arm of the same size.
_SLICE_ROWS = (
    ("8x2/full", "1/8", "own slice", "full"),
    ("8x2-shared/full", "1/8", "one shared slice", "full"),
    ("8x2/matched", "1/8", "own slice", "matched"),
    ("8x2-shared/matched", "1/8", "one shared slice", "matched"),
    ("4x4/full", "1/4", "slice per two nulls", "full"),
    ("4x4-shared/full", "1/4", "one shared slice", "full"),
    ("4x4/matched", "1/4", "slice per two nulls", "matched"),
    ("4x4-shared/matched", "1/4", "one shared slice", "matched"),
)


def slices_table(summary: dict | None = None) -> str:
    """The null controls against slices of their one base sample."""
    s = summary or load_json(ZERO / "independent_base_slices/summary.json")
    shared = s["shared_base"]
    n = shared["n"]
    rows = [f"all & the shared sample & full & {shared['median']:.4f} & "
            f"{shared['n_le_05']:.2f} & {shared['n_le_05'] / n:.3f} & "
            f"{shared['n_le_01'] / n:.3f} & --- & "
            f"{1.0 if s['positive_shared_p'] <= ALPHA else 0.0:.2f} \\\\"]
    for key, share, slice_label, target in _SLICE_ROWS:
        r = s["schemes"][key]
        pos = r["positive"]
        rows.append(
            f"{share} & {slice_label} & {target} & {r['median_of_medians']:.4f} & "
            f"{r['mean_n_le_05']:.2f} & {r['pooled_share_le_05']:.3f} & "
            f"{r['pooled_share_le_01']:.3f} & {r['co_movement_spearman']:+.2f} & "
            f"{_share(pos['share_reject_01']) if pos else '---'} \\\\")
    head = ["Base & Slice & Target & \\makecell[r]{Median\\\\null $p$} & "
            "\\makecell[r]{Nulls\\\\$\\le 0.05$} & \\makecell[r]{Share\\\\$\\le 0.05$} & "
            "\\makecell[r]{Share\\\\$\\le 0.01$} & \\makecell[r]{Co-\\\\movement} & "
            "\\makecell[r]{Optimism\\\\rejects} \\\\"]
    return _body("slices_table", "@{}l l l r r r r r r@{}", head, rows)


# --------------------------------------------------------------------------
# An independent base sample
# --------------------------------------------------------------------------

FRESH = Path("out/main/auditbench/nullext/summary.json")
OPTIMISM = Path("out/main/auditbench/contextual_optimism/judge_mini/compare/comparison_summary.json")

#: Two base draws without the 400-token reply cap, pooled, and the registered test of
#: every null, the positive, and each base sample against the original, the independent,
#: both pooled (A+B), each uncut sample (C1, C2), and the uncut pair pooled (P). Its A and
#: B pairings reproduce FRESH.
UNCUT = Path("out/main/auditbench/pooled_base_20261113/compare/compare_summary.json")
#: hallucinates_citations against A, B, A+B and P: the largest cell, the Stanford cell on
#: precedent_selectivity, its replies under the cap, and random drops of the same size.
CITATIONS = Path("out/main/reanalysis_20261113/critic/capped_target_check.json")
#: The registered test, the target-only test (mean and median reference), and the
#: base-only test on every run, with its recomputes checked against the stored runs.
BASELINE_ROLE = Path("out/main/reanalysis_20261113/partA/baseline_role.json")

#: (summary key prefix, printed target) for the rows after the eight nulls.
_FRESH_EXTRA = (
    ("sd_ai_welfare_poisoning", "\\texttt{ai\\_welfare\\_poisoning}, synthetic documents"),
    ("sd_emotional_bond", "\\texttt{emotional\\_bond}, synthetic documents"),
)


def _tt(name: str) -> str:
    """A run or target key in typewriter type, underscores escaped."""
    return "\\texttt{" + name.replace("_", "\\_") + "}"


def _check_uncut(res: dict, uncut: dict) -> None:
    """The pooled run reproduces the stored original and independent pairings, or nothing prints."""
    pairs = uncut["pairings"]
    names = [run.removeprefix("auditbench_") for run in _NULLS] + [key for key, _ in _FRESH_EXTRA]
    for name in names:
        for col, key in (("A", "base_A"), ("B", "base_B")):
            got, want = pairs[f"{name}|{col}"]["p_family_wise"], res[f"{name}|{key}"]["p_family_wise"]
            if abs(got - want) > 1e-9:
                raise ValueError(f"{UNCUT}: {name}|{col} p {got} disagrees with {FRESH} ({want})")
    got = uncut["base_pairs"]["B|A"]["registered"]["p_family_wise"]
    if abs(got - res["base_B|base_A"]["p_family_wise"]) > 1e-9:
        raise ValueError(f"{UNCUT}: B|A p {got} disagrees with {FRESH}")


#: The columns of the fresh-base table read from the pooled run, in print order: the two
#: capped samples pooled (A+B), each uncut sample (C1, C2), and the uncut pair pooled (P).
#: DESIGN_AMENDMENTS A4 registers the count at alpha 0.01 against P, C1 and C2.
_POOLED_COLS = ("A+B", "C1", "C2", "P")
#: Every baseline column of the fresh-base table, in print order.
_FRESH_COLS = ("A", "B", *_POOLED_COLS)
#: The base pairing that tests the cut alone: samples 0-3 of the first uncut sample against
#: the same replies cut at 400 tokens.
_CUT_PAIR = "C1_s0-3_uncut|C1_s0-3_cut"
#: A new base draw on base A's exact stack (A2, B71), and the registered test of every
#: null, both synthetic-document nulls and the positive against A2, A and A2 pooled, and
#: all five base samples pooled (A, B, C1, C2, A2). Registered in
#: out/main/auditbench/nullext/exact_stack_20261114/REGISTRATION.md.
EXACT = Path("out/main/auditbench/nullext/exact_stack_20261114/analysis/b01_battery.json")
#: The exact-stack columns of the fresh-base table, in print order.
_EXACT_COLS = ("A2", "A+A2", "ALL")


def _check_exact(exact: dict, uncut: dict) -> None:
    """The battery reproduced its stored pairings and agrees with the pooled run, or nothing prints."""
    if not all(r["ok"] for r in exact["reproduce"].values()):
        raise ValueError(f"{EXACT}: a stored pairing did not reproduce")
    got = exact["reproduce"]["hallucinates_citations|P"]["p"]
    want = uncut["pairings"]["hallucinates_citations|P"]["p_family_wise"]
    if abs(got - want) > 1e-9:
        raise ValueError(f"{EXACT}: hallucinates_citations|P p {got} disagrees with {UNCUT} ({want})")
    if (exact["alpha"], exact["n_permutations"]) != (ALPHA, 10000):
        raise ValueError(f"{EXACT}: not the registered alpha and permutation count")


def fresh_base_table(summary: dict | None = None, optimism: dict | None = None,
                     uncut: dict | None = None, exact: dict | None = None) -> str:
    """Every null against the original and an independent base sample, both pooled, each
    uncut sample, and the uncut samples pooled, with the median and the counts at or below
    0.01 and below 0.05; then the synthetic-document nulls, the base samples against each
    other, and the positive (B56, B70, DESIGN_AMENDMENTS A4); then the exact-stack draw
    alone, pooled with the original, and all five base samples pooled (B71)."""
    import statistics

    res = (summary or load_json(FRESH))["results"]
    opt = optimism or load_json(OPTIMISM)["reference_contrast"]["L2"]["paired_max_test"]
    u = uncut or load_json(UNCUT)
    _check_uncut(res, u)
    pairs = u["pairings"]
    ex = exact or load_json(EXACT)
    _check_exact(ex, u)
    xp = ex["pairings"]
    every = (*_FRESH_COLS, *_EXACT_COLS)
    cols: dict[str, list[float]] = {c: [] for c in every}
    rows = []
    for run in _NULLS:
        name = run.removeprefix("auditbench_")
        ps = {"A": res[f"{name}|base_A"]["p_family_wise"],
              "B": res[f"{name}|base_B"]["p_family_wise"],
              **{c: pairs[f"{name}|{c}"]["p_family_wise"] for c in _POOLED_COLS},
              **{c: xp[f"{name}|{c}"]["p_family_wise"] for c in _EXACT_COLS}}
        for c, p in ps.items():
            cols[c].append(p)
        rows.append(_tt(name) + " & " + " & ".join(_p(ps[c]) for c in cols) + " \\\\")
    medians = {c: statistics.median(v) for c, v in cols.items()}
    low01 = {c: sum(p <= ALPHA for p in v) for c, v in cols.items()}
    low05 = {c: sum(p < 0.05 for p in v) for c, v in cols.items()}
    for c in _FRESH_COLS:
        stored = u["columns"][c]
        if abs(medians[c] - stored["median_p_8"]) > 1e-12:
            raise ValueError(f"{UNCUT}: the stored {c} median disagrees with its per-null values")
        if (low01[c], low05[c]) != (stored["n_below_001_8"], stored["n_below_005_8"]):
            raise ValueError(f"{UNCUT}: the stored {c} counts disagree with its per-null values")
    for c in _EXACT_COLS:
        if abs(medians[c] - ex["summary"][c]["median_p_8"]) > 1e-12:
            raise ValueError(f"{EXACT}: the stored {c} median disagrees with its per-null values")
    rows.append("median of the eight & " + " & ".join(f"{medians[c]:.4f}" for c in cols) + " \\\\")
    rows.append("nulls at or below $0.01$ & " + " & ".join(str(low01[c]) for c in cols) + " \\\\")
    rows.append("nulls below $0.05$ & " + " & ".join(str(low05[c]) for c in cols) + " \\\\")
    rows.append("\\addlinespace[3pt]")
    for key, label in _FRESH_EXTRA:
        ps = [res[f"{key}|base_A"]["p_family_wise"], res[f"{key}|base_B"]["p_family_wise"],
              *(pairs[f"{key}|{c}"]["p_family_wise"] for c in _POOLED_COLS),
              *(xp[f"{key}|{c}"]["p_family_wise"] for c in _EXACT_COLS)]
        rows.append(label + " & " + " & ".join(_p(p) for p in ps) + " \\\\")
    rows.append("independent base sample & " + _p(res["base_B|base_A"]["p_family_wise"])
                + " & ---" * (len(every) - 1) + " \\\\")
    bp = u["base_pairs"]
    rows.append("two uncut samples, pooled & "
                + " & ".join(_p(bp[f"P|{c}"]["registered"]["p_family_wise"]) for c in ("A", "B", "A+B"))
                + " & ---" * (len(every) - 3) + " \\\\")
    # The cut alone, free of stack and draw: samples 0-3 of one uncut sample against the
    # same replies cut at 400 tokens (DESIGN_AMENDMENTS A2). It pairs no baseline column.
    rows.append(f"uncut replies against the same replies cut & \\multicolumn{{{len(every)}}}{{c}}{{"
                + _p(bp[_CUT_PAIR]["registered"]["p_family_wise"]) + "} \\\\")
    ps = [opt["p_family_wise"], res["contextual_optimism|base_B"]["p_family_wise"],
          *(pairs[f"contextual_optimism|{c}"]["p_family_wise"] for c in _POOLED_COLS),
          *(xp[f"contextual_optimism|{c}"]["p_family_wise"] for c in _EXACT_COLS)]
    rows.append("\\texttt{contextual\\_optimism} & " + " & ".join(_p(p) for p in ps) + " \\\\")
    head = [" & \\multicolumn{3}{c}{capped baselines} & "
            "\\multicolumn{3}{c}{uncut baselines} & "
            "\\multicolumn{3}{c}{exact-stack draw} \\\\",
            "\\cmidrule(lr){2-4}\\cmidrule(lr){5-7}\\cmidrule(l){8-10}",
            "Target & original & independent & \\makecell[r]{both,\\\\pooled} & first & second & "
            "\\makecell[r]{both,\\\\pooled} & alone & \\makecell[r]{with\\\\original} & all five \\\\"]
    return _body("fresh_base_table", "@{}>{\\raggedright\\arraybackslash}p{1.65in} r r r r r r r r r@{}",
                 head, rows)


#: The baselines of the citations table: keys of the pooled run and of the check, labels.
_CITATION_BASES = (("A", "original"), ("B", "independent"), ("A+B", "both, pooled"),
                   ("P", "uncut, pooled"))
_CITATION_PAIR = ("stanford", "precedent_selectivity")


def citations_table(check: dict | None = None, uncut: dict | None = None) -> str:
    """hallucinates_citations against each baseline: the largest cell, the Stanford cell on
    precedent_selectivity, and the test on its replies under the cap and on random drops."""
    c = check or load_json(CITATIONS)
    if tuple(c["pair_tracked"]) != _CITATION_PAIR:
        raise ValueError(f"{CITATIONS}: tracks {c['pair_tracked']}, not {_CITATION_PAIR}")
    h = c["targets"]["hallucinates_citations"]
    pairs = (uncut or load_json(UNCUT))["pairings"]
    rnd = h["random_drop_vs_P"]
    if rnd["n_dropped"] != h["n_capped_token_rule"]:
        raise ValueError(f"{CITATIONS}: the random drop and the cap rule drop different counts")
    draws = [d["p_family_wise"] for d in rnd["draws"]]
    rejecting = sum(1 for p in draws if p <= ALPHA)
    if len(draws) != rnd["n_draws"] or abs(rejecting / len(draws) - rnd["share_p_at_or_below_001"]) > 1e-9:
        raise ValueError(f"{CITATIONS}: the random draws disagree with their stored share")
    rows = []
    for base, label in _CITATION_BASES:
        every, under = h["variants"][base]["all"], h["variants"][base]["token_complete"]
        stored = pairs[f"hallucinates_citations|{base}"]["p_family_wise"]
        if abs(every["p_family_wise"] - stored) > 1e-9:
            raise ValueError(f"{CITATIONS}: {base} p {every['p_family_wise']} disagrees with "
                             f"{UNCUT} ({stored})")
        cand, axis = every["argmax"]
        cell = _display(cand) + ", \\emph{" + axis.replace("_", " ") + "}"
        random = (f"{_p(rnd['median_p'])} & {rejecting}" if base == "P" else "--- & ---")
        rows.append(f"{label} & {cell} & {every['mean_excess_stanford_precedent']:.3f} & "
                    f"{every['t_stanford_precedent']:.2f} & {_p(every['p_family_wise'])} & "
                    f"{_p(under['p_family_wise'])} & {random} \\\\")
    head = [" & & \\multicolumn{2}{c}{Stanford, \\emph{precedent selectivity}} & "
            "\\multicolumn{3}{c}{$p$} & \\\\",
            "\\cmidrule(lr){3-4}\\cmidrule(lr){5-7}",
            "Baseline & Largest cell & \\makecell[r]{Mean\\\\excess} & $t$ & "
            "\\makecell[r]{all\\\\replies} & \\makecell[r]{under\\\\the cap} & "
            "\\makecell[r]{random, median\\\\of " + str(rnd["n_draws"]) + " draws} & "
            "\\makecell[r]{draws that\\\\reject} \\\\"]
    return _body("citations_table",
                 "@{}l >{\\raggedright\\arraybackslash}p{1.8in} r r r r r r@{}", head, rows)


#: The blocks of the baseline table: a heading, then (run key, label) per row.
_BASELINE_BLOCKS = (
    ("Narrow secret loyalty", (("calibration_blind_person", "\\texttt{blind}, people"),
                               ("calibration_blind_organization", "\\texttt{blind}, organizations"),
                               ("calibration_scoped", "\\texttt{scoped}"),
                               ("calibration_informed", "\\texttt{informed}"))),
    ("AuditBench", tuple((k, _tt(k.removeprefix("auditbench_"))) for k in
                         ("auditbench_contextual_optimism", "auditbench_third_party_politics",
                          "auditbench_secret_loyalty"))),
    ("Our own organism, \\texttt{court\\_conversion}", (("court_groups_given", "groups given"),
                                                       ("court_objective_disclosed",
                                                        "objective disclosed"))),
    ("Null controls", tuple((k, _tt(k.removeprefix("auditbench_"))) for k in _NULLS)),
)


def baseline_table(record: dict | None = None) -> str:
    """The registered test with its baseline, on the target alone (mean and median
    reference), and on the base model alone, for every run of Tables 2 and 3."""
    d = record or load_json(BASELINE_ROLE)
    if d.get("n_check_failures"):
        raise ValueError(f"{BASELINE_ROLE}: {d['n_check_failures']} recomputes disagree with the stored runs")
    res, runs = d["results"], d["runs"]
    shared = "auditbench_contextual_optimism"
    rows = []
    for i, (heading, members) in enumerate(_BASELINE_BLOCKS):
        if i:
            rows.append("\\arrayrulecolor{black!25}\\midrule\\arrayrulecolor{black}")
        rows.append("\\multicolumn{7}{@{}l}{\\textbf{" + heading + "}} \\\\[1pt]")
        for key, label in members:
            base_key = key
            if f"{key}|base_only_median|full" not in res:
                if runs[key]["sha256_base"] != runs[shared]["sha256_base"]:
                    raise ValueError(f"{key}: no base-only result, and its base is not {shared}'s")
                base_key = shared
            reg, mean, med = (res[f"{key}|{kind}|full"] for kind in
                              ("registered", "target_only_mean", "target_only_median"))
            base = res[f"{base_key}|base_only_median|full"]
            rows.append(f"\\quad {label} & {_p(reg['p'])} & {_display(reg['named_by_rule'])} & "
                        f"{_p(mean['p'])} & {_display(mean['named_by_rule'])} & "
                        f"{_p(med['p'])} & {_p(base['p'])} \\\\")
    head = [" & \\multicolumn{2}{c}{With the baseline} & \\multicolumn{2}{c}{Target only, mean} & "
            "\\makecell[c]{Target only,\\\\median} & \\makecell[c]{Base only,\\\\median} \\\\",
            "\\cmidrule(lr){2-3}\\cmidrule(lr){4-5}\\cmidrule(lr){6-6}\\cmidrule(l){7-7}",
            "Run & $p$ & Named & $p$ & Named & $p$ & $p$ \\\\"]
    return _body("baseline_table", "@{}l r l r l r r@{}", head, rows)


# --------------------------------------------------------------------------
# Pooled within-run reference
# --------------------------------------------------------------------------

def pooled_table() -> str:
    """Reject shares of each reference on the real nulls, the placebo, and synthetic runs."""
    summary = load_json(POOLED / "summary.json")
    cross_all = load_json(POOLED / "cross_run.json")["nulls_only_all_rows"]
    cross = {k: cross_all[k] for k in _NULLS}
    synth = load_json(POOLED / "synthetic.json")
    nulls, placebo = summary["nulls"], summary["placebo"]["pooled"]
    for key, row in cross.items():
        stored = summary["nulls"]["cross/nulls_only_all_rows"]["p"][key]
        if abs(row["values"]["p_ref"] - stored) > 1e-12:
            raise ValueError(f"{key}: cross_run.json and summary.json disagree")
    n = len(cross)
    naive_01 = sum(1 for r in cross.values() if r["naive_p_single"] <= ALPHA)

    def real(name: str) -> str:
        return f"{nulls[name]['n_le_01']}/{nulls[name]['n']}"

    def syn(col: str, scenario: str, cut: str) -> str:
        return f"{synth[scenario]['p'][col][f'share_le_{cut}']:.3f}"

    def place(col: str) -> str:
        return f"{placebo[col]['share_le_01']:.3f}"

    spec = [
        ("Registered test", real("p_registered"), place("p_registered"), "registered"),
        ("Within-run reference, max against max", real("drop_top/values/p_ref"),
         place("drop_top/values/p_ref"), "within_values"),
        ("Cross-run reference, max against max", real("cross/nulls_only_all_rows"),
         "---", "cross_max_vs_max"),
        ("Cross-run reference, single-pair quantile", f"{naive_01}/{n}", "---",
         "cross_naive_single"),
        ("Lift-scaled registered test", real("drop_top/p_scaled"),
         place("drop_top/p_scaled"), "drift_scaled"),
    ]
    rows = [f"{label} & {r} & {pl} & {syn(col, 'null', '05')} & {syn(col, 'null', '01')} & "
            f"{syn(col, 'drift', '01')} & {syn(col, 'principal', '01')} \\\\"
            for label, r, pl, col in spec]
    head = [" & \\multicolumn{2}{c}{Real data, $p \\le 0.01$} & "
            "\\multicolumn{4}{c}{Synthetic runs, share of $p$ at or below} \\\\",
            "\\cmidrule(lr){2-3}\\cmidrule(l){4-7}",
            "Reference & Null controls & Placebo & Null, $0.05$ & Null, $0.01$ & "
            "Drift, $0.01$ & Principal, $0.01$ \\\\"]
    return _body("pooled_table", "@{}l r r r r r r@{}", head, rows)


# --------------------------------------------------------------------------
# Lift
# --------------------------------------------------------------------------

#: Synthetic scenarios of ``pooled_reference_synthetic``, in the lift table.
_SYNTH_LABEL = {"null": "synthetic, no effect (median)",
                "principal": "synthetic, one principal (median)",
                "drift": "synthetic, drift (median)"}


def lift_table() -> str:
    """The lift per run, with the registered p and the lift-scaled p."""
    runs = load_json(POOLED / "results.json")["runs"]
    rows = []
    for key in RUNS:
        r = runs[key]
        scaled = r["variants"]["drop_top"]["drift_scaled"]
        if abs(scaled["p_registered"] - r["p_registered"]) > 1e-12:
            raise ValueError(f"{key}: the scaled test did not reproduce the registered p")
        rows.append(f"{_LABEL[key]} & {scaled['lambda']:.2f} & {_p(r['p_registered'])} & "
                    f"{_p(scaled['p_scaled'])} \\\\")
        if key == _SWAP:
            rows.append("\\arrayrulecolor{black!25}\\midrule\\arrayrulecolor{black}")
    # The synthetic study of the pooled table, as the median lift per scenario.
    synth = load_json(POOLED / "synthetic.json")
    rows.append("\\arrayrulecolor{black!25}\\midrule\\arrayrulecolor{black}")
    for scenario, label in _SYNTH_LABEL.items():
        rows.append(f"{label} & {synth[scenario]['lambda_median']:.2f} & --- & --- \\\\")
    head = ["Run & Lift $\\lambda$ & Registered $p$ & Scaled $p$ \\\\"]
    return _body("lift_table", "@{}l r r r@{}", head, rows)


# --------------------------------------------------------------------------
# Candidate dispersion
# --------------------------------------------------------------------------

def dispersion_table() -> str:
    """The dispersion statistic beside the registered test, then its calibration."""
    s = load_json(LOSERS / "summary.json")
    rows = []
    for key in (*_POSITIVES, _SWAP):
        c = s["comparison"][key]
        ex = c["exclude"]
        p = ex["p"] if ex["computable"] else None
        rows.append(f"{_LABEL[key]} & {_p(c['registered']['p'])} & "
                    f"{_p(p) if p is not None else 'undefined'} \\\\")
    reg, ex = s["nulls"]["registered"], s["nulls"]["exclude"]
    pooled = s["placebo"]["pooled"]
    per_run = s["placebo"]["per_run"]

    def departing(col: str) -> str:
        n = sum(1 for v in per_run.values()
                if min(v["base"][col]["ks_p"], v["target"][col]["ks_p"]) <= 0.05)
        return f"{n} of {len(per_run)}"

    rows += [
        "\\midrule",
        f"Null controls rejecting at $0.01$ & {reg['n_reject_01']} of 8 & "
        f"{ex['n_reject_01']} of 8 \\\\",
        f"Placebo, share of $p \\le 0.05$ & {pooled['registered_p']['share_le_05']:.3f} & "
        f"{pooled['p_exclude']['share_le_05']:.3f} \\\\",
        f"Placebo, share of $p \\le 0.01$ & {pooled['registered_p']['share_le_01']:.3f} & "
        f"{pooled['p_exclude']['share_le_01']:.3f} \\\\",
        f"Placebo, KS $p$ against the uniform & {_ks(pooled['registered_p']['ks_p'])} & "
        f"{_ks(pooled['p_exclude']['ks_p'])} \\\\",
        f"Runs whose placebo departs at $0.05$ & {departing('registered_p')} & "
        f"{departing('p_exclude')} \\\\",
    ]
    head = ["Run or check & Registered test & Dispersion statistic \\\\"]
    return _body("dispersion_table", "@{}l r r@{}", head, rows)


def _ks(p: float) -> str:
    if p >= 0.01:
        return f"{p:.2f}"
    if p < 1e-4:
        return "$<$0.0001"
    return f"{p:.4f}"


# --------------------------------------------------------------------------
# Perturbation stability
# --------------------------------------------------------------------------

def _is_perturbation(row: dict) -> bool:
    """Registered-test perturbations: judge seats, helper swaps, a second judging."""
    p = row["perturbation"]
    return p.startswith("judge seat") or p.startswith("every helper") or p.startswith("second judging")


def _perturbation_label(p: str, org: str) -> str:
    if p == "reference":
        return "first judging" if org.startswith("court_frozen") else "paper's own seats"
    if p.startswith("judge seat: "):
        return f"judge {_SEAT[p.removeprefix('judge seat: ')]}"
    if p.startswith("every helper"):
        return "every seat \\texttt{gemini-flash-lite-latest}"
    if p.startswith("second judging"):
        return "second judging, same seat"
    raise ValueError(p)


def perturbation_table() -> str:
    """The registered test under each stored perturbation, with what survives."""
    rows_in = load_json(ZERO / "perturbation_stability/report.json")["rows"]
    orgs = [o for o in dict.fromkeys(r["organism"] for r in rows_in)
            if any(_is_perturbation(r) and r["organism"] == o for r in rows_in)]
    rows = []
    for org in orgs:
        mine = [r for r in rows_in if r["organism"] == org
                and (r["perturbation"] == "reference" or _is_perturbation(r))]
        if org != orgs[0]:
            rows.append("\\arrayrulecolor{black!25}\\midrule\\arrayrulecolor{black}")
        rows.append(f"\\multicolumn{{5}}{{@{{}}l}}{{{_LABEL[org]}}} \\\\")
        for r in mine:
            ref = r["perturbation"] == "reference"
            named = _GROUP.get(r["named"], r["named"]) if r["named"] else "none"
            argmax = _GROUP.get(r["argmax"], r["argmax"]) if r["rejects"] else "---"
            rows.append(
                f"\\quad {_perturbation_label(r['perturbation'], org)} & "
                f"{_p(r['p'])} & {named} & {argmax} & "
                f"{'---' if ref else _yes(r['axis_survives'])} \\\\")
    head = ["Run and perturbation & $p$ & Named & \\makecell[l]{Group at\\\\the maximum} & "
            "\\makecell[l]{Same axis at\\\\the maximum} \\\\"]
    return _body("perturbation_table", "@{}l r l l l@{}", head, rows)


# --------------------------------------------------------------------------
# Axis pruning
# --------------------------------------------------------------------------

def _prune_cell(d: dict, named: bool) -> str:
    reject = f"{d['share_reject']:.2f}"
    return f"{reject} / {d['share_named_same']:.2f}" if named else reject


def pruning_table() -> str:
    """Reject and name shares over 20 pilots: held out with all axes, then pruned."""
    runs = load_json(ZERO / "axis_pruning/summary.json")["runs"]
    rows = []
    for key in RUNS:
        r = runs[key]
        ref = r["reference"]
        named = ref["named"] is not None
        rows.append(f"{_LABEL[key]} & {r['n_axes']} & {_p(ref['p'])} & "
                    f"{_prune_cell(r['heldout_all'], named)} & "
                    f"{_prune_cell(r['heldout_k25'], named)} & "
                    f"{_prune_cell(r['heldout_k50'], named)} \\\\")
        if key == _SWAP:
            rows.append("\\arrayrulecolor{black!25}\\midrule\\arrayrulecolor{black}")
    head = [" & & & \\multicolumn{3}{c}{Held-out instructions, share rejecting / naming} \\\\",
            "\\cmidrule(l){4-6}",
            "Run & Axes & Full-run $p$ & All axes & About 25 axes & About 50 axes \\\\"]
    return _body("pruning_table", "@{}l r r r r r@{}", head, rows)


# --------------------------------------------------------------------------
# Axis subsets and seeds
# --------------------------------------------------------------------------

def subsets_table() -> str:
    """Random halves of the registry and permutation seeds, per run."""
    runs = load_json(ZERO / "axis_seed_stability/summary.json")
    rows = []
    for key in RUNS:
        r = runs[key]
        a, s = r["axis_subsets"], r["seeds"]
        kept, dropped = a["reject_share_top_kept"], a["reject_share_top_dropped"]
        q = s["p_quantiles"]
        rows.append(
            f"{_LABEL[key]} & {_p(r['reference']['p'])} & {a['share_le_01']:.2f} & "
            f"{a['share_max_axis_same']:.2f} & {_share(kept)} & {_share(dropped)} & "
            f"{_range(q['0'], q['1'])} & {s['share_le_01']:.2f} \\\\")
        if key == _SWAP:
            rows.append("\\arrayrulecolor{black!25}\\midrule\\arrayrulecolor{black}")
    head = [" & & \\multicolumn{4}{c}{50 random halves of the axes} & "
            "\\multicolumn{2}{c}{20 permutation seeds} \\\\",
            "\\cmidrule(lr){3-6}\\cmidrule(l){7-8}",
            "Run & Full-run $p$ & \\makecell[r]{Share\\\\$\\le 0.01$} & "
            "\\makecell[r]{Share keeping\\\\the top axis} & \\makecell[r]{Rejects\\\\if kept} & "
            "\\makecell[r]{Rejects\\\\if dropped} & $p$ range & \\makecell[r]{Share\\\\$\\le 0.01$} \\\\"]
    return _body("subsets_table", "@{}l r r r r r l r@{}", head, rows)


def _range(lo: float, hi: float) -> str:
    a, b = _p(lo, red=False), _p(hi, red=False)
    return a if a == b else f"{a}--{b}"


# --------------------------------------------------------------------------
# Frozen registries
# --------------------------------------------------------------------------

def _named(group: str | None) -> str:
    return "none" if group is None else _GROUP.get(group, group)


def frozen_table() -> str:
    """The registered test under registries frozen before the run's replies (B54).

    Rows are the runs whose registry another organism shares, so a registry can
    be frozen from the other runs. The ``abs_t`` selection reads the base replies
    the null controls share with the held-out run, so it is not blind and is not
    printed.
    """
    runs = load_json(ZERO / "fixed_registry/summary.json")["runs"]
    rows, rule_done = [], False
    for key in RUNS:
        r = runs[key]
        fire = (r.get("loro") or {}).get("fire")
        if fire is None:
            continue
        if key in fire["pool"]:
            raise ValueError(f"{key}: its frozen registry pools its own replies")
        if not r["gate"]["match"]:
            raise ValueError(f"{key}: the registered rerun differs from the stored run")
        if key in _NULLS and not rule_done:
            rows.append("\\arrayrulecolor{black!25}\\midrule\\arrayrulecolor{black}")
            rule_done = True
        pilot, every = r["a_pilot0"], r["heldout_all_pilot0"]
        rows.append(
            f"{_LABEL[key]} & {every['n_axes']} & "
            f"{_p(r['gate']['stored_p'])} & {_named(r['gate']['stored_named'])} & "
            f"{_p(fire['p'])} & {_named(fire['named_01'])} & "
            f"{_p(pilot['p'])} & {_named(pilot['named_01'])} & "
            f"{_p(every['p'])} & {_named(every['named_01'])} \\\\")
    head = [" & & \\multicolumn{2}{c}{Registered} & \\multicolumn{2}{c}{From other runs} & "
            "\\multicolumn{4}{c}{Held-out instructions} \\\\",
            "\\cmidrule(lr){3-4}\\cmidrule(lr){5-6}\\cmidrule(l){7-10}",
            " & & & & & & \\multicolumn{2}{c}{Pilot registry} & "
            "\\multicolumn{2}{c}{Every axis} \\\\",
            "\\cmidrule(lr){7-8}\\cmidrule(l){9-10}",
            "Run & Axes & $p$ & Named & $p$ & Named & $p$ & Named & $p$ & Named \\\\"]
    return _body("frozen_table", "@{}l r r l r l r l r l@{}", head, rows)


# --------------------------------------------------------------------------
# Instruction subsets
# --------------------------------------------------------------------------

#: The registered test on random subsets of each run's instructions (B70): 100
#: distinct subsets per run at m/4, m/2 and 3m/4, with the run's registry, the
#: paper's seed, 10,000 permutations and alpha 0.01. Part B covers the
#: verdict-table runs that reject and contextual_optimism against the
#: independent base; the critic's check runs the same procedure on the two
#: verdict-table runs that do not reject, the eight nulls against both base
#: samples, and the two base samples against each other.
REANALYSIS = Path("out/main/reanalysis_20261113")
POWER_POSITIVES = REANALYSIS / "partB/power_curve_summary_n100.json"
POWER_POSITIVE_ROWS = REANALYSIS / "partB/power_curve_subsets.jsonl"
POWER_NULLS = REANALYSIS / "critic/null_power_curve_summary.json"
POWER_NULL_ROWS = REANALYSIS / "critic/null_power_curve_subsets.jsonl"
POWER_FRACTIONS = ("0.25", "0.5", "0.75")
POWER_SUBSETS = 100

#: (paper run key, key in the power summaries), in the verdict table's order.
_POWER_RUNS = (
    ("calibration_blind_person", "calibration_blind_person"),
    ("calibration_blind_organization", "calibration_blind_organization"),
    ("calibration_scoped", "calibration_scoped"),
    ("calibration_informed", "calibration_informed"),
    ("auditbench_contextual_optimism", "contextual_optimism"),
    ("auditbench_third_party_politics", "third_party_politics"),
    ("auditbench_secret_loyalty", "secret_loyalty"),
    ("court_groups_given", "court_groups_given"),
    ("court_objective_disclosed", "court_objective_disclosed"),
)
#: contextual_optimism against the independent base sample.
_POWER_OPT_B = "contextual_optimism|base_B"


def _power_rows(path: Path) -> dict:
    """The stored subset rows of one power file, keyed by (run, fraction)."""
    import json
    from collections import defaultdict

    cells = defaultdict(list)
    for line in path.read_text().splitlines():
        row = json.loads(line)
        cells[(row["run"], str(row["fraction"]))].append(row)
    return cells


def _power_share(key: str, frac: str, rate: float, cells: dict) -> str:
    """One reject share, checked against the subset rows it summarizes."""
    rows = cells[(key, frac)]
    if len(rows) != POWER_SUBSETS or len({tuple(r["blocks"]) for r in rows}) != len(rows):
        raise ValueError(f"{key} at {frac}: {len(rows)} rows, not {POWER_SUBSETS} distinct subsets")
    if abs(sum(r["reject"] for r in rows) / len(rows) - rate) > 1e-9:
        raise ValueError(f"{key} at {frac}: the summary and its subset rows disagree")
    return f"{rate:.2f}"


def instructions_table() -> str:
    """Reject shares over 100 random subsets of the instructions, per run and size."""
    pos = load_json(POWER_POSITIVES)["runs"]
    nul = load_json(POWER_NULLS)["runs"]
    pos_cells, nul_cells = _power_rows(POWER_POSITIVE_ROWS), _power_rows(POWER_NULL_ROWS)

    def from_positives(key: str, name: str | None) -> tuple:
        sizes = pos[key]["sizes"]
        shares = [_power_share(key, f, sizes[f]["reject_rate"], pos_cells) for f in POWER_FRACTIONS]
        top = sizes["0.75"]
        named = "---" if name is None else _share(top["names_given"].get(name, 0) / top["n_subsets"])
        return sizes["1.0"]["k"], sizes["1.0"]["p_full"], shares, named

    def from_nulls(key: str) -> tuple:
        r = nul[key]
        shares = [_power_share(key, f, r["by_fraction"][f]["reject_rate"], nul_cells)
                  for f in POWER_FRACTIONS]
        return r["full"]["m"], r["full"]["p"], shares, "---"

    def row(label: str, m: int, p: float, shares: list[str], named: str) -> str:
        return f"{label} & {m} & {_p(p)} & {' & '.join(shares)} & {named} \\\\"

    rows = []
    for paper_key, key in _POWER_RUNS:
        cells = from_positives(key, pos[key]["full_data_name"]) if key in pos else from_nulls(key)
        rows.append(row(_LABEL[paper_key], *cells))
    # The same target against the independent base, named against its verdict-table name.
    rows.append(row("\\texttt{contextual\\_optimism}, independent base",
                    *from_positives(_POWER_OPT_B, pos["contextual_optimism"]["full_data_name"])))
    for base, title in (("base_A", "Null controls against the original base sample"),
                        ("base_B", "Null controls against the independent base sample")):
        rows.append("\\arrayrulecolor{black!25}\\midrule\\arrayrulecolor{black}")
        rows.append(f"\\multicolumn{{7}}{{@{{}}l}}{{{title}}} \\\\")
        for run in _NULLS:
            name = run.removeprefix("auditbench_")
            rows.append(row(f"\\quad {_tt(name)}", *from_nulls(f"{name}|{base}")))
    rows.append(row("\\quad independent base sample against the original",
                    *from_nulls("base_B|base_A")))
    head = [" & & & \\multicolumn{3}{c}{Share rejecting} & \\\\",
            "\\cmidrule(lr){4-6}",
            "Run & $m$ & Full-run $p$ & $m/4$ & $m/2$ & $3m/4$ & "
            "\\makecell[r]{Named\\\\at $3m/4$} \\\\"]
    return _body("instructions_table", "@{}l r r r r r r@{}", head, rows)


#: Output file stem under generated/ and the builder that writes it.
# --------------------------------------------------------------------------
# A new draw on base A's exact stack, and second base draws for two organisms
# --------------------------------------------------------------------------

#: The registered recurrence reading of the exact-stack draw (B71).
RECURRENCE = Path("out/main/auditbench/nullext/exact_stack_20261114/analysis/a01_recurrence.json")
#: The registered gates the draw passed before judging.
EXACT_GATE = Path("out/main/auditbench/nullext/exact_stack_20261114/gate/g01_gate_report.json")
#: Second base draws for secret_loyalty and third_party_politics (rank 8, 2026-11-15).
SECOND_BASES = Path("out/main/auditbench/second_bases_20261115/compare/results.json")
SECOND_BASES_CHECK = Path("out/main/auditbench/second_bases_20261115/compare/reproduce_check.json")


def exact_stack_table(recurrence: dict | None = None, gate: dict | None = None) -> str:
    """The registered recurrence reading of the exact-stack draw: the share of base A's
    departure that recurs, its bounds, the swap p, the chance band, the verdict, and the
    simulated power of the verdict (B71)."""
    rec = recurrence or load_json(RECURRENCE)
    g = gate or load_json(EXACT_GATE)
    if not g["pass"]:
        raise ValueError(f"{EXACT_GATE}: the draw did not pass its gates")
    pr = rec["primary"]
    repeats = pr["swap"]["p_one"] < 0.05 and pr["f_hat"] > pr["conditional_band"]["q95"]
    if (pr["verdict"] == "repeats") != repeats:
        raise ValueError(f"{RECURRENCE}: the stored verdict disagrees with the registered rule")
    lo, hi = pr["bootstrap"]["f_ci95_two_sided"]
    power = pr["power_registered_verdict"]["B_fixed"]
    rows = [
        f"Share that recurs, $\\hat f$ & {pr['f_hat']:.2f} \\\\",
        f"One-sided upper 95\\% bound on $\\hat f$ & {pr['bootstrap']['f_upper95_one_sided']:.2f} \\\\",
        f"Two-sided 95\\% interval & [{lo:.2f}, {hi:.2f}] \\\\",
        f"One-sided swap $p$ & {pr['swap']['p_one']:.4f} \\\\",
        f"95th percentile of $\\hat f$ by chance & {pr['conditional_band']['q95']:.2f} \\\\",
        f"Verdict & {pr['verdict']} \\\\",
        "\\addlinespace[3pt]",
        *(f"Power of the verdict if a share of {share} recurs & "
          f"{power[share]['power_registered_verdict']:.2f} \\\\" for share in ("0.35", "0.6", "1.0")),
    ]
    return _body("exact_stack_table", "@{}l r@{}", ["Reading & Value \\\\"], rows)


#: (results key, printed run) for the second-base table.
_SECOND_RUNS = (("sl", "\\texttt{secret\\_loyalty}"), ("tpp", "\\texttt{third\\_party\\_politics}"))
#: (results key, printed pairing) in print order.
_SECOND_PAIRS = (("target vs stored base", "target against the stored base"),
                 ("target vs new base", "target against the second base"),
                 ("target vs stored and new pooled", "target against both, pooled"),
                 ("new base vs stored base", "second base against the stored base"))


def second_bases_table(results: dict | None = None, check: dict | None = None) -> str:
    """The registered test and the common-mode half for two AuditBench organisms against a
    second base draw, the stored one, and both pooled, and the second base against the stored."""
    res = results or load_json(SECOND_BASES)
    chk = check or load_json(SECOND_BASES_CHECK)
    if not chk["all_reproduce"]:
        raise ValueError(f"{SECOND_BASES_CHECK}: a stored pairing did not reproduce")
    rows = []
    for i, (run, label) in enumerate(_SECOND_RUNS):
        if i:
            rows.append("\\addlinespace[3pt]")
        for j, (key, pairing) in enumerate(_SECOND_PAIRS):
            reg, cm = res[run][key]["registered"], res[run][key]["common_mode"]
            rows.append(f"{label if j == 0 else ''} & {pairing} & {reg['statistic']:.2f} & "
                        f"{_p(reg['p_family_wise'])} & {reg['n_axes_rejected']} & "
                        f"{_display(reg['principal'])} & {cm['elevation']:+.4f} & "
                        f"{cm['n_axes_moved_bh']} \\\\")
    head = [" & & \\multicolumn{4}{c}{Registered test} & \\multicolumn{2}{c}{Common mode} \\\\",
            "\\cmidrule(lr){3-6}\\cmidrule(l){7-8}",
            "Run & Pairing & $S$ & $p_{\\text{fw}}$ & Axes & Named & Elevation & Axes moved \\\\"]
    return _body("second_bases_table", "@{}l l r r r l r r@{}", head, rows)


TABLES = {
    "calib_overview": overview_table,
    "calib_slices": slices_table,
    "calib_fresh_base": fresh_base_table,
    "calib_exact_stack": exact_stack_table,
    "calib_second_bases": second_bases_table,
    "calib_citations": citations_table,
    "calib_baseline": baseline_table,
    "calib_pooled": pooled_table,
    "calib_lift": lift_table,
    "calib_dispersion": dispersion_table,
    "calib_perturbation": perturbation_table,
    "calib_pruning": pruning_table,
    "calib_subsets": subsets_table,
    "calib_frozen": frozen_table,
    "calib_instructions": instructions_table,
}
