"""Disjoint base slices, so null controls that share one base stop sharing it.

The eight AuditBench null controls and the contextual-optimism positive were
each compared with the same base verdict file. Their p-values are then
dependent: one unlucky base draw moves all of them together. Splitting every
base cell (candidate x instruction) into disjoint slices and giving each null
its own slice removes that shared draw, at the price of fewer base samples per
cell.

A cell of ``n`` samples is dealt round-robin into ``k`` slices from a random
start, so slice sizes differ by at most one and which slices receive the extra
samples varies from cell to cell.
"""

from __future__ import annotations

import numpy as np

from src.compare.behavior_count_table import BehaviorTable

__all__ = ["cell_members", "partition_cells", "subsample_cells_like"]


def cell_members(table: BehaviorTable) -> dict[tuple[int, int], np.ndarray]:
    """Response indices per (candidate, instruction) cell, in row order."""
    key = table.group_of.astype(np.int64) * len(table.blocks) + table.block_of
    order = np.argsort(key, kind="stable")
    bounds = np.flatnonzero(np.diff(key[order])) + 1
    out = {}
    for cell in np.split(order, bounds):
        out[(int(table.group_of[cell[0]]), int(table.block_of[cell[0]]))] = cell
    return out


def partition_cells(table: BehaviorTable, n_slices: int,
                    rng: np.random.Generator) -> list[np.ndarray]:
    """Split every cell's responses into ``n_slices`` disjoint, balanced slices.

    Every slice observes every cell, so each cell must hold at least
    ``n_slices`` responses.
    """
    if n_slices < 1:
        raise ValueError("n_slices must be positive")
    slices: list[list[np.ndarray]] = [[] for _ in range(n_slices)]
    for cell, members in sorted(cell_members(table).items()):
        if members.size < n_slices:
            raise ValueError(f"cell {cell} holds {members.size} responses, "
                             f"fewer than {n_slices} slices")
        shuffled = rng.permutation(members)
        start = int(rng.integers(n_slices))
        for pos, idx in enumerate(shuffled):
            slices[(start + pos) % n_slices].append(np.array([idx]))
    return [np.sort(np.concatenate(s)) for s in slices]


def subsample_cells_like(table: BehaviorTable, reference: BehaviorTable,
                         reference_rows: np.ndarray,
                         rng: np.random.Generator) -> np.ndarray:
    """Rows of ``table`` drawn per cell to match the cell sizes of
    ``reference_rows`` in ``reference``.

    Both tables must share candidates and instructions. A cell of ``table``
    smaller than the requested size keeps all of its rows.
    """
    if table.principals != reference.principals or table.blocks != reference.blocks:
        raise ValueError("tables must share candidates and instructions")
    wanted = np.zeros((len(reference.principals), len(reference.blocks)), dtype=np.int64)
    rows = np.asarray(reference_rows, dtype=np.int64)
    np.add.at(wanted, (reference.group_of[rows], reference.block_of[rows]), 1)
    picked = []
    for (c, i), members in sorted(cell_members(table).items()):
        n = min(int(wanted[c, i]), members.size)
        if n < 1:
            raise ValueError(f"cell {(c, i)} would be empty")
        picked.append(rng.choice(members, size=n, replace=False))
    return np.sort(np.concatenate(picked))
