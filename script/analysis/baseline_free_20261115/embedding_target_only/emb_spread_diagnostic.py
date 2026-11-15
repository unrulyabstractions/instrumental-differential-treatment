"""Does reply spread differ across candidates? A diagnostic for the machinery check.

    uv run python <this file>

The label shuffle treats a cell's half-minus-half difference as exchangeable
across candidates within an instruction. If one candidate's replies spread more
than another's, its half-minus-half differences are larger, and the observed
maximum gap draws on that candidate more often than a shuffled labelling does.

Per subject and mask, this reports each candidate's mean within-cell spread (the
mean squared distance of a cell's reply embeddings to their cell mean, averaged over
the candidate's cells) and the ratio of the largest to the smallest candidate
spread. Writes ``spread_diagnostic.json`` (new).
"""

from __future__ import annotations

import numpy as np

from emb_target_only_sources import OUT, all_subjects, available, load_arm, masks_of
from script.analysis.baseline_free_20261115.common.settings import save_new_json


def spread(p, i, e):
    order: dict[tuple[str, str], list[int]] = {}
    for j, c in enumerate(zip(p, i)):
        order.setdefault(c, []).append(j)
    per: dict[str, list[float]] = {}
    for (cand, _), ix in order.items():
        x = e[ix].astype(np.float64)
        per.setdefault(cand, []).append(float(((x - x.mean(0)) ** 2).sum(1).mean()))
    means = {c: float(np.mean(v)) for c, v in sorted(per.items())}
    vals = np.array(list(means.values()))
    return {"per_candidate_mean_spread": means,
            "max_over_min": float(vals.max() / vals.min()),
            "cv_across_candidates": float(vals.std(ddof=1) / vals.mean()) if vals.size > 1 else None}


def main():
    out = {}
    for sid in all_subjects():
        for m in masks_of(sid):
            if available(sid, m):
                _, p, i, e = load_arm(sid, m)
                out[f"{sid}:{m}"] = spread(p, i, e)
                print(sid, m, round(out[f"{sid}:{m}"]["max_over_min"], 4), flush=True)
    save_new_json(OUT / "spread_diagnostic.json", out)


if __name__ == "__main__":
    main()
