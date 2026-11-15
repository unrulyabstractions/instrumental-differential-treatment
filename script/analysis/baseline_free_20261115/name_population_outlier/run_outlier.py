"""The name-population outlier test on every subject with k >= 3. No spend.

    PYTHONPATH=. nice -n 10 .venv/bin/python \\
        script/analysis/baseline_free_20261115/name_population_outlier/run_outlier.py --workers 14

Each subject is one model's verdict table read with no base model. Every
candidate gets two scalars from the target-only t-grid of
``reference_free_max_statistic`` (one-vs-median-of-rest gaps, paired t over
instructions): its peak |t| over axes and its row RMS of t. The user-awareness
subjects also get two signed scalars, positive toward lower grades: the largest
signed t over the grade-threshold axes and the mean signed t.

One permutation stream per subject (within-instruction relabelling, 10,000
shuffles, seed 20260726, the stream ``reference_free_max_test`` and
``candidate_detachment_test`` draw) carries every null at once: the target-only
maximum, the MAD detachment of each scalar, the Grubbs D and G of each scalar,
and every candidate's deleted residual. The normal-theory null of G is a Monte
Carlo of 10^6 draws per k (``grubbs.grubbs_null``); it is exact only for i.i.d.
normal scalars, and the field that holds it keeps the name ``p_exact_mc`` for
the readers of ``outlier_table.csv``. Holm combines the two scalars of each
method.

The same stream also measures the size of every normal-theory test under the
shuffle (the share of shuffles whose normal-theory p falls at or below alpha),
and, for the user-awareness subjects, each safety identity's residual against
the six general identities alone.

Refuses to run until ``selfcheck.json`` and ``selfcheck_revision.json`` say
their checks passed. ``--out`` other than the family folder is a staging folder:
a run there with the registered settings on every subject is a full run that
is moved into the family folder after its checks; any other setting is a dry
run. Refuses to overwrite a file in the output folder.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from script.analysis.baseline_free_20261115.name_population_outlier import grubbs as gb  # noqa: E402
from script.analysis.baseline_free_20261115.name_population_outlier.subjects import (  # noqa: E402
    PARTA, Subject, load_table, registered_result, subjects, undefined)
from src.common.file_io import load_json  # noqa: E402
from src.compare.behavior_count_table import BehaviorTable  # noqa: E402
from src.compare.candidate_detachment_measures import (  # noqa: E402
    _leave_one_out, candidate_peaks, detachment)
from src.compare.paired_excess_measures import (  # noqa: E402
    cell_rates, max_abs_statistic, permutation_tail_share, standardized_excess)
from src.compare.reference_free_max_statistic import (  # noqa: E402
    permute_within_instructions, reference_free_effect)
from src.external.user_awareness_materials import IDENTITIES  # noqa: E402

OUT = REPO / "out/main/baseline_free_20261115/name_population_outlier"
SEED, N_PERM, ALPHA = 20260726, 10000, 0.01
ALPHAS = (0.01, 0.05)
MC_DRAWS, MC_SEED, MC_KS = 1_000_000, 20260726, tuple(range(3, 12))
UNSIGNED = ("peak", "rms")
SIGNED = ("peak_signed", "mean_signed")


# ----------------------------------------------------------------------------
# The engine: one table, one permutation stream
# ----------------------------------------------------------------------------
def candidate_scalars(t: np.ndarray, names) -> dict[str, np.ndarray]:
    """Each candidate's scalar summaries of its row of the t-grid."""
    all_nan = np.all(np.isnan(t), axis=1)
    out = {}
    with np.errstate(invalid="ignore", over="ignore"):
        for n in names:
            if n == "peak":
                v = candidate_peaks(t)
            elif n == "rms":
                v = np.sqrt(np.nanmean(t * t, axis=1))
            elif n == "peak_signed":
                v = np.nanmax(np.where(np.isnan(t), -np.inf, t), axis=1)
            elif n == "mean_signed":
                v = np.nanmean(t, axis=1)
            else:
                raise ValueError(n)
            out[n] = np.where(all_nan, np.nan, v)
    return out


def _finite_summary(x: np.ndarray) -> dict:
    f = x[np.isfinite(x)]
    return {"n_finite": int(f.size), "n_inf": int(np.isinf(x).sum()),
            "mean": float(f.mean()) if f.size else float("nan"),
            "p95": float(np.quantile(f, 0.95)) if f.size else float("nan"),
            "p99": float(np.quantile(f, 0.99)) if f.size else float("nan")}


def outlier_test(table: BehaviorTable, n_permutations: int = N_PERM, seed: int = SEED,
                 scalar_names=UNSIGNED, return_nulls: bool = False) -> dict:
    """Every Level-1 outlier statistic of one table, from one permutation stream.

    With ``return_nulls`` the record also carries ``_nulls``: the shuffled
    scalars and the shuffled G, D and deleted residuals of every scalar. The
    driver reads them for the size checks and drops them before writing.
    """
    rates, candidates, instructions = cell_rates(table)
    d = reference_free_effect(rates)
    t_obs, mean_obs, m_obs = standardized_excess(d)
    k = len(candidates)
    x_obs = candidate_scalars(t_obs, scalar_names)

    rng = np.random.default_rng(seed)
    maxabs_null = np.empty(n_permutations)
    x_null = {n: np.empty((n_permutations, k)) for n in scalar_names}
    for b in range(n_permutations):
        t_null, _, _ = standardized_excess(permute_within_instructions(d, rng))
        maxabs_null[b] = max_abs_statistic(t_null, signed=False)
        for n, v in candidate_scalars(t_null, scalar_names).items():
            x_null[n][b] = v

    # The target-only maximum, exactly as reference_free_max_test reports it.
    s_max = max_abs_statistic(t_obs, signed=False)
    ci, cj = np.unravel_index(np.nanargmax(np.abs(t_obs)), t_obs.shape)
    out = {
        "candidates": list(candidates), "k": k, "n_instructions": len(instructions),
        "n_axes": len(table.axes), "n_responses": int(table.n_responses),
        "n_permutations": n_permutations, "seed": seed,
        "target_only_max": {
            "statistic": s_max,
            "p_family_wise": permutation_tail_share(maxabs_null, s_max, n_permutations),
            "null_mean": float(maxabs_null.mean()),
            "null_p95": float(np.quantile(maxabs_null, 0.95)),
            "argmax_candidate": candidates[int(ci)], "argmax_axis": table.axes[int(cj)],
            "argmax_t": float(t_obs[ci, cj])},
        "scalars": {},
    }
    for n in scalar_names:
        xo, xn = x_obs[n], x_null[n]
        # MAD detachment, the stored test's statistic and null.
        s_det, lead_det = detachment(xo)
        det_null = np.array([detachment(row)[0] for row in xn])
        rest = np.delete(xo, lead_det)
        rest = rest[~np.isnan(rest)]
        finite = det_null[np.isfinite(det_null)]
        mad = {
            "statistic": s_det,
            "p_family_wise": permutation_tail_share(det_null, s_det, n_permutations),
            "leading": candidates[lead_det], "leading_value": float(xo[lead_det]),
            "bulk_median": float(np.median(rest)) if rest.size else float("nan"),
            "null_mean": float(finite.mean()) if finite.size else float("nan"),
            "null_p95": float(np.quantile(finite, 0.95)) if finite.size else float("nan"),
            "n_null_infinite": int(np.isinf(det_null).sum()),
            "leave_one_out": dict(zip(candidates, _leave_one_out(xo), strict=True)),
        }
        # Grubbs form, top chosen as the maximum.
        D_obs, G_obs, lead_g, k_used = gb.grubbs_top(xo)
        DG_null = np.array([gb.grubbs_top(row)[:2] for row in xn])
        D_null, G_null = DG_null[:, 0], DG_null[:, 1]
        r_obs = gb.deleted_residuals(xo)
        r_null = np.array([gb.deleted_residuals(row) for row in xn])
        grubbs = {
            "D": D_obs, "G": G_obs, "G_max": gb.G_MAX(k_used), "k_used": k_used,
            "leading": candidates[lead_g],
            "p_shuffle_G": permutation_tail_share(G_null, G_obs, n_permutations),
            "p_shuffle_D": permutation_tail_share(D_null, D_obs, n_permutations),
            "p_bound": gb.grubbs_bound_p_from_r(float(r_obs[lead_g]), k_used),
            "p_bound_from_G": gb.grubbs_bound_p(G_obs, k_used),
            "deleted_residual_of_leader": float(r_obs[lead_g]),
            "null_G": _finite_summary(G_null), "null_D": _finite_summary(D_null),
        }
        df = k_used - 2
        per_candidate = {}
        rp = gb.rank_p(xo)
        for c, name in enumerate(candidates):
            per_candidate[name] = {
                "value": float(xo[c]), "deleted_residual": float(r_obs[c]),
                "p_t": float(gb.t_sf(r_obs[c], df)),
                "p_shuffle": permutation_tail_share(r_null[:, c], r_obs[c], n_permutations),
                "rank_p": float(rp[c]),
                "null_r": _finite_summary(r_null[:, c])}
        out["scalars"][n] = {"values": dict(zip(candidates, map(float, xo), strict=True)),
                             "mad_detachment": mad, "grubbs": grubbs,
                             "per_candidate": per_candidate, "df": df}
        if return_nulls:
            out.setdefault("_nulls", {})[n] = {"x": xn, "G": G_null, "D": D_null, "r": r_null}
    return out


# ----------------------------------------------------------------------------
# Worker
# ----------------------------------------------------------------------------
def _sha(path: str) -> str:
    return hashlib.sha256((REPO / path).read_bytes()).hexdigest()


def run_subject(subject: Subject, n_permutations: int = N_PERM) -> dict:
    t0 = time.time()
    by_key = {s.key: s for s in subjects()}
    table = load_table(subject, by_key)
    names = UNSIGNED + (SIGNED if subject.signed_toward else ())
    res = outlier_test(table, n_permutations=n_permutations, scalar_names=names, return_nulls=True)
    res["key"] = subject.key
    res["seconds"] = round(time.time() - t0, 1)
    return res


# ----------------------------------------------------------------------------
# Driver: exact p values, decisions, checks, tables
# ----------------------------------------------------------------------------
def attach_exact(res: dict, mc: dict) -> None:
    for sc in res["scalars"].values():
        g = sc["grubbs"]
        k = g["k_used"]
        g["p_exact_mc"] = gb.mc_tail_p(mc[k]["G"], g["G"])
        g["degenerate"] = bool(np.isinf(g["D"]))


def _holm2_min(p1: np.ndarray, p2: np.ndarray) -> np.ndarray:
    """The smaller Holm-adjusted p of a two-member family, draw by draw."""
    return np.minimum(1.0, 2.0 * np.fmin(p1, p2))


def attach_calibration(res: dict, mc: dict) -> None:
    """Size of each normal-theory test under this subject's own shuffle stream.

    For every shuffle b the normal-theory p of the shuffled G (and of every
    candidate's shuffled deleted residual) is computed exactly as for the
    observed table; the size is the share of the 10,000 shuffles at or below
    alpha. The shuffle carries sampling noise alone, so a size above alpha is
    the normal-theory test firing on noise.
    """
    nulls = res["_nulls"]
    cands = res["candidates"]
    pG, pT = {}, {}
    for n, sc in res["scalars"].items():
        g, nl = sc["grubbs"], nulls[n]
        k = g["k_used"]
        pG[n] = gb.mc_tail_p_many(mc[k]["G"], nl["G"])
        pT[n] = np.asarray(gb.t_sf(nl["r"], sc["df"]), dtype=float)
        g["normal_theory_size_under_shuffle"] = {str(a): float(np.mean(pG[n] <= a)) for a in ALPHAS}
        g["shuffle_G_quantiles"] = {q: float(np.quantile(nl["G"], float(q))) for q in ("0.95", "0.99")}
        g["normal_G_quantiles"] = {q: float(np.quantile(mc[k]["G"], float(q))) for q in ("0.95", "0.99")}
        sc["deleted_residual_size_under_shuffle"] = {
            str(a): {"mean_over_candidates": float(np.mean(pT[n] <= a)),
                     "any_candidate": float(np.mean(np.any(pT[n] <= a, axis=1))),
                     "per_candidate": {c: float(np.mean(pT[n][:, i] <= a)) for i, c in enumerate(cands)}}
            for a in ALPHAS}
    cal = {"n_shuffles": int(next(iter(nulls.values()))["G"].size)}
    for fam, pair in (("unsigned", UNSIGNED), ("signed", SIGNED)):
        if not all(n in pG for n in pair):
            continue
        hg = _holm2_min(pG[pair[0]], pG[pair[1]])
        ht = _holm2_min(pT[pair[0]], pT[pair[1]])
        cal[fam] = {
            "scalars": list(pair),
            "grubbs_normal_holm_size": {str(a): float(np.mean(hg <= a)) for a in ALPHAS},
            "grubbs_normal_size": {n: res["scalars"][n]["grubbs"]["normal_theory_size_under_shuffle"]
                                   for n in pair},
            "deleted_residual_holm_size": {
                str(a): {"mean_over_candidates": float(np.mean(ht <= a)),
                         "any_candidate": float(np.mean(np.any(ht <= a, axis=1)))} for a in ALPHAS},
            "deleted_residual_size": {n: {str(a): res["scalars"][n]["deleted_residual_size_under_shuffle"]
                                          [str(a)]["mean_over_candidates"] for a in ALPHAS} for n in pair},
            "shuffle_G99_above_normal_G99": {
                n: bool(res["scalars"][n]["grubbs"]["shuffle_G_quantiles"]["0.99"]
                        > res["scalars"][n]["grubbs"]["normal_G_quantiles"]["0.99"]) for n in pair},
        }
    res["normal_theory_calibration"] = cal


def _ref_row(xo: np.ndarray, xn: np.ndarray, c: int, ref: list[int], n_perm: int) -> dict:
    """One identity's residual against a fixed reference set, with every p."""
    df = len(ref) - 1
    r_obs = float(gb.reference_residuals(xo, c, ref))
    r_null = gb.reference_residuals(xn, c, ref)
    pool = [c] + list(ref)
    return {"value": float(xo[c]), "residual": r_obs, "df": df,
            "p_t": float(gb.t_sf(r_obs, df)), "p_t_two_sided": float(gb.t_sf_two_sided(r_obs, df)),
            "p_shuffle": permutation_tail_share(r_null, r_obs, n_perm),
            "p_shuffle_two_sided": permutation_tail_share(np.abs(r_null), abs(r_obs), n_perm),
            "rank_p": float(np.sum(xo[pool] >= xo[c])) / len(pool),
            "n_null_undefined": int(np.isnan(r_null).sum())}


def ua_general_reference(res: dict, subject: Subject, alpha: float = ALPHA) -> dict:
    """Each safety identity and the affiliation twin against the six general identities.

    The per-identity scalars are the ones the main test reads (signed t over the
    grade-threshold axes, positive toward lower grades). Only the reference set
    of the residual changes: the six general identities, so the residual has
    five degrees of freedom. Each general identity also serves as a placebo
    target against the other five (four degrees of freedom).
    """
    group = {i["key"]: i["group"] for i in IDENTITIES}
    cands = res["candidates"]
    gen = [i for i, c in enumerate(cands) if group[c] == "general"]
    tested = [c for c in cands if group[c] != "general"]
    n_perm = res["n_permutations"]
    out = {"reference": [cands[i] for i in gen], "df": len(gen) - 1, "scalars": list(SIGNED),
           "direction": "lower grades (positive signed t)", "identities": {}, "placebo_general": {}}
    for n in SIGNED:
        xo = np.array([res["scalars"][n]["values"][c] for c in cands])
        xn = res["_nulls"][n]["x"]
        for c in tested:
            out["identities"].setdefault(c, {"group": group[c]})[n] = _ref_row(xo, xn, cands.index(c), gen, n_perm)
        for gi in gen:
            ref = [j for j in gen if j != gi]
            out["placebo_general"].setdefault(cands[gi], {})[n] = _ref_row(xo, xn, gi, ref, n_perm)
    safety = [c for c in tested if group[c] == "safety"]
    fam = {}
    for kind in ("p_t", "p_shuffle", "p_t_two_sided", "p_shuffle_two_sided"):
        adj = gb.holm({f"{c}|{n}": out["identities"][c][n][kind] for c in safety for n in SIGNED})
        fam[kind] = {"holm": adj, "min_holm": min(adj.values()),
                     "reject": bool(min(adj.values()) <= alpha)}
    out["safety_family"] = {"identities": safety, **fam}
    for c in tested:
        if group[c] == "safety":
            continue
        out["identities"][c]["holm_over_scalars"] = {
            kind: min(gb.holm({n: out["identities"][c][n][kind] for n in SIGNED}).values())
            for kind in ("p_t", "p_shuffle", "p_t_two_sided", "p_shuffle_two_sided")}
    for g, row in out["placebo_general"].items():
        row["holm_p_t"] = min(gb.holm({n: row[n]["p_t"] for n in SIGNED}).values())
        row["holm_p_shuffle"] = min(gb.holm({n: row[n]["p_shuffle"] for n in SIGNED}).values())
        row["holm_rank_p"] = min(gb.holm({n: row[n]["rank_p"] for n in SIGNED}).values())
    return out


def ua_paired_grades(subject: Subject) -> dict:
    """Each identity's mean grade minus the general identities' mean, paired over exchanges.

    Cell means are taken over the parsed grades of one identity on one exchange;
    the difference is paired by exchange and read with a two-sided t test.
    """
    from scipy import stats
    group = {i["key"]: i["group"] for i in IDENTITIES}
    cells: dict[tuple[str, str], list[int]] = {}
    for f in subject.files:
        with (REPO / f).open() as fh:
            for line in fh:
                r = json.loads(line)
                if int(r["level"]) != subject.level or r.get("failed") or r.get("grade") is None:
                    continue
                cells.setdefault((r["principal"], r["instruction_id"]), []).append(int(r["grade"]))
    ids = sorted({p for p, _ in cells})
    instr = sorted({i for _, i in cells})
    M = np.array([[np.mean(cells[(p, i)]) if (p, i) in cells else np.nan for i in instr] for p in ids])
    gen = [j for j, p in enumerate(ids) if group[p] == "general"]
    gmean = np.nanmean(M[gen], axis=0)
    out = {"n_exchanges": len(instr),
           "samples_per_cell": sorted({len(v) for v in cells.values()}),
           "general_mean_grade": float(np.nanmean(gmean)), "identities": {}}
    for j, p in enumerate(ids):
        if group[p] == "general":
            continue
        d = M[j] - gmean
        d = d[~np.isnan(d)]
        t = float(d.mean() / (d.std(ddof=1) / np.sqrt(d.size)))
        out["identities"][p] = {"group": group[p], "mean_grade": float(np.nanmean(M[j])),
                                "mean_difference": float(d.mean()), "paired_t": t,
                                "df": int(d.size - 1),
                                "p_two_sided": float(2 * stats.t.sf(abs(t), d.size - 1))}
    safety = [p for p in out["identities"] if out["identities"][p]["group"] == "safety"]
    adj = gb.holm({p: out["identities"][p]["p_two_sided"] for p in safety})
    out["safety_holm_two_sided"] = adj
    out["safety_min_holm_two_sided"] = min(adj.values())
    return out


def _decide(pmap: dict[str, float], leaders: dict[str, str], alpha: float) -> dict:
    adj = gb.holm(pmap)
    rej = {k: bool(v <= alpha) for k, v in adj.items()}
    named = sorted({leaders[k] for k, r in rej.items() if r})
    return {"p": pmap, "holm": adj, "reject_holm": rej, "reject_any": any(rej.values()),
            "named": named[0] if len(named) == 1 else (named or None)}


def decisions(res: dict, subject: Subject, alpha: float = ALPHA) -> dict:
    sc = res["scalars"]
    out = {}
    lead_mad = {n: sc[n]["mad_detachment"]["leading"] for n in UNSIGNED}
    lead_g = {n: sc[n]["grubbs"]["leading"] for n in UNSIGNED}
    out["mad_detachment"] = _decide({n: sc[n]["mad_detachment"]["p_family_wise"] for n in UNSIGNED},
                                    lead_mad, alpha)
    out["grubbs_shuffle"] = _decide({n: sc[n]["grubbs"]["p_shuffle_G"] for n in UNSIGNED}, lead_g, alpha)
    out["grubbs_exact"] = _decide({n: sc[n]["grubbs"]["p_exact_mc"] for n in UNSIGNED}, lead_g, alpha)
    out["grubbs_bound"] = _decide({n: sc[n]["grubbs"]["p_bound"] for n in UNSIGNED}, lead_g, alpha)
    pre = {}
    signed = subject.signed_toward is not None
    names = SIGNED if signed else UNSIGNED
    fam_t, fam_s, fam_r = {}, {}, {}
    for target in subject.preregistered:
        row = {}
        for n in names:
            pc = sc[n]["per_candidate"][target]
            row[n] = {kk: pc[kk] for kk in ("value", "deleted_residual", "p_t", "p_shuffle", "rank_p")}
            fam_t[f"{target}|{n}"] = pc["p_t"]
            fam_s[f"{target}|{n}"] = pc["p_shuffle"]
            fam_r[f"{target}|{n}"] = pc["rank_p"]
        row["holm_over_scalars_t"] = gb.holm({n: row[n]["p_t"] for n in names})
        row["holm_over_scalars_shuffle"] = gb.holm({n: row[n]["p_shuffle"] for n in names})
        row["holm_over_scalars_rank"] = gb.holm({n: row[n]["rank_p"] for n in names})
        row["reject_t"] = any(v <= alpha for v in row["holm_over_scalars_t"].values())
        row["reject_shuffle"] = any(v <= alpha for v in row["holm_over_scalars_shuffle"].values())
        row["reject_rank"] = any(v <= alpha for v in row["holm_over_scalars_rank"].values())
        row["rank_floor"] = 1.0 / res["k"]
        pre[target] = row
    if pre:
        pre_family = {"scalars": list(names),
                      "direction": "lower grades (positive signed t)" if signed else "upward",
                      "holm_t": gb.holm(fam_t), "holm_shuffle": gb.holm(fam_s),
                      "holm_rank": gb.holm(fam_r)}
        pre_family["reject_t"] = any(v <= alpha for v in pre_family["holm_t"].values())
        pre_family["reject_shuffle"] = any(v <= alpha for v in pre_family["holm_shuffle"].values())
        pre_family["reject_rank"] = any(v <= alpha for v in pre_family["holm_rank"].values())
        out["preregistered"] = {"targets": pre, "family": pre_family}
    if signed:
        lead_sg = {n: sc[n]["grubbs"]["leading"] for n in SIGNED}
        out["grubbs_exact_signed"] = _decide({n: sc[n]["grubbs"]["p_exact_mc"] for n in SIGNED},
                                             lead_sg, alpha)
        out["grubbs_shuffle_signed"] = _decide({n: sc[n]["grubbs"]["p_shuffle_G"] for n in SIGNED},
                                               lead_sg, alpha)
    return out


def subset_source(subject: Subject, all_subjects: list[Subject]) -> str | None:
    """The full table a subset subject (a sample range or a split half) is drawn from."""
    if subject.half is not None:
        return subject.half[0]
    if subject.s_range is not None:
        return next(s.key for s in all_subjects if s.files == subject.files and s.s_range is None
                    and s.half is None and s.level == subject.level)
    return None


def placebo_rows(res: dict, subject: Subject, subset_of: str | None = None,
                 ua_ref: dict | None = None) -> list[dict]:
    """Every candidate outside the hypothesis as a pre-registered placebo target.

    Organism rosters read the two unsigned scalars against the other k - 1
    candidates. The user-awareness subjects read the two signed scalars the
    safety family reads: the seven identities outside the safety group against
    the other nine (``all_others``), and each general identity against the
    other five general identities (``general_others``).
    """
    rows = []
    base = {"subject": subject.key, "role": subject.role, "model": subject.model,
            "roster": subject.roster, "level": subject.level, "k": res["k"],
            "overlap": subset_of is not None, "subset_of": subset_of}
    names = SIGNED if subject.role == "ua" else UNSIGNED
    for c in res["candidates"]:
        if subject.role == "ua" and c in subject.preregistered:
            continue
        rec = {**base, "reference": "all_others", "df": res["k"] - 2, "placebo_target": c}
        pt, ps, pr = {}, {}, {}
        for n in names:
            pc = res["scalars"][n]["per_candidate"][c]
            rec[f"{n}_value"] = pc["value"]
            rec[f"{n}_deleted_residual"] = pc["deleted_residual"]
            rec[f"{n}_p_t"] = pc["p_t"]
            rec[f"{n}_p_shuffle"] = pc["p_shuffle"]
            rec[f"{n}_rank_p"] = pc["rank_p"]
            pt[n], ps[n], pr[n] = pc["p_t"], pc["p_shuffle"], pc["rank_p"]
        rec["holm_p_t"] = min(gb.holm(pt).values())
        rec["holm_p_shuffle"] = min(gb.holm(ps).values())
        rec["holm_rank_p"] = min(gb.holm(pr).values())
        rows.append(rec)
    if ua_ref:
        for c, row in ua_ref["placebo_general"].items():
            rec = {**base, "reference": "general_others", "df": row[SIGNED[0]]["df"],
                   "placebo_target": c}
            for n in SIGNED:
                rec[f"{n}_value"] = row[n]["value"]
                rec[f"{n}_deleted_residual"] = row[n]["residual"]
                rec[f"{n}_p_t"] = row[n]["p_t"]
                rec[f"{n}_p_shuffle"] = row[n]["p_shuffle"]
                rec[f"{n}_rank_p"] = row[n]["rank_p"]
            rec["holm_p_t"] = row["holm_p_t"]
            rec["holm_p_shuffle"] = row["holm_p_shuffle"]
            rec["holm_rank_p"] = row["holm_rank_p"]
            rows.append(rec)
    return rows


def check_reproduction(res_by_key: dict, subj_by_key: dict) -> list[dict]:
    """Every stored record this run overlaps, compared field by field."""
    checks = []
    parta = load_json(REPO / PARTA)["results"]
    for key, s in subj_by_key.items():
        res = res_by_key.get(key)
        if res is None:
            continue
        mad = res["scalars"]["peak"]["mad_detachment"]
        tmax = res["target_only_max"]
        peaks = res["scalars"]["peak"]["values"]
        for path, seat in s.stored_reference_free:
            rec = load_json(REPO / path)
            st = rec["seats"].get(seat)
            c = {"subject": key, "stored": f"{path}#seats.{seat}", "kind": "reference_free.json"}
            if st is None:
                c.update(match=False, reason="seat missing in stored record")
                checks.append(c)
                continue
            det = st.get("detachment", {})
            fields = {
                "max.statistic": (st["statistic"], tmax["statistic"]),
                "max.p_family_wise": (st["p_family_wise"], tmax["p_family_wise"]),
                "max.null_mean": (st["null_mean"], tmax["null_mean"]),
                "max.null_p95": (st["null_p95"], tmax["null_p95"]),
                "detachment.statistic": (det.get("statistic"), mad["statistic"]),
                "detachment.p_family_wise": (det.get("p_family_wise"), mad["p_family_wise"]),
                "detachment.leading_peak": (det.get("leading_peak"), mad["leading_value"]),
                "detachment.bulk_median_peak": (det.get("bulk_median_peak"), mad["bulk_median"]),
                "detachment.null_mean": (det.get("null_mean"), mad["null_mean"]),
                "detachment.null_p95": (det.get("null_p95"), mad["null_p95"]),
            }
            for cand, v in (det.get("peaks") or {}).items():
                fields[f"detachment.peaks.{cand}"] = (v, peaks.get(cand))
            for cand, v in (det.get("leave_one_out") or {}).items():
                fields[f"detachment.leave_one_out.{cand}"] = (v, mad["leave_one_out"].get(cand))
            diffs = {}
            exact = True
            for f, (a, b) in fields.items():
                if a is None or b is None:
                    exact = False
                    diffs[f] = "missing"
                    continue
                same = (a == b) or (np.isnan(a) and np.isnan(b))
                exact &= bool(same)
                if not same:
                    diffs[f] = {"stored": a, "got": b, "abs_diff": abs(a - b)}
            same_lead = det.get("leading") == mad["leading"]
            same_flag = det.get("detached") == bool(mad["p_family_wise"] <= det.get("alpha", 0.05))
            c.update({"match": bool(exact and same_lead and same_flag),
                      "n_fields": len(fields) + 2, "mismatches": diffs,
                      "stored_detachment_S": det.get("statistic"), "got_detachment_S": mad["statistic"],
                      "stored_detachment_p": det.get("p_family_wise"),
                      "got_detachment_p": mad["p_family_wise"],
                      "stored_leading": det.get("leading"), "got_leading": mad["leading"],
                      "stored_detached_at_alpha": [det.get("detached"), det.get("alpha")],
                      "stored_level": rec["level"], "stored_seed": rec["seed"],
                      "stored_n_permutations": rec["n_permutations"]})
            checks.append(c)
        for rid in s.stored_parta:
            got = parta.get(rid)
            c = {"subject": key, "stored": f"{PARTA}#results.{rid}", "kind": "partA target-only max"}
            if got is None:
                c.update(match=False, reason="partA id missing")
            else:
                c.update({"match": bool(got["S"] == tmax["statistic"]
                                        and got["p"] == tmax["p_family_wise"]
                                        and got["argmax_candidate"] == tmax["argmax_candidate"]),
                          "stored_S": got["S"], "got_S": tmax["statistic"],
                          "stored_p": got["p"], "got_p": tmax["p_family_wise"],
                          "stored_argmax": got["argmax_candidate"],
                          "got_argmax": tmax["argmax_candidate"]})
            checks.append(c)
        if s.stored_ua:
            rec = load_json(REPO / s.stored_ua)["reference_free"]
            det = rec["detachment"]
            ok = (rec["statistic"] == tmax["statistic"] and rec["p_family_wise"] == tmax["p_family_wise"]
                  and det["statistic"] == mad["statistic"] and det["p_family_wise"] == mad["p_family_wise"]
                  and det["leading"] == mad["leading"]
                  and all(det["peaks"][c] == peaks[c] for c in det["peaks"])
                  and det["null_mean"] == mad["null_mean"] and det["null_p95"] == mad["null_p95"])
            checks.append({"subject": key, "stored": s.stored_ua, "kind": "user_awareness_detection.json",
                           "match": bool(ok),
                           "stored_max": [rec["statistic"], rec["p_family_wise"]],
                           "got_max": [tmax["statistic"], tmax["p_family_wise"]],
                           "stored_detachment": [det["statistic"], det["p_family_wise"], det["leading"]],
                           "got_detachment": [mad["statistic"], mad["p_family_wise"], mad["leading"]]})
    return checks


def grubbs_null_record(mc: dict, draws: int = MC_DRAWS) -> dict:
    from scipy import stats
    rec = {"draws_per_k": draws, "seed": MC_SEED,
           "scheme": "one numpy default_rng(seed) draws k = 3..11 in order, each as 10^6 rows "
                     "of k standard normals in chunks of 200,000 rows; G and D for the row maximum",
           "levels": {}}
    qs = (0.5, 0.9, 0.95, 0.99, 0.995, 0.999)
    for k, arr in mc.items():
        G, D = arr["G"], arr["D"]
        tq = {str(q): float(stats.t.ppf(q, k - 2)) for q in (0.95, 0.99)}
        rec["levels"][str(k)] = {
            "G_max": gb.G_MAX(k), "rank_floor": 1.0 / k,
            "G_quantiles": {str(q): float(np.quantile(G, q)) for q in qs},
            "D_top_quantiles": {str(q): float(np.quantile(D, q)) for q in qs},
            "D_prespecified_quantiles": {q: v * float(np.sqrt(1 + 1 / (k - 1))) for q, v in tq.items()},
            "deleted_residual_t_quantiles": tq,
            "bound_G_critical": {
                str(a): float((k - 1) / np.sqrt(k) * np.sqrt(
                    stats.t.ppf(1 - a / k, k - 2) ** 2 / (k - 2 + stats.t.ppf(1 - a / k, k - 2) ** 2)))
                for a in (0.05, 0.01)},
            "mc_p_at_bound_critical": {
                str(a): gb.mc_tail_p(G, float((k - 1) / np.sqrt(k) * np.sqrt(
                    stats.t.ppf(1 - a / k, k - 2) ** 2 / (k - 2 + stats.t.ppf(1 - a / k, k - 2) ** 2))))
                for a in (0.05, 0.01)},
        }
    return rec


def write_new(path: Path, text: str) -> None:
    if path.exists():
        raise SystemExit(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _json(obj) -> str:
    def default(o):
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, np.bool_):
            return bool(o)
        raise TypeError(type(o))
    return json.dumps(obj, indent=1, default=default, allow_nan=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=14)
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--out", type=Path, default=OUT,
                    help="output folder; another folder is a staging folder (see the module notes)")
    ap.add_argument("--permutations", type=int, default=N_PERM,
                    help="dry runs only; the registered setting is 10,000")
    ap.add_argument("--mc-draws", type=int, default=MC_DRAWS, help="dry runs only")
    ap.add_argument("--save-nulls", type=Path, default=None,
                    help="folder outside the repository for the shuffled scalars (one .npz per subject)")
    args = ap.parse_args()
    out_dir = args.out
    if out_dir.resolve() == OUT.resolve() and (args.permutations != N_PERM or args.mc_draws != MC_DRAWS
                                                 or args.only):
        raise SystemExit("the default output folder takes only the registered settings on every subject")
    for name in ("selfcheck.json", "selfcheck_revision.json"):
        sc_path = OUT / name
        if not sc_path.exists() or not json.loads(sc_path.read_text()).get("passed"):
            raise SystemExit(f"{name} missing or not passed; run its selfcheck first")
    mine = {"results.json", "outlier_table.csv", "placebo_targets.csv", "grubbs_null_k3_k11.json",
            "reproduce_check.json", "settings.json", "runs", "run.log"}
    for p in (out_dir.iterdir() if out_dir.exists() else ()):
        if p.name in mine and p.name != "run.log":
            raise SystemExit(f"{p} already exists; outputs are never overwritten")

    all_subj = subjects()
    subj = all_subj
    if args.only:
        subj = [s for s in subj if s.key in set(args.only)]
    by_key = {s.key: s for s in subj}
    settings = {
        "n_permutations": args.permutations, "seed": SEED, "alpha": ALPHA,
        "permutation": "within-instruction relabelling of the one-vs-median-of-rest gaps "
                       "(reference_free_max_statistic.permute_within_instructions), one stream "
                       "per subject shared by every statistic",
        "monte_carlo_se_at_alpha": float(np.sqrt(ALPHA * (1 - ALPHA) / args.permutations)),
        "contrast": "reference_free_effect: candidate cell rate minus the median of the other candidates",
        "t_grid": "paired_excess_measures.standardized_excess over instructions",
        "scalars": {"peak": "max over axes of |t| (candidate_peaks)",
                    "rms": "sqrt(mean over axes of t^2)",
                    "peak_signed": "max over axes of t; UA only, positive = more low grades",
                    "mean_signed": "mean over axes of t; UA only, positive = more low grades"},
        "mad_detachment": "candidate_detachment_measures.detachment: (x_top - median_others) / "
                          "(1.4826 MAD_others), within-instruction shuffle null",
        "grubbs": "D = (x_top - mean_others)/sd_others; G^2 = ((k-1)^3/k^2) D^2/((k-2)+((k-1)/k) D^2)",
        "grubbs_normal_theory_null": {
            "draws_per_k": args.mc_draws, "seed": MC_SEED, "k": list(MC_KS),
            "p": "(1 + #{G_mc >= G}) / (1 + draws)",
            "exact_only_if": "the k candidate scalars are i.i.d. normal",
            "fields": "runs/*.json grubbs.p_exact_mc, decisions.grubbs_exact and the outlier_table.csv "
                      "columns grubbs_*_p_exact, grubbs_exact_* hold this normal-theory p; the names "
                      "are kept for the files' readers"},
        "normal_theory_size_under_shuffle": "share of the subject's 10,000 shuffles whose normal-theory "
                                            "p (G, or a candidate's deleted residual) is at or below alpha; "
                                            "Holm of two scalars rejects a shuffle when min(1, 2 min p) <= alpha",
        "grubbs_bound": "k * P(T_{k-2} > t_G), t_G^2 = k(k-2)G^2/((k-1)^2 - kG^2)",
        "deleted_residual": "(x_c - m_-c)/(s_-c sqrt(1+1/(k-1))) ~ t_{k-2}; one-sided upward",
        "rank_p": "#{j: x_j >= x_c}/k, floor 1/k",
        "holm": "Holm over the two scalars of each method; UA pre-registered family is Holm over "
                "3 identities x 2 signed scalars",
        "preregistered": {s.key: list(s.preregistered) for s in subj if s.preregistered},
        "preregistered_label": {"auditbench_contextual_optimism": "documented principal (oracle)",
                                "auditbench_secret_loyalty": "documented principal (oracle)",
                                "ua": "hypothesized group (the user-awareness study's safety identities)"},
        "ua_general_reference": "each safety identity and the affiliation twin against the six general "
                                "identities: (x_c - mean_gen)/(sd_gen sqrt(1+1/6)) ~ t_5, one-sided toward "
                                "lower grades and two-sided; shuffle p from the same stream; each general "
                                "identity against the other five as a placebo (t_4)",
        "ua_paired_grades": "identity cell-mean grade minus the six general identities' cell mean, paired "
                            "over exchanges, two-sided t; Holm over the three safety identities",
        "placebo_targets": "every candidate of every null, base and half, and every UA identity outside the "
                           "safety group, read as a pre-registered target with the scalars of its own family; "
                           "tables drawn from another table (a sample range or a split half) are marked overlap",
        "k3": "defined, no power: the deleted residual has 1 degree of freedom and the normal-theory "
              "critical G sits at its ceiling",
        "split_half_seed": 20260726,
        "levels": {s.key: s.level for s in subj},
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    write_new(out_dir / "settings.json", _json(settings))

    t0 = time.time()
    print(f"Monte Carlo Grubbs null: {args.mc_draws} draws for k in {MC_KS}", flush=True)
    mc = gb.grubbs_null(MC_KS, args.mc_draws, MC_SEED)
    print(f"  done in {time.time() - t0:.0f}s", flush=True)
    write_new(out_dir / "grubbs_null_k3_k11.json", _json(grubbs_null_record(mc, args.mc_draws)))

    results: dict[str, dict] = {}
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(run_subject, s, args.permutations): s.key for s in subj}
        for f in as_completed(futs):
            r = f.result()
            attach_exact(r, mc)
            attach_calibration(r, mc)
            results[r["key"]] = r
            pk = r["scalars"]["peak"]
            cal = r["normal_theory_calibration"]["unsigned"]
            print(f"{r['key']:40s} k={r['k']} max p={r['target_only_max']['p_family_wise']:.4f} "
                  f"MAD p={pk['mad_detachment']['p_family_wise']:.4f} "
                  f"G={pk['grubbs']['G']:.3f} p_normal={pk['grubbs']['p_exact_mc']:.4f} "
                  f"lead={pk['grubbs']['leading']} size@0.01 G-Holm "
                  f"{cal['grubbs_normal_holm_size']['0.01']:.4f} ({r['seconds']}s)", flush=True)

    files_sha = {}
    for s in subj:
        for f in s.files:
            files_sha.setdefault(f, _sha(f))
        if s.axes != "ua_grade_axes":
            files_sha.setdefault(s.axes, _sha(s.axes))
    per_run = {}
    placebo = []
    for s in subj:
        r = results[s.key]
        ua_ref = ua_general_reference(r, s) if s.role == "ua" else None
        if args.save_nulls is not None:
            args.save_nulls.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(args.save_nulls / f"{s.key}.npz", **{
                f"{n}_{part}": v.astype(np.float32) for n, d in r["_nulls"].items() for part, v in d.items()})
        r.pop("_nulls")
        dec = decisions(r, s)
        reg = registered_result(s)
        src = subset_source(s, all_subj)
        record = {"subject": {k: v for k, v in s.__dict__.items() if k != "extra"},
                  "settings": {"n_permutations": args.permutations, "seed": SEED, "alpha": ALPHA,
                               "mc_draws": args.mc_draws, "mc_seed": MC_SEED, "level": s.level},
                  "input_sha256": {f: files_sha[f] for f in s.files},
                  "subset_of": src,
                  "registered": reg, "result": r, "decisions": dec}
        if ua_ref is not None:
            record["ua_general_reference"] = ua_ref
            record["ua_paired_grades"] = ua_paired_grades(s)
        per_run[s.key] = record
        write_new(out_dir / "runs" / f"{s.key}.json", _json(record))
        if s.role in ("null", "base", "half", "ua"):
            placebo.extend(placebo_rows(r, s, subset_of=src, ua_ref=ua_ref))
    checks = check_reproduction(results, by_key)
    n_bad = sum(not c["match"] for c in checks)
    write_new(out_dir / "reproduce_check.json", _json({
        "n_checks": len(checks), "n_mismatch": n_bad, "checks": checks,
        "note": "partA never checked the detachment fields of reference_free.json; this does"}))
    und = undefined()
    from script.analysis.baseline_free_20261115.name_population_outlier.summarize import summarize
    summary = summarize(per_run, placebo, checks, und)
    write_new(out_dir / "results.json", _json({
        "settings": settings, "summary": summary, "undefined_k2": und,
        "runs": {k: {"registered": v["registered"], "decisions": v["decisions"],
                     "k": v["result"]["k"], "role": v["subject"]["role"],
                     "target_only_max": v["result"]["target_only_max"],
                     "normal_theory_calibration": v["result"]["normal_theory_calibration"]}
                 for k, v in per_run.items()},
        "input_sha256": files_sha}))
    from script.analysis.baseline_free_20261115.name_population_outlier.summarize import (
        outlier_table_rows, write_csv)
    write_csv(out_dir / "outlier_table.csv", outlier_table_rows(per_run))
    write_csv(out_dir / "placebo_targets.csv", placebo)
    print(f"{len(checks)} reproduction checks, {n_bad} mismatches; {time.time() - t0:.0f}s total")


if __name__ == "__main__":
    main()
