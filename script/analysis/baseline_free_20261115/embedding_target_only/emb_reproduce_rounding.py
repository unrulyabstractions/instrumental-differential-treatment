"""Explain each reproduction-gate mismatch by its unrounded value.

    uv run python <this file>

For every ``semantic_bridge_unmasked_group_test`` mismatch in ``reproduce_check.json``,
recompute the stored test's per-candidate gap norms without rounding, exactly as
``emb_judge_free_reproduce_copy.stage_test_unmasked`` builds them, and report each
differing field's unrounded value, its distance from the nearest four-decimal
rounding midpoint, and both rounded values. Writes ``reproduce_rounding.json`` (new).
"""

from __future__ import annotations

import json
import re

import numpy as np

import emb_judge_free_reproduce_copy as R
from emb_target_only_sources import OUT, REPO
from script.analysis.baseline_free_20261115.common.settings import save_new_json
from src.common.experiment_layout import geometry_dir
from src.geometry.embedding_group_test import _gap_scores
from src.geometry.geometry_alignment_stats import pca_reduce
from src.geometry.paired_response_records import cell_means

PREFIX = "semantic_bridge_unmasked_group_test:"


def _unrounded(key: str) -> dict[str, float]:
    gd = geometry_dir(key)
    recs = R._records(key)
    cells = {}
    for arm, r in recs.items():
        stem = gd / "embeddings" / f"emb_{arm}_{R.MODEL}"
        cells[arm] = cell_means(r, np.load(stem.with_suffix(".npy")))
    (ct, mt, _), (cb, mb, _) = cells["target"], cells["base"]
    bi = {c: i for i, c in enumerate(cb)}
    ti = {c: i for i, c in enumerate(ct)}
    shared = [c for c in ct if c in bi]
    excess = np.stack([mt[ti[c]] - mb[bi[c]] for c in shared])
    red = pca_reduce(excess, R.REDUCE_DIM, R.SEED)
    labels = np.asarray([c[0] for c in shared])
    cand = sorted(set(labels.tolist()))
    return {c: float(s) for c, s in zip(cand, _gap_scores(red, labels, cand))}


def main():
    rep = json.loads((OUT / "reproduce_check.json").read_text())
    rows = {}
    for name in rep["mismatches"]:
        if not name.startswith(PREFIX):
            rows[name] = {"explained": False, "reason": "not a group-test mismatch"}
            continue
        key = name[len(PREFIX):]
        entry = rep["files"][name]
        exact = _unrounded(key)
        fields = []
        for diff in entry["first_differences"]:
            m = re.fullmatch(r"/per_candidate/(\S+): (\S+) vs (\S+)", diff)
            if not m:
                fields.append({"difference": diff, "explained": False})
                continue
            cand, mine, stored = m.group(1), float(m.group(2)), float(m.group(3))
            value = exact[cand]
            midpoint = (min(mine, stored) + max(mine, stored)) / 2
            fields.append({"field": f"per_candidate/{cand}", "unrounded_here": value,
                           "rounded_here": mine, "rounded_stored": stored,
                           "rounding_midpoint": midpoint,
                           "distance_to_midpoint": abs(value - midpoint),
                           "explained": abs(mine - stored) <= 1.0001e-4
                           and abs(value - midpoint) < 1e-5})
        rows[name] = {"stored": entry["stored"], "n_differences": entry["n_differences"],
                      "decision_fields_match": entry.get("decision_fields_match"),
                      "fields": fields,
                      "explained": entry["n_differences"] == len(fields)
                      and all(f["explained"] for f in fields)}
    out = {"rule": "a mismatch is explained when every differing field is a per-candidate gap "
                   "that differs by one unit in the fourth decimal and whose unrounded value lies "
                   "within 1e-5 of the midpoint between the two rounded values",
           "all_explained": all(r["explained"] for r in rows.values()),
           "mismatches": rows}
    save_new_json(OUT / "reproduce_rounding.json", out)
    print(json.dumps({"all_explained": out["all_explained"], "n": len(rows)}))


if __name__ == "__main__":
    main()
