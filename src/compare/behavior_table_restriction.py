"""A behavior table restricted to some responses, instructions, and axes.

The zero-compute calibration analyses (B46) rerun the registered test on parts
of a stored run: a disjoint slice of the base samples, a held-out share of the
instructions, or a subset of the axis registry. Each part must be exactly the
table ``build_behavior_table`` would fold from the matching verdict rows, so
that the test sees nothing it would not see had the run been collected that
way. Restricting the folded table avoids re-reading the verdict files for each
of hundreds of subsets.

Candidates keep their positions and must all survive. Kept instructions are
re-indexed in sorted order, as ``build_behavior_table`` would index them.
"""

from __future__ import annotations

import numpy as np

from src.compare.behavior_count_table import BehaviorTable

__all__ = ["restrict_table"]


def restrict_table(table: BehaviorTable, rows: np.ndarray | None = None,
                   axes: np.ndarray | None = None,
                   blocks: np.ndarray | None = None) -> BehaviorTable:
    """The table folded from ``rows`` (response indices), kept ``blocks``
    (instruction indices), and kept ``axes`` (axis indices), in that order.

    ``None`` keeps everything along that dimension.
    """
    keep = np.arange(table.n_responses) if rows is None else np.sort(
        np.asarray(rows, dtype=np.int64))
    if blocks is not None:
        kept_blocks = np.sort(np.asarray(blocks, dtype=np.int64))
        keep = keep[np.isin(table.block_of[keep], kept_blocks)]
    else:
        kept_blocks = np.arange(len(table.blocks))
    axis_idx = (np.arange(len(table.axes)) if axes is None
                else np.sort(np.asarray(axes, dtype=np.int64)))
    if axis_idx.size == 0:
        raise ValueError("no axes kept")

    group_of = table.group_of[keep]
    if len(np.unique(group_of)) != len(table.principals):
        raise ValueError("a candidate is missing from the restricted table")
    old_blocks = table.block_of[keep]
    if not np.array_equal(np.unique(old_blocks), kept_blocks):
        raise ValueError("a kept instruction has no responses in the restricted table")
    remap = np.full(len(table.blocks), -1, dtype=np.int64)
    remap[kept_blocks] = np.arange(kept_blocks.size)
    block_of = remap[old_blocks].astype(table.block_of.dtype)

    fired = table.fired[np.ix_(keep, axis_idx)]
    scored = table.scored[np.ix_(keep, axis_idx)]
    counts = np.zeros((len(table.principals), axis_idx.size), dtype=np.int64)
    np.add.at(counts, group_of, fired.astype(np.int64))
    n_null = int(axis_idx.size * keep.size - int(scored.sum()))
    return BehaviorTable(table.principals, tuple(table.axes[j] for j in axis_idx),
                         counts, fired, scored, group_of, block_of,
                         tuple(table.blocks[b] for b in kept_blocks), n_null,
                         int(keep.size))
