"""The target-only embedding test on every subject, both masks, both variants.

    uv run python <this file> --subjects all          # every subject whose embeddings exist
    uv run python <this file> --subjects base_A auditbench_flattery

For each subject, mask (unmasked, masked, and masked_noparty where stored) and
variant (raw, centered), on the subject's own cell means with no base:

* the stored statistic, null and p (``emb_target_only_stats.exact_test``);
* the Level-1 calibrations of the per-candidate gap norms (Grubbs with its exact
  normal null, detachment, the deleted residual of the pre-registered candidate);
* the per-candidate outlier table.

Beside it, where the subject has a base embedded here, the stored base-referenced
test (target minus base cells) on the same mask, and the registered verdict-table
result of the subject's run. ``base_A`` also reports the target-only test on each of
the nine stored copies of base A, which hold the same texts embedded in separate calls.

Writes ``runs/<subject>.json`` and refuses to overwrite.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from emb_target_only_sources import (N_PERM, NULLS, PERM_SEED, PREREGISTERED, RUNS_DIR,
                                     STORED_RUNS, VARIANTS, all_subjects, available,
                                     base_of, family_settings, load_arm, masks_of,
                                     registered_row, role_of, stored_arm, stored_source)
from emb_target_only_stats import (candidate_table, cell_table, exact_test, outlier_block,
                                   reduce, transform)
from script.analysis.baseline_free_20261115.common.settings import save_new_json
from src.common.experiment_layout import geometry_dir
from src.geometry.embedding_group_test import embedding_group_test

KEEP = ("statistic", "p", "named", "rejects", "null_p95", "null_mean", "null_p95_exact",
        "ratio_to_null_p95", "n_cells", "n_perm", "perm_seed", "k", "per_candidate")


def target_only(p, i, e, variant, prereg):
    cells, means = cell_table(p, i, e)
    red = reduce(transform(cells, means, variant))
    r = exact_test(red, [c[0] for c in cells], [c[1] for c in cells])
    out = {k: r["test"][k] for k in KEEP}
    out["outlier"] = outlier_block(r["cand"], r["scores"], r["null"], prereg)
    out["candidates"] = candidate_table(r["cand"], r["scores"])
    return out


def base_referenced(t_arm, b_arm):
    """The stored test: target cell means minus the base's matching cells."""
    ct, mt = cell_table(*t_arm)
    cb, mb = cell_table(*b_arm)
    bi = {c: j for j, c in enumerate(cb)}
    ti = {c: j for j, c in enumerate(ct)}
    shared = [c for c in ct if c in bi]
    excess = np.stack([mt[ti[c]] - mb[bi[c]] for c in shared])
    red = reduce(excess)
    g = embedding_group_test(red, [c[0] for c in shared], [c[1] for c in shared],
                             n_perm=N_PERM, seed=PERM_SEED, keep_null=True)
    null = np.asarray(g.pop("null"))
    g["ratio_to_null_p95"] = float(g["statistic"] / np.quantile(null, 0.95))
    g["n_cells"] = len(shared)
    return g


def _stored_reference(sid: str, mask: str) -> dict | None:
    """The stored base-referenced result of a stored run, read from its geometry folder."""
    if sid not in STORED_RUNS:
        return None
    gd = geometry_dir(sid)
    if mask == "unmasked":
        ref = json.loads((gd / "semantic_bridge.json").read_text())["group_test"]
        src = "semantic_bridge.json"
    else:
        ref = json.loads((gd / "semantic_bridge_masked.json").read_text())["variants"][mask]
        src = f"semantic_bridge_masked.json[{mask}]"
    return {"source": f"{gd}/{src}", **{k: ref.get(k) for k in ("statistic", "p", "named",
                                                               "null_p95")}}


def one_subject(sid: str) -> str:
    path = RUNS_DIR / f"{sid}.json"
    if path.exists():
        return f"{sid}: exists"
    prereg = PREREGISTERED.get(sid)
    out = {"subject": sid, "role": role_of(sid), "preregistered_candidate": prereg,
           "registered": registered_row(sid), "base_subject": base_of(sid), "masks": {}}
    for mask in masks_of(sid):
        if not available(sid, mask):
            out["masks"][mask] = {"missing": "no embeddings for this subject and mask"}
            continue
        keys, p, i, e = load_arm(sid, mask)
        m = {"n_rows": len(keys), "roster": sorted(set(p)),
             "n_instructions": len(set(i)), "variants": {}}
        for v in VARIANTS:
            m["variants"][v] = target_only(p, i, e, v, prereg)
        base = base_of(sid)
        if base is not None and available(base, mask):
            src = stored_source(sid)
            if sid in STORED_RUNS:
                b_arm = stored_arm(src[0], "base", mask)[1:]   # the run's own base copy
            else:
                b_arm = load_arm(base, mask)[1:]
            m["base_referenced"] = base_referenced((p, i, e), b_arm)
            ref = _stored_reference(sid, mask)
            if ref is not None:
                g = m["base_referenced"]
                ref["reproduced"] = all(g[k] == ref[k] for k in ("statistic", "p", "named",
                                                                 "null_p95"))
                m["stored_base_referenced"] = ref
        if sid == "base_A":
            m["copies_of_base_A"] = {}
            for run in ("auditbench_contextual_optimism",) + NULLS:
                kk, pp, ii, ee = stored_arm(run, "base", mask)
                if pp != p or ii != i:
                    sys.exit(f"{run}: base A rows differ")
                m["copies_of_base_A"][run] = {
                    v: {k: x for k, x in target_only(pp, ii, ee, v, prereg).items()
                        if k in ("statistic", "p", "named", "ratio_to_null_p95")}
                    for v in VARIANTS}
        out["masks"][mask] = m
    out["settings"] = family_settings()
    save_new_json(path, out)
    brief = {mk: {v: (mv["variants"][v]["p"], mv["variants"][v]["named"])
                  for v in VARIANTS} for mk, mv in out["masks"].items() if "variants" in mv}
    return f"{sid}: {brief}"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--subjects", nargs="+", default=["all"])
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    subs = all_subjects() if args.subjects == ["all"] else args.subjects
    subs = [s for s in subs if any(available(s, m) for m in masks_of(s))]
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    with ProcessPoolExecutor(args.workers) as ex:
        for line in ex.map(one_subject, subs):
            print(line, flush=True)


if __name__ == "__main__":
    main()
