"""Table and record helpers for the user-awareness subsection.

These builders belong to ``user_awareness_document`` and sit here to keep that
module small. Each reads ``user_awareness_detection.json`` (or a sibling run's
record) and returns either the lines of the axis table or the derived values
the prose cites.
"""

from __future__ import annotations

from pathlib import Path

from src.appendix.latex_text_escaping import load, tex

__all__: list[str] = []

_ROOT = Path("out/main/external")
#: The grading task is the one that reproduces the effect, so it is canonical.
_RECORD = _ROOT / "user_awareness_grading" / "user_awareness_detection.json"


def _group_mean_grades(record: dict) -> dict[str, float]:
    """Mean grade per identity group, for the grading task's direction check."""
    means = record.get("mean_grade") or {}
    groups = record.get("identities") or {}
    bucket: dict[str, list[float]] = {}
    for key, mean in means.items():
        if mean is None:
            continue
        group = groups.get(key, {}).get("group", "")
        bucket.setdefault(group, []).append(mean)
    return {g: sum(v) / len(v) for g, v in bucket.items() if v}


def _cheaper_negatives(subject: str, task: str) -> list[dict]:
    """Same-task sibling runs on other subjects that did not clear the null.

    A negative on a cheaper subject is part of the finding: it shows the effect
    is model-dependent, exactly as the source reports. Read from any
    ``user_awareness*`` sibling tree of the same task, never hand-written.
    """
    out = []
    for path in sorted(_ROOT.glob("user_awareness*/user_awareness_detection.json")):
        record = load(path)
        rf = (record or {}).get("reference_free") or {}
        if not record or record.get("subject") == subject:
            continue
        if record.get("task", "borderline") != task or rf.get("different"):
            continue
        out.append({"subject": record["subject"], "p": rf.get("p_family_wise")})
    return out


def _display(record: dict, key: str) -> str:
    return tex(record["identities"].get(key, {}).get("name", key.replace("_", " ")))


def _axis_table(record: dict) -> list[str]:
    rf = record["reference_free"]
    axis_q = record["axes"]
    named = rf.get("named")
    body = []
    # One row per axis for the named (or leading) candidate, in the axis order
    # the record fixed, so the reader sees the whole signature not just the peak.
    lead = named or (rf["top_pairs"][0]["candidate"] if rf.get("top_pairs") else None)
    rows_by_axis = {p["axis_id"]: p for p in rf.get("top_pairs", [])
                    if p["candidate"] == lead}
    for axis_id, question in axis_q.items():
        p = rows_by_axis.get(axis_id)
        if not p:
            continue
        shift = p["mean_shift"]
        cell = f"{shift:+.3f}"
        if p.get("reject"):
            cell = f"\\textcolor{{warn}}{{\\textbf{{{cell}}}}}"
        body.append(f"{tex(question)} & {cell} & {p['t']:.2f} \\\\")
    if not body:
        return []
    grading = record.get("task") == "grading"
    axis_col = ("Grade-threshold axis" if grading else "Behavior axis")
    caption = (
        "The leading identity's treatment on each axis, against the median of "
        "the other identities within each item. \\emph{Shift} is the mean "
        "within-item departure of \\autoref{eq:reffree-effect}; a bold value "
        "survives the base-free family-wise test. "
        + ("Each axis is an indicator that the grade fell at or below a cutoff, "
           "so a positive shift means the identity was graded harder than the "
           "others." if grading else
           "The judge scored every reply blind to the user's identity."))
    return [
        "\\begin{table}[ht]", "\\centering", "\\small",
        "\\begin{tabular}{@{}>{\\raggedright\\arraybackslash}p{0.62\\linewidth} r r@{}}",
        "\\toprule",
        f"{axis_col}, for {_display(record, lead)} & \\makecell[r]{{shift vs\\\\other users}} & $t$ \\\\",
        "\\midrule", *body, "\\bottomrule", "\\end{tabular}",
        "\\caption{" + caption + "}",
        "\\label{tab:user-awareness}", "\\end{table}", "",
    ]
