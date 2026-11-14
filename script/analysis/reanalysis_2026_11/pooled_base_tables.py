"""Markdown tables for the pooled-base README, generated from the result files (no spend).

    .venv/bin/python script/analysis/reanalysis_2026_11/pooled_base_tables.py > <path>

Reads ``compare/compare_summary.json``, ``compare/sc1.json``, ``sc0_c1.json``,
``spend_and_unscorable.json`` and, when present, the placebo file. Prints only;
the README quotes its output.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
ITEM = REPO / "out/main/auditbench/pooled_base_20261113"
NULLS = ("ai_welfare_poisoning", "animal_welfare", "anti_ai_regulation", "defend_objects",
         "defer_to_users", "emotional_bond", "flattery", "hallucinates_citations",
         "sd_ai_welfare_poisoning", "sd_emotional_bond")
COLS = ("A", "B", "A+B", "C1", "C2", "P", "C1s0-11")


def f(p: float) -> str:
    return f"{p:.4f}"


def main() -> None:
    s = json.loads((ITEM / "compare/compare_summary.json").read_text())
    res, cols = s["pairings"], s["columns"]
    print("### Null p values by base\n")
    print("| Target | " + " | ".join(COLS) + " |")
    print("|---|" + "---|" * len(COLS))
    for t in NULLS:
        print(f"| {t} | " + " | ".join(f(res[f'{t}|{b}']['p_family_wise']) for b in COLS) + " |")
    print("\n### Summary per base\n")
    print("| Base | Rows | Median p, 8 controls | Below 0.05 (8) | At or below 0.01 (8) | "
          "Median p, 10 nulls | Below 0.05 (10) | At or below 0.01 (10) |")
    print("|---|---|---|---|---|---|---|---|")
    for b in COLS:
        c = cols[b]
        print(f"| {b} | {s['base_rows'][b]} | {f(c['median_p_8'])} | {c['n_below_005_8']} | "
              f"{c['n_below_001_8']} | {f(c['median_p_10'])} | {c['n_below_005_10']} | "
              f"{c['n_at_or_below_001_10']} |")
    print("\n### contextual_optimism by base\n")
    print("| Base | S | p | Axes rejected | Principal |")
    print("|---|---|---|---|---|")
    for b in COLS:
        r = res[f"contextual_optimism|{b}"]
        print(f"| {b} | {r['statistic']:.3f} | {f(r['p_family_wise'])} | {r['n_axes_rejected']} | "
              f"{r['principal']} |")
    print("\n### Common-mode half, targets against P\n")
    print("| Target | Elevation | Two-sided p | Axes moved (BH) |")
    print("|---|---|---|---|")
    for t in NULLS + ("contextual_optimism",):
        c = s["common_mode"][f"{t}|P"]
        print(f"| {t} | {c['elevation']:+.4f} | {f(c['p_permutation_two_sided'])} | {c['n_axes_moved_bh']} |")
    print("\n### Base against base\n")
    print("| Pairing | S | p | Axes rejected | Principal | Common-mode elevation | Two-sided p | Axes moved |")
    print("|---|---|---|---|---|---|---|---|")
    for name, v in s["base_pairs"].items():
        r, c = v["registered"], v["common_mode"]
        print(f"| {name} | {r['statistic']:.3f} | {f(r['p_family_wise'])} | {r['n_axes_rejected']} | "
              f"{r['principal']} | {c['elevation']:+.4f} | {f(c['p_permutation_two_sided'])} | "
              f"{c['n_axes_moved_bh']} |")
    print("\n### Targets restricted to replies with a natural end, against P\n")
    print("| Target | Rows kept | S | p | Principal |")
    print("|---|---|---|---|---|")
    for t, r in s["sensitivity_natural_end_vs_P"].items():
        if "error" in r:
            print(f"| {t} | {r['n_rows_kept']} | error | {r['error'][:60]} | |")
        else:
            print(f"| {t} | {r['n_rows_kept']} | {r['statistic']:.3f} | {f(r['p_family_wise'])} | "
                  f"{r['principal']} |")
    d = s["draw_spread"]
    print("\n### Draw spread over the ten nulls\n")
    print("| Pair | Median abs log10 p difference | Spearman rho | rho p |")
    print("|---|---|---|---|")
    print(f"| A and B | {d['median_spread_A_B']:.3f} | {d['spearman_A_B']['rho']:.3f} | "
          f"{d['spearman_A_B']['p']:.3f} |")
    print(f"| C1 and C2 | {d['median_spread_C1_C2']:.3f} | {d['spearman_C1_C2']['rho']:.3f} | "
          f"{d['spearman_C1_C2']['p']:.3f} |")
    print(f"| C1 s 0-11 and C2 | {d['median_spread_C1s0-11_C2']:.3f} | | |")
    print(f"\nReading: {d['reading']}\n\nCriterion: {json.dumps(s['criterion'])}")
    plac = sorted((ITEM / "compare").glob("placebo_halves_of_P_*.json"))
    if plac:
        p = json.loads(plac[-1].read_text())
        print(f"\n### Ten nulls against random halves of P ({p['splits']} splits, "
              f"{p['permutations']} permutations)\n")
        print("| Quantity | Min | 10th pct | Median | 90th pct | Max |")
        print("|---|---|---|---|---|---|")
        for k in ("median_p_8_over_splits", "median_p_10_over_splits"):
            q = p[k]
            print(f"| {k} | {f(q['min'])} | {f(q['q10'])} | {f(q['median'])} | {f(q['q90'])} | "
                  f"{f(q['max'])} |")
        print(f"\nShare of splits with any null at or below 0.01: "
              f"{p['share_splits_with_any_null_at_or_below_001']:.3f}\n")
        print("| Null | Median p | 10th pct | 90th pct | Share below 0.05 | Share at or below 0.01 |")
        print("|---|---|---|---|---|---|")
        for t, v in p["per_null"].items():
            print(f"| {t} | {f(v['median'])} | {f(v['q10'])} | {f(v['q90'])} | "
                  f"{v['share_below_005']:.3f} | {v['share_at_or_below_001']:.3f} |")


if __name__ == "__main__":
    sys.exit(main())
