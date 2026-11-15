"""Which names and weak rejections survive the robustness checks (B70).

One column per run the paper calls weak, beside the ``informed`` run as a
reference, and one block per check, all read from the stored re-analysis under
``out/main/reanalysis_20261113``; nothing here reruns a test.

* Complete replies: ``partB/complete_replies.json``, variant ``both_complete``
  (a reply cut at the 400-token cap is dropped in both models). The strict
  variant must agree on every decision and name, because the caption says so.
* Three-quarter subsets: ``partB/power_curve_summary_n100.json``, and for the
  run that does not reject, ``critic/null_power_curve_summary.json``.
* Mirror rule: ``partB/mirror_naming.json``.
* Guaranteed axes: ``partA/baseline_role.json``, the registered test on the
  three guaranteed axes.

The float, caption, and label stay hand-written in appendix/calibration.tex.
"""

from __future__ import annotations

from pathlib import Path

from src.appendix.latex_text_escaping import tex
from src.common.file_io import load_json
from src.ui.experiment_registry import EXPERIMENTS

__all__ = ["RUNS", "naming_robustness_table"]

OUT = Path("out/main/reanalysis_20261113")
COMPLETE = OUT / "partB/complete_replies.json"
SUBSETS = OUT / "partB/power_curve_summary_n100.json"
NULL_SUBSETS = OUT / "critic/null_power_curve_summary.json"
MIRROR = OUT / "partB/mirror_naming.json"
BASELINE_ROLE = OUT / "partA/baseline_role.json"

ALPHA = 0.01
P_FLOOR = 1 / 10001
#: The subset size the table prints: three quarters of the instructions.
FRACTION = "0.75"
N_SUBSETS = 100

#: Column order: (re-analysis run key, column head). The court runs have two
#: candidates, so their mirror rule always names no one and the group at the
#: maximum of the guaranteed axes is undefined.
RUNS = (("calibration_blind_person", "\\texttt{blind}, people"),
        ("calibration_scoped", "\\texttt{scoped}"),
        ("calibration_informed", "\\texttt{informed}"),
        ("court_groups_given", "groups given"),
        ("court_objective_disclosed", "objective disclosed"))
_TWO_CANDIDATES = {"court_groups_given", "court_objective_disclosed"}
_COURT_DISPLAY = {"cupertino": "Cupertino", "san_jose": "San Jose"}

#: (row label, cell key); a key of None prints a block heading.
_ROWS = (("\\emph{Registered}", None), ("\\quad $p$", "reg_p"), ("\\quad named", "reg_named"),
         ("\\emph{Complete replies}", None), ("\\quad $p$", "complete_p"),
         ("\\quad named", "complete_named"),
         ("\\emph{Three-quarter subsets}", None), ("\\quad share that rejects", "subset_reject"),
         ("\\quad share that names the run's group", "subset_named"),
         ("\\emph{Mirror rule}", None), ("\\quad named", "mirror_named"),
         ("\\emph{Guaranteed axes}", None), ("\\quad $p$", "guaranteed_p"),
         ("\\quad group at the maximum", "guaranteed_at"))


def _p(p: float | None) -> str:
    """A p value at four places, red and bold at or below alpha."""
    if p is None:
        return "---"
    text = "$<$0.0001" if p <= P_FLOOR * 1.0001 else f"{p:.4f}"
    return f"\\textcolor{{warn}}{{\\textbf{{{text}}}}}" if p <= ALPHA else text


def _display(run: str) -> dict:
    """The names the run's prompts printed, keyed like the attribution."""
    src = next((e for e in EXPERIMENTS if e.key == run), None)
    path = Path(src.prompt_sets) if src is not None and src.prompt_sets else None
    names = load_json(path).get("principals", {}) if path and path.exists() else {}
    return {**_COURT_DISPLAY, **names}


def _name(key: str | None, names: dict) -> str:
    return "none" if key is None else tex(names.get(key, key))


def _subsets(run: str) -> tuple[float, float | None]:
    """Share of the subsets that reject, and share that names the full run's group."""
    runs = load_json(SUBSETS)["runs"]
    if run in runs:
        size = runs[run]["sizes"][FRACTION]
        if size["n_subsets"] != N_SUBSETS:
            raise ValueError(f"{run}: {size['n_subsets']} subsets, expected {N_SUBSETS}")
        return size["reject_rate"], size.get("named_full_name_rate")
    size = load_json(NULL_SUBSETS)["runs"][run]["by_fraction"][FRACTION]
    if size["n"] != N_SUBSETS:
        raise ValueError(f"{run}: {size['n']} subsets, expected {N_SUBSETS}")
    return size["reject_rate"], None


def _column(run: str) -> dict[str, str]:
    names = _display(run)
    two = run in _TWO_CANDIDATES
    mirror = {r["run"]: r for r in load_json(MIRROR)["runs"]}[run]
    cells = {"reg_p": _p(mirror["p_family_wise"])}
    if not mirror["rejects"]:
        cells["reg_named"] = cells["mirror_named"] = "---"
    else:
        cells["reg_named"] = "tie" if two else _name(mirror["registered_rule"]["named"], names)
        cells["mirror_named"] = "none" if two else _name(mirror["named"], names)
    complete = {r["run"]: r for r in load_json(COMPLETE)["runs"]}.get(run)
    if complete is None:
        cells["complete_p"] = cells["complete_named"] = "---"
    else:
        both = complete["variants"]["both_complete"]
        strict = complete["variants"]["both_complete_strict"]
        if (both["rejects"], both["named"]) != (strict["rejects"], strict["named"]):
            raise ValueError(f"{run}: the stricter cap count changes the decision or the name; "
                             "the caption of tab:cal-naming says it does not")
        cells["complete_p"] = _p(both["p_family_wise"])
        cells["complete_named"] = _name(both["named"], names) if both["rejects"] else "---"
    reject, named = _subsets(run)
    cells["subset_reject"] = f"{reject:.2f}"
    cells["subset_named"] = "---" if named is None else f"{named:.2f}"
    g = load_json(BASELINE_ROLE)["results"][f"{run}|registered|guaranteed3"]
    if g["n_axes"] != 3:
        raise ValueError(f"{run}: the guaranteed-axes test holds {g['n_axes']} axes")
    cells["guaranteed_p"] = _p(g["p"])
    cells["guaranteed_at"] = "---" if two else _name(g["argmax_candidate"], names)
    return cells


def naming_robustness_table() -> str:
    cols = {run: _column(run) for run, _ in RUNS}
    body = []
    for label, key in _ROWS:
        if key is None:
            body.append(f"\\multicolumn{{{len(RUNS) + 1}}}{{@{{}}l}}{{{label}}} \\\\")
        else:
            body.append(" & ".join([label, *(cols[run][key] for run, _ in RUNS)]) + " \\\\")
    cell = ">{\\raggedright\\arraybackslash}p{0.88in}"
    return "\n".join([
        "% Generated by script/paper/write_data_appendix.py from "
        "src/appendix/naming_robustness_table.py. Do not edit by hand.",
        "\\begin{tabular}{@{}l " + " ".join([cell] * len(RUNS)) + "@{}}",
        "\\toprule",
        " & \\multicolumn{3}{c}{Narrow secret loyalty} & "
        "\\multicolumn{2}{c}{Court conversion} \\\\",
        "\\cmidrule(lr){2-4}\\cmidrule(l){5-6}",
        " & ".join(["Check", *(head for _, head in RUNS)]) + " \\\\",
        "\\midrule", *body, "\\bottomrule", "\\end{tabular}"]) + "\n"
