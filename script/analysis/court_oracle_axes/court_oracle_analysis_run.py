"""Run the court ceiling's registered tests on the scored verdicts. No model is called.

Rows of the decomposition table, each under tests 1 to 6 (a family whose axes
carry no sign runs test 2 only):

* row 1 and row 2: every judge and matcher family on OWN, GG and OD;
* row 1b: the same families on each of OWN's five four-sample slices;
* the A1 split-baseline null control on every corpus;
* row 2x2 and row 2E: block E's two direct families under GPT-5 mini;
* row 3: the pipeline's stored verdicts, unsigned over its whole registry,
  checked against the stored ``comparison_summary.json``;
* row 3b: the stored verdicts on the mapped families with the mapped signs;
* row 2c: the new GPT-5 mini L2 verdicts joined by reply to the stored
  verdicts, unsigned over 104 (GG) or 86 (OD) axes;
* test 8: the common-mode half on L2's six axes per corpus and judge.

Every result file is written once under ``analysis/`` and never overwritten.

    .venv/bin/python -m script.analysis.court_oracle_axes.court_oracle_analysis_run --workers 12
"""

from __future__ import annotations

import argparse
import json
import time
from multiprocessing import Pool

from script.analysis.court_oracle_axes.court_oracle_analysis_core import (
    ANALYSIS, CORPORA, EXT, JUDGE_FAMILIES, JUDGES, L2_SIX, MATCHER_FAMILIES,
    MATCHERS, N_PERM, SIGN, arms, dump, e_families, load_rows, mapped_families,
    null_share, run_family, split_baseline)
from src.common.file_io import load_json, read_jsonl
from src.compare.behavior_count_table import build_behavior_table
from src.compare.common_mode_elevation import common_mode_elevation

SLICES = [set(range(k, k + 4)) for k in range(0, 20, 4)]
SPLIT = {"OWN": (set(range(10)), set(range(10, 20))), "GG": ({0, 1}, {2, 3}), "OD": ({0, 1}, {2, 3})}
RUN_DIR = {"GG": EXT / "court_full", "OD": EXT / "court_full_scoped"}
NULL_GUARD = 0.2


def families_for(rater: str) -> dict:
    """Family name -> (file level, axes, signs or None) for one rater."""
    if rater in MATCHERS.values():
        fams = MATCHER_FAMILIES
    else:
        fams = JUDGE_FAMILIES
    out = {name: (lv, axes, [SIGN[a] for a in axes] if signed else None)
           for name, (lv, axes, signed) in fams.items()}
    if rater == JUDGES["gpt"]:
        out.update({name: (lv, axes, signs) for name, (lv, axes, signs) in e_families().items()})
    return out


def jobs() -> list[dict]:
    out = []
    for corpus in CORPORA:
        for rater in list(JUDGES.values()) + list(MATCHERS.values()):
            for fam, (lv, axes, signs) in families_for(rater).items():
                base = {"corpus": corpus, "rater": rater, "family": fam, "file_level": lv,
                        "axes": axes, "signs": signs}
                out.append({**base, "group": "full", "selector": None})
                out.append({**base, "group": "split_control", "selector": "split"})
                if corpus == "OWN":
                    for k in range(5):
                        out.append({**base, "group": "slices", "selector": k})
    return out


def _guard(rows: list[dict], axes: list[str], s_keep=None) -> dict:
    t, b = arms(rows, axes, s_keep)
    return {"target": null_share(t), "baseline": null_share(b)}


def work(job: dict) -> dict:
    t0 = time.time()
    rows = load_rows(job["corpus"], job["file_level"], job["rater"])
    label = f"{job['group']} {job['corpus']} {job['rater']} {job['family']} {job['selector']}"
    # Null guard, per arm and per block file, as the registration and the project script do.
    guard = _guard(rows, list(rows[0]["verdicts"]))
    res = {k: v for k, v in job.items()}
    res["null_guard"] = guard
    if max(guard.values()) > NULL_GUARD:
        res["status"] = "failed seat (null guard)"
        return res
    if job["group"] == "split_control":
        first, second = SPLIT[job["corpus"]]
        t, b = split_baseline(rows, job["axes"], first, second)
    else:
        s_keep = SLICES[job["selector"]] if job["group"] == "slices" else None
        t, b = arms(rows, job["axes"], s_keep)
    res.update(run_family(t, b, job["axes"], job["signs"], label=label))
    res["status"] = "run"
    res["seconds"] = round(time.time() - t0, 2)
    return res


# ---------------------------------------------------------------- pipeline rows

def stored_rows(run: str) -> dict[str, list[dict]]:
    d = RUN_DIR[run] / "score"
    out = {}
    for cond, name in (("target", "verdicts_prompted_target.jsonl"), ("baseline", "verdicts_prompted_base.jsonl")):
        rows = list(read_jsonl(d / name))
        levels = {r["level"] for r in rows}
        if levels != {2}:
            raise SystemExit(f"{run} {cond}: levels {levels}")
        out[cond] = rows
    return out


def registry(run: str) -> list[str]:
    return [a["axis_id"] for a in load_json(RUN_DIR[run] / "conjecture/scoring_questions.json")["axes"]]


def _fmt(rows, axes):
    return [{"principal": r["principal"], "instruction_id": r["instruction_id"],
             "verdicts": {a: r["verdicts"][a] for a in axes}} for r in rows]


def pipeline_work(job: dict) -> dict:
    t0 = time.time()
    run = job["corpus"]
    stored = stored_rows(run)
    axes_all = registry(run)
    res = dict(job)
    if job["group"] == "row3":
        res.update(run_family(_fmt(stored["target"], axes_all), _fmt(stored["baseline"], axes_all),
                              axes_all, None, label=f"row3 {run}"))
        summary = load_json(RUN_DIR[run] / "compare_prompted/comparison_summary.json")
        ref = summary["reference_contrast"]["L2"]["paired_max_test"]
        mine = res["test2_unsigned"]["project"]
        keys = ("statistic", "p_family_wise", "null_mean", "null_p95", "loyal", "principal",
                "principal_axis", "n_axes_rejected", "rejected_axes")
        res["stored_comparison"] = {k: {"stored": ref[k], "recomputed": mine[k], "equal": ref[k] == mine[k]}
                                    for k in keys}
        res["matches_stored"] = all(v["equal"] for v in res["stored_comparison"].values())
    elif job["group"] == "row3b":
        axes, signs = mapped_families(run)[job["family"]]
        res["axes"], res["signs"] = axes, signs
        res.update(run_family(_fmt(stored["target"], axes), _fmt(stored["baseline"], axes),
                              axes, signs, label=f"row3b {run} {job['family']}"))
    elif job["group"] == "row2c":
        ours = load_rows(run, "L2", JUDGES["gpt"])
        key = lambda c, r: (c, r["principal"], r["prompt_id"], int(r["s"]))
        index = {key(r["condition"], r): r for r in ours}
        if len(index) != len(ours):
            raise SystemExit("our L2 rows are not unique by reply")
        added = L2_SIX[:3]
        joined = {}
        used = set()
        for cond in ("target", "baseline"):
            out = []
            for r in stored[cond]:
                k = key(cond, r)
                mine = index[k]
                if mine["instruction_id"] != r["instruction_id"]:
                    raise SystemExit(f"instruction mismatch at {k}")
                used.add(k)
                out.append({"principal": r["principal"], "instruction_id": r["instruction_id"],
                            "verdicts": {**{a: r["verdicts"][a] for a in axes_all},
                                         **{a: mine["verdicts"][a] for a in added}}})
            joined[cond] = out
        if used != set(index):
            raise SystemExit("the join does not cover every scored reply once")
        axes = axes_all + added
        res["axes_added"] = added
        res["n_joined"] = {c: len(v) for c, v in joined.items()}
        res.update(run_family(joined["target"], joined["baseline"], axes, None, label=f"row2c {run}"))
    res["seconds"] = round(time.time() - t0, 2)
    return res


def common_mode_work(job: dict) -> dict:
    rows = load_rows(job["corpus"], "L2", job["rater"])
    t, b = arms(rows, L2_SIX)
    target, base = build_behavior_table(t, L2_SIX), build_behavior_table(b, L2_SIX)
    return {**job, "axes": L2_SIX, "common_mode": common_mode_elevation(target, base, n_permutations=N_PERM)}


def dispatch(job: dict) -> dict:
    if job["group"] in ("row3", "row3b", "row2c"):
        return pipeline_work(job)
    if job["group"] == "common_mode":
        return common_mode_work(job)
    return work(job)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args()
    targets = {g: ANALYSIS / f"tests_{g}.json" for g in
               ("full", "slices", "split_control", "row3", "row3b", "row2c", "common_mode")}
    for p in targets.values():
        if p.exists():
            raise SystemExit(f"{p} exists; this run never overwrites")
    todo = jobs()
    for run in ("GG", "OD"):
        todo.append({"group": "row3", "corpus": run, "rater": "stored pipeline verdicts", "family": "all"})
        todo.append({"group": "row2c", "corpus": run, "rater": "stored + openai_gpt-5-mini L2", "family": "all+L2"})
        for fam in ("direct", "direct_partial", "direct_partial_wo_h065_g003"):
            todo.append({"group": "row3b", "corpus": run, "rater": "stored pipeline verdicts", "family": fam})
    for corpus in CORPORA:
        for rater in JUDGES.values():
            todo.append({"group": "common_mode", "corpus": corpus, "rater": rater, "family": "L2_six"})
    print(f"{len(todo)} jobs", flush=True)
    t0 = time.time()
    results: dict[str, list] = {g: [] for g in targets}
    with Pool(args.workers) as pool:
        for i, res in enumerate(pool.imap_unordered(dispatch, todo), 1):
            results[res["group"]].append(res)
            if i % 25 == 0:
                print(f"{i}/{len(todo)} done, {time.time() - t0:.0f}s", flush=True)
    order = lambda r: (r["corpus"], r["rater"], r["family"], str(r.get("selector")))
    for g, p in targets.items():
        dump({"n_permutations": N_PERM, "seed": 20260726, "alpha": 0.01,
              "results": sorted(results[g], key=order)}, p)
        print(f"wrote {p} ({len(results[g])} results)")
    print(f"total {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
