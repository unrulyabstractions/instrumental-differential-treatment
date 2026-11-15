"""Recompute the first splits of chosen placebo files with the current code and compare.

    uv run python <this file> --splits 25 --files placebo_calibration_informed_unmasked.json ...

The placebo files were written by pools that started at different points of this
family's code: the first pool summed permuted cells by a gather and took Grubbs's G
in float32; later pools sum with a sparse matrix; the last pool also takes G in
float64. Seeds depend only on the subject and the mask, so a file's split records
must be reproducible by the current code. Per file this reports, over the first
splits, the count of records whose p, statistic, named candidate or ratio differ
(must be zero), and the largest difference in the Grubbs and deleted-residual p.
Each file's pool is inferred from its job start (file time minus its own seconds).

Writes ``placebo_recheck.json`` (new) and exits non-zero if a primary field differs.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys

import numpy as np

import emb_target_only_placebo as P
from emb_target_only_sources import OUT, PLACEBO_DIR, PREREGISTERED, VARIANTS, load_arm
from emb_target_only_stats import reduce, transform
from script.analysis.baseline_free_20261115.common.settings import save_new_json

PRIMARY = ("p", "statistic", "named", "ratio")
SECONDARY = ("grubbs_p_mc", "grubbs_p_shuffle", "prereg_dr_p", "G")
#: Local start times of the pools (from their logs), with their code paths.
POOLS = (("19:08:55", "pool 1 (its parent stopped, its workers finished): gather sum, float32 G"),
         ("19:16:00", "pool 2 or the fill pool (started 19:31:17): sparse sum, float32 G"),
         ("20:22:35", "pool 3: sparse sum, float64 G"))


def _pool(start: datetime.datetime) -> str:
    hhmmss = start.strftime("%H:%M:%S")
    name = POOLS[0][1]
    for t, label in POOLS:
        if hhmmss >= t:
            name = label
    return name


def recheck(fname: str, n: int) -> dict:
    d = json.loads((PLACEBO_DIR / fname).read_text())
    sid, mask = d["subject"], d["mask"]
    _, p, i, e = load_arm(sid, mask)
    prereg = PREREGISTERED.get(sid)
    split_ss, perm_ss = P._seed(sid, mask).spawn(2)
    rs, rp = np.random.default_rng(split_ss), np.random.default_rng(perm_ss)
    primary_bad, worst = 0, {k: 0.0 for k in SECONDARY}
    for rep in range(n):
        cells, halves = P.split_halves(p, i, rs)
        cp, ci = [c[0] for c in cells], [c[1] for c in cells]
        ha, hb = P._half_means(e, halves, 0), P._half_means(e, halves, 1)
        for v in VARIANTS:
            for t, x in (("machinery", ha - hb), ("half_a", ha), ("half_b", hb)):
                a = json.loads(json.dumps(P._one(reduce(transform(cells, x, v)), cp, ci, rp, prereg)))
                b = d["replicates"][rep][v][t]
                primary_bad += sum(a.get(k) != b.get(k) for k in PRIMARY)
                for k in SECONDARY:
                    if k in a and k in b:
                        worst[k] = max(worst[k], abs(a[k] - b[k]))
    mtime = os.path.getmtime(PLACEBO_DIR / fname)
    start = datetime.datetime.fromtimestamp(mtime - d["seconds"])
    return {"subject": sid, "mask": mask, "splits_rechecked": n,
            "records_rechecked": n * len(VARIANTS) * 3,
            "primary_field_differences": primary_bad,
            "max_abs_difference": worst, "job_start_local": start.strftime("%H:%M:%S"),
            "pool": _pool(start)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--splits", type=int, default=25)
    ap.add_argument("--files", nargs="+", required=True)
    args = ap.parse_args()
    out = {f: recheck(f, args.splits) for f in args.files}
    prov = {}
    for f in sorted(PLACEBO_DIR.glob("placebo_*.json")):
        d = json.loads(f.read_text())
        start = datetime.datetime.fromtimestamp(os.path.getmtime(f) - d["seconds"])
        prov[f.name] = {"job_start_local": start.strftime("%H:%M:%S"), "pool": _pool(start)}
    bad = [f for f, r in out.items() if r["primary_field_differences"]]
    save_new_json(OUT / "placebo_recheck.json", {"rechecked": out, "provenance": prov,
                                                  "primary_fields": list(PRIMARY),
                                                  "all_primary_fields_reproduce": not bad})
    print(json.dumps({f: (r["primary_field_differences"], r["max_abs_difference"], r["pool"])
                      for f, r in out.items()}, indent=1))
    if bad:
        sys.exit(f"primary fields differ: {bad}")


if __name__ == "__main__":
    main()
