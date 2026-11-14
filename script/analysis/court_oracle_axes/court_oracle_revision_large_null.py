"""Exact and large permutation nulls for the court ceiling's revision. No model is called.

Exploratory, outside the registration. The registered tests use 10,000 draws
of the project's permutation loop. With two candidates, relabeling the
candidates within one instruction flips the sign of that instruction's
Cupertino excess, so the permutation null is a sign-flip null over
instructions. This script evaluates the same statistics over larger nulls:

* every one of the 2^m sign patterns when m is at most 20 (OWN, its slices,
  its split control, and the matched-size subsets), so the p-value is exact;
* 2,000,000 random sign patterns with seed 20261114 when m is 36 (GG, OD and
  the pipeline's stored verdicts), the same patterns for every family of one
  corpus.

Ties are counted with a relative tolerance of 1e-9, so a null value equal to
the observed one in exact arithmetic counts against it whatever rounding did.

Before any large null is read, every family is checked against the project:
the observed d, t and statistics must equal the registered ones, and the
sign patterns the project's own generator draws for its first 2,000
permutations must reproduce the project's null (``nulls`` in the analysis
core, which reproduces ``paired_max_test``) to 1e-9.

    uv run --no-sync python -m script.analysis.court_oracle_axes.court_oracle_revision_large_null --workers 14
"""

from __future__ import annotations

import argparse
import json
import time
from multiprocessing import Pool

import numpy as np

from script.analysis.court_oracle_axes.court_oracle_analysis_core import (
    ANALYSIS, CORPORA, JUDGES, L2_SIX, SEED, arms, dump, load_rows,
    mapped_families, nulls, split_baseline)
from script.analysis.court_oracle_axes.court_oracle_analysis_run import (
    SLICES, SPLIT, _fmt, families_for, registry, stored_rows)
from src.compare.behavior_count_table import build_behavior_table
from src.compare.paired_excess_measures import cell_rates, excess_effect

REVISION = ANALYSIS / "revision"
N_MC = 2_000_000
MC_SEED = 20261114
CHUNK = 1 << 16
TOL = 1e-9
N_CHECK = 2000
EXACT_MAX_M = 20


# ---------------------------------------------------------------- the engine

def cupertino_d(target_rows, base_rows, axes):
    """The project's excess d for the Cupertino row, (m, J), from the project's measures."""
    target = build_behavior_table(target_rows, axes)
    base = build_behavior_table(base_rows, axes)
    p_t, principals, instructions = cell_rates(target)
    p_b, _, _ = cell_rates(base)
    if len(principals) != 2 or not principals[0].lower().startswith("cupertino"):
        raise ValueError(f"row 0 is not Cupertino: {principals}")
    d = excess_effect(p_t, p_b)
    # One-versus-rest computes the rest as (p0 + p1) - p0, which equals p1 only
    # up to rounding, so the two rows are antisymmetric to about 1e-16.
    if not np.allclose(d[1], -d[0], rtol=0, atol=1e-12, equal_nan=True):
        raise AssertionError("the two-candidate excess is not antisymmetric")
    return d[0], target, base, instructions


class SignFlip:
    """Paired t over instructions for many sign patterns at once."""

    def __init__(self, d: np.ndarray):
        self.d = d
        self.valid = ~np.isnan(d)
        self.dz = np.where(self.valid, d, 0.0)
        self.mm = self.valid.sum(axis=0).astype(float)
        self.q = (self.dz ** 2).sum(axis=0)

    def t(self, signs: np.ndarray) -> np.ndarray:
        """t of the Cupertino row for each pattern: (K, J). Mirrors ``standardized_excess``."""
        s = signs @ self.dz
        mm = self.mm[None, :]
        with np.errstate(invalid="ignore", divide="ignore"):
            mean = s / mm
            var = (self.q[None, :] - mm * mean ** 2) / (mm - 1)
            scale = np.maximum(self.q[None, :] / np.maximum(mm, 1), 1e-300)
            var = np.where(var <= 1e-12 * scale, 0.0, var)
            t = mean / np.sqrt(var / mm)
        zero_var = var == 0
        with np.errstate(invalid="ignore"):
            t = np.where(zero_var & (np.abs(mean) > 1e-12), np.sign(mean) * np.inf, t)
        t = np.where(zero_var & (np.abs(mean) <= 1e-12), 0.0, t)
        t = np.where(mm < 2, np.nan, t)
        return t


def exact_patterns(m: int):
    total = 1 << m
    shifts = np.arange(m, dtype=np.int64)
    for start in range(0, total, CHUNK):
        idx = np.arange(start, min(start + CHUNK, total), dtype=np.int64)
        yield 1.0 - 2.0 * ((idx[:, None] >> shifts) & 1).astype(np.float64)


def mc_patterns(m: int, n: int = N_MC, seed: int = MC_SEED):
    rng = np.random.default_rng(seed)
    done = 0
    while done < n:
        k = min(CHUNK, n - done)
        yield 1.0 - 2.0 * rng.integers(0, 2, size=(k, m)).astype(np.float64)
        done += k


def project_patterns(n_i: int, n_perm: int, seed: int = SEED) -> np.ndarray:
    """The sign patterns ``paired_max_test``'s generator draws, in its call order."""
    rng = np.random.default_rng(seed)
    out = np.empty((n_perm, n_i))
    for k in range(n_perm):
        for i in range(n_i):
            out[k, i] = 1.0 if rng.permutation(2)[0] == 0 else -1.0
    return out


def tail(null: np.ndarray, value: float) -> int:
    if np.isnan(value):
        return len(null)
    if np.isinf(value):
        return int(np.sum(null >= value))
    return int(np.sum(null >= value - TOL * max(1.0, abs(value))))


def atoms_near(null: np.ndarray, q: float) -> dict:
    """The distinct null values just below and above the 99th percentile."""
    vals = np.unique(np.round(null[np.isfinite(null)], 9))
    below = vals[vals <= q + 1e-12]
    above = vals[vals > q + 1e-12]
    return {"atom_at_or_below": float(below[-1]) if below.size else None,
            "atom_above": float(above[0]) if above.size else None}


def large_test(d: np.ndarray, pol: np.ndarray | None) -> dict:
    """Unsigned (test 2) and directional (test 4) over the exact or 2M null."""
    eng = SignFlip(d)
    m = d.shape[0]
    t_obs = eng.t(np.ones((1, m)))[0]
    exact = m <= EXACT_MAX_M
    gen = exact_patterns(m) if exact else mc_patterns(m)
    nu, nd = [], []
    for sg in gen:
        tn = eng.t(sg)
        nu.append(np.nanmax(np.abs(tn), axis=1))
        if pol is not None:
            nd.append(np.nanmax(tn * pol[None, :], axis=1))
    null_u = np.concatenate(nu)
    n = len(null_u)
    out = {"m": m, "exact": exact, "n_null": n, "t_cupertino": t_obs.tolist()}

    def p_of(null, value):
        c = tail(null, value)
        return c / n if exact else (1 + c) / (1 + n)

    def adjusted(values, null):
        order = np.argsort(-np.nan_to_num(values, nan=-np.inf))
        adj = np.ones(len(values))
        running = 0.0
        for j in order:
            if np.isnan(values[j]):
                continue
            running = max(running, p_of(null, values[j]))
            adj[j] = running
        return adj.tolist()

    s_u = float(np.nanmax(np.abs(t_obs)))
    q99_u = float(np.quantile(null_u, 0.99))
    p_u = p_of(null_u, s_u)
    out["unsigned"] = {"S": s_u, "p": p_u, "q99": q99_u, "margin": s_u - q99_u,
                       "q95": float(np.quantile(null_u, 0.95)),
                       "mc_se": None if exact else float(np.sqrt(p_u * (1 - p_u) / n)),
                       "p_adj": adjusted(np.abs(t_obs), null_u), **atoms_near(null_u, q99_u)}
    if pol is not None:
        null_d = np.concatenate(nd)
        row = t_obs * pol
        s_d = float(np.nanmax(row))
        q99_d = float(np.quantile(null_d, 0.99))
        p_d = p_of(null_d, s_d)
        out["directional"] = {"S": s_d, "p": p_d, "q99": q99_d, "margin": s_d - q99_d,
                              "q95": float(np.quantile(null_d, 0.95)),
                              "mc_se": None if exact else float(np.sqrt(p_d * (1 - p_d) / n)),
                              "p_adj": adjusted(row, null_d), **atoms_near(null_d, q99_d)}
    return out


def check_against_project(d, target, base, pol) -> dict:
    """The engine must reproduce the project's statistic and its first 2,000 null draws."""
    eng = SignFlip(d)
    g = nulls(target, base, pol, N_CHECK)
    t_mine = eng.t(np.ones((1, d.shape[0])))[0]
    t_proj = g["t_raw"][0]
    both = ~np.isnan(t_proj)
    if not np.allclose(t_mine[both], t_proj[both], rtol=1e-10, atol=1e-12, equal_nan=True):
        raise AssertionError("observed t differs from the project's")
    pats = project_patterns(d.shape[0], N_CHECK)
    tn = eng.t(pats)
    mu = np.nanmax(np.abs(tn), axis=1)
    diff_u = float(np.max(np.abs(mu - g["null_u"])))
    res = {"n_checked": N_CHECK, "max_abs_diff_unsigned": diff_u}
    if pol is not None:
        md = np.nanmax(tn * pol[None, :], axis=1)
        res["max_abs_diff_directional"] = float(np.max(np.abs(md - g["null_d"])))
    if max(v for k, v in res.items() if k.startswith("max")) > 1e-9:
        raise AssertionError(f"null differs from the project's: {res}")
    return res


# ---------------------------------------------------------------- the families

def registered_index() -> dict:
    """Registered results keyed for the cross-check of every observed statistic."""
    idx = {}
    for g in ("full", "slices", "split_control", "row3", "row3b", "row2c"):
        for r in json.loads((ANALYSIS / f"tests_{g}.json").read_text())["results"]:
            if r.get("status", "run") != "run":
                continue
            idx[(g, r["corpus"], r["rater"], r["family"], str(r.get("selector")))] = r
    return idx


def jobs() -> list[dict]:
    out = []
    for corpus in CORPORA:
        for rater in ("openai_gpt-5-mini", "anthropic_claude-haiku-4-5", "matcher_M1", "matcher_M1a"):
            for fam, (lv, axes, signs) in families_for(rater).items():
                base = {"corpus": corpus, "rater": rater, "family": fam, "file_level": lv,
                        "axes": axes, "signs": signs}
                out.append({**base, "group": "full", "selector": None})
                out.append({**base, "group": "split_control", "selector": "split"})
                if corpus == "OWN":
                    for k in range(5):
                        out.append({**base, "group": "slices", "selector": k})
    for run in ("GG", "OD"):
        out.append({"group": "row3", "corpus": run, "rater": "stored pipeline verdicts",
                    "family": "all", "selector": None})
        out.append({"group": "row2c", "corpus": run, "rater": "stored + openai_gpt-5-mini L2",
                    "family": "all+L2", "selector": None})
        for fam in ("direct", "direct_partial", "direct_partial_wo_h065_g003"):
            out.append({"group": "row3b", "corpus": run, "rater": "stored pipeline verdicts",
                        "family": fam, "selector": None})
    return out


def rows2c(run: str, stored: dict, axes_all: list[str]):
    """Row 2c's join, as ``court_oracle_analysis_run.pipeline_work`` builds it."""
    ours = load_rows(run, "L2", JUDGES["gpt"])
    key = lambda c, r: (c, r["principal"], r["prompt_id"], int(r["s"]))
    index = {key(r["condition"], r): r for r in ours}
    joined = {}
    for cond in ("target", "baseline"):
        joined[cond] = [{"principal": r["principal"], "instruction_id": r["instruction_id"],
                         "verdicts": {**{a: r["verdicts"][a] for a in axes_all},
                                      **{a: index[key(cond, r)]["verdicts"][a] for a in L2_SIX[:3]}}}
                        for r in stored[cond]]
    return joined["target"], joined["baseline"], axes_all + L2_SIX[:3]


def build(job: dict):
    g = job["group"]
    if g in ("row3", "row3b", "row2c"):
        run = job["corpus"]
        stored = stored_rows(run)
        axes_all = registry(run)
        if g == "row3":
            return _fmt(stored["target"], axes_all), _fmt(stored["baseline"], axes_all), axes_all, None
        if g == "row3b":
            axes, signs = mapped_families(run)[job["family"]]
            return _fmt(stored["target"], axes), _fmt(stored["baseline"], axes), axes, signs
        t, b, axes = rows2c(run, stored, axes_all)
        return t, b, axes, None
    rows = load_rows(job["corpus"], job["file_level"], job["rater"])
    if g == "split_control":
        first, second = SPLIT[job["corpus"]]
        t, b = split_baseline(rows, job["axes"], first, second)
    else:
        s_keep = SLICES[job["selector"]] if g == "slices" else None
        t, b = arms(rows, job["axes"], s_keep)
    return t, b, job["axes"], job["signs"]


def work(args) -> dict:
    job, registered = args
    t0 = time.time()
    t_rows, b_rows, axes, signs = build(job)
    d, target, base, instructions = cupertino_d(t_rows, b_rows, axes)
    pol = np.array(signs, dtype=float) if signs is not None else None
    res = {k: v for k, v in job.items() if k not in ("axes",)}
    res["axes"] = list(axes)
    res["n_axes"] = len(axes)
    res["check_project_null"] = check_against_project(d, target, base, pol)
    res.update(large_test(d, pol))
    # The observed statistics must equal the registered ones.
    if registered is not None:
        reg_u = registered["test2_unsigned"]["statistic"]
        if abs(reg_u - res["unsigned"]["S"]) > 1e-9:
            raise AssertionError(f"{job}: unsigned S {res['unsigned']['S']} != registered {reg_u}")
        res["registered"] = {"unsigned_S": reg_u, "unsigned_p": registered["test2_unsigned"]["p_family_wise"],
                             "unsigned_q99": registered["test2_unsigned"]["null_p99"],
                             "unsigned_margin": registered["test2_unsigned"]["margin"]}
        if pol is not None:
            t4 = registered["test4_directional"]
            if abs(t4["statistic"] - res["directional"]["S"]) > 1e-9:
                raise AssertionError(f"{job}: S_dir differs from registered")
            res["registered"].update({"dir_S": t4["statistic"], "dir_p": t4["p"], "dir_q99": t4["null_p99"],
                                      "dir_margin": t4["margin"],
                                      "signed_p": registered["test1_signed"]["p_family_wise"]})
        res["registered_matches_statistic"] = True
    res["seconds"] = round(time.time() - t0, 2)
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=14)
    args = ap.parse_args()
    out_path = REVISION / "large_null.json"
    if out_path.exists():
        raise SystemExit(f"{out_path} exists; this run never overwrites")
    reg = registered_index()
    todo, skipped = [], []
    for j in jobs():
        key = (j["group"], j["corpus"], j["rater"], j["family"], str(j.get("selector")))
        if j["group"] in ("full", "slices", "split_control") and key not in reg:
            skipped.append(key)  # a family the registered run did not run (failed seat)
            continue
        todo.append((j, reg.get(key)))
    print(f"skipped {len(skipped)} families the registered run did not run: {skipped}", flush=True)
    missing = [j for j, r in todo if r is None]
    if missing:
        raise SystemExit(f"{len(missing)} families have no registered counterpart")
    print(f"{len(todo)} families", flush=True)
    t0 = time.time()
    results = []
    with Pool(args.workers) as pool:
        for i, res in enumerate(pool.imap_unordered(work, todo), 1):
            results.append(res)
            if i % 20 == 0:
                print(f"{i}/{len(todo)} done, {time.time() - t0:.0f}s", flush=True)
    results.sort(key=lambda r: (r["group"], r["corpus"], r["rater"], r["family"], str(r.get("selector"))))
    dump({"n_mc": N_MC, "mc_seed": MC_SEED, "exact_max_m": EXACT_MAX_M, "tie_tolerance": TOL,
          "n_check_against_project": N_CHECK, "results": results}, out_path)
    print(f"wrote {out_path} ({len(results)} families) in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
