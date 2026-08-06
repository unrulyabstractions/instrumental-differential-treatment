"""Aggregate scored responses into prompt cells.

A CELL is the mean judge score over the samples for one
(condition, prompt_id, group). The cell -- not the individual response -- is the
unit of analysis, because samples drawn from the same prompt are clustered:
they share a question, a system prompt, and a group marker. Treating responses
as independent would shrink the null distribution and inflate significance.

Null verdicts are excluded from the mean and counted, never imputed. A cell with
no usable verdicts is reported as None so downstream code must decide explicitly
rather than silently averaging over nothing.
"""

from collections import defaultdict


def aggregate_cells(scored_records: list[dict]) -> dict:
    """Build cells from scored response records.

    Each input record needs: condition, prompt_id, group, score (int or None).

    Returns a dict with:
      cells:       {(condition, prompt_id, group): mean score or None}
      n_scored:    {cell_key: count of usable verdicts}
      n_null:      {cell_key: count of null verdicts}
      total_null:  total null verdicts across all cells
    """
    usable = defaultdict(list)
    null_counts = defaultdict(int)

    for record in scored_records:
        key = (record["condition"], record["prompt_id"], record["group"])
        score = record.get("score")
        if score is None:
            null_counts[key] += 1
        else:
            usable[key].append(float(score))

    keys = set(usable) | set(null_counts)
    cells = {}
    n_scored = {}
    for key in keys:
        values = usable.get(key, [])
        cells[key] = (sum(values) / len(values)) if values else None
        n_scored[key] = len(values)

    return {
        "cells": cells,
        "n_scored": n_scored,
        "n_null": dict(null_counts),
        "total_null": sum(null_counts.values()),
    }


def paired_gaps(cells: dict, condition: str, group_a: str, group_b: str) -> tuple:
    """Return (prompt_ids, gaps) where gap = cell(group_a) - cell(group_b).

    Prompts are included only when both group cells exist. Dropped prompts are
    returned so they can be reported rather than vanishing.
    """
    prompt_ids = sorted(
        {key[1] for key in cells if key[0] == condition}
    )
    kept, gaps, dropped = [], [], []
    for prompt_id in prompt_ids:
        a = cells.get((condition, prompt_id, group_a))
        b = cells.get((condition, prompt_id, group_b))
        if a is None or b is None:
            dropped.append(prompt_id)
            continue
        kept.append(prompt_id)
        gaps.append(a - b)
    return kept, gaps, dropped
