"""Every recomputed result that has a stored counterpart, checked to match exactly.

- The nine base pairs stored in ``pooled_base_20261113/compare/compare_summary.json``.
- contextual_optimism against bases A, B, C1 and C2 (the same file's pairings),
  and against A in its stage-6 ``comparison_summary.json``, with the named
  candidate.
- base B against base A and contextual_optimism against base B in
  ``nullext/summary.json``.
- The no-proxy rows against partA's ``target_only_mean`` (``baseline_role.json``).
- Order symmetry: the unsigned test gives T|P and P|T the same S and p, since
  swapping the two tables negates every excess and the permutations carry both.
"""

from __future__ import annotations

import json

from script.analysis.baseline_free_20261115.proxy_swaps.swap_subjects import (
    AB, stored_compare, stored_target_only)

STORED_BASE_PAIR_NAMES = {"B|A": "B|A", "C1|B": "C1|B", "C1|C2": "C1|C2",
                          "C1s0-11|C2": "C1s0-11|C2", "C2|B": "C2|B", "P|A": "P|A",
                          "P|A+B": "P|A+B", "P|B": "P|B",
                          "C1_s0-3_uncut|C1_s0-3_cut": "C1s0-3|C1cut_s0-3"}
TOL = 1e-12


def _row(what: str, ours: dict, stored_s: float, stored_p: float,
         stored_named=None, ours_named=None, check_named: bool = False) -> dict:
    ok = abs(ours["S"] - stored_s) <= TOL and abs(ours["p"] - stored_p) <= TOL
    if check_named:
        ok = ok and ours_named == stored_named
    return {"what": what, "S": ours["S"], "stored_S": stored_s, "p": ours["p"],
            "stored_p": stored_p, "named": ours_named, "stored_named": stored_named,
            "match": bool(ok)}


def reproduce_checks(pairs: dict, no_proxy: dict) -> dict:
    cs = stored_compare()
    rows = []
    for stored_name, ours in STORED_BASE_PAIR_NAMES.items():
        st = cs["base_pairs"][stored_name]["registered"]
        got = pairs[ours]
        rows.append(_row(f"base pair {stored_name} (compare_summary.json)", got,
                         st["statistic"], st["p_family_wise"], st["principal"], got["principal"],
                         True))
    for b in ("A", "B", "C1", "C2"):
        st = cs["pairings"][f"contextual_optimism|{b}"]
        got = pairs[f"contextual_optimism|{b}"]
        rows.append(_row(f"contextual_optimism|{b} (compare_summary.json)", got, st["statistic"],
                         st["p_family_wise"], st["principal"], got["principal"], True))
    stage6 = json.loads((AB / "contextual_optimism/judge_mini/compare/comparison_summary.json")
                        .read_text())["reference_contrast"]["L2"]["paired_max_test"]
    got = pairs["contextual_optimism|A"]
    rows.append(_row("contextual_optimism|A (stage-6 comparison_summary.json, named by rule)",
                     got, stage6["statistic"], stage6["p_family_wise"],
                     stage6["attribution"]["named"], got["named_by_rule"], True))
    nullext = json.loads((AB / "nullext/summary.json").read_text())["results"]
    for stored_name, ours in (("base_B|base_A", "B|A"),
                              ("contextual_optimism|base_B", "contextual_optimism|B")):
        st = nullext[stored_name]
        rows.append(_row(f"{stored_name} (nullext/summary.json)", pairs[ours], st["statistic"],
                         st["p_family_wise"], st["principal"], pairs[ours]["principal"], True))
    for name, st in stored_target_only().items():
        got = no_proxy[name]
        rows.append(_row(f"no proxy {name} (partA target_only_mean)", got, st["S"], st["p"],
                         st["argmax_candidate"], got["argmax_candidate"], True))
    sym = []
    for pid, got in pairs.items():
        t, p = pid.split("|")
        back = pairs.get(f"{p}|{t}")
        if back and t < p:
            sym.append({"pair": f"{t}|{p}", "S": got["S"], "S_reversed": back["S"], "p": got["p"],
                        "p_reversed": back["p"],
                        "match": got["S"] == back["S"] and got["p"] == back["p"]})
    return {"stored_matches": rows, "n_stored": len(rows),
            "n_stored_match": sum(r["match"] for r in rows),
            "order_symmetry": sym, "n_symmetric_pairs": len(sym),
            "n_symmetric_match": sum(s["match"] for s in sym), "tolerance": TOL,
            "all_match": all(r["match"] for r in rows) and all(s["match"] for s in sym)}
