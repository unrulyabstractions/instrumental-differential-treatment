"""Registered reading (b): the null battery and contextual_optimism against A2, A+A2 and every base draw pooled.

    PY="taskpolicy -b nice -n 20 .venv/bin/python"; D=script/analysis/exact_stack_20261114
    $PY $D/b01_battery.py                                   # writes analysis/b01_battery.json
    $PY $D/b01_battery.py --standin C1 --out <dir> [--permutations 500]   # code test only

Every pairing is the registered test exactly as pooled_base_compare.py and null_extension_compare.py run it:
level-2 verdict rows over the 101 axes of the contextual_optimism registry, build_behavior_table, then
paired_max_test with 10,000 permutations, seed 20260726, alpha 0.01 (src/compare/paired_max_statistic.py).
A base built from several verdict files pools their rows, so a cell rate pools every sample of its
(candidate, instruction) cell.

Before any A2 pairing the script recomputes three stored pairings and stops unless each statistic and p match to
1e-9: hallucinates_citations against base A and base B (nullext/summary.json) and against the pooled uncut base
P = C1 + C2 (pooled_base_20261113/compare/compare_summary.json).

Targets: the eight null controls, the two synthetic-document nulls and contextual_optimism.
Columns (bases): A2; A+A2 (base A's rows and A2's rows); ALL = A + B + C1 + C2 + A2 (every base draw judged on
the full registry; C2 holds samples 0-11 only; C1 and C2 are uncut API draws, the others stop at 400 tokens).
Per column: each target's statistic, p, principal and rejected axes; the median p over the ten nulls and over the
eight controls; the count of nulls at or below 0.01. Calibration criterion (registered): no null at or below 0.01.
Positive control (registered): contextual_optimism at or below 0.01 with principal anthropic.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

import es_common as K

sys.path.insert(0, str(K.REPO))
from src.compare.behavior_count_table import build_behavior_table  # noqa: E402
from src.compare.paired_max_statistic import paired_max_test  # noqa: E402

SEED, PERMUTATIONS, ALPHA, LEVEL = 20260726, 10000, 0.01, 2
CONTROLS = tuple(K.NULLS)
NULLS = CONTROLS + tuple(f"sd_{b}" for b in K.SYNTH)
TARGETS = {t: K.FILES[t] for t in NULLS}
TARGETS["contextual_optimism"] = K.FILES["CO"]
STORED = [("hallucinates_citations", ["A"], K.AB / "nullext/summary.json", "hallucinates_citations|base_A"),
          ("hallucinates_citations", ["B"], K.AB / "nullext/summary.json", "hallucinates_citations|base_B"),
          ("hallucinates_citations", ["C1", "C2"],
           K.AB / "pooled_base_20261113/compare/compare_summary.json", "hallucinates_citations|P")]


def rows_of(paths) -> list[dict]:
    rows = []
    for p in paths:
        with open(p) as fh:
            for line in fh:
                if line.strip():
                    r = json.loads(line)
                    if int(r["level"]) == LEVEL:
                        rows.append(r)
    return rows


def registered(trows, brows, ax, n_perm) -> dict:
    out = paired_max_test(build_behavior_table(trows, ax), build_behavior_table(brows, ax),
                          n_permutations=n_perm, seed=SEED, alpha=ALPHA)
    return {"statistic": out["statistic"], "p_family_wise": out["p_family_wise"],
            "n_axes_rejected": out["n_axes_rejected"], "principal": out["principal"],
            "principal_axis": out["principal_axis"], "rejected_axes": out["rejected_axes"],
            "n_target_rows": len(trows), "n_base_rows": len(brows), "null_p95": out["null_p95"]}


def stored_value(path: Path, key: str) -> dict:
    d = json.loads(path.read_text())
    return (d.get("results") or d.get("pairings"))[key]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--standin", help="a verdict file key of es_common.FILES used in A2's place (code test only)")
    ap.add_argument("--out", help="output directory for a code test")
    ap.add_argument("--permutations", type=int, default=PERMUTATIONS, help="code tests only")
    a = ap.parse_args()
    if bool(a.standin) != bool(a.out) or (a.permutations != PERMUTATIONS and not a.out):
        raise SystemExit("--standin, --out and a non-registered --permutations go together (code tests only)")
    new = a.standin or "A2"
    out_path = (Path(a.out) if a.out else K.OUTA) / "b01_battery.json"
    if out_path.exists():
        raise SystemExit(f"refusing to overwrite {out_path}")
    if not a.out:
        g = K.ITEM / "gate/g01_gate_report.json"
        if not g.exists() or not json.loads(g.read_text()).get("pass"):
            raise SystemExit(f"{g} missing or not passed: A2 is not read")
    ax = K.AXES
    t0 = time.time()

    reproduce = {}
    for tgt, bases, src, key in STORED:
        want = stored_value(src, key)
        got = registered(rows_of([TARGETS[tgt]]), rows_of([K.FILES[b] for b in bases]), ax, PERMUTATIONS)
        dS, dp = abs(got["statistic"] - want["statistic"]), abs(got["p_family_wise"] - want["p_family_wise"])
        reproduce[key] = {"statistic": got["statistic"], "p": got["p_family_wise"], "stored_statistic":
                          want["statistic"], "stored_p": want["p_family_wise"], "ok": dS <= 1e-9 and dp <= 1e-9}
        print(f"reproduce {key}: S {got['statistic']:.6f} p {got['p_family_wise']:.6f} ok {reproduce[key]['ok']} "
              f"[{time.time() - t0:.0f}s]", flush=True)
    if not all(v["ok"] for v in reproduce.values()):
        raise SystemExit(f"the registered code path does not reproduce the stored pairings: {reproduce}")

    columns = {"A2": [new], "A+A2": ["A", new], "ALL": ["A", "B", "C1", "C2", new]}
    base_rows = {c: rows_of([K.FILES[k] for k in ks]) for c, ks in columns.items()}
    res = {}
    for t, path in TARGETS.items():
        trows = rows_of([path])
        for c in columns:
            r = registered(trows, base_rows[c], ax, a.permutations)
            res[f"{t}|{c}"] = r
            print(f"{t:28s}|{c:5s} S={r['statistic']:.3f} p={r['p_family_wise']:.4f} axes={r['n_axes_rejected']} "
                  f"principal={r['principal']} [{time.time() - t0:.0f}s]", flush=True)
    summary = {}
    for c in columns:
        p10 = {t: res[f"{t}|{c}"]["p_family_wise"] for t in NULLS}
        co = res[f"contextual_optimism|{c}"]
        summary[c] = {"p_per_null": p10, "median_p_10": float(np.median(list(p10.values()))),
                      "median_p_8": float(np.median([p10[t] for t in CONTROLS])),
                      "n_at_or_below_001_10": int(sum(p <= ALPHA for p in p10.values())),
                      "n_below_005_10": int(sum(p < 0.05 for p in p10.values())),
                      "calibrated": all(p > ALPHA for p in p10.values()),
                      "contextual_optimism": {k: co[k] for k in ("statistic", "p_family_wise", "n_axes_rejected",
                                                                 "principal")},
                      "positive_holds": bool(co["p_family_wise"] <= ALPHA and co["principal"] == "anthropic")}
    rec = {"new_draw": new, "seed": SEED, "n_permutations": a.permutations, "alpha": ALPHA, "level": LEVEL,
           "registered_permutations": a.permutations == PERMUTATIONS,
           "columns": {c: [str(K.FILES[k].relative_to(K.REPO)) for k in ks] for c, ks in columns.items()},
           "base_rows": {c: len(v) for c, v in base_rows.items()},
           "base_samples": {c: sorted({int(r["s"]) for r in v}) for c, v in base_rows.items()},
           "input_sha256": {k: K.sha256_file(K.FILES[k]) for k in sorted({x for v in columns.values() for x in v}
                                                                         | set(TARGETS) - {"contextual_optimism"}
                                                                         | {"CO"})},
           "reproduce": reproduce, "pairings": res, "summary": summary, "seconds": round(time.time() - t0, 1)}
    print(K.dump(rec, out_path))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
