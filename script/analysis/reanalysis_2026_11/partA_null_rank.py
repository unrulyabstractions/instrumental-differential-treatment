"""Part A (e): contextual_optimism's S ranked among the nulls on its roster and axes.

    .venv/bin/python -m script.analysis.reanalysis_2026_11.partA_null_rank

The ten nulls are the eight AuditBench null controls and the two
synthetic-document nulls of the null extension. All eleven organisms are LoRA
deltas over one base, and all are scored on the contextual_optimism registry
with the same six candidates and 36 instructions; this script checks that.

For base A (the shared stage-6 base) and base B (the null extension's fresh
base), every pairing is run through ``null_extension_compare.run_pairing``
(the registered test, 10,000 permutations, seed 20260726, alpha 0.01), and
checked against stage 6 and against ``out/main/auditbench/nullext/summary.json``.
The rank-based p is (1 + number of nulls with S at least as large) / (1 + N),
whose floor is 1 / (1 + N).

The target-only S (no base) of the same eleven organisms is read from this
run's ``baseline_role.json`` and ranked the same way.

Writes only ``out/main/reanalysis_20261113/partA/null_rank.json``.
"""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from script.analysis.null_extension_compare import (AB, AXES, BASE_A, BASE_B, EXT, SYNTH,
                                                    _null_target, _table, run_pairing,
                                                    stored_null)
from src.common.experiment_layout import _AB_CONTROLS
from src.common.file_io import load_json

OUT = Path("out/main/reanalysis_20261113/partA")
CO_TARGET = AB / "contextual_optimism/judge_mini/verdicts_target.jsonl"
CO_SUMMARY = AB / "contextual_optimism/judge_mini/compare/comparison_summary.json"
NULLEXT_SUMMARY = EXT / "summary.json"


def organisms() -> dict[str, Path]:
    out = {"contextual_optimism": CO_TARGET}
    out.update({c: _null_target(c) for c in _AB_CONTROLS})
    out.update({f"sd_{b}": EXT / "synth" / b / "verdicts_target.jsonl" for b in SYNTH})
    return out


def _pair(args: tuple[str, str, str, str]) -> tuple[str, dict]:
    name, target, base, _ = args
    axes = [a["axis_id"] for a in load_json(AXES)["axes"]]
    return name, run_pairing(Path(target), Path(base), axes)


def rank_p(s_obs: float, null_s: list[float]) -> dict:
    n = len(null_s)
    at_least = sum(1 for s in null_s if s >= s_obs)
    return {"S_observed": s_obs, "N_nulls": n, "n_nulls_at_least_as_large": at_least,
            "rank_from_top": 1 + sum(1 for s in null_s if s > s_obs),
            "rank_p": (1 + at_least) / (1 + n), "floor": 1 / (1 + n),
            "max_null_S": max(null_s), "ratio_to_max_null_S": s_obs / max(null_s),
            "null_S_sorted_desc": sorted(null_s, reverse=True)}


def main() -> None:
    out_path = OUT / "null_rank.json"
    if out_path.exists():
        raise SystemExit(f"{out_path} exists; never overwritten")
    orgs = organisms()
    axes = [a["axis_id"] for a in load_json(AXES)["axes"]]

    # Same roster, instructions and axes for every organism and both bases.
    shape = {}
    for name, path in {**orgs, "base_A": BASE_A, "base_B": BASE_B}.items():
        t = _table(Path(path), axes)
        shape[name] = {"candidates": list(t.principals), "n_instructions": len(t.blocks),
                       "instructions_sha": hash(t.blocks), "n_axes": len(t.axes),
                       "n_responses": t.n_responses}
    ref = shape["contextual_optimism"]
    same = {k: (v["candidates"] == ref["candidates"] and v["n_axes"] == ref["n_axes"]
                and v["instructions_sha"] == ref["instructions_sha"]) for k, v in shape.items()}
    if not all(same.values()):
        raise SystemExit(f"roster, instructions or axes differ: {same}")
    for v in shape.values():
        v.pop("instructions_sha")

    jobs = [(f"{o}|{b}", str(p), str(bp), b) for o, p in orgs.items()
            for b, bp in (("base_A", BASE_A), ("base_B", BASE_B))]
    with ProcessPoolExecutor(max_workers=min(12, len(jobs))) as ex:
        got = dict(ex.map(_pair, jobs))

    # Checks: stage 6 for every base-A pairing that stage 6 ran, and the null
    # extension's stored summary for every pairing it holds.
    stored_ext = load_json(NULLEXT_SUMMARY)["results"]
    checks = []
    co_stage6 = load_json(CO_SUMMARY)["reference_contrast"]["L2"]["paired_max_test"]
    for name, res in got.items():
        org, base = name.split("|")
        wants = []
        if base == "base_A" and org in _AB_CONTROLS:
            wants.append(("stage 6", stored_null(org)))
        if name == "contextual_optimism|base_A":
            wants.append(("stage 6", co_stage6))
        if name in stored_ext:
            wants.append(("nullext summary.json", stored_ext[name]))
        for what, want in wants:
            checks.append({"pairing": name, "against": what,
                           "stored_S": want["statistic"], "got_S": res["statistic"],
                           "stored_p": want["p_family_wise"], "got_p": res["p_family_wise"],
                           "match": (res["statistic"] == want["statistic"]
                                     and res["p_family_wise"] == want["p_family_wise"])})
    bad = [c for c in checks if not c["match"]]
    if bad:
        raise SystemExit(f"recompute does not reproduce stored values: {bad}")

    nulls = [o for o in orgs if o != "contextual_optimism"]
    by_base = {}
    for b in ("base_A", "base_B"):
        null_s = [got[f"{o}|{b}"]["statistic"] for o in nulls]
        by_base[b] = {**rank_p(got[f"contextual_optimism|{b}"]["statistic"], null_s),
                      "per_organism": {o: {"S": got[f"{o}|{b}"]["statistic"],
                                           "p": got[f"{o}|{b}"]["p_family_wise"],
                                           "n_axes_rejected": got[f"{o}|{b}"]["n_axes_rejected"],
                                           "principal": got[f"{o}|{b}"]["principal"]}
                                       for o in orgs}}

    # Target-only S from this run's baseline-role record (no base involved).
    br_path = OUT / "baseline_role.json"
    target_only = {}
    if br_path.is_file():
        br = load_json(br_path)["results"]
        key = {"contextual_optimism": "auditbench_contextual_optimism",
               **{c: f"auditbench_{c}" for c in _AB_CONTROLS},
               **{f"sd_{b}": f"nullext_sd_{b}" for b in SYNTH}}
        for variant in ("target_only_median", "target_only_mean"):
            s = {o: br[f"{key[o]}|{variant}|full"]["S"] for o in orgs}
            p = {o: br[f"{key[o]}|{variant}|full"]["p"] for o in orgs}
            target_only[variant] = {**rank_p(s["contextual_optimism"], [s[o] for o in nulls]),
                                    "per_organism": {o: {"S": s[o], "p": p[o]} for o in orgs}}
    else:
        target_only = {"skipped": f"{br_path} not found"}

    record = {"axes": str(AXES), "base_A": str(BASE_A), "base_B": str(BASE_B),
              "nulls": nulls, "shape": shape, "checks": checks,
              "registered_rank": by_base, "target_only_rank": target_only,
              "rule": "rank_p = (1 + #nulls with S >= S_co) / (1 + N); floor 1/(1+N)"}
    with out_path.open("x") as fh:
        json.dump(record, fh, indent=1)
    for b, r in by_base.items():
        print(f"{b}: S_co={r['S_observed']:.3f} max null S={r['max_null_S']:.3f} "
              f"rank p={r['rank_p']:.4f} floor={r['floor']:.4f}")
    for v, r in target_only.items():
        if isinstance(r, dict) and "rank_p" in r:
            print(f"{v}: S_co={r['S_observed']:.3f} max null S={r['max_null_S']:.3f} "
                  f"n at least as large={r['n_nulls_at_least_as_large']} rank p={r['rank_p']:.4f}")
    print(f"{len(checks)} checks, all match")


if __name__ == "__main__":
    main()
