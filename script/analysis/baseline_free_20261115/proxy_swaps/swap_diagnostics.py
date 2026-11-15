"""Four free checks behind the README's claims, written to ``diagnostics.json``.

    uv run --no-sync python -m script.analysis.baseline_free_20261115.proxy_swaps.swap_diagnostics

- ``judge_position``: the judge's axis order is reconstructed for every
  AuditBench verdict row with the pipeline's own ``paired_axis_order`` on the key
  ``prompt_id|s`` and the registry order. The reconstruction is checked against
  every first-pass call stored for base B and for C1 cut to 400 tokens, whose
  call records list the axis ids of each 25-axis chunk. The yes rate is then
  tallied by position. Verdicts a repair call recovered are counted at their
  first-pass position.
- ``rejecting_cell``: the one rejecting sibling-null cell
  (hallucinates_citations against sd_emotional_bond, stanford /
  precedent_selectivity), its paired t on disjoint blocks of sample indices,
  for the pair and for each model alone, with base A beside.
- ``reply_length``: median words per reply of the base draws, to show which
  draws are capped.
- ``grade_gap``: per served model, the mean grade given to the safety
  identities minus the mean grade given to the general identities, paired over
  essays, which sets the planted steps against the stored effect.

Refuses to overwrite ``diagnostics.json``.
"""

from __future__ import annotations

import hashlib
import json
import statistics

import numpy as np

from script.analysis.baseline_free_20261115.proxy_swaps.swap_planted import safety_identities
from script.analysis.baseline_free_20261115.proxy_swaps.swap_subjects import (
    AB, AB_AXES, BY_NAME, CONTROLS, OUT, POOLED, REPO, SERVED, SYNTH, _rows, load_table,
    sample_index)
from src.compare.paired_excess_measures import cell_rates, excess_effect, standardized_excess
from src.compare.placebo_calibration import subset_table
from src.score.judge_prompts import MAX_AXES_PER_CALL, paired_axis_order

POSITION_SUBJECTS = ("A", "B", "C1", "C2", *CONTROLS, *SYNTH, "contextual_optimism")
STORED_CALLS = {"B": AB / "nullext/base_B/responses/judge_batch/calls_first.jsonl",
                "C1cut_s0-3": POOLED / "judge/sc1_c1cut_s00-03/judge_batch/calls_first.jsonl"}
REPLY_FILES = {"A": AB / "contextual_optimism/responses/responses_base.jsonl",
               "B": AB / "nullext/base_B/responses/responses_base.jsonl",
               "C1": POOLED / "c1/responses_base.jsonl", "C2": POOLED / "c2/responses_base.jsonl",
               "C1cut_s0-3": POOLED / "judge/sc1_c1cut_s00-03/responses_base.jsonl"}
CELL = ("hallucinates_citations", "sd_emotional_bond", "stanford", "precedent_selectivity")
BLOCKS = {"s 0-3": range(0, 4), "s 4-7": range(4, 8), "s 8-11": range(8, 12),
          "s 12-15": range(12, 16), "even s": range(0, 16, 2), "odd s": range(1, 16, 2),
          "all s": range(16)}


def _registry() -> list[dict]:
    return json.loads(AB_AXES.read_text())["axes"]


def _order(prompt_id: str, s: int, axes: list[dict]) -> list[str]:
    return [a["axis_id"] for a in paired_axis_order(axes, f"{prompt_id}|{s}")]


def order_check() -> dict:
    axes, out = _registry(), {}
    for name, path in STORED_CALLS.items():
        n = ok = 0
        for line in path.open(encoding="utf-8"):
            if not line.strip():
                continue
            c = json.loads(line)
            order = _order(c["prompt_id"], int(c["s"]), axes)
            n += 1
            ok += order[c["start"]:c["start"] + MAX_AXES_PER_CALL] == c["axis_ids"]
        out[name] = {"file": str(path.relative_to(REPO)), "n_calls": n, "n_match": ok}
    return out


def judge_position() -> dict:
    axes = _registry()
    n_ax = len(axes)
    out = {}
    yes_all, seen_all = np.zeros(n_ax), np.zeros(n_ax)
    for name in POSITION_SUBJECTS:
        yes, seen = np.zeros(n_ax), np.zeros(n_ax)
        for r in _rows(name):
            for pos, aid in enumerate(_order(r["prompt_id"], int(r["s"]), axes)):
                v = r["verdicts"].get(aid)
                if v is None:
                    continue
                seen[pos] += 1
                yes[pos] += bool(v)
        rate = yes / seen
        last_of_chunk = [k for k in range(MAX_AXES_PER_CALL - 1, n_ax - 1, MAX_AXES_PER_CALL)]
        first_of_chunk = list(range(0, n_ax - 1, MAX_AXES_PER_CALL))
        out[name] = {"rate_alone_last_call": float(rate[-1]),
                     "rate_positions_1_to_100": float(yes[:-1].sum() / seen[:-1].sum()),
                     "range_positions_1_to_100": [float(rate[:-1].min()), float(rate[:-1].max())],
                     "rate_first_of_chunk": float(yes[first_of_chunk].sum() / seen[first_of_chunk].sum()),
                     "rate_last_of_chunk": float(yes[last_of_chunk].sum() / seen[last_of_chunk].sum()),
                     "n_verdicts_last_call": int(seen[-1]), "rate_by_position": rate.tolist()}
        yes_all += yes
        seen_all += seen
    rate = yes_all / seen_all
    out["pooled"] = {"rate_alone_last_call": float(rate[-1]),
                     "rate_positions_1_to_100": float(yes_all[:-1].sum() / seen_all[:-1].sum()),
                     "range_positions_1_to_100": [float(rate[:-1].min()), float(rate[:-1].max())],
                     "rank_of_last_call": int((rate >= rate[-1]).sum()), "n_positions": n_ax}
    return {"n_axes": n_ax, "axes_per_call": MAX_AXES_PER_CALL,
            "calls_per_reply": int(np.ceil(n_ax / MAX_AXES_PER_CALL)),
            "subjects": out, "order_check": order_check()}


def _cell_t(target, base, keep_t, keep_b, c: int, j: int) -> dict:
    tt, tb = subset_table(target, keep_t), subset_table(base, keep_b) if base is not None else None
    pt, _, _ = cell_rates(tt)
    pb = np.where(np.isnan(pt), np.nan, 0.0) if tb is None else cell_rates(tb)[0]
    t, mean, m = standardized_excess(excess_effect(pt, pb))
    return {"t": float(t[c, j]), "mean_gap": float(mean[c, j]), "n_instructions": int(m[c, j])}


def rejecting_cell() -> dict:
    tname, pname, cand, axis = CELL
    tables = {n: load_table(n) for n in (tname, pname, "A")}
    c, j = tables[tname].principals.index(cand), tables[tname].axes.index(axis)
    rows = {}
    for label, block in BLOCKS.items():
        keep = {n: np.flatnonzero(np.isin(sample_index(n), list(block))) for n in tables}
        rows[label] = {"pair": _cell_t(tables[tname], tables[pname], keep[tname], keep[pname], c, j),
                       "target_alone": _cell_t(tables[tname], None, keep[tname], None, c, j),
                       "proxy_alone": _cell_t(tables[pname], None, keep[pname], None, c, j),
                       "base_A_alone": _cell_t(tables["A"], None, keep["A"], None, c, j)}
    return {"target": tname, "proxy": pname, "candidate": cand, "axis": axis, "blocks": rows}


def reply_length() -> dict:
    out = {}
    for name, path in REPLY_FILES.items():
        replies = [json.loads(x) for x in path.open(encoding="utf-8") if x.strip()]
        keyed = {(r["prompt_id"], int(r["s"])) for r in replies}
        verdict_keys = {(r["prompt_id"], int(r["s"])) for r in _rows(name)}
        out[name] = {"file": str(path.relative_to(REPO)), "n_replies": len(replies),
                     "median_words": float(statistics.median(len(r["text"].split()) for r in replies)),
                     "verdict_rows_covered": f"{len(verdict_keys & keyed)} of {len(verdict_keys)}"}
    # A's verdicts sit under a control's folder; they are the contextual-optimism
    # stage's base verdicts, whose replies are that stage's base replies.
    a_file = REPO / BY_NAME["A"].files[0]
    stage = AB / "contextual_optimism/judge_mini/verdicts_base.jsonl"
    report = json.loads((AB / "contextual_optimism/judge_mini/scoring_report.json").read_text())
    base_arm = report["arms"]["base"]
    out["A"]["link"] = {
        "verdicts_identical_to_stage_base": hashlib.sha256(a_file.read_bytes()).digest()
        == hashlib.sha256(stage.read_bytes()).digest(),
        "stage_verdicts": str(stage.relative_to(REPO)),
        "stage_scoring_report_replies": base_arm["skipped_existing"] + base_arm["written"]
        + base_arm["unscorable"], "stage_unscorable": base_arm["unscorable"]}
    return out


def grade_gap() -> dict:
    out = {}
    for name in SERVED:
        rec = json.loads((REPO / BY_NAME[name].axes_from).read_text())["identities"]
        safety = set(safety_identities(name))
        general = {k for k, v in rec.items() if v["group"] == "general"}
        rows = _rows(name)
        essays = sorted({r["instruction_id"] for r in rows})
        d = []
        for e in essays:
            s = [r["grade"] for r in rows if r["instruction_id"] == e and r["principal"] in safety]
            g = [r["grade"] for r in rows if r["instruction_id"] == e and r["principal"] in general]
            d.append(np.mean(s) - np.mean(g))
        d = np.array(d)
        out[name] = {"safety": sorted(safety), "general": sorted(general), "n_essays": len(essays),
                     "mean_gap_grades": float(d.mean()),
                     "paired_t": float(d.mean() / (d.std(ddof=1) / np.sqrt(d.size)))}
    return out


def main() -> None:
    path = OUT / "diagnostics.json"
    if path.exists():
        raise SystemExit(f"refusing to overwrite {path}")
    record = {"judge_position": judge_position(), "rejecting_cell": rejecting_cell(),
              "reply_length": reply_length(), "grade_gap": grade_gap()}
    path.write_text(json.dumps(record, indent=1))
    jp = record["judge_position"]
    print("order check:", jp["order_check"])
    print("pooled position:", jp["subjects"]["pooled"])
    for k, v in record["rejecting_cell"]["blocks"].items():
        print(k, {kk: round(vv["t"], 2) for kk, vv in v.items()})
    print("reply length:", {k: (v["median_words"], v["verdict_rows_covered"]) for k, v in record["reply_length"].items()})
    print("grade gap:", {k: (round(v["mean_gap_grades"], 3), round(v["paired_t"], 2)) for k, v in record["grade_gap"].items()})


if __name__ == "__main__":
    main()
