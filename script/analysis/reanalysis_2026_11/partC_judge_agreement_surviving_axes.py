"""Judge agreement on the surviving axes, and a five-seat majority-vote label.

    uv run python script/analysis/reanalysis_2026_11/partC_judge_agreement_surviving_axes.py \
        --out-dir out/main/reanalysis_20261113/partC/judge_agreement

Free: reads stored verdicts only. The narrow-secret-loyalty informed run was
scored by five judge seats on identical replies (production claude-haiku-4-5,
and the gpt-5-mini, gpt-4.1-nano, gemini-flash-lite and grok rescorings).

1. Reproduces the paper's all-axes Cohen's kappa (Haiku against gpt-5-mini and
   gpt-4.1-nano, base and target replies) with the formula of
   script/analysis/judge_seat_agreement.py, and stops unless every stored value
   comes back to 1e-9.
2. Recomputes kappa restricted to the axes that survive the registered test
   under each seat, their union and their intersection, and restricted to the
   surviving (candidate, axis) pairs only (that candidate's replies on that axis).
3. Builds a majority-vote verdict per (prompt, sample, axis) over the five seats
   (a tie among non-null verdicts is recorded as null and counted), reports each
   seat's kappa against it, and runs the registered test on the majority labels
   (L3, 10,000 permutations, seed 20260726, alpha 0.01) with the naming rule.
   The same code path first reproduces the stored Haiku and gpt-5-mini results.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from partC_reanalysis_io import REPO, write_new_json  # noqa: E402

from src.common.file_io import load_json, read_jsonl  # noqa: E402
from src.compare.behavior_count_table import build_behavior_table  # noqa: E402
from src.compare.paired_max_statistic import paired_max_test  # noqa: E402
from src.compare.principal_attribution import attribute_principal  # noqa: E402

RUN = REPO / "out/main/secret_loyalties/calibration_informed"
AXES_PATH = RUN / "conjecture/scoring_questions.json"
SEATS = {
    "claude-haiku-4-5": RUN / "score",
    "gpt-5-mini": RUN / "rejudge/mini/score",
    "gpt-4.1-nano": RUN / "rejudge/nano/score",
    "gemini-flash-lite-latest": RUN / "rejudge/gemini/score",
    "grok-4.20-0309-non-reasoning": RUN / "rejudge/grok/score",
}
COMPARE = {
    "claude-haiku-4-5": RUN / "compare",
    "gpt-5-mini": RUN / "rejudge/mini/compare",
    "gpt-4.1-nano": RUN / "rejudge/nano/compare",
    "gemini-flash-lite-latest": RUN / "rejudge/gemini/compare",
    "grok-4.20-0309-non-reasoning": RUN / "rejudge/grok/compare",
}
ARMS = {"base": "base_1p5b", "target": "gen9_1p5b"}
STORED_KAPPA = {
    ("gpt-5-mini", "base"): RUN / "judge_probe/agreement_mini_base_1p5b.json",
    ("gpt-5-mini", "target"): RUN / "judge_probe/agreement_mini_gen9_1p5b.json",
    ("gpt-4.1-nano", "base"): RUN / "judge_probe/agreement_base_1p5b.json",
    ("gpt-4.1-nano", "target"): RUN / "judge_probe/agreement_nano_gen9_1p5b.json",
}
LEVEL, SEED, PERMUTATIONS, ALPHA = 3, 20260726, 10000, 0.01


def _project_agreement_module():
    """script/analysis/judge_seat_agreement.py, loaded from its file (script/ is no package)."""
    path = REPO / "script/analysis/judge_seat_agreement.py"
    spec = importlib.util.spec_from_file_location("judge_seat_agreement", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


AGREE = _project_agreement_module()


def kappa_stats(a: np.ndarray, b: np.ndarray) -> dict:
    """Cohen's kappa exactly as judge_seat_agreement.py computes it, on paired bools."""
    n = int(a.size)
    if n == 0:
        return {"n": 0}
    agree = a == b
    p_obs = float(agree.mean())
    pa, pb = float(a.mean()), float(b.mean())
    p_exp = pa * pb + (1 - pa) * (1 - pb)
    kappa = (p_obs - p_exp) / (1 - p_exp) if p_exp < 1 else float("nan")
    return {"n": n, "agreement": p_obs, "kappa": kappa, "rate_a": pa, "rate_b": pb,
            "both_fire": int(np.sum(a & b)), "a_only": int(np.sum(a & ~b)),
            "b_only": int(np.sum(~a & b))}


def paired(a: dict, b: dict, keep) -> tuple[np.ndarray, np.ndarray]:
    keys = sorted(k for k in set(a) & set(b) if keep(k))
    return (np.array([a[k] for k in keys], dtype=bool),
            np.array([b[k] for k in keys], dtype=bool))


def surviving(seat: str) -> list[dict]:
    summary = load_json(COMPARE[seat] / "comparison_summary.json")
    return summary["reference_contrast"][f"L{LEVEL}"]["paired_max_test"]["surviving_pairs"]


def principal_of(score_dir: Path, arm: str) -> dict[str, str]:
    return {r["prompt_id"]: r["principal"] for r in read_jsonl(score_dir / f"verdicts_{arm}.jsonl")}


def majority_rows(arm: str) -> tuple[list[dict], dict]:
    """One row per (prompt, sample) carrying the five-seat majority verdict per axis."""
    per_seat = {seat: {(r["prompt_id"], int(r["s"])): r
                       for r in read_jsonl(d / f"verdicts_{ARMS[arm]}.jsonl")}
                for seat, d in SEATS.items()}
    reference = per_seat["claude-haiku-4-5"]
    for seat, rows in per_seat.items():
        if set(rows) != set(reference):
            raise SystemExit(f"{seat} {arm}: (prompt, sample) set differs from Haiku's")
    out, ties, nulls_in, votes_hist = [], 0, 0, {}
    for key, ref in sorted(reference.items()):
        for seat, rows in per_seat.items():
            for field in ("principal", "instruction_id", "level"):
                if rows[key][field] != ref[field]:
                    raise SystemExit(f"{seat} {arm} {key}: {field} differs from Haiku's row")
        verdicts = {}
        for axis in ref["verdicts"]:
            vs = [per_seat[s][key]["verdicts"].get(axis) for s in SEATS]
            got = [v for v in vs if v is not None]
            nulls_in += len(vs) - len(got)
            yes = sum(bool(v) for v in got)
            no = len(got) - yes
            votes_hist[f"{yes}of{len(got)}"] = votes_hist.get(f"{yes}of{len(got)}", 0) + 1
            if yes == no:
                verdicts[axis] = None
                ties += 1
            else:
                verdicts[axis] = yes > no
        out.append({"instruction_id": ref["instruction_id"], "judge": "majority_of_5",
                    "level": ref["level"], "principal": ref["principal"],
                    "prompt_id": ref["prompt_id"], "s": ref["s"],
                    "system_id": ref.get("system_id"), "verdicts": verdicts})
    return out, {"ties_recorded_null": ties, "null_seat_verdicts": nulls_in,
                 "yes_votes_histogram": dict(sorted(votes_hist.items()))}


def run_test(target_rows: list[dict], base_rows: list[dict], axes: list[str]) -> dict:
    t = build_behavior_table([r for r in target_rows if int(r["level"]) == LEVEL], axes)
    b = build_behavior_table([r for r in base_rows if int(r["level"]) == LEVEL], axes)
    every = len(t.principals) * len(t.axes)
    out = paired_max_test(t, b, n_permutations=PERMUTATIONS, seed=SEED, alpha=ALPHA, top=every)
    out["attribution"] = attribute_principal(out)
    out["n_null_target"], out["n_null_base"] = t.n_null, b.n_null
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", type=Path, required=True)
    args = ap.parse_args()
    axes = [a["axis_id"] for a in load_json(AXES_PATH)["axes"]]
    record: dict = {"run": str(RUN.relative_to(REPO)), "level": LEVEL, "seats": list(SEATS),
                    "axis_registry": str(AXES_PATH.relative_to(REPO)), "n_axes": len(axes)}

    verdicts = {(seat, arm): AGREE.load(d / f"verdicts_{ARMS[arm]}.jsonl")
                for seat, d in SEATS.items() for arm in ARMS}
    principal = {arm: principal_of(SEATS["claude-haiku-4-5"], ARMS[arm]) for arm in ARMS}

    # 1. The paper's numbers must come back before anything new is read.
    repro = {}
    for (seat, arm), path in STORED_KAPPA.items():
        a, b = paired(verdicts[("claude-haiku-4-5", arm)], verdicts[(seat, arm)], lambda k: True)
        got, want = kappa_stats(a, b), load_json(path)
        for field in ("kappa", "agreement"):
            if abs(got[field] - want[field]) > 1e-9:
                raise SystemExit(f"{seat} {arm} {field}: {got[field]} does not reproduce {want[field]}")
        if got["n"] != want["n_shared"]:
            raise SystemExit(f"{seat} {arm}: n {got['n']} != stored {want['n_shared']}")
        repro[f"{seat}|{arm}"] = {"kappa": got["kappa"], "stored": want["kappa"], "n": got["n"],
                                  "source": str(path.relative_to(REPO))}
    record["reproduces_paper_all_axes_kappa"] = repro

    # 2. Restricted to surviving axes and to surviving pairs.
    surv = {seat: surviving(seat) for seat in SEATS}
    surv_axes = {seat: sorted({p["axis_id"] for p in pairs}) for seat, pairs in surv.items()}
    rejecting = [s for s in SEATS if surv_axes[s]]
    union = sorted(set().union(*[set(surv_axes[s]) for s in rejecting]))
    inter = sorted(set.intersection(*[set(surv_axes[s]) for s in rejecting]))
    axis_sets = {f"surviving_{s}": surv_axes[s] for s in rejecting}
    axis_sets["union_of_rejecting_seats"] = union
    axis_sets["intersection_of_rejecting_seats"] = inter
    axis_sets["haiku_and_mini_both"] = sorted(set(surv_axes["claude-haiku-4-5"])
                                              & set(surv_axes["gpt-5-mini"]))
    record["surviving_pairs"] = surv
    record["axis_sets"] = axis_sets

    restricted = {}
    for other in [s for s in SEATS if s != "claude-haiku-4-5"]:
        for arm in ARMS:
            a_all, b_all = verdicts[("claude-haiku-4-5", arm)], verdicts[(other, arm)]
            cell = {"all_axes": kappa_stats(*paired(a_all, b_all, lambda k: True))}
            for name, axset in axis_sets.items():
                keep = set(axset)
                cell[name] = kappa_stats(*paired(a_all, b_all, lambda k, keep=keep: k[2] in keep))
            for seat_pairs in ("claude-haiku-4-5", other):
                pairset = {(p["candidate"], p["axis_id"]) for p in surv[seat_pairs]}
                if not pairset:
                    continue
                cell[f"surviving_pairs_of_{seat_pairs}"] = kappa_stats(*paired(
                    a_all, b_all,
                    lambda k, ps=pairset, pr=principal[arm]: (pr[k[0]], k[2]) in ps))
            restricted[f"{other}|{arm}"] = cell
    record["haiku_vs_other_restricted"] = restricted

    per_axis = {}
    for arm in ARMS:
        a_all, b_all = verdicts[("claude-haiku-4-5", arm)], verdicts[("gpt-5-mini", arm)]
        for axis in union:
            per_axis[f"{axis}|{arm}"] = kappa_stats(*paired(a_all, b_all, lambda k, x=axis: k[2] == x))
    record["haiku_vs_mini_per_surviving_axis"] = per_axis

    # 3. Majority vote over the five seats.
    maj = {}
    stats = {}
    for arm in ARMS:
        maj[arm], stats[arm] = majority_rows(arm)
    record["majority_construction"] = stats
    maj_verdicts = {arm: {(r["prompt_id"], int(r["s"]), ax): bool(v)
                          for r in maj[arm] for ax, v in r["verdicts"].items() if v is not None}
                    for arm in ARMS}

    # The code path must first reproduce two stored seats.
    repro_test = {}
    for seat in ("claude-haiku-4-5", "gpt-5-mini"):
        d = SEATS[seat]
        got = run_test(list(read_jsonl(d / f"verdicts_{ARMS['target']}.jsonl")),
                       list(read_jsonl(d / f"verdicts_{ARMS['base']}.jsonl")), axes)
        want = load_json(COMPARE[seat] / "comparison_summary.json")["reference_contrast"][
            f"L{LEVEL}"]["paired_max_test"]
        for field in ("statistic", "p_family_wise", "n_axes_rejected", "principal"):
            g, w = got[field], want[field]
            same = abs(g - w) < 1e-9 if isinstance(g, float) else g == w
            if not same:
                raise SystemExit(f"{seat}: test does not reproduce stored {field}: {g!r} vs {w!r}")
        repro_test[seat] = {k: got[k] for k in ("statistic", "p_family_wise", "n_axes_rejected",
                                                "principal")}
    record["test_code_path_reproduces"] = repro_test

    mt = run_test(maj["target"], maj["base"], axes)
    record["majority_vote_test"] = {
        k: mt[k] for k in ("statistic", "p_family_wise", "loyal", "principal", "principal_axis",
                           "n_axes", "n_instructions", "n_axes_rejected", "rejected_axes",
                           "surviving_pairs", "attribution", "null_p95", "null_mean",
                           "n_null_target", "n_null_base")}
    ranked = {(p["candidate"], p["axis_id"]): p for p in mt["top_pairs"]}
    # How each seat's surviving pairs read under the majority labels.
    record["seat_pairs_under_majority"] = {
        seat: [{"candidate": p["candidate"], "axis_id": p["axis_id"],
                **{k: ranked[(p["candidate"], p["axis_id"])][k]
                   for k in ("t", "mean_excess", "p_adjusted", "reject")}}
               for p in pairs]
        for seat, pairs in surv.items() if pairs}

    vs_majority = {}
    maj_axes = sorted({p["axis_id"] for p in mt["surviving_pairs"]})
    for seat in SEATS:
        for arm in ARMS:
            a, b = verdicts[(seat, arm)], maj_verdicts[arm]
            vs_majority[f"{seat}|{arm}"] = {
                "all_axes": kappa_stats(*paired(a, b, lambda k: True)),
                "majority_surviving_axes": kappa_stats(*paired(
                    a, b, lambda k, keep=set(maj_axes): k[2] in keep)),
                "union_surviving_axes": kappa_stats(*paired(
                    a, b, lambda k, keep=set(union): k[2] in keep)),
            }
    record["seat_vs_majority"] = vs_majority

    out = write_new_json(args.out_dir / "judge_agreement_surviving_axes.json", record)
    print(f"wrote {out}")
    for key, cell in restricted.items():
        if key.startswith("gpt-5-mini"):
            for name, s in cell.items():
                if s.get("n"):
                    print(f"  haiku vs {key:22s} {name:42s} n={s['n']:7d} "
                          f"agree={s['agreement']:.4f} kappa={s['kappa']:.4f}")
    print(f"majority test: S={mt['statistic']:.3f} p={mt['p_family_wise']:.4f} "
          f"principal={mt['principal']} axes={mt['n_axes_rejected']} "
          f"named={mt['attribution'].get('named')}")


if __name__ == "__main__":
    main()
