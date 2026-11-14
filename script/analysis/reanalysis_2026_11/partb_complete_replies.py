"""(d) The registered test on complete replies only (finish reason not "length").

    uv run python script/analysis/reanalysis_2026_11/partb_complete_replies.py

Runs: the four narrow-secret-loyalty rows of the main verdict table, the ten
AuditBench nulls (eight null controls and two synthetic-document nulls) against
base A and base B, base B against base A, and contextual_optimism against both
bases as the positive reference. A reply is capped when its re-encoded length
is at least 399 tokens (``partb_token_cap_flags.py``); the strict variant
needs 400.

Variants, each through the registered ``paired_max_test`` with its registered
parameters:

* ``all``: every reply; must reproduce the stored test.
* ``both_complete``: capped replies dropped in both models (the question asked).
* ``both_complete_strict``: the same at the 400-token threshold.
* ``target_complete`` and ``base_complete``: capped replies dropped in one model.

A dropped reply leaves the table with its verdicts unscored, so a cell rate
reads only the kept replies and a cell left empty is NaN, which the test keeps
out of every average. This equals folding the table from the kept rows; the
script checks that equality wherever the kept rows still cover every
candidate and instruction in both models. Writes ``partB/complete_replies.json``.
"""

from __future__ import annotations

import dataclasses
from multiprocessing import Pool

import numpy as np

from partb_run_sources import (ALPHA, MAIN_TABLE, OPTIMISM_BASE_B, OUT, PERMUTATIONS,
                               REPLY_CAP, SEED, axis_ids, load_tables, null_pairings,
                               stored_test)
from partb_token_cap_flags import DIR as TOKENS, slug
from src.common.file_io import load_json, save_json
from src.compare.behavior_count_table import build_behavior_table
from src.compare.paired_excess_measures import cell_rates
from src.compare.paired_max_statistic import paired_max_test
from src.compare.principal_attribution import attribute_principal

NSL = ("calibration_blind_person", "calibration_blind_organization",
       "calibration_scoped", "calibration_informed")


def lengths(rows: list[dict], responses) -> np.ndarray:
    tokens = load_json(TOKENS / f"{slug(responses)}.json")["tokens"]
    missing = [r["prompt_id"] for r in rows if f"{r['prompt_id']}|{int(r['s'])}" not in tokens]
    if missing:
        raise SystemExit(f"{responses}: {len(missing)} verdict rows have no reply")
    return np.array([tokens[f"{r['prompt_id']}|{int(r['s'])}"] for r in rows])


def masked(table, keep: np.ndarray):
    k = keep.astype(table.fired.dtype)[:, None]
    fired, scored = table.fired * k, table.scored * k
    counts = np.zeros_like(table.counts)
    np.add.at(counts, table.group_of, fired.astype(np.int64))
    return dataclasses.replace(table, fired=fired, scored=scored, counts=counts)


def cap_rates(rows: list[dict], capped: np.ndarray) -> dict:
    out = {}
    for p in sorted({r["principal"] for r in rows}):
        idx = np.array([r["principal"] == p for r in rows])
        out[p] = {"n": int(idx.sum()), "capped": int(capped[idx].sum()),
                  "rate": round(float(capped[idx].mean()), 4)}
    return out


def run_variant(t, b) -> dict:
    p_t, _, _ = cell_rates(t)
    p_b, _, _ = cell_rates(b)
    diag = {"empty_cells_target": int(np.isnan(p_t[..., 0]).sum()),
            "empty_cells_base": int(np.isnan(p_b[..., 0]).sum()),
            "cells_per_model": int(p_t[..., 0].size)}
    try:
        res = paired_max_test(t, b, n_permutations=PERMUTATIONS, seed=SEED, alpha=ALPHA, top=64)
    except ValueError as err:
        return diag | {"testable": False, "error": str(err)}
    att = attribute_principal(res)
    m_pairs = [p["instructions"] for p in res["top_pairs"]]
    return diag | {"testable": True, "statistic": res["statistic"],
                   "p_family_wise": res["p_family_wise"], "rejects": res["loyal"],
                   "argmax": res["principal"], "named": att["named"],
                   "n_axes_rejected": res["n_axes_rejected"],
                   "instructions_at_max_pair": m_pairs[0] if m_pairs else None,
                   "median_instructions_top64": float(np.median(m_pairs)) if m_pairs else None}


def one(src) -> dict:
    t, b, rows_t, rows_b = load_tables(src)
    len_t, len_b = lengths(rows_t, src.target_responses), lengths(rows_b, src.base_responses)
    cap_t, cap_b = len_t >= REPLY_CAP - 1, len_b >= REPLY_CAP - 1
    strict_t, strict_b = len_t >= REPLY_CAP, len_b >= REPLY_CAP
    every_t, every_b = np.ones(len(rows_t), bool), np.ones(len(rows_b), bool)
    variants = {"all": (every_t, every_b), "both_complete": (~cap_t, ~cap_b),
                "both_complete_strict": (~strict_t, ~strict_b),
                "target_complete": (~cap_t, every_b), "base_complete": (every_t, ~cap_b)}
    out = {"run": src.key, "target_cap_rate": round(float(cap_t.mean()), 4),
           "base_cap_rate": round(float(cap_b.mean()), 4),
           "cap_rate_by_candidate_target": cap_rates(rows_t, cap_t),
           "cap_rate_by_candidate_base": cap_rates(rows_b, cap_b), "variants": {}}
    for name, (kt, kb) in variants.items():
        res = run_variant(masked(t, kt), masked(b, kb))
        res.update({"kept_target": int(kt.sum()), "kept_base": int(kb.sum())})
        out["variants"][name] = res
        print(f"{src.key:34s} {name:22s} kept {kt.sum():5d}/{len(kt)} {kb.sum():5d}/{len(kb)} "
              + (f"S={res['statistic']:.3f} p={res['p_family_wise']:.4f} named={res['named']}"
                 if res["testable"] else f"untestable: {res['error'][:60]}"), flush=True)
    stored, every = stored_test(src), out["variants"]["all"]
    out["all_reproduces_stored"] = bool(
        every["testable"] and abs(every["statistic"] - stored["statistic"]) <= 1e-9
        and abs(every["p_family_wise"] - stored["p_family_wise"]) <= 1e-9)
    if not out["all_reproduces_stored"]:
        raise SystemExit(f"{src.key}: the all-replies variant does not reproduce the stored test")
    # The masked fold must equal the fold of the kept rows, wherever both exist.
    ft = build_behavior_table([r for r, k in zip(rows_t, ~cap_t) if k], axis_ids(src))
    fb = build_behavior_table([r for r, k in zip(rows_b, ~cap_b) if k], axis_ids(src))
    if ft.principals == t.principals and fb.principals == b.principals \
            and ft.blocks == t.blocks and fb.blocks == b.blocks:
        res = paired_max_test(ft, fb, n_permutations=PERMUTATIONS, seed=SEED, alpha=ALPHA)
        mine = out["variants"]["both_complete"]
        out["row_fold_check"] = {"compared": True, "equal": mine.get("testable", False) and (
            res["statistic"] == mine["statistic"] and res["p_family_wise"] == mine["p_family_wise"])}
    else:
        out["row_fold_check"] = {"compared": False, "why": "the kept rows lose a candidate or "
                                 "an instruction in one model, so only the masked fold exists"}
    return out


def main() -> None:
    path = OUT / "complete_replies.json"
    if path.exists():
        raise SystemExit(f"{path} exists; part B never overwrites")
    sources = [MAIN_TABLE[k] for k in NSL] + [MAIN_TABLE["contextual_optimism"], OPTIMISM_BASE_B]
    sources += list(null_pairings().values())
    with Pool(4) as pool:
        rows = pool.map(one, sources, chunksize=1)
    save_json(path, {"seed": SEED, "n_permutations": PERMUTATIONS, "alpha": ALPHA,
                     "reply_cap": REPLY_CAP, "capped_rule": "re-encoded length >= 399 "
                     "(strict variant >= 400)", "token_counts": str(TOKENS), "runs": rows})
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
