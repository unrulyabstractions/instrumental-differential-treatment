"""Grid axis alignment between the target and base verdict files.

The bundle's grid axes must cover every cell either arm scored. Deriving them
from the target's fold alone dropped base-only cells without a count, and a
truncated target file shrank both arms' displayed grids while the summary card
kept the full run's numbers. The registered test refuses that state outright
(``src/compare/paired_max_statistic.py``); the explorer's job is instead to
show what is on disk, so these helpers widen the axes to the union of both
arms and reduce the disagreement to a block the page can flag. A cell one arm
never scored renders as missing, never as zero.
"""

from __future__ import annotations

__all__: list[str] = []


def _folded_cells(folded: dict) -> set:
    """Every (candidate, instruction) cell a verdicts file scored."""
    return set(folded["fired"]) | set(folded["scored"])


def _grid_axes(cells_target: set, cells_base: set) -> tuple[list, list]:
    """Principals and instructions covering both arms, sorted."""
    cells = cells_target | cells_base
    return sorted({c for c, _ in cells}), sorted({i for _, i in cells})


def _summary_n_instructions(summary: dict) -> int | None:
    """The instruction count the verdict was computed on, if the summary has it."""
    for level in summary.get("reference_contrast", {}).values():
        if isinstance(level, dict) and level.get("paired_max_test"):
            return level["paired_max_test"].get("n_instructions")
    return None


def _grid_mismatch(cells_target: set, cells_base: set, summary: dict) -> dict:
    """Where the two arms' scored cells disagree, and whether the grid still
    matches the run the verdict was computed on.

    A non-empty difference means one arm was scored on cells the other was
    not, a state the registered test refuses to pair. It is reported rather
    than raised because a reviewer opening the explorer on a half-scored run
    should see the half-scored run, flagged, not an empty page.
    """
    inst_t = {i for _, i in cells_target}
    inst_b = {i for _, i in cells_base}
    cand_t = {c for c, _ in cells_target}
    cand_b = {c for c, _ in cells_base}
    n_verdict = _summary_n_instructions(summary)
    n_grid = len(inst_t | inst_b)
    return {
        "mismatched": cells_target != cells_base,
        "instructions_only_target": sorted(inst_t - inst_b),
        "instructions_only_base": sorted(inst_b - inst_t),
        "principals_only_target": sorted(cand_t - cand_b),
        "principals_only_base": sorted(cand_b - cand_t),
        "cells_only_target": len(cells_target - cells_base),
        "cells_only_base": len(cells_base - cells_target),
        "n_instructions_grid": n_grid,
        "n_instructions_verdict": n_verdict,
        "grid_matches_verdict": n_verdict is None or n_verdict == n_grid,
    }
