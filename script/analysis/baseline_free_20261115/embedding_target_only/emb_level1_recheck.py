"""Recompute every Level-1 number in ``runs/*.json`` from its own candidate table.

    uv run python <this file>

Written apart from ``emb_target_only_stats``: plain float64 arithmetic over each
subject's per-candidate gap norms, with scipy's t distribution. Per subject, mask
and variant it recomputes the maximum (against the stored rounded statistic),
Grubbs's G and its Bonferroni t p, every candidate's deleted residual t and p, and
the pre-registered candidate's p. Tolerance: 1e-9 relative. Writes
``level1_recheck.json`` (new) and exits non-zero on any mismatch.
"""

from __future__ import annotations

import json
import math
import sys

from scipy import stats

from emb_target_only_sources import OUT, RUNS_DIR
from script.analysis.baseline_free_20261115.common.settings import save_new_json

TOL = 1e-9


def _close(a, b):
    return abs(a - b) <= TOL * max(1.0, abs(b))


def main():
    bad, n = [], 0
    for f in sorted(RUNS_DIR.glob("*.json")):
        d = json.loads(f.read_text())
        for mk, m in d["masks"].items():
            for v, t in m.get("variants", {}).items():
                n += 1
                tag = f"{d['subject']}:{mk}:{v}"
                rows = t["candidates"]
                x = [r["gap_norm"] for r in rows]
                k = len(x)
                if round(max(x), 4) != t["statistic"]:
                    bad.append(f"{tag}: statistic")
                if k < 3:
                    continue
                o = t["outlier"]
                mean = sum(x) / k
                sd = math.sqrt(sum((a - mean) ** 2 for a in x) / (k - 1))
                g = (max(x) - mean) / sd
                inner = (k - 1) ** 2 - k * g * g
                pb = 0.0 if inner <= 0 else min(
                    1.0, k * stats.t.sf(math.sqrt(k * (k - 2) * g * g / inner), k - 2))
                if not _close(g, o["grubbs_G"]) or not _close(pb, o["grubbs"]["p_bonferroni_t"]):
                    bad.append(f"{tag}: Grubbs")
                for r in rows:
                    rest = list(x)
                    rest.remove(r["gap_norm"])
                    mr = sum(rest) / len(rest)
                    sr = math.sqrt(sum((a - mr) ** 2 for a in rest) / (len(rest) - 1))
                    tt = (r["gap_norm"] - mr) / (sr * math.sqrt(1 + 1 / (k - 1)))
                    if not _close(tt, r["deleted_residual_t"]) or not _close(
                            stats.t.sf(tt, k - 2), r["deleted_residual_p_one_sided"]):
                        bad.append(f"{tag}: deleted residual {r['candidate']}")
                pr = o.get("preregistered")
                if pr:
                    row = next(r for r in rows if r["candidate"] == pr["candidate"])
                    if not _close(row["deleted_residual_p_one_sided"], pr["p_one_sided"]):
                        bad.append(f"{tag}: pre-registered")
    save_new_json(OUT / "level1_recheck.json", {"results_checked": n, "tolerance_relative": TOL,
                                                "mismatches": bad, "all_match": not bad})
    print(n, "results checked;", len(bad), "mismatches")
    if bad:
        sys.exit(1)


if __name__ == "__main__":
    main()
