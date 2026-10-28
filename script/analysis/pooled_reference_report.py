"""Fold the B45 outputs into ``summary.json`` and ``comparison.md``.

    .venv/bin/python -m script.analysis.pooled_reference_report

Reads ``results.json``, ``cross_run.json``, ``placebo_replicates.jsonl`` and
``synthetic.json`` under ``out/main/calibration/pooled_reference/``, checks every
placebo replicate's registered S and p against B42's stored replicate, and
writes nothing anywhere else.
"""

from __future__ import annotations

import numpy as np

from script.analysis.placebo_calibration import OUT as PLACEBO_OUT, RUNS
from script.analysis.pooled_reference_calibration import NULLS, OUT
from src.common.file_io import load_json, read_jsonl, save_json
from src.compare.placebo_calibration import calibration_summary

POSITIVES = tuple(s.key for s in RUNS if s.key not in NULLS)
PLACEBO_COLUMNS = ("p_registered", "drop_top/values/p_ref", "drop_top/axes/p_ref",
                   "drop_top/candidates/p_ref", "drop_top2/values/p_ref",
                   "drop_top/p_exact_values", "drop_top/naive_p_single",
                   "drop_top/p_scaled", "drop_top/p_scaled_unfloored")


def _get(run: dict, path: str):
    if path == "p_registered":
        return run["p_registered"]
    variant, *rest = path.split("/")
    v = run["variants"][variant]
    if not v.get("computable"):
        return None
    if rest[0] in ("values", "axes", "candidates"):
        return v[rest[0]][rest[1]]
    if rest[0] in ("lambda", "p_scaled", "p_scaled_unfloored"):
        return v["drift_scaled"][rest[0]]
    return v[rest[0]]


def _null_block(ps: dict) -> dict:
    ok = [p for p in ps.values() if p is not None]
    return {"p": ps, "min": min(ok), "median": float(np.median(ok)), "max": max(ok),
            "n_le_05": int(sum(p <= 0.05 for p in ok)),
            "n_le_01": int(sum(p <= 0.01 for p in ok)), "n": len(ok)}


def summarize() -> dict:
    runs = load_json(OUT / "results.json")["runs"]
    cross = load_json(OUT / "cross_run.json")
    measures = ("p_registered", "drop_top/values/p_ref", "drop_top/axes/p_ref",
                "drop_top/candidates/p_ref", "drop_top/p_scaled",
                "drop_surviving/p_scaled")
    out: dict = {"nulls": {m: _null_block({k: _get(runs[k], m) for k in NULLS})
                           for m in measures}}
    for pool in cross["pools"]:
        out["nulls"][f"cross/{pool}"] = _null_block(
            {k: cross[pool][k]["values"]["p_ref"] for k in NULLS})
    out["positives_vs_nulls"] = {
        k: {m: {"p": _get(runs[k], m),
                "nulls_at_or_below": int(sum(q <= _get(runs[k], m)
                                             for q in out["nulls"][m]["p"].values()))
                if _get(runs[k], m) is not None else None}
            for m in measures} for k in POSITIVES}

    reps = list(read_jsonl(OUT / "placebo_replicates.jsonl"))
    b42 = {(r["key"], r["model"], r["replicate"]): r for r in read_jsonl(
        PLACEBO_OUT / "replicates.jsonl")}
    keys = [(r["key"], r["model"], r["replicate"]) for r in reps]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate placebo replicates")
    mism = [k for k, r in zip(keys, reps)
            if b42[k]["p"] != r["p_registered"] or abs(b42[k]["statistic"] - r["S"]) > 1e-12]
    def block(rs):
        return {c: calibration_summary([r[c] for r in rs if r.get(c) is not None])
                for c in PLACEBO_COLUMNS if any(r.get(c) is not None for r in rs)}
    multi = [r for r in reps if not r["tied"]]
    out["placebo"] = {
        "n_replicates": len(reps), "b42_mismatches": mism[:20],
        "n_b42_mismatches": len(mism), "n_tied": int(sum(r["tied"] for r in reps)),
        "pooled": block(reps), "pooled_untied": block(multi),
        "pooled_null_controls": block([r for r in reps if r["key"] in NULLS]),
        "per_run": {s.key: {m: block([r for r in reps
                                      if r["key"] == s.key and r["model"] == m])
                            for m in ("base", "target")} for s in RUNS},
        "lambda_median": float(np.median([r["drop_top/lambda"] for r in reps])),
        "total_seconds_cpu": float(sum(r["seconds"] for r in reps))}
    out["synthetic"] = load_json(OUT / "synthetic.json")
    out["cpu_seconds_real_runs"] = float(sum(r["seconds"] for r in runs.values()))
    save_json(OUT / "summary.json", out)
    return out


def _f(p) -> str:
    if p is None:
        return "n/a"
    return "<=0.0001" if p <= 1.0001e-4 else f"{p:.4f}"


def markdown(out: dict) -> str:
    runs = load_json(OUT / "results.json")["runs"]
    cross = load_json(OUT / "cross_run.json")
    lines = ["# Pooled within-run reference (B45, exploratory)", "",
             "p_ref floor is 1/10001. lambda and p_scaled use the drop_surviving "
             "reference when computable, else drop_top.", "",
             "| Run | Table | N | M | S | top | p reg | p_ref values / axes / cands "
             "(drop top) | p_ref drop2 | p_ref drop surv | R | naive R | lambda | "
             "p scaled | cross (nulls, all rows) | flags |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for spec in RUNS:
        r = runs[spec.key]
        v = r["variants"]
        lam_v = v["drop_surviving"] if v["drop_surviving"].get("computable") else v["drop_top"]
        dt = v["drop_top"]
        cr = cross["nulls_only_all_rows"].get(spec.key)
        flags = ", ".join(x for x in ("mirror" if r["mirror"] else "",
                                      "S tied" if r["S_tied_by_other_candidate"] else "")
                          if x)
        lines.append(
            f"| {spec.key} | {spec.table} | {r['n_candidates']} | {r['M']} | "
            f"{r['S']:.2f} | {r['top_candidate_name']} | {_f(r['p_registered'])} | "
            f"{_f(dt['values']['p_ref'])} / {_f(dt['axes']['p_ref'])} / "
            f"{_f(dt['candidates']['p_ref'])} | "
            f"{_f(_get(r, 'drop_top2/values/p_ref'))} | "
            f"{_f(_get(r, 'drop_surviving/values/p_ref'))} | "
            f"{dt['values']['R']:.3f} | {dt['naive_R']:.3f} | "
            f"{lam_v['drift_scaled']['lambda']:.3f} | "
            f"{_f(lam_v['drift_scaled']['p_scaled'])} | "
            f"{_f(cr['values']['p_ref']) if cr else 'n/a'} | {flags} |")
    lines += ["", "## Null controls", "",
              "| Measure | min | median | max | <=0.05 | <=0.01 |", "|---|---|---|---|---|---|"]
    for m, b in out["nulls"].items():
        lines.append(f"| {m} | {_f(b['min'])} | {_f(b['median'])} | {_f(b['max'])} | "
                     f"{b['n_le_05']}/{b['n']} | {b['n_le_01']}/{b['n']} |")
    pl = out["placebo"]
    lines += ["", "## Placebo (B42 splits, replicates 0-199 per run and model)", "",
              f"{pl['n_replicates']} replicates; registered S and p differ from B42 on "
              f"{pl['n_b42_mismatches']}; S tied by another candidate on {pl['n_tied']}; "
              f"median lambda {pl['lambda_median']:.3f}.", "",
              "| Measure | pool | n | share <=0.05 | share <=0.01 | KS p |",
              "|---|---|---|---|---|---|"]
    for pool in ("pooled", "pooled_untied", "pooled_null_controls"):
        for c, v in pl[pool].items():
            lines.append(f"| {c} | {pool} | {v['n']} | {v['share_le_05']:.3f} | "
                         f"{v['share_le_01']:.3f} | {v['ks_p']:.3g} |")
    syn = out["synthetic"]
    lines += ["", "## Synthetic (share of p <= 0.05 / <= 0.01)", "",
              "| Measure | " + " | ".join(s for s in ("null", "drift", "principal")) + " |",
              "|---|---|---|---|"]
    for c in syn["null"]["p"]:
        lines.append(f"| {c} | " + " | ".join(
            f"{syn[s]['p'][c]['share_le_05']:.3f} / {syn[s]['p'][c]['share_le_01']:.3f}"
            for s in ("null", "drift", "principal")) + " |")
    for c in ("lambda_median", "within_R_share_gt1", "within_naive_R_share_gt1",
              "cross_R_share_gt1", "cross_naive_R_share_gt1", "cross_R_median",
              "cross_naive_R_median"):
        lines.append(f"| {c} | " + " | ".join(f"{syn[s][c]:.3f}"
                                               for s in ("null", "drift", "principal")) + " |")
    return "\n".join(lines) + "\n"


def main() -> None:
    out = summarize()
    (OUT / "comparison.md").write_text(markdown(out))
    print(f"wrote {OUT / 'summary.json'} and {OUT / 'comparison.md'}")


if __name__ == "__main__":
    main()
