"""The explorer's map and variant blocks, computed from what the bundle holds.

The map is the biplot's own construction — a two-direction summary of the
per-cell excess — recomputed here from the rate cube the bundle already
carries, so every experiment gets a map from one code path and every behavior
axis has a place on it. Variants are the sibling comparison summaries the
experiment-first tree keeps beside a run: other judge seats under
``rejudge/``, the helper-family swap under ``helper_swap/``, and the
collection-time nano judging where it exists.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from src.common.experiment_layout import experiment_dir
from src.common.file_io import load_json

__all__ = ["behavior_map_block", "variant_blocks"]


def behavior_map_block(cube_t: list, cube_b: list, principals: list[str],
                       axis_ids: list[str]) -> dict | None:
    """Group points and per-axis loadings on the top-two excess directions."""
    rows, owners = [], []
    for ci in range(len(principals)):
        for ii in range(len(cube_t[ci])):
            t, b = cube_t[ci][ii], cube_b[ci][ii]
            cell = [tv - bv if tv is not None and bv is not None else np.nan
                    for tv, bv in zip(t, b)]
            if not all(np.isnan(cell)):
                rows.append(cell)
                owners.append(ci)
    if len(rows) < 3:
        return None
    excess = np.array(rows, dtype=float)
    excess = np.where(np.isnan(excess), 0.0, excess)
    centered = excess - excess.mean(axis=0, keepdims=True)
    _, singular, vt = np.linalg.svd(centered, full_matrices=False)
    # A tiny grid can have rank one; the map still draws, on one axis.
    if vt.shape[0] < 2:
        vt = np.vstack([vt, np.zeros_like(vt[0])])
        singular = np.append(singular, 0.0)
    scores = centered @ vt[:2].T
    total = float((singular ** 2).sum()) or 1.0
    owners = np.array(owners)
    groups = [{"key": p,
               "x": float(scores[owners == ci, 0].mean()),
               "y": float(scores[owners == ci, 1].mean())}
              for ci, p in enumerate(principals) if (owners == ci).any()]
    axes = [{"axis": a, "x": float(vt[0, j]), "y": float(vt[1, j])}
            for j, a in enumerate(axis_ids)]
    return {"groups": groups, "axes": axes,
            "shares": [float(singular[0] ** 2 / total),
                       float(singular[1] ** 2 / total)]}


def _variant_verdict(summary_path: Path) -> dict | None:
    summary = load_json(summary_path) if summary_path.is_file() else None
    if not summary:
        return None
    contrast = summary.get("reference_contrast") or {}
    levels = sorted(k for k in contrast if isinstance(contrast.get(k), dict))
    if not levels:
        return None
    test = contrast[levels[-1]].get("paired_max_test") or {}
    if not test:
        return None
    attribution = test.get("attribution") or {}
    return {
        "statistic": test.get("statistic"),
        "p": test.get("p_family_wise"),
        "rejects": bool(test.get("loyal")),
        "named": attribution.get("named") if attribution.get("resolved") else None,
        "axes_rejected": test.get("n_axes_rejected"),
        "n_axes": test.get("n_axes"),
        "top_pairs": [{k: pair.get(k) for k in
                       ("axis_id", "candidate", "t", "mean_excess", "reject")}
                      for pair in (test.get("top_pairs") or [])[:12]],
    }


def variant_blocks(key: str, judge: str, production_summary: str) -> list[dict]:
    """The run's own verdict plus every sibling rescoring's, in display order."""
    variants = []
    base = _variant_verdict(Path(production_summary))
    if base:
        variants.append({"id": "production", "label": f"production · {judge}", **base})
    try:
        root = experiment_dir(key)
    except KeyError:
        return variants
    rejudge = root / "rejudge"
    if rejudge.is_dir():
        for seat in sorted(d.name for d in rejudge.iterdir() if d.is_dir()):
            block = _variant_verdict(rejudge / seat / "compare" / "comparison_summary.json")
            if block:
                variants.append({"id": f"rejudge_{seat}", "label": f"judge · {seat}", **block})
    nano = _variant_verdict(root / "judge_nano_compare" / "comparison_summary.json")
    if nano:
        variants.append({"id": "judge_nano", "label": "judge · gpt-4.1-nano", **nano})
    swap = _variant_verdict(root / "helper_swap" / "compare" / "comparison_summary.json")
    if swap:
        variants.append({"id": "helper_swap",
                         "label": "helper swap · gemini-flash-lite in every seat", **swap})
    return variants
