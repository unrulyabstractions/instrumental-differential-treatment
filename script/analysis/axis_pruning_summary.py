"""Fold the axis-pruning replicates into a summary (B46, section C).

A pruned run "keeps" the reference result when it rejects at alpha 0.01 and,
where the full run names a candidate, names the same one. The reference is the
full run as reproduced by the gate, so every comparison is against the paper's
test on the paper's data.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from script.analysis.zero_compute_runner import OUT
from src.common.file_io import load_json, read_jsonl, save_json
from src.compare.axis_pruning_selection import judge_cost_share
from src.score.judge_prompts import MAX_AXES_PER_CALL


def _fold(sel: list[dict], ref: dict, pilot_share: float) -> dict:
    out = {"n": len(sel), "share_reject": float(np.mean([r["loyal"] for r in sel])),
           "median_p": float(np.median([r["p"] for r in sel])),
           "share_argmax_same": float(np.mean([r["argmax"] == ref["argmax"] for r in sel])),
           "share_max_axis_same": float(np.mean([r["max_axis"] == ref["max_axis"] for r in sel]))}
    if ref["named"] is not None:
        out["share_named_same"] = float(np.mean([r["named"] == ref["named"] for r in sel]))
    out["share_named_other"] = float(np.mean(
        [r["named"] is not None and r["named"] != ref["named"] for r in sel]))
    kept = [r["meta"]["n_kept"] for r in sel]
    total = sel[0]["meta"]["n_axes_total"]
    out["median_kept"] = float(np.median(kept))
    out["range_kept"] = [int(min(kept)), int(max(kept))]
    if sel[0]["meta"]["design"] == "heldout":
        cost = [judge_cost_share(total, k, pilot_share, MAX_AXES_PER_CALL) for k in kept]
        out["median_cost"] = {f: float(np.median([c[f] for c in cost])) for f in cost[0]}
    return out


def summarize(folder: Path, pilot_share: float) -> dict:
    ref = {r["key"]: r["full"] for r in load_json(OUT / "reproduction.json")["runs"]}
    rows = list(read_jsonl(folder / "replicates.jsonl"))
    out = {"axes_per_call": MAX_AXES_PER_CALL, "pilot_share": pilot_share, "runs": {}}
    for key in ref:
        mine = [r for r in rows if r["key"] == key]
        if not mine:
            continue
        entry = {"reference": ref[key], "n_axes": mine[0]["meta"]["n_axes_total"]}
        for design, k in (("heldout_all", None), ("heldout", 25), ("heldout", 50)):
            sel = [r for r in mine if r["meta"]["design"] == design and r["meta"]["k"] == k]
            entry[design if k is None else f"{design}_k{k}"] = _fold(sel, ref[key], pilot_share)
        for k in (25, 50):
            (opt,) = [r for r in mine if r["meta"]["design"] == "optimistic"
                      and r["meta"]["k"] == k]
            entry[f"optimistic_k{k}"] = {f: opt[f] for f in
                                         ("p", "loyal", "named", "argmax", "max_axis")}
            entry[f"optimistic_k{k}"]["n_kept"] = opt["meta"]["n_kept"]
        entry["cpu_seconds"] = float(sum(r["seconds"] for r in mine))
        out["runs"][key] = entry
    save_json(folder / "summary.json", out)
    _markdown(folder, out)
    return out


def _cell(d: dict, ref: dict) -> str:
    named = (f"{d['share_named_same']:.2f}" if ref["named"]
             else f"other {d['share_named_other']:.2f}")
    # Against a reference that does not reject, a rejection is a disagreement.
    flag = "" if ref["loyal"] else " (ref no)"
    return f"{d['share_reject']:.2f}{flag} / {named}"


def _markdown(folder: Path, s: dict) -> None:
    lines = ["# Axis-pruning simulation (B46 C)", "",
             f"Pilot = random {s['pilot_share']:.0%} of instructions, 20 pilots per run. "
             "Cells read `share rejecting at 0.01 / share naming the reference's candidate` "
             "(`other x`: the reference names nobody, x is the share naming someone). "
             f"Cost = (reply, axis) verdicts and judge calls ({s['axes_per_call']} axes per "
             "call), pilot included, as a share of judging every axis everywhere. "
             "`(ref no)`: the full run does not reject, so the share is disagreement with it.",
             "",
             "Reading notes. The 20 held-out sets overlap and are all subsets of the reference "
             "data, so a share is sensitivity to the split, not an error rate or a power. Only "
             "the gap between a pruned column and `held-out, all axes` measures pruning; the "
             "rest comes from dropping the pilot instructions. `select on all` picks axes by "
             "pooled firing rate on every instruction and tests on every instruction: its p is "
             "valid, because pooled rates do not change under the registered permutation, but "
             "it saves no judging. third_party_politics has 8 axes, so no column prunes it. "
             "The simulation assumes a verdict does not depend on which axes share its judge "
             "call; that is untested.", "",
             "| Run | K | ref p | ref named | held-out, all axes | k25 kept | k25 | k25 cost "
             "(verdicts, calls) | k50 kept | k50 | k50 cost (verdicts, calls) | "
             "select on all k25: p, named | select on all k50: p, named |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for key, e in s["runs"].items():
        ref = e["reference"]
        parts = [key, str(e["n_axes"]), f"{ref['p']:.4f}", str(ref["named"]),
                 _cell(e["heldout_all"], ref)]
        for k in (25, 50):
            d = e[f"heldout_k{k}"]
            parts += [f"{d['median_kept']:.1f} ({d['range_kept'][0]}-{d['range_kept'][1]})",
                      _cell(d, ref),
                      f"{d['median_cost']['axis_verdicts']:.2f}, "
                      f"{d['median_cost']['judge_calls']:.2f}"]
        for k in (25, 50):
            o = e[f"optimistic_k{k}"]
            parts.append(f"{o['p']:.4f}, {o['named']}")
        lines.append("| " + " | ".join(parts) + " |")
    (folder / "summary.md").write_text("\n".join(lines) + "\n")
