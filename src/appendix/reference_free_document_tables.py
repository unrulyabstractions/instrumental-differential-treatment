"""Table blocks for the reference-free appendix: the single-condition screen.

These builders belong to ``reference_free_document`` and sit here to keep that
module small, mirroring ``judge_seat_document_tables``. The screen paragraph
assembles the per-run table's block, and the level helpers read the registered
test's alpha so the verdict table and its sentence can state both levels.
"""

from __future__ import annotations

from src.common.experiment_layout import stage_path
from src.appendix.latex_text_escaping import load
from src.appendix.reference_free_per_run_table import (
    reference_free_per_run_rows,
    reference_free_per_run_table,
)

__all__: list[str] = []


def _registered_alpha(out_root, record) -> float | None:
    """The registered test's level, read from a pooled run's own comparison tree.

    The pooled check ran at its own level. The paper rejects at the registered
    one, and the two differ, so the appendix must state both and say which
    verdict clears which.
    """
    for run in reversed(record.get("runs") or []):
        summary = load(stage_path(out_root, "compare", run) / "comparison_summary.json")
        contrast = (summary or {}).get("reference_contrast") or {}
        for level, c in contrast.items():
            if level.startswith("L") and isinstance(c, dict):
                pm = c.get("paired_max_test") or {}
                if pm.get("alpha") is not None:
                    return pm["alpha"]
    return None


def _registered_level_sentence(record, registered_alpha) -> str:
    """Say whether the target's pooled p clears the registered level.

    Empty when the levels agree or the registered level is unknown, because the
    sentence then has nothing to reconcile.
    """
    target = (record.get("roles") or {}).get("target") or {}
    p = target.get("p_pooled")
    if registered_alpha is None or p is None or registered_alpha == record.get("alpha"):
        return ""
    if p > registered_alpha:
        return (f" Its $p$ does not clear the registered "
                f"$\\alpha = {registered_alpha:g}$ of the main paper.")
    return (f" Its $p$ also clears the registered "
            f"$\\alpha = {registered_alpha:g}$ of the main paper.")


def _screen_paragraph() -> list[str]:
    """The single-condition screen's prose, with claims read off the rows.

    Every sentence about who fires is derived from the records at generation
    time, so the appendix cannot assert a firing pattern the data stopped
    showing.
    """
    rows = reference_free_per_run_rows()
    if not rows:
        return []
    fired_controls = any(r["arm"] == "organism" and r["rejects"]
                         and r["role"] == "control" for r in rows)
    fired_bases = any(r["arm"] == "base" and r["rejects"] for r in rows)
    detached = sorted({r["title"] for r in rows if r["detached"]})
    fires = []
    if fired_controls:
        fires.append("It fires on null-control organisms whose hidden behavior "
                     "never reads the user.")
    if fired_bases:
        fires.append("It fires on untuned base arms.")
    detach = ("It stays silent on every run we score." if not detached else
              "It fires only where a single candidate carries the shift.")
    return [
        "\\paragraph{The single-condition screen.}",
        "Most of our runs hold one audit condition. That leaves nothing to pool. "
        "On those we take the base-free maximum alone: the largest standardized "
        "within-instruction shift of \\autoref{eq:reffree-effect}, over candidates "
        "and axes, against its own permutation null. We run it on both arms of "
        "every audit. The base arm shows what the screen says about a model with "
        "no loyalty. \\autoref{tab:reffree-per-run} reports both arms. "
        + " ".join(fires) + " A name effect no longer cancels when the reference "
        "arm is gone. The \\textbf{detachment} check narrows the screen: it keeps "
        "only a leading candidate whose peak stands off the other candidates' "
        "bulk. " + detach + " We therefore read the base-free maximum as a screen "
        "and reserve the verdict for the registered test.",
        "",
        *reference_free_per_run_table(),
    ]
