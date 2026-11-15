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
and every candidate's deleted residual. The exact normal null of G is a Monte
Carlo of 10^6 draws per k (``grubbs.grubbs_null``). Holm combines the two
scalars of each method.

Refuses to run until ``selfcheck.json`` says the selfcheck passed. Writes only
under ``out/main/baseline_free_20261115/name_population_outlier/`` and refuses to
overwrite a file there.
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

OUT = REPO / "out/main/baseline_free_20261115/name_population_outlier"
SEED, N_PERM, ALPHA = 20260726, 10000, 0.01
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
                 scalar_names=UNSIGNED) -> dict:
    """Every Level-1 outlier statistic of one table, from one permutation stream."""
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
    res = outlier_test(table, n_permutations=n_permutations, scalar_names=names)
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


def placebo_rows(res: dict, subject: Subject) -> list[dict]:
    rows = []
    for c in res["candidates"]:
        if subject.role == "ua" and c in subject.preregistered:
            continue
        rec = {"subject": subject.key, "role": subject.role, "model": subject.model,
               "roster": subject.roster, "k": res["k"], "placebo_target": c}
        pt, ps, pr = {}, {}, {}
        for n in UNSIGNED:
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
                    help="output folder; anything but the default is a dry run")
    ap.add_argument("--permutations", type=int, default=N_PERM,
                    help="dry runs only; the registered setting is 10,000")
    ap.add_argument("--mc-draws", type=int, default=MC_DRAWS, help="dry runs only")
    args = ap.parse_args()
    out_dir = args.out
    if out_dir.resolve() == OUT.resolve() and (args.permutations != N_PERM or args.mc_draws != MC_DRAWS
                                                 or args.only):
        raise SystemExit("the default output folder takes only the registered settings on every subject")
    sc_path = OUT / "selfcheck.json"
    if not sc_path.exists() or not json.loads(sc_path.read_text()).get("passed"):
        raise SystemExit("selfcheck.json missing or not passed; run selfcheck.py first")
    mine = {"results.json", "outlier_table.csv", "placebo_targets.csv", "grubbs_null_k3_k11.json",
            "reproduce_check.json", "settings.json", "runs", "run.log"}
    for p in (out_dir.iterdir() if out_dir.exists() else ()):
        if p.name in mine and p.name != "run.log":
            raise SystemExit(f"{p} already exists; outputs are never overwritten")

    subj = subjects()
    if args.only:
        subj = [s for s in subj if s.key in set(args.only)]
    by_key = {s.key: s for s in subj}
    settings = {
        "n_permutations": args.permutations, "seed": SEED, "alpha": ALPHA,
        "permutation": "within-instruction relabelling of the one-vs-median-of-rest gaps "
                       "(reference_free_max_statistic.permute_within_instructions), one stream "
                       "per subject shared by every statistic",
        "contrast": "reference_free_effect: candidate cell rate minus the median of the other candidates",
        "t_grid": "paired_excess_measures.standardized_excess over instructions",
        "scalars": {"peak": "max over axes of |t| (candidate_peaks)",
                    "rms": "sqrt(mean over axes of t^2)",
                    "peak_signed": "max over axes of t; UA only, positive = more low grades",
                    "mean_signed": "mean over axes of t; UA only, positive = more low grades"},
        "mad_detachment": "candidate_detachment_measures.detachment: (x_top - median_others) / "
                          "(1.4826 MAD_others), within-instruction shuffle null",
        "grubbs": "D = (x_top - mean_others)/sd_others; G^2 = ((k-1)^3/k^2) D^2/((k-2)+((k-1)/k) D^2)",
        "grubbs_exact_null": {"draws_per_k": args.mc_draws, "seed": MC_SEED, "k": list(MC_KS),
                              "p": "(1 + #{G_mc >= G}) / (1 + draws)"},
        "grubbs_bound": "k * P(T_{k-2} > t_G), t_G^2 = k(k-2)G^2/((k-1)^2 - kG^2)",
        "deleted_residual": "(x_c - m_-c)/(s_-c sqrt(1+1/(k-1))) ~ t_{k-2}; one-sided upward",
        "rank_p": "#{j: x_j >= x_c}/k, floor 1/k",
        "holm": "Holm over the two scalars of each method; UA pre-registered family is Holm over "
                "3 identities x 2 signed scalars",
        "preregistered": {s.key: list(s.preregistered) for s in subj if s.preregistered},
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
            results[r["key"]] = r
            pk = r["scalars"]["peak"]
            print(f"{r['key']:40s} k={r['k']} max p={r['target_only_max']['p_family_wise']:.4f} "
                  f"MAD p={pk['mad_detachment']['p_family_wise']:.4f} "
                  f"G={pk['grubbs']['G']:.3f} p_exact={pk['grubbs']['p_exact_mc']:.4f} "
                  f"lead={pk['grubbs']['leading']} ({r['seconds']}s)", flush=True)

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
        dec = decisions(r, s)
        reg = registered_result(s)
        record = {"subject": {k: v for k, v in s.__dict__.items() if k != "extra"},
                  "settings": {"n_permutations": args.permutations, "seed": SEED, "alpha": ALPHA,
                               "mc_draws": args.mc_draws, "mc_seed": MC_SEED, "level": s.level},
                  "input_sha256": {f: files_sha[f] for f in s.files},
                  "registered": reg, "result": r, "decisions": dec}
        per_run[s.key] = record
        write_new(out_dir / "runs" / f"{s.key}.json", _json(record))
        if s.role in ("null", "base", "half", "ua"):
            placebo.extend(placebo_rows(r, s))
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
                     "target_only_max": v["result"]["target_only_max"]}
                 for k, v in per_run.items()},
        "input_sha256": files_sha}))
    from script.analysis.baseline_free_20261115.name_population_outlier.summarize import (
        outlier_table_rows, write_csv)
    write_csv(out_dir / "outlier_table.csv", outlier_table_rows(per_run))
    write_csv(out_dir / "placebo_targets.csv", placebo)
    print(f"{len(checks)} reproduction checks, {n_bad} mismatches; {time.time() - t0:.0f}s total")


if __name__ == "__main__":
    main()
