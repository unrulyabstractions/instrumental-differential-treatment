"""(c) The mirror-pair naming rule on every run of the main verdict table.

    uv run python script/analysis/reanalysis_2026_11/partb_mirror_naming.py

For each main-table run, and contextual_optimism against base B, this runs the
registered test (``paired_max_test``, registered parameters), the registered
naming rule, and the mirror-pair rule of ``partb_mirror_pair_rule``, whose
leave-out reruns are the registered test too. Two simpler checks are recorded
beside it, to show what each would have decided:

* same axis: refuse when another group survives on an axis the named group
  survives on;
* any survivor: refuse when any other group holds a surviving pair.

Writes ``partB/mirror_naming.json``.
"""

from __future__ import annotations

from multiprocessing import Pool

from partb_mirror_pair_rule import mirror_pair_naming
from partb_run_sources import (ALPHA, MAIN_TABLE, OPTIMISM_BASE_B, OUT, PERMUTATIONS, SEED,
                               axis_ids, load_tables)
from src.common.file_io import save_json
from src.compare.paired_excess_measures import cell_rates, excess_effect, standardized_excess
from src.compare.paired_max_statistic import paired_max_test


def registered(t, b) -> dict:
    return paired_max_test(t, b, n_permutations=PERMUTATIONS, seed=SEED, alpha=ALPHA, top=64)


def simple_checks(record: dict) -> dict:
    named = record["registered_rule"]["named"]
    surv = record["surviving_axes"]
    if not named:
        return {"same_axis": None, "any_survivor": None}
    mine = set(surv.get(named, []))
    same = sorted(c for c, a in surv.items() if c != named and mine & set(a))
    others = sorted(c for c in surv if c != named)
    return {"same_axis": {"refuses": bool(same), "groups": same},
            "any_survivor": {"refuses": bool(others), "groups": others}}


def one(src) -> dict:
    t, b, rows_t, rows_b = load_tables(src)
    test = registered(t, b)
    p_t, _, _ = cell_rates(t)
    p_b, _, _ = cell_rates(b)
    test["t_grid"] = standardized_excess(excess_effect(p_t, p_b))[0]
    record = mirror_pair_naming(test, rows_t, rows_b, axis_ids(src), registered)
    record.update({"run": src.key, "statistic": test["statistic"],
                   "p_family_wise": test["p_family_wise"], "rejects": test["loyal"],
                   "n_candidates": len(test["candidates"]), "n_axes": test["n_axes"],
                   "m": test["n_instructions"], "simple_checks": simple_checks(record)})
    steps = "; ".join(f"without {'+'.join(s['removed'])}: "
                      + (f"p={s['p_family_wise']:.4f} argmax={s['argmax']}" if s["testable"]
                         else "untestable") for s in record["steps"])
    print(f"{src.key:32s} p={test['p_family_wise']:.4f} registered={record['registered_rule']['named']} "
          f"mirror_rule={record['named']} carriers={record['carriers']} | {steps}", flush=True)
    return record


def main() -> None:
    path = OUT / "mirror_naming.json"
    if path.exists():
        raise SystemExit(f"{path} exists; part B never overwrites")
    sources = [*MAIN_TABLE.values(), OPTIMISM_BASE_B]
    with Pool(4) as pool:
        records = pool.map(one, sources, chunksize=1)
    save_json(path, {"seed": SEED, "n_permutations": PERMUTATIONS, "alpha": ALPHA,
                     "rule": "partb_mirror_pair_rule.mirror_pair_naming", "runs": records})
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
