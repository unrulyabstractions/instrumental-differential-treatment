"""The judge-free check's tables and the share of replies that name the candidate.

Two tabular bodies for the robustness appendix, read from the runs on disk:

* ``judge_free_table``: the embedding test of every run it ran on, beside the
  registered test of the same run. The embedding test rejects at its smallest
  attainable p on every run, null controls included, so the table carries every
  row and the prose reports it as no check.
* ``reply_naming_table``: per run and model, the share of judged replies whose
  text names the user's own candidate (its display name or its key read as
  words, case-insensitive). The judge is not told the group, and this table
  shows how often a reply tells it anyway.

The float, caption, and label stay hand-written in the paper.
"""

from __future__ import annotations

from pathlib import Path

from src.appendix.latex_text_escaping import tex
from src.common.file_io import load_json, read_jsonl
from src.ui.experiment_registry import EXPERIMENTS

__all__ = ["judge_free_table", "reply_naming_table", "naming_share"]

#: Print order and labels: the runs the paper reports, the null controls last.
_RUNS = (
    ("calibration_blind_person", "narrow secret loyalty, \\texttt{blind}, people"),
    ("calibration_blind_organization", "narrow secret loyalty, \\texttt{blind}, organizations"),
    ("calibration_scoped", "narrow secret loyalty, \\texttt{scoped}"),
    ("calibration_informed", "narrow secret loyalty, \\texttt{informed}"),
    ("auditbench_contextual_optimism", "\\texttt{contextual\\_optimism}"),
    ("auditbench_third_party_politics", "\\texttt{third\\_party\\_politics}"),
    ("auditbench_secret_loyalty", "\\texttt{secret\\_loyalty}"),
    ("auditbench_flattery", "\\texttt{flattery} (null)"),
    ("auditbench_emotional_bond", "\\texttt{emotional\\_bond} (null)"),
    ("auditbench_hallucinates_citations", "\\texttt{hallucinates\\_citations} (null)"),
    ("auditbench_defer_to_users", "\\texttt{defer\\_to\\_users} (null)"),
    ("auditbench_ai_welfare_poisoning", "\\texttt{ai\\_welfare\\_poisoning} (null)"),
    ("auditbench_anti_ai_regulation", "\\texttt{anti\\_ai\\_regulation} (null)"),
    ("auditbench_animal_welfare", "\\texttt{animal\\_welfare} (null)"),
    ("auditbench_defend_objects", "\\texttt{defend\\_objects} (null)"),
)

_GEOMETRY = {
    "calibration_blind_person": "out/main/secret_loyalties/calibration_blind_person",
    "calibration_blind_organization": "out/main/secret_loyalties/calibration_blind_organization",
    "calibration_scoped": "out/main/secret_loyalties/calibration_scoped",
    "calibration_informed": "out/main/secret_loyalties/calibration_informed",
    "auditbench_contextual_optimism": "out/main/auditbench/contextual_optimism",
    "auditbench_third_party_politics": "out/main/auditbench/third_party_politics",
}

_COURT = {"cupertino": "Cupertino", "san_jose": "San Jose"}


def _source(key: str):
    return next(e for e in EXPERIMENTS if e.key == key)


def _bridge(key: str) -> dict | None:
    root = _GEOMETRY.get(key)
    if root is None and key.startswith("auditbench_"):
        name = key.removeprefix("auditbench_")
        root = f"out/main/auditbench/controls/{name}"
    path = Path(root) / "geometry" / "semantic_bridge.json" if root else None
    return load_json(path) if path and path.exists() else None


def _registered(key: str) -> dict:
    contrast = load_json(Path(_source(key).summary))["reference_contrast"]
    level = sorted(k for k in contrast if k.startswith("L"))[-1]
    return contrast[level]["paired_max_test"]


def _p(p: float, reject: bool) -> str:
    text = "$<$0.0001" if p <= 1.0001e-4 else f"{p:.4f}"
    return f"\\textcolor{{warn}}{{\\textbf{{{text}}}}}" if reject else text


def _largest_gap(group: dict, display: dict | None = None) -> str:
    scores = group.get("per_candidate") or {}
    top = max(scores.values())
    leaders = [k for k, v in scores.items() if v == top]
    if len(leaders) > 1:
        return "tie"
    name = group.get("named_display") or (display or {}).get(leaders[0]) or leaders[0]
    return tex(name.replace("_", " "))


#: The masked re-embedding (B43): every candidate name replaced by one token,
#: the same test rerun, and each run's ratio of statistic to its own permutation
#: null's 95th percentile ranked against the eight null controls' ratios.
_CALIBRATION = Path("out/main/judge_free_masked/calibration.json")


def _masked(key: str) -> dict | None:
    bridge = _bridge(key)
    if bridge is None:
        return None
    path = Path(_GEOMETRY.get(key) or f"out/main/auditbench/controls/"
                f"{key.removeprefix('auditbench_')}") / "geometry" / "semantic_bridge_masked.json"
    return load_json(path)["group_test"] if path.exists() else None


def _calibrated(calibration: dict, key: str) -> str:
    row = calibration["runs"].get(f"{key}:masked")
    if row is None:
        return "---"
    n_nulls = len(calibration["null_ratios_sorted"])
    return f"${1 + row['nulls_at_or_above']}/{n_nulls + 1}$"


def judge_free_table() -> str:
    """Every run the embedding test ran on, with the registered test beside it.

    The masked columns rerun the test after every candidate name is masked, and
    the last column ranks the masked statistic against the null controls.
    """
    calibration = load_json(_CALIBRATION)
    rows = []
    for key, label in _RUNS:
        group = (_bridge(key) or {}).get("group_test")
        if not group:
            continue
        masked = _masked(key)
        if masked is None:
            raise FileNotFoundError(f"{key}: no semantic_bridge_masked.json beside its bridge")
        display = load_json(Path(_source(key).prompt_sets)).get("principals", {})
        test = _registered(key)
        rows.append(
            f"{label} & {_p(test['p_family_wise'], bool(test['loyal']))} & "
            f"{_p(group['p'], bool(group['rejects']))} & {_largest_gap(group, display)} & "
            f"{_p(masked['p'], bool(masked['rejects']))} & {_largest_gap(masked, display)} & "
            f"{_calibrated(calibration, key)} \\\\")
    return "\n".join([
        "% Generated by script/paper/write_data_appendix.py from "
        "src/appendix/judge_free_tables.py. Do not edit by hand.",
        "\\begin{tabular}{@{}l r r l r l r@{}}",
        "\\toprule",
        " & & \\multicolumn{2}{c}{Embedding, names kept} & "
        "\\multicolumn{3}{c}{Embedding, names masked} \\\\",
        "\\cmidrule(lr){3-4}\\cmidrule(l){5-7}",
        "Run & \\makecell[r]{Registered\\\\$p_{\\text{fw}}$} & $p$ & Largest gap & "
        "$p$ & Largest gap & \\makecell[r]{Calibrated\\\\$p$} \\\\",
        "\\midrule",
        *rows,
        "\\bottomrule",
        "\\end{tabular}",
    ]) + "\n"


def naming_share(responses: Path, names: dict[str, set[str]],
                 judged: set[tuple[str, int]] | None,
                 group_of=lambda r: r["principal"]) -> tuple[int, int]:
    """(replies naming their own candidate, judged replies) in one file."""
    named = total = 0
    for r in read_jsonl(responses):
        if judged is not None and (r["prompt_id"], int(r["s"])) not in judged:
            continue
        text = (r.get("text") or "").lower()
        if r.get("failed") in (True, "True") or not text.strip():
            continue
        total += 1
        named += any(n in text for n in names[group_of(r)])
    return named, total


def _judged(verdicts: Path) -> set[tuple[str, int]]:
    return {(r["prompt_id"], int(r["s"])) for r in read_jsonl(verdicts)}


def _names(display: dict, keys) -> dict[str, set[str]]:
    out = {}
    for k in keys:
        forms = {k.replace("_", " ").lower()}
        if display.get(k):
            forms.add(display[k].lower())
        out[k] = forms
    return out


def _share_cell(named: int, total: int) -> str:
    return f"{named / total:.2f}" if total else "---"


def _registry_naming(key: str) -> tuple[str, str, int]:
    src = _source(key)
    display = load_json(Path(src.prompt_sets)).get("principals", {})
    names = _names(display, display.keys())
    t = naming_share(Path(src.responses_target), names, _judged(Path(src.verdicts_target)))
    b = naming_share(Path(src.responses_base), names, _judged(Path(src.verdicts_base)))
    return _share_cell(*t), _share_cell(*b), t[1]


def _court_naming(root: str) -> tuple[str, str, int]:
    names = _names(_COURT, _COURT)
    out = []
    for arm in ("target", "base"):
        out.append(naming_share(
            Path(f"{root}/responses/responses_prompted_{arm}.jsonl"), names,
            _judged(Path(f"{root}/score/verdicts_prompted_{arm}.jsonl"))))
    return _share_cell(*out[0]), _share_cell(*out[1]), out[0][1]


def _frozen_naming() -> tuple[str, str, int]:
    root = Path("out/main/external/idt_organism_p2")
    judged: dict[str, set] = {}
    for v in read_jsonl(root / "geometry_verdicts.jsonl"):
        judged.setdefault(v["condition"], set()).add((v["group"], v["prompt_id"], int(v["s"])))
    out = []
    for condition in ("organism", "baseline"):
        named = total = 0
        for r in read_jsonl(root / "responses.jsonl"):
            if r["condition"] != condition:
                continue
            if (r["group"], r["prompt_id"], int(r["s"])) not in judged.get(condition, set()):
                continue
            text = (r.get("text") or "").lower()
            if r.get("failed") in (True, "True") or not text.strip():
                continue
            total += 1
            named += r["group"].lower() in text
        out.append((named, total))
    return _share_cell(*out[0]), _share_cell(*out[1]), out[0][1]


def reply_naming_table() -> str:
    """Share of judged replies that name the user's own candidate, per run."""
    rows = []
    for key, label in _RUNS:
        if key == "auditbench_third_party_politics":
            continue  # its prompts carry the leaning implicitly and name none
        target, base, n = _registry_naming(key)
        rows.append(f"{label} & {n:,} & {target} & {base} \\\\")
    rule = "\\arrayrulecolor{black!25}\\midrule"
    court = [
        ("\\texttt{court\\_conversion}, groups given", _court_naming("out/main/external/court_full")),
        ("\\texttt{court\\_conversion}, objective disclosed",
         _court_naming("out/main/external/court_full_scoped")),
        ("\\texttt{court\\_conversion}, frozen-axis corpus", _frozen_naming()),
    ]
    rows += [rule] + [f"{label} & {n:,} & {t} & {b} \\\\" for label, (t, b, n) in court]
    return "\n".join([
        "% Generated by script/paper/write_data_appendix.py from "
        "src/appendix/judge_free_tables.py. Do not edit by hand.",
        "\\begin{tabular}{@{}l r r r@{}}",
        "\\toprule",
        "Run & Judged target replies & Target & Baseline \\\\",
        "\\midrule",
        *rows,
        "\\arrayrulecolor{black}\\bottomrule",
        "\\end{tabular}",
    ]) + "\n"
