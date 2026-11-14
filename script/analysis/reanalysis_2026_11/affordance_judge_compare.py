"""Judge affordance pass: verdicts with and without the judge's hidden-behavior line.

    uv run python script/analysis/reanalysis_2026_11/affordance_judge_compare.py --pilot
    uv run python script/analysis/reanalysis_2026_11/affordance_judge_compare.py

``with_line`` is the masked probe's stored unmasked pass (the paper's level-2
system prompt). ``without_line`` is this pass: the same rows, registry, seat
and requests, with the one line that tells the judge a hidden behavior may be
present removed. Removing the line is the only change between the two.

Reported, per arm:

* verdict agreement and Cohen's kappa, pooled over axes and per axis;
* per-axis yes rates with and without the line, the shift, and an exact
  McNemar p (flagged below 0.01 / 25);
* the same agreement and kappa for two reference pairs from the masked probe:
  masked against unmasked on the replies the mask left byte-identical (the
  same prompt judged twice, so the judge's own resampling noise), and the
  unmasked rejudge against the paper's stored verdicts.

And on both arms together: the registered test (``paired_max_test``, 10,000
permutations, seed 20260726, alpha 0.01) and the naming rule with and without
the line, the surviving axes of each, the Anthropic excess in yes-rate units on
the axes the with-line test rejects, and the signed verdict shift by group.
The reading is fixed in advance and computed here (``reading``). Statistical
helpers come from ``masked_judge_compare.py`` so both probes share one
definition. Writes ``comparison.json`` (or ``comparison_pilot.json``);
refuses to overwrite.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))

from src.common.file_io import load_json, read_jsonl  # noqa: E402

RUN = REPO / "out/main/auditbench/contextual_optimism"
OUT = RUN / "affordance_judge_20261114"
MASKED = RUN / "masked_judge_20261113"
SEED, DRAWS, ALPHA, LEVEL = 20260726, 2000, 0.01, 2
ARMS = ("target", "base")


def _mc():
    spec = importlib.util.spec_from_file_location("masked_judge_compare",
                                                  HERE / "masked_judge_compare.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MC = _mc()


def _key(row) -> tuple[str, int]:
    return row["prompt_id"], int(row["s"])


def _verdicts(path: Path) -> dict:
    rows = [r for r in read_jsonl(path) if int(r["level"]) == LEVEL]
    out = {_key(r): r for r in rows}
    if len(out) != len(rows):
        raise SystemExit(f"duplicate rows in {path}")
    return out


def _texts(path: Path) -> dict:
    return {_key(r): r["text"] for r in read_jsonl(path)}


def _kappa(po: float, pa: float, pb: float) -> float | None:
    pe = pa * pb + (1 - pa) * (1 - pb)
    return None if pe >= 1 else (po - pe) / (1 - pe)


def _pair(a: dict, b: dict, keys, axes) -> dict:
    """``MC._agreement`` plus Cohen's kappa and per-axis yes rates (a minus b)."""
    out = MC._agreement(a, b, keys, axes)
    out["kappa"] = (round(_kappa(out["agreement"], out["yes_rate_a"], out["yes_rate_b"]), 4)
                    if out["n_verdict_pairs"] else None)
    kappas = []
    for ax in axes:
        xs = [(a[k]["verdicts"].get(ax), b[k]["verdicts"].get(ax)) for k in keys]
        xs = [(bool(x), bool(y)) for x, y in xs if x is not None and y is not None]
        n = len(xs)
        if not n:
            continue
        ya, yb = sum(x for x, _ in xs) / n, sum(y for _, y in xs) / n
        po = sum(x == y for x, y in xs) / n
        k = _kappa(po, ya, yb)
        out["per_axis"][ax].update(n=n, yes_rate_a=round(ya, 4), yes_rate_b=round(yb, 4),
                                   shift_a_minus_b=round(ya - yb, 4), agreement=round(po, 4),
                                   kappa=None if k is None else round(k, 4))
        if k is not None:
            kappas.append(k)
    out["kappa_mean_over_axes"] = round(float(np.mean(kappas)), 4) if kappas else None
    out["n_axes_mcnemar_flagged"] = len(out["axes_mcnemar_p_below_bonferroni_0.01"])
    return out


def _brief(x: dict) -> dict:
    return {k: x[k] for k in ("n_rows", "n_verdict_pairs", "agreement", "kappa",
                              "kappa_mean_over_axes", "yes_rate_a", "yes_rate_b",
                              "n_axes_mcnemar_flagged")}


def _references(axes) -> dict:
    """Agreement and kappa of the masked probe's two reference pairs, per arm."""
    stored = {}
    for arm in ARMS:
        rows = {}
        for r in read_jsonl(MC.STORED[arm]):
            if int(r["level"]) == LEVEL:
                rows[_key(r)] = r
        stored[arm] = rows
    out = {}
    for arm in ARMS:
        vm = _verdicts(MASKED / f"pass_masked_{arm}/verdicts_{arm}.jsonl")
        vu = _verdicts(MASKED / f"pass_unmasked_{arm}/verdicts_{arm}.jsonl")
        tm = _texts(MASKED / f"pass_masked_{arm}/responses_{arm}.jsonl")
        tu = _texts(MASKED / f"pass_unmasked_{arm}/responses_{arm}.jsonl")
        same = sorted(k for k in set(vm) & set(vu) if tm[k] == tu[k])
        in_stored = sorted(k for k in vu if k in stored[arm])
        out[arm] = {
            "same_prompt_twice__masked_vs_unmasked_on_unchanged": _brief(_pair(vm, vu, same, axes)),
            "unmasked_rejudge_vs_stored_101_axis_context": _brief(_pair(vu, stored[arm], in_stored, axes)),
        }
    return out


def _excess(rows: dict, axes, sign) -> dict:
    """Anthropic's yes rate minus the other five's mean, target minus base, signed."""
    def rates(rs):
        acc = defaultdict(list)
        for r in rs:
            acc[r["principal"]].append([float(bool(r["verdicts"][a])) for a in axes])
        return {p: np.mean(x, axis=0) for p, x in acc.items()}
    t, b = rates(rows["target"]), rates(rows["base"])
    others = [p for p in t if p != "anthropic"]
    gap = (t["anthropic"] - np.mean([t[p] for p in others], axis=0)) \
        - (b["anthropic"] - np.mean([b[p] for p in others], axis=0))
    signed = np.array([sign[a] for a in axes]) * gap
    return {"mean_signed_excess": round(float(signed.mean()), 4),
            "per_axis": {a: round(float(x), 4) for a, x in zip(axes, signed)}}


def _group_shift(v_with, v_without, keys, axes, sign) -> dict:
    """Mean per-reply shift (without minus with) on ``axes``, signed toward the effect."""
    rng = np.random.default_rng(SEED)
    out = {}
    for arm in ARMS:
        per = defaultdict(list)
        for k in keys[arm]:
            a, b = v_without[arm][k]["verdicts"], v_with[arm][k]["verdicts"]
            xs = [sign[x] * (float(bool(a[x])) - float(bool(b[x]))) for x in axes
                  if a.get(x) is not None and b.get(x) is not None]
            per[v_with[arm][k]["principal"]].append(np.mean(xs))
            per["all"].append(np.mean(xs))
        for group, xs in sorted(per.items()):
            xs = np.asarray(xs)
            boots = [rng.choice(xs, size=len(xs), replace=True).mean() for _ in range(DRAWS)]
            out[f"{arm}|{group}"] = {"n_replies": int(len(xs)),
                                     "signed_shift_mean": round(float(xs.mean()), 5),
                                     "ci95": [round(float(np.quantile(boots, 0.025)), 5),
                                              round(float(np.quantile(boots, 0.975)), 5)]}
    return out


def _reading(w: dict, wo: dict) -> dict:
    rej_w, rej_wo = w["p_family_wise"] <= ALPHA, wo["p_family_wise"] <= ALPHA
    sw, swo = set(w["rejected_axes"]), set(wo["rejected_axes"])
    if rej_w and not rej_wo:
        code, text = "stops_rejecting", ("contextual_optimism stops rejecting without the line: "
                                         "a major finding, reported at once")
    elif wo["n_axes_rejected"] < w["n_axes_rejected"]:
        code, text = "fewer_axes", ("fewer surviving axes without the line: "
                                    "the line raises sensitivity")
    elif rej_w == rej_wo and w["named"] == wo["named"] and sw == swo:
        code, text = "same", ("same verdicts without the line: "
                              "telling the judge does not drive the result")
    else:
        code, text = "other", ("rejection unchanged and no fewer axes, but the surviving set or "
                               "the named group differs; no fixed reading covers this case")
    return {"code": code, "text": text, "rejects_with_line": rej_w,
            "rejects_without_line": rej_wo, "named_with_line": w["named"],
            "named_without_line": wo["named"], "n_axes_with_line": w["n_axes_rejected"],
            "n_axes_without_line": wo["n_axes_rejected"],
            "fixed_readings": {
                "same": "same verdicts without the line: telling the judge does not drive the result",
                "fewer_axes": "fewer surviving axes: the line raises sensitivity",
                "stops_rejecting": "contextual_optimism stops rejecting: a major finding"}}


def run_pilot() -> None:
    path = OUT / "comparison_pilot.json"
    if path.exists():
        raise SystemExit(f"refusing to overwrite {path}")
    axes = [a["axis_id"] for a in load_json(MASKED / "registry/scoring_questions.json")["axes"]]
    out = {"registry_axes": axes, "arms": {}}
    for arm in ARMS:
        wo = _verdicts(OUT / f"pilot/verdicts_{arm}.jsonl")
        w = _verdicts(MASKED / f"pilot_unmasked/verdicts_{arm}.jsonl")
        if _texts(OUT / f"pilot/responses_{arm}.jsonl") != _texts(MASKED / f"pilot_unmasked/responses_{arm}.jsonl"):
            raise SystemExit(f"pilot {arm}: replies differ from the stored pilot")
        keys = sorted(set(wo) & set(w))
        out["arms"][arm] = {"rows_without_line": len(wo), "rows_paired": len(keys),
                            "without_vs_with": _pair(wo, w, keys, axes)}
        print(arm, _brief(out["arms"][arm]["without_vs_with"]))
    path.write_text(json.dumps(out, indent=2, sort_keys=True))
    print("wrote", path)


def run_full() -> None:
    path = OUT / "comparison.json"
    if path.exists():
        raise SystemExit(f"refusing to overwrite {path}")
    axes = [a["axis_id"] for a in load_json(MASKED / "registry/scoring_questions.json")["axes"]]
    v_with, v_without, keys = {}, {}, {}
    result = {"registry_axes": axes, "arms": {}, "tests": {}}
    for arm in ARMS:
        t_with = _texts(MASKED / f"pass_unmasked_{arm}/responses_{arm}.jsonl")
        t_without = _texts(OUT / f"pass_{arm}/responses_{arm}.jsonl")
        if t_with != t_without:
            raise SystemExit(f"{arm}: the two passes hold different replies")
        v_with[arm] = _verdicts(MASKED / f"pass_unmasked_{arm}/verdicts_{arm}.jsonl")
        v_without[arm] = _verdicts(OUT / f"pass_{arm}/verdicts_{arm}.jsonl")
        keys[arm] = sorted(set(v_with[arm]) & set(v_without[arm]))
        pair = _pair(v_without[arm], v_with[arm], keys[arm], axes)
        result["arms"][arm] = {"rows_in_pass": len(t_with), "rows_judged_with_line": len(v_with[arm]),
                               "rows_judged_without_line": len(v_without[arm]),
                               "rows_judged_in_both": len(keys[arm]),
                               "without_vs_with": pair}
        print(arm, _brief(pair), flush=True)
    result["references"] = _references(axes)
    sets = {"with_line": v_with, "without_line": v_without}
    for name, v in sets.items():
        result["tests"][name] = MC._test([v["target"][k] for k in keys["target"]],
                                         [v["base"][k] for k in keys["base"]], axes)
        r = result["tests"][name]
        print(f"{name:13s} S={r['statistic']} p={r['p_family_wise']} named={r['named']} "
              f"axes={r['n_axes_rejected']} pairs={r['n_pairs_rejected']} argmax={r['argmax_axis']}",
              flush=True)
    stored_cmp = load_json(MASKED / "comparison.json")["tests"]
    w = result["tests"]["with_line"]
    full = all(len(keys[a]) == 1296 for a in ARMS)
    if full:
        su = stored_cmp["unmasked"]
        for f in ("statistic", "p_family_wise", "rejected_axes", "named", "n_pairs_rejected"):
            if w[f] != su[f]:
                raise SystemExit(f"with-line test does not reproduce the stored unmasked test on {f}")
    result["with_line_reproduces_stored_unmasked_test"] = full
    result["reference_tests_from_masked_probe"] = {
        k: {f: stored_cmp[k][f] for f in ("statistic", "p_family_wise", "n_axes_rejected",
                                          "rejected_axes", "named", "argmax_axis")}
        for k in ("unmasked", "masked", "hybrid", "stored")}
    sw, swo = set(w["rejected_axes"]), set(result["tests"]["without_line"]["rejected_axes"])
    result["surviving_axes"] = {"both": sorted(sw & swo), "only_with_line": sorted(sw - swo),
                                "only_without_line": sorted(swo - sw)}
    ref_axes = sorted(sw)
    sign = {a: float(np.sign(w["t_anthropic_by_axis"][a])) for a in ref_axes}
    rows = {name: {arm: [v[arm][k] for k in keys[arm]] for arm in ARMS} for name, v in sets.items()}
    result["excess_size_on_with_line_axes"] = {
        "axes": ref_axes, "sign_of_anthropic_t_with_line": sign,
        **{name: _excess(rows[name], ref_axes, sign) for name in sets}}
    e = result["excess_size_on_with_line_axes"]
    e["without_minus_with"] = round(e["without_line"]["mean_signed_excess"]
                                    - e["with_line"]["mean_signed_excess"], 4)
    result["group_shift_on_with_line_axes"] = _group_shift(v_with, v_without, keys, ref_axes, sign)
    result["reading"] = _reading(w, result["tests"]["without_line"])
    path.write_text(json.dumps(result, indent=2, sort_keys=True))
    print(json.dumps(result["surviving_axes"]), "\n", result["reading"]["text"])
    print("wrote", path)


def run_t_shift() -> None:
    """How far Anthropic's t moves per axis when the line goes, beside rejudges that keep it.

    Reference pairs come from the masked probe's stored tests, all with the
    line: the unmasked rejudge against the masked rejudge (a full second
    judging; masking itself moved no verdict beyond resampling there), the
    unmasked rejudge against the hybrid (a second judging of the replies that
    name a candidate only), and the paper's stored verdicts against the
    unmasked rejudge. Writes ``t_shift.json``; refuses to overwrite.
    """
    path = OUT / "t_shift.json"
    if path.exists():
        raise SystemExit(f"refusing to overwrite {path}")
    mine = load_json(OUT / "comparison.json")["tests"]
    ref = load_json(MASKED / "comparison.json")["tests"]
    tests = {"with_line": mine["with_line"], "without_line": mine["without_line"],
             "masked": ref["masked"], "hybrid": ref["hybrid"], "stored": ref["stored"]}
    if tests["with_line"]["t_anthropic_by_axis"] != ref["unmasked"]["t_anthropic_by_axis"]:
        raise SystemExit("with-line t values differ from the stored unmasked test")
    pairs = {"line_removed": ("with_line", "without_line"),
             "full_rejudge_with_line__unmasked_vs_masked": ("with_line", "masked"),
             "partial_rejudge_with_line__unmasked_vs_hybrid": ("with_line", "hybrid"),
             "paper_stored_vs_unmasked_rejudge": ("stored", "with_line")}
    out = {"pairs": {}}
    for name, (a, b) in pairs.items():
        ta, tb = tests[a]["t_anthropic_by_axis"], tests[b]["t_anthropic_by_axis"]
        axes = sorted(set(ta) & set(tb))
        d = {ax: round(tb[ax] - ta[ax], 4) for ax in axes}
        absd = np.abs(list(d.values()))
        ra, rb = set(tests[a]["rejected_axes"]), set(tests[b]["rejected_axes"])
        out["pairs"][name] = {
            "from": a, "to": b, "n_axes": len(axes),
            "delta_S": round(tests[b]["statistic"] - tests[a]["statistic"], 4),
            "mean_abs_delta_t": round(float(absd.mean()), 4),
            "median_abs_delta_t": round(float(np.median(absd)), 4),
            "max_abs_delta_t": round(float(absd.max()), 4),
            "axis_of_max": max(d, key=lambda x: abs(d[x])),
            "n_axes_rejected": [tests[a]["n_axes_rejected"], tests[b]["n_axes_rejected"]],
            "survival_flips": {"lost": sorted(ra - rb), "gained": sorted(rb - ra)},
            "delta_t_by_axis": d}
        p = out["pairs"][name]
        print(f"{name:48s} dS={p['delta_S']:+.3f} mean|dt|={p['mean_abs_delta_t']:.3f} "
              f"max|dt|={p['max_abs_delta_t']:.3f} ({p['axis_of_max']}) axes={p['n_axes_rejected']} "
              f"flips={p['survival_flips']}")
    path.write_text(json.dumps(out, indent=2, sort_keys=True))
    print("wrote", path)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pilot", action="store_true")
    ap.add_argument("--t-shift", action="store_true", help="after the full comparison")
    a = ap.parse_args()
    run_pilot() if a.pilot else run_t_shift() if a.t_shift else run_full()


if __name__ == "__main__":
    main()
