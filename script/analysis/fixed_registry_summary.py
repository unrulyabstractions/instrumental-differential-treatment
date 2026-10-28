"""Fold the fixed-registry replicates into one row per run (B49, internal only).

The registered row must equal the stored comparison summary (S and p exactly,
and the stored name where the summary carries one), or nothing is written. For
the 18 gate runs, every (a) pilot row is also checked against the axis-pruning
analysis's k=25 replicate for the same run and pilot, which used the same
split and selection: S, p and name must be equal.
"""

from __future__ import annotations

from collections import Counter

import numpy as np

from script.analysis.fixed_registry_runs import fixed_runs
from script.analysis.zero_compute_runner import OUT
from src.common.file_io import load_json, read_jsonl, save_json

DIR = OUT / "fixed_registry"
PRUNING = OUT / "axis_pruning" / "replicates.jsonl"


def _cell(r: dict) -> dict:
    return {"S": r["S"], "p": r["p"], "reject_01": r["loyal"], "reject_05": r["reject_05"],
            "named_01": r["named"], "named_05": r["named_05"], "argmax": r["argmax"],
            "max_axis": r["max_axis"], "n_axes": r["n_axes"],
            "n_instructions": r["n_instructions"]}


def _gate(run, reg: dict) -> dict:
    stored = load_json(run.summary)["reference_contrast"][f"L{run.level}"]["paired_max_test"]
    named = (stored.get("attribution") or {}).get("named", "absent")
    ok = (reg["S"] == stored["statistic"] and reg["p"] == stored["p_family_wise"]
          and (named == "absent" or named == reg["named"]))
    if not ok:
        raise SystemExit(f"{run.key}: registered rerun differs from {run.summary}")
    return {"stored_S": stored["statistic"], "stored_p": stored["p_family_wise"],
            "stored_named": named, "match": True}


def _pilots(rows: list[dict]) -> dict:
    p = np.array([r["p"] for r in rows])
    return {"n": len(rows), "median_p": float(np.median(p)),
            "share_reject_01": float(np.mean(p <= 0.01)),
            "share_reject_05": float(np.mean(p <= 0.05)),
            "named_01": dict(Counter(str(r["named"]) for r in rows).most_common()),
            "named_05": dict(Counter(str(r["named_05"]) for r in rows).most_common()),
            "median_kept": float(np.median([r["n_axes"] for r in rows]))}


def _changes(ref: dict, alt: dict | None) -> list[str]:
    """Each decision or name at 0.01 and 0.05 that differs from the registered run."""
    if alt is None:
        return []
    out = []
    for a, label in (("01", "0.01"), ("05", "0.05")):
        for field in ("reject", "named"):
            if ref[f"{field}_{a}"] != alt[f"{field}_{a}"]:
                out.append(f"{field}@{label}: {ref[f'{field}_{a}']} -> {alt[f'{field}_{a}']}")
    return out


def summarize() -> dict:
    rows = list(read_jsonl(DIR / "replicates.jsonl"))
    by_id = {r["id"]: r for r in rows}
    selections = load_json(DIR / "selections.json")
    pruning = ({r["id"]: r for r in read_jsonl(PRUNING)} if PRUNING.exists() else {})
    out, cross = {}, {"checked": 0, "equal": 0}
    for run in fixed_runs():
        key = run.key
        reg = by_id[f"{key}|registered"]
        pilots = sorted((r for r in rows if r["key"] == key and r["meta"]["design"] == "pilot"),
                        key=lambda r: r["meta"]["pilot"])
        held = [r for r in rows if r["key"] == key and r["meta"]["design"] == "heldout_all"]
        for r in pilots:
            old = pruning.get(f"{key}|heldout|k25|{r['meta']['pilot']}")
            if old is not None:
                cross["checked"] += 1
                cross["equal"] += (old["S"] == r["S"] and old["p"] == r["p"]
                                   and old["named"] == r["named"])
        entry = {"registered": _cell(reg), "gate": _gate(run, reg),
                 "a_pilot0": _cell(pilots[0]), "a_pilot0_axes": pilots[0]["kept_axis_ids"],
                 "a_all_pilots": _pilots(pilots), "heldout_all_pilots": _pilots(held),
                 "heldout_all_pilot0": _cell(min(held, key=lambda r: r["meta"]["pilot"])),
                 "loro": {}}
        for score in ("fire", "abs_t"):
            r = by_id.get(f"{key}|loro_{score}")
            entry["loro"][score] = (None if r is None else
                                    {**_cell(r), "axes": r["kept_axis_ids"],
                                     "pool": r["meta"]["pool"]})
        entry["loro_skipped"] = selections[key].get("skipped")
        ref = entry["registered"]
        entry["changes"] = {"a_pilot0": _changes(ref, entry["a_pilot0"]),
                            "heldout_all_pilot0": _changes(ref, entry["heldout_all_pilot0"]),
                            **{f"loro_{s}": _changes(ref, entry["loro"][s])
                               for s in ("fire", "abs_t")}}
        out[key] = entry
    if cross["checked"] != cross["equal"]:
        raise SystemExit(f"pilot rows differ from the axis-pruning replicates: {cross}")
    save_json(DIR / "summary.json", {"runs": out, "cross_check_axis_pruning": cross,
                                     "n_replicates": len(rows)})
    _table(out)
    return out


def _fmt(c: dict | None) -> str:
    if c is None:
        return "skipped | "
    return f"{c['p']:.4f} | {c['named_01'] or '-'}"


def _table(out: dict) -> None:
    lines = ["| Run | registered p | name | (a) pilot 0 p | name | (a) 20 pilots: share p<=0.01 / "
             "<=0.05 | (b) fire p | name | (b) abs t p | name |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for key, e in out.items():
        a = e["a_all_pilots"]
        lines.append(f"| {key} | {_fmt(e['registered'])} | {_fmt(e['a_pilot0'])} | "
                     f"{a['share_reject_01']:.2f} / {a['share_reject_05']:.2f} | "
                     f"{_fmt(e['loro']['fire'])} | {_fmt(e['loro']['abs_t'])} |")
    (DIR / "table.md").write_text("\n".join(lines) + "\n")
