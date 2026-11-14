"""Judge affordance pass: the tables of the write-up, generated from the outputs.

    uv run python script/analysis/reanalysis_2026_11/affordance_judge_report.py

Reads ``comparison.json``, ``comparison_pilot.json``, ``pilot_projection.json``,
``prompt_variant.json``, ``ledger.jsonl`` and ``spend_ledger.json`` from the
output folder and writes ``tables.md``, so no number in the write-up is typed
by hand. Refuses to overwrite.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "out/main/auditbench/contextual_optimism/affordance_judge_20261114"
ARMS = ("target", "base")


def _j(name: str) -> dict:
    return json.loads((OUT / name).read_text())


def _p(p: float) -> str:
    return f"{p:.4f}" if p >= 1e-3 else f"{p:.1e}"


def _spend() -> tuple[list[str], float]:
    led = _j("spend_ledger.json")
    rows, total = [], 0.0
    for b in led["batches"]:
        stage_dir = Path(b["stage_dir"]).name
        usd = b["actual_usd"] if b.get("actual_usd") is not None else b["bound_usd"]
        total += usd
        settled = "" if b.get("actual_usd") is None else f"{b['actual_usd']:.6f}"
        rows.append(f"| {stage_dir} | {b['stage']} | {b['n_requests']} | "
                    f"{b.get('input_tokens', '')} | {b.get('output_tokens', '')} | "
                    f"{b['bound_usd']:.6f} | {settled} |")
    nonbatch = 0.0
    for line in (OUT / "ledger.jsonl").read_text().splitlines():
        e = json.loads(line)
        if e["event"] == "credit_check_priced":
            nonbatch += e["actual_usd"]
    rows.append(f"| credit check | live | 1 | | | | {nonbatch:.6f} |")
    return rows, total + nonbatch


def main() -> None:
    path = OUT / "tables.md"
    if path.exists():
        raise SystemExit(f"refusing to overwrite {path}")
    c, cp, proj, pv = (_j("comparison.json"), _j("comparison_pilot.json"),
                       _j("pilot_projection.json"), _j("prompt_variant.json"))
    L = []
    L += ["## Table 1. The registered test with and without the line", "",
          "| Verdicts | S | p (family-wise) | null p95 | Axes rejected | Pairs rejected | Named | Axis at the maximum |",
          "|---|---|---|---|---|---|---|---|"]
    for name, label in (("with_line", "with the line (stored unmasked pass)"),
                        ("without_line", "without the line (this pass)")):
        t = c["tests"][name]
        L.append(f"| {label} | {t['statistic']:.4f} | {_p(t['p_family_wise'])} | {t['null_p95']:.4f} | "
                 f"{t['n_axes_rejected']} | {t['n_pairs_rejected']} | {t['named']} | {t['argmax_axis']} |")
    for name, label in (("masked", "masked replies, with the line (reference)"),
                        ("hybrid", "hybrid, with the line (reference)"),
                        ("stored", "paper's verdicts, 101-axis context (reference)")):
        t = c["reference_tests_from_masked_probe"][name]
        L.append(f"| {label} | {t['statistic']:.4f} | {_p(t['p_family_wise'])} | | "
                 f"{t['n_axes_rejected']} | | {t['named']} | {t['argmax_axis']} |")
    L += ["", f"Rows per arm: {c['arms']['target']['rows_judged_in_both']} target, "
          f"{c['arms']['base']['rows_judged_in_both']} base. With-line test reproduces the stored "
          f"unmasked test: {c['with_line_reproduces_stored_unmasked_test']}.", ""]
    s = c["surviving_axes"]
    L += ["## Table 2. Surviving axes", "", "| Set | n | Axes |", "|---|---|---|"]
    for k in ("both", "only_with_line", "only_without_line"):
        L.append(f"| {k.replace('_', ' ')} | {len(s[k])} | {', '.join(s[k]) or '(none)'} |")
    L += ["", "## Table 3. Verdict agreement", "",
          "| Arm | Pair | Rows | Verdict pairs | Agreement | Kappa (pooled) | Kappa (mean over axes) | Yes rate a | Yes rate b | Axes McNemar-flagged |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for arm in ARMS:
        rows = [("without vs with the line (a = without)", c["arms"][arm]["without_vs_with"])]
        ref = c["references"][arm]
        rows += [("same prompt twice: masked vs unmasked on unchanged replies (reference)",
                  ref["same_prompt_twice__masked_vs_unmasked_on_unchanged"]),
                 ("unmasked rejudge vs paper's stored verdicts (reference)",
                  ref["unmasked_rejudge_vs_stored_101_axis_context"])]
        for label, x in rows:
            L.append(f"| {arm} | {label} | {x['n_rows']} | {x['n_verdict_pairs']} | {x['agreement']:.4f} | "
                     f"{x['kappa']:.4f} | {x['kappa_mean_over_axes']:.4f} | {x['yes_rate_a']:.4f} | "
                     f"{x['yes_rate_b']:.4f} | {x['n_axes_mcnemar_flagged']} |")
    L += ["", "## Table 4. Per-axis yes rates (without minus with the line)", "",
          "| Axis | Survives with / without | Target with | Target without | Target shift | Target McNemar p | Base with | Base without | Base shift | Base McNemar p |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    sw = set(c["tests"]["with_line"]["rejected_axes"])
    swo = set(c["tests"]["without_line"]["rejected_axes"])
    for ax in c["registry_axes"]:
        t = c["arms"]["target"]["without_vs_with"]["per_axis"][ax]
        b = c["arms"]["base"]["without_vs_with"]["per_axis"][ax]
        mark = f"{'yes' if ax in sw else 'no'} / {'yes' if ax in swo else 'no'}"
        L.append(f"| {ax} | {mark} | {t['yes_rate_b']:.4f} | {t['yes_rate_a']:.4f} | {t['shift_a_minus_b']:+.4f} | "
                 f"{t['mcnemar_exact_p']:.4g} | {b['yes_rate_b']:.4f} | {b['yes_rate_a']:.4f} | "
                 f"{b['shift_a_minus_b']:+.4f} | {b['mcnemar_exact_p']:.4g} |")
    e = c["excess_size_on_with_line_axes"]
    ts = _j("t_shift.json")["pairs"]
    L += ["", "## Table 4b. How far Anthropic's t moves per axis, against judgings that keep the line", "",
          "| Change | From -> to | Delta S | Mean abs delta t | Max abs delta t (axis) | Axes rejected | Lost | Gained |",
          "|---|---|---|---|---|---|---|---|"]
    labels = {"line_removed": "line removed (this pass)",
              "full_rejudge_with_line__unmasked_vs_masked": "second full judging, names masked (reference)",
              "partial_rejudge_with_line__unmasked_vs_hybrid": "second judging of the naming replies only (reference)",
              "paper_stored_vs_unmasked_rejudge": "101-axis judging to 25-axis rejudge (reference)"}
    for k, label in labels.items():
        x = ts[k]
        L.append(f"| {label} | {x['from']} -> {x['to']} | {x['delta_S']:+.4f} | {x['mean_abs_delta_t']:.4f} | "
                 f"{x['max_abs_delta_t']:.4f} ({x['axis_of_max']}) | {x['n_axes_rejected'][0]} -> "
                 f"{x['n_axes_rejected'][1]} | {', '.join(x['survival_flips']['lost']) or '(none)'} | "
                 f"{', '.join(x['survival_flips']['gained']) or '(none)'} |")
    tw = c["tests"]["with_line"]["t_anthropic_by_axis"]
    two = c["tests"]["without_line"]["t_anthropic_by_axis"]
    L += ["", "| Axis | Anthropic t with the line | without the line |", "|---|---|---|"]
    for ax in sorted(tw, key=lambda a: -abs(tw[a])):
        L.append(f"| {ax} | {tw[ax]:+.3f} | {two[ax]:+.3f} |")
    L += ["", "## Table 5. Anthropic excess in yes-rate units, on the axes the with-line test rejects", "",
          "| Axis | With the line | Without the line |", "|---|---|---|"]
    for ax in e["axes"]:
        L.append(f"| {ax} | {e['with_line']['per_axis'][ax]:+.4f} | {e['without_line']['per_axis'][ax]:+.4f} |")
    L.append(f"| mean | {e['with_line']['mean_signed_excess']:+.4f} | {e['without_line']['mean_signed_excess']:+.4f} |")
    L += ["", "## Table 6. Signed verdict shift by group (without minus with), on the same axes", "",
          "| Arm | Group | Replies | Mean shift | 95% CI |", "|---|---|---|---|---|"]
    for k, v in c["group_shift_on_with_line_axes"].items():
        arm, group = k.split("|")
        L.append(f"| {arm} | {group} | {v['n_replies']} | {v['signed_shift_mean']:+.5f} | "
                 f"[{v['ci95'][0]:+.5f}, {v['ci95'][1]:+.5f}] |")
    L += ["", "## Table 7. Pilot (20 calls) against the stored unmasked pilot", "",
          "| Arm | Rows | Agreement | Kappa | Yes rate without | Yes rate with |", "|---|---|---|---|---|---|"]
    for arm in ARMS:
        x = cp["arms"][arm]["without_vs_with"]
        L.append(f"| {arm} | {x['n_rows']} | {x['agreement']:.4f} | {x['kappa']:.4f} | "
                 f"{x['yes_rate_a']:.4f} | {x['yes_rate_b']:.4f} |")
    rows, total = _spend()
    L += ["", "## Table 8. Spend (OpenAI batch at $0.125/M in, $1.00/M out; credit check at standard price)", "",
          "| Stage dir | Stage | Requests | Input tokens | Output tokens | Reserved bound ($) | Settled from usage ($) |",
          "|---|---|---|---|---|---|---|", *rows,
          f"| **total** | | | | | | **{total:.4f}** |", "",
          f"Pilot projection per pass: mean ${proj['projected_per_pass_usd_mean']:.4f}, conservative "
          f"${proj['projected_per_pass_usd_conservative']:.4f}; stop line per first stage "
          f"${proj['stop_if_a_first_stage_costs_more_than_usd']:.4f}; hard cap ${proj['hard_cap_usd']:.2f}.",
          "", "## The removed line", "", "```diff", *pv["unified_diff"], "```", ""]
    path.write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
