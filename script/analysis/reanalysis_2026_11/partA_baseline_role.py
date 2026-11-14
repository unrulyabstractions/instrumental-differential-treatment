"""Part A (a): what the base model does for the registered test. No spend.

    .venv/bin/python -m script.analysis.reanalysis_2026_11.partA_baseline_role --workers 12

Every run with a stored ``compare/reference_free.json``, the court runs that have
none, and the null-extension arms (base B, the two synthetic-document nulls) are
read four ways on their own stored verdicts:

- ``registered``: ``paired_max_test`` (target excess over its base), exactly as
  stage 6 ran it. Refuses unless S and p equal the stored summary.
- ``target_only_median``: ``reference_free_max_test`` on the target replies
  alone (one-vs-median-of-rest, permutation within instruction). This is the
  statistic the stored ``reference_free.json`` files hold. Refuses unless S and
  p equal the stored record.
- ``base_only_median``: the same test on the base replies alone, so a
  target-only rejection can be checked against the untuned model.
- ``target_only_mean``: ``paired_max_test`` with the base replaced by an
  all-zero table on the target's own cells, so the only change from the
  registered test is that nothing is subtracted (one-vs-mean-of-rest).

Each is run on the full registry and on the three guaranteed axes
(``GUARANTEED_AXES``), where the registry carries all three with identical
wording. 10,000 permutations, seed 20260726, alpha 0.01; the naming rule
(``attribute_principal``) is applied to every variant.

Writes only under ``out/main/reanalysis_20261113/partA/``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from script.analysis.null_extension_compare import AXES as AB_AXES
from script.analysis.null_extension_compare import BASE_A, BASE_B, EXT, SYNTH
from src.common.file_io import load_json, read_jsonl
from src.compare.behavior_count_table import BehaviorTable
from src.compare.behavior_table_restriction import restrict_table
from src.compare.paired_max_statistic import paired_max_test
from src.compare.placebo_calibration import load_level_table
from src.compare.principal_attribution import attribute_principal
from src.compare.reference_free_max_statistic import reference_free_max_test
from src.conjecture.guaranteed_axis_registry import GUARANTEED_AXES
from src.ui.experiment_registry import EXPERIMENTS, HELD_OUT_EXPERIMENTS

OUT = Path("out/main/reanalysis_20261113/partA")
SEED, N_PERM, ALPHA = 20260726, 10000, 0.01
G_IDS = tuple(a[0] for a in GUARANTEED_AXES)
G_QUESTIONS = {a[0]: a[2] for a in GUARANTEED_AXES}

#: Runs the paper's Table 2 / Table 3 report. Everything else is labelled.
PAPER_RUNS = {
    "calibration_blind_person", "calibration_blind_organization", "calibration_scoped",
    "calibration_informed", "auditbench_contextual_optimism",
    "auditbench_third_party_politics", "auditbench_secret_loyalty",
    "court_groups_given", "court_objective_disclosed",
    *(f"auditbench_{c}" for c in ("flattery", "emotional_bond", "hallucinates_citations",
                                  "defer_to_users", "ai_welfare_poisoning",
                                  "anti_ai_regulation", "animal_welfare", "defend_objects")),
}


@dataclass(frozen=True)
class Run:
    key: str
    role: str
    note: str
    target: str
    base: str | None  # None: no paired base (a target-only row)
    axes: str
    level: int
    summary: str | None  # stored stage-6 summary, checked against the recompute
    reference_free: str | None  # stored reference_free.json, checked likewise


def _level(summary: str) -> int:
    contrast = load_json(Path(summary))["reference_contrast"]
    return int(sorted(k for k in contrast if k.startswith("L"))[-1][1:])


def runs() -> list[Run]:
    out: list[Run] = []
    court_alias = {"court_prompted": "court_groups_given",
                   "court_weights": "court_groups_given_weights_arm"}
    for e in (*EXPERIMENTS, *HELD_OUT_EXPERIMENTS):
        rf = Path(e.summary).parent / "reference_free.json"
        key = court_alias.get(e.key, e.key)
        note = ("held out of the paper" if e.role == "challenge" else
                "in the paper" if key in PAPER_RUNS else "not in the paper's tables")
        if key.endswith("weights_arm"):
            note = "weights arm, dropped from the paper (B24, B30)"
        out.append(Run(key, e.role, note, e.verdicts_target, e.verdicts_base, e.axes,
                       _level(e.summary), e.summary, str(rf) if rf.is_file() else None))
    scoped = "out/main/external/court_full_scoped"
    for arm, key, note in (("prompted", "court_objective_disclosed", "in the paper"),
                           ("weights", "court_objective_disclosed_weights_arm",
                            "weights arm, dropped from the paper (B24, B30)")):
        summary = f"{scoped}/compare_{arm}/comparison_summary.json"
        out.append(Run(key, "positive", note, f"{scoped}/score/verdicts_{arm}_target.jsonl",
                       f"{scoped}/score/verdicts_{arm}_base.jsonl",
                       f"{scoped}/conjecture/scoring_questions.json", _level(summary),
                       summary, None))
    # Null extension: base B as a target over base A, and the synthetic-document
    # nulls over base A. Stage 6 never ran these, so nothing stored is checked
    # here; the null-extension summary is checked in partA_null_rank.
    out.append(Run("nullext_base_B", "null", "null extension (base B sampled again)",
                   str(BASE_B), str(BASE_A), str(AB_AXES), 2, None, None))
    for b in SYNTH:
        out.append(Run(f"nullext_sd_{b}", "null", "null extension (synthetic-document null)",
                       str(EXT / "synth" / b / "verdicts_target.jsonl"), str(BASE_A),
                       str(AB_AXES), 2, None, None))
    return out


# ----------------------------------------------------------------------------
# Worker side
# ----------------------------------------------------------------------------
_CACHE: dict = {}


def _table(path: str, axes_path: str, level: int) -> BehaviorTable:
    k = (path, axes_path, level)
    if k not in _CACHE:
        axes = [a["axis_id"] for a in load_json(Path(axes_path))["axes"]]
        _CACHE[k] = load_level_table(read_jsonl(Path(path)), axes, level)
    return _CACHE[k]


def _zero_base(t: BehaviorTable) -> BehaviorTable:
    """The target's own cells with every verdict a returned "no".

    Same responses, instructions and ``scored`` mask, so every cell the target
    observed is a zero rate and every cell it did not stays NaN. Its
    one-vs-rest gap is zero wherever the target's is defined, so the excess is
    the target's own gap and the permutation (which carries both together) is
    the target-only permutation.
    """
    fired = np.zeros_like(t.fired)
    counts = np.zeros_like(t.counts)
    return BehaviorTable(t.principals, t.axes, counts, fired, t.scored.copy(),
                         t.group_of, t.block_of, t.blocks, t.n_null, t.n_responses)


def _restrict(t: BehaviorTable, subset: str) -> BehaviorTable:
    if subset == "full":
        return t
    idx = np.array([t.axes.index(a) for a in G_IDS])
    return restrict_table(t, axes=idx)


def _digest(res: dict, kind: str, n_axes: int) -> dict:
    """One shape for every variant, plus the naming rule on all of them."""
    if kind == "registered" or kind == "target_only_mean":
        pairs = res["top_pairs"]
        loyal = bool(res["loyal"])
        surviving = res["surviving_pairs"]
        argmax = res["top_pairs"][0]["candidate"] if pairs else None
        att = attribute_principal(res)
        shift_key = "mean_excess"
    else:
        pairs = res["top_pairs"]
        loyal = bool(res["p_family_wise"] <= ALPHA)
        surviving = [{"candidate": p["candidate"], "axis_id": p["axis_id"]}
                     for p in pairs if p["p_adjusted"] <= ALPHA]
        argmax = pairs[0]["candidate"] if pairs else None
        att = attribute_principal({"loyal": loyal, "surviving_pairs": surviving,
                                   "principal": argmax if loyal else None,
                                   "n_axes": n_axes})
        shift_key = "mean_shift"
    hist: dict[str, set] = {}
    for p in surviving:
        hist.setdefault(p["candidate"], set()).add(p["axis_id"])
    top = pairs[0] if pairs else {}
    g_rows = [{"candidate": p["candidate"], "axis_id": p["axis_id"], "t": p["t"],
               "shift": p[shift_key], "p_adjusted": p["p_adjusted"]}
              for p in pairs if p["axis_id"] in G_IDS]
    g_best = {}
    for row in g_rows:
        cur = g_best.get(row["axis_id"])
        if cur is None or abs(row["t"]) > abs(cur["t"]):
            g_best[row["axis_id"]] = row
    return {
        "S": float(res["statistic"]), "p": float(res["p_family_wise"]),
        "reject_0.01": loyal, "argmax_candidate": argmax,
        "argmax_axis": top.get("axis_id"), "argmax_t": top.get("t"),
        "named_by_rule": att["named"], "naming_reason": att.get("reason", ""),
        "surviving_axes_by_candidate": {c: len(a) for c, a in sorted(hist.items())},
        "n_surviving_pairs": len(surviving),
        "n_axes": int(res["n_axes"]), "n_instructions": int(res["n_instructions"]),
        "candidates": list(res["candidates"]),
        "null_mean": float(res["null_mean"]), "null_p95": float(res["null_p95"]),
        "guaranteed_axis_best_pairs": [g_best[a] for a in G_IDS if a in g_best],
    }


def run_task(task: dict) -> dict:
    t0 = time.time()
    kind, subset = task["kind"], task["subset"]
    tgt = _restrict(_table(task["table"], task["axes"], task["level"]), subset)
    n_cells = len(tgt.principals) * len(tgt.axes)
    if kind == "registered":
        base = _restrict(_table(task["base"], task["axes"], task["level"]), subset)
        res = paired_max_test(tgt, base, n_permutations=N_PERM, seed=SEED, alpha=ALPHA,
                              top=n_cells)
    elif kind == "target_only_mean":
        res = paired_max_test(tgt, _zero_base(tgt), n_permutations=N_PERM, seed=SEED,
                              alpha=ALPHA, top=n_cells)
    elif kind == "median":
        res = reference_free_max_test(tgt, n_permutations=N_PERM, seed=SEED, alpha=ALPHA,
                                      top=n_cells)
    else:
        raise ValueError(kind)
    out = {**task, **_digest(res, kind, len(tgt.axes)), "seconds": round(time.time() - t0, 1)}
    return out


# ----------------------------------------------------------------------------
# Driver
# ----------------------------------------------------------------------------
def _sha(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def guaranteed_status(axes_path: str) -> dict:
    axes = {a["axis_id"]: a.get("question") for a in load_json(Path(axes_path))["axes"]}
    present = [a for a in G_IDS if a in axes]
    identical = [a for a in present if axes[a] == G_QUESTIONS[a]]
    return {"n_axes": len(axes), "present": present, "identical_wording": identical,
            "carries_all_three": len(identical) == 3}


def build_tasks(rs: list[Run]) -> tuple[list[dict], dict]:
    tasks, meta = [], {}
    seen_median = set()
    for r in rs:
        g = guaranteed_status(r.axes)
        meta[r.key] = {**asdict(r), "guaranteed": g,
                       "sha256_target": _sha(r.target),
                       "sha256_base": _sha(r.base) if r.base else None}
        subsets = ["full"] + (["guaranteed3"] if g["carries_all_three"] else [])
        for s in subsets:
            common = {"run": r.key, "subset": s, "axes": r.axes, "level": r.level}
            if r.base:
                tasks.append({**common, "id": f"{r.key}|registered|{s}", "kind": "registered",
                              "table": r.target, "base": r.base})
            tasks.append({**common, "id": f"{r.key}|target_only_mean|{s}",
                          "kind": "target_only_mean", "table": r.target})
            tasks.append({**common, "id": f"{r.key}|target_only_median|{s}",
                          "kind": "median", "seat": "target", "table": r.target})
            # The base-only test is one task per distinct base file and registry.
            if r.base:
                bsha = meta[r.key]["sha256_base"]
                bk = (bsha, r.axes, r.level, s)
                if bk not in seen_median:
                    seen_median.add(bk)
                    tasks.append({**common, "id": f"{r.key}|base_only_median|{s}",
                                  "kind": "median", "seat": "base", "table": r.base,
                                  "base_sha256": bsha})
    return tasks, meta


def check_against_stored(results: dict, meta: dict) -> list[dict]:
    """Every recompute that has a stored counterpart must match it exactly."""
    checks = []
    for key, m in meta.items():
        if m["summary"]:
            stored = load_json(Path(m["summary"]))["reference_contrast"][f"L{m['level']}"][
                "paired_max_test"]
            got = results.get(f"{key}|registered|full")
            if got:
                ok = (got["S"] == stored["statistic"] and got["p"] == stored["p_family_wise"]
                      and got["named_by_rule"] == (stored.get("attribution") or {}).get("named"))
                checks.append({"run": key, "what": "registered vs comparison_summary.json",
                               "stored_S": stored["statistic"], "got_S": got["S"],
                               "stored_p": stored["p_family_wise"], "got_p": got["p"],
                               "stored_named": (stored.get("attribution") or {}).get("named"),
                               "got_named": got["named_by_rule"], "match": ok})
        if m["reference_free"]:
            rec = load_json(Path(m["reference_free"]))
            seat_target = Path(m["target"]).stem.removeprefix("verdicts_")
            seat_base = Path(m["base"]).stem.removeprefix("verdicts_")
            for seat, rid in ((seat_target, f"{key}|target_only_median|full"),
                              (seat_base, None)):
                if rid is None:
                    rid = next((k for k, v in results.items()
                                if v["kind"] == "median" and v.get("seat") == "base"
                                and v["subset"] == "full" and v["axes"] == m["axes"]
                                and v["level"] == m["level"]
                                and v["base_sha256"] == m["sha256_base"]), None)
                got = results.get(rid)
                st = rec["seats"].get(seat)
                if not (got and st):
                    checks.append({"run": key, "what": f"reference_free seat {seat}",
                                   "match": False, "reason": "missing seat or recompute"})
                    continue
                ok = (got["S"] == st["statistic"] and got["p"] == st["p_family_wise"]
                      and rec["level"] == m["level"] and rec["seed"] == SEED
                      and rec["n_permutations"] == N_PERM)
                checks.append({"run": key, "what": f"reference_free.json seat {seat}",
                               "stored_S": st["statistic"], "got_S": got["S"],
                               "stored_p": st["p_family_wise"], "got_p": got["p"],
                               "stored_named_at_0.05": st["named"],
                               "got_argmax": got["argmax_candidate"], "match": ok})
    return checks


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    args = ap.parse_args()
    if any(OUT.iterdir()) if OUT.exists() else False:
        existing = sorted(p.name for p in OUT.iterdir())
        mine = {"baseline_role.json", "baseline_role_tasks.jsonl"}
        if set(existing) - mine:
            raise SystemExit(f"{OUT} holds files this script did not write: {existing}")
        if set(existing) & mine:
            raise SystemExit(f"{OUT} already holds this script's outputs; never overwritten")
    OUT.mkdir(parents=True, exist_ok=True)

    rs = runs()
    tasks, meta = build_tasks(rs)
    print(f"{len(rs)} runs, {len(tasks)} tasks", flush=True)
    results: dict[str, dict] = {}
    log = OUT / "baseline_role_tasks.jsonl"
    with ProcessPoolExecutor(max_workers=args.workers) as ex, log.open("x") as fh:
        futs = {ex.submit(run_task, t): t["id"] for t in tasks}
        for f in as_completed(futs):
            r = f.result()
            results[r["id"]] = r
            fh.write(json.dumps(r) + "\n")
            fh.flush()
            print(f"{r['id']:70s} S={r['S']:.3f} p={r['p']:.4f} "
                  f"argmax={r['argmax_candidate']} named={r['named_by_rule']} "
                  f"({r['seconds']}s)", flush=True)

    checks = check_against_stored(results, meta)
    bad = [c for c in checks if not c["match"]]
    record = {"seed": SEED, "n_permutations": N_PERM, "alpha": ALPHA,
              "guaranteed_axes": G_IDS, "runs": meta, "results": results,
              "checks": checks, "n_checks": len(checks), "n_check_failures": len(bad)}
    with (OUT / "baseline_role.json").open("x") as fh:
        json.dump(record, fh, indent=1, default=str)
    print(f"{len(checks)} checks against stored records, {len(bad)} failures")
    for c in bad:
        print("MISMATCH", c)


if __name__ == "__main__":
    main()
