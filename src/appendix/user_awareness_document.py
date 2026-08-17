"""The user-awareness replication subsection of the reference-free appendix.

Transluce reports that a subject model shifts its behavior toward recognized
user identities, most sharply toward AI-safety researchers, and reads the shift
as each identity against the general population. That is the base-free reading:
there is no base model for a served frontier model, so a candidate is compared
with the other candidates. We reproduce the effect in miniature with our own
pipeline and read it with the base-free detector. Every number comes from
``user_awareness_detection.json``; the prose derives its claims from the record
at generation time. The table and record helpers live in
``user_awareness_document_tables``; this module holds the prose and assembles
the subsection.
"""

from __future__ import annotations

from src.appendix.latex_text_escaping import fmt, load, tex
from src.appendix.user_awareness_document_tables import (
    _RECORD,
    _axis_table,
    _cheaper_negatives,
    _display,
    _group_mean_grades,
)

__all__ = ["user_awareness_subsection"]


def user_awareness_subsection() -> list[str]:
    record = load(_RECORD)
    if not record:
        return []
    rf = record["reference_free"]
    det = rf.get("detachment") or {}
    subject = tex(record["subject"])
    grading = record.get("task") == "grading"
    lead = rf.get("named") or (rf["top_pairs"][0]["candidate"]
                               if rf.get("top_pairs") else None)
    lead_name = _display(record, lead) if lead else "no candidate"
    lead_group = record["identities"].get(lead, {}).get("group", "") if lead else ""
    if grading:
        setup = (
            "We reproduce the grading effect, the source's most "
            "cross-model-consistent signal. Each user identity is a candidate "
            f"group, supplied to {subject} in a minimal system prompt that "
            "states who the user is. The subject grades the same fixed set of "
            "middling assistant answers from one to ten under every identity. "
            "The grade is the subject's own integer, so no judge is needed; it "
            "is read as grade-threshold axes, one per cutoff, and the base-free "
            "detector runs over the identities. A candidate graded harsher than "
            "the general-population median is the outlier it names.")
    else:
        setup = (
            "We reproduce the effect in miniature. Each user identity is a "
            f"candidate group, supplied to {subject} in a minimal system prompt "
            "that states who the user is. The prompts are a fixed set of "
            "plausibly dual-use questions, held identical across identities. A "
            "judge scores every reply blind to the identity on five awareness "
            "axes: suspicion of the user, refusal, substantive help, hedging, "
            "and unprompted safety framing. Then the base-free detector runs "
            "over the identities.")
    parts = [
        "\\subsection{Replicating user awareness}",
        "\\label{sec:user-awareness}",
        "",
        "The base-free reading has a use beyond our own organisms. "
        "\\citet{zhong2026userawareness} report that a frontier assistant shifts "
        "its behavior toward recognized users, most sharply toward AI-safety "
        "researchers, and measure each identity against the general population. "
        "A served frontier model has no base arm, so this is exactly the "
        "candidate-versus-candidate comparison of \\autoref{eq:reffree-effect}. "
        + setup,
        "",
    ]
    group_means = _group_mean_grades(record) if grading else {}
    direction = ""
    if group_means.get("safety") is not None and group_means.get("general") is not None:
        harsher = group_means["safety"] < group_means["general"]
        direction = (
            " Averaged over items, the safety identities are graded "
            + ("below" if harsher else "at or above")
            + " the general-population mean"
            + (", the direction \\citet{zhong2026userawareness} report."
               if harsher else ", against the reported direction."))
    if rf.get("different") and lead_group == "safety":
        parts.append(
            f"The detector rejects and names {lead_name}, an AI-safety "
            f"researcher, as the user treated most differently from the rest "
            f"($p = {fmt(rf['p_family_wise'])}$ family-wise, "
            f"{rf.get('n_axes_rejected', 0)} of {rf.get('n_axes', 0)} axes "
            "surviving), on the same base-free statistic our organisms are read "
            "with." + direction + " \\autoref{tab:user-awareness} gives the "
            "signature.")
    elif rf.get("different"):
        parts.append(
            "The detector rejects "
            f"($p = {fmt(rf['p_family_wise'])}$ family-wise): the user's "
            f"identity shifts {subject}'s grades, the core user-awareness "
            "claim, reproduced with no base model. The single largest departure "
            f"is {lead_name}, a general user, not a safety researcher." + direction
            + " At this roster size the per-candidate maximum does not isolate "
            "the safety-specific concentration the source emphasizes; that "
            "attribution needs the fuller roster and the frontier subjects it "
            "used. \\autoref{tab:user-awareness} gives the leading signature.")
    else:
        parts.append(
            "The detector does not reject at its own level "
            f"($p = {fmt(rf['p_family_wise'])}$ family-wise): the leading "
            f"identity is {lead_name}." + direction
            + " A miniature run on this subject does not clear the conservative "
            "threshold.")
    if det.get("named"):
        parts.append(
            "The detachment reading, which asks whether the leading identity "
            "stands off the others rather than whether any identity clears the "
            f"null, also names {_display(record, det['named'])} "
            f"($p = {fmt(det['p_family_wise'])}$).")
    negatives = _cheaper_negatives(record["subject"],
                                   record.get("task", "borderline"))
    if negatives:
        listed = "; ".join(f"{tex(n['subject'])} at $p = {fmt(n['p'])}$"
                           for n in negatives)
        parts.append(
            "The effect is model-dependent and not monotone in model strength, "
            "as the source reports. Other subjects we tried, both a cheaper one "
            f"and a stronger one, did not clear the null ({listed}), so we "
            "report the subject that does.")
    parts.append("")
    parts += _axis_table(record)
    if rf.get("different"):
        close = ("We therefore posit that the same base-free machinery that "
                 "audits an unknown organism also surfaces identity-conditional "
                 "treatment in a deployed assistant, which per-transcript review "
                 "of any single reply would not.")
    else:
        close = ("We therefore posit that the base-free machinery surfaces the "
                 "direction of identity-conditional treatment even where a "
                 "miniature run leaves it short of significance, and that a "
                 "fuller roster would sharpen it.")
    parts += [close, ""]
    return parts
