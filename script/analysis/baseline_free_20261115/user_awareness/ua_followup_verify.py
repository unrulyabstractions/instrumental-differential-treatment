"""Independent recomputation of every number the limits-and-controls outputs add.

    uv run python -m script.analysis.baseline_free_20261115.user_awareness.ua_followup_verify [--out DIR]

Imports nothing from this family or from ``src``: json, numpy and scipy only.
It reads the raw grade rows, rebuilds every statistic by its own route, and
compares it with the JSON the driver wrote. Exact statistics must agree to
1e-9. Monte Carlo p values use other draws (seed 7) and must agree within four
binomial standard errors plus 0.002. The REML fit uses a grid then a bounded
refinement on tau^2 rather than the driver's search on log tau^2, so the
calibration shares agree within 0.01. Writes ``verification.json`` once and
exits non-zero on any mismatch.
"""

from __future__ import annotations

import argparse
import json
import sys
from itertools import combinations
from pathlib import Path

import numpy as np
from scipy import optimize, stats

REPO = Path(__file__).resolve().parents[4]
OUT = REPO / "out/main/baseline_free_20261115/user_awareness"
FIRST = {"gpt-5-mini": "out/main/external/user_awareness_grading",
         "gpt-4.1-mini": "out/main/external/user_awareness_grading_gpt41mini",
         "gpt-5": "out/main/external/user_awareness_grading_gpt5"}
SAFETY = ["amanda_askell", "ryan_greenblatt", "eliezer_yudkowsky"]
ORIG = SAFETY + ["affiliation_twin"] + [f"general_{c}" for c in "abcdef"]
GENERAL6 = [f"general_{c}" for c in "abcdef"]
ALPHA = 0.01
CHECKS: list[dict] = []


def check(name: str, recorded, mine, tol: float) -> None:
    if isinstance(recorded, (list, tuple)):
        ok = len(recorded) == len(mine) and all(
            (a == b) if isinstance(a, str) else abs(a - b) <= tol for a, b in zip(recorded, mine))
    elif isinstance(recorded, (str, bool)) or recorded is None:
        ok = recorded == mine
    else:
        ok = abs(float(recorded) - float(mine)) <= tol
    CHECKS.append({"check": name, "recorded": recorded, "recomputed": mine, "tolerance": tol,
                   "ok": bool(ok)})


def mc_tol(p: float, n: int = 10000) -> float:
    return 4 * np.sqrt(max(p, 1 / n) * (1 - min(p, 1 - 1 / n)) / n) + 0.002


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def cube(rows: list[dict], ids: list[str]) -> np.ndarray:
    ex = sorted({r["instruction_id"] for r in rows})
    c = np.full((len(ids), len(ex), 4), np.nan)
    for r in rows:
        if r["principal"] in ids and int(r["level"]) == 1 and r.get("grade") is not None \
                and not r.get("failed"):
            c[ids.index(r["principal"]), ex.index(r["instruction_id"]), int(r["s"])] = r["grade"]
    return c


def blocked(c: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Blocked means and their noise variance, for a complete cube."""
    cm = c.mean(axis=2)
    k = c.shape[0]
    x = (cm - cm.mean(axis=0, keepdims=True)).mean(axis=1)
    v = c.var(axis=2, ddof=1) / c.shape[2]
    tot = v.sum(axis=0, keepdims=True)
    vd = (1 - 1 / k) ** 2 * v + (tot - v) / k ** 2
    return x, vd.sum(axis=1) / c.shape[1] ** 2


def bh(p) -> np.ndarray:
    p = np.asarray(p, dtype=float)
    m = p.size
    o = np.argsort(p)
    q = np.minimum.accumulate((p[o] * m / np.arange(1, m + 1))[::-1])[::-1]
    out = np.empty(m)
    out[o] = np.minimum(q, 1)
    return out


def pred_p(x, ref):
    ref = np.asarray(ref, dtype=float)
    n = ref.size
    t = (x - ref.mean()) / (ref.std(ddof=1) * np.sqrt(1 + 1 / n))
    return t, stats.t.cdf(t, n - 1)


GRID = np.concatenate([[0.0], np.logspace(-9, 0.5, 1500)])


def reml(y, se2):
    y, se2 = np.asarray(y, dtype=float), np.asarray(se2, dtype=float)

    def nll(t2):
        v = t2 + se2
        w = 1 / v
        mu = np.sum(w * y) / np.sum(w)
        return 0.5 * (np.sum(np.log(v)) + np.log(np.sum(w)) + np.sum(w * (y - mu) ** 2))

    v = GRID[:, None] + se2[None, :]
    w = 1 / v
    mu = (w * y).sum(1) / w.sum(1)
    vals = 0.5 * (np.log(v).sum(1) + np.log(w.sum(1)) + (w * (y[None] - mu[:, None]) ** 2).sum(1))
    i = int(np.argmin(vals))
    t2 = GRID[i]
    if i > 0:
        lo, hi = GRID[max(i - 1, 0)], GRID[min(i + 1, GRID.size - 1)]
        r = optimize.minimize_scalar(nll, bounds=(lo, hi), method="bounded",
                                     options={"xatol": 1e-14})
        if r.fun <= vals[i]:
            t2 = r.x
    w = 1 / (t2 + se2)
    return float(np.sum(w * y) / np.sum(w)), float(t2)


def exact_gap(xa, xb):
    x = np.concatenate([xa, xb])
    m = len(xa)
    s = np.array([x[list(c)].sum() for c in combinations(range(len(x)), m)])
    vals = s / m - (x.sum() - s) / (len(x) - m)
    obs = np.mean(xa) - np.mean(xb)
    return obs, len(vals), np.mean(vals <= obs + 1e-12), np.mean(vals >= obs - 1e-12)


def second_session(name):
    rows = load(OUT / f"grades_{name}.jsonl")
    groups = {r["principal"]: r["group"] for r in rows}
    ids = sorted(groups)
    c = cube(rows, ids)
    if np.isnan(c).any():
        raise SystemExit(f"{name}: incomplete cube")
    x, se2 = blocked(c)
    return rows, groups, ids, c, dict(zip(ids, x)), dict(zip(ids, se2))


def verify_floor(floor, first_x, sess2):
    for name, (xi, se) in first_x.items():
        pool = np.array([xi[k] for k in GENERAL6])
        rec = floor["first_session"][name]["analytic"]
        sd = pool.std(ddof=1)
        check(f"floor {name} first predictive 0.01", rec["predictive_t_alpha"],
              stats.t.ppf(0.01, 5) * sd * np.sqrt(1 + 1 / 6), 1e-9)
        check(f"floor {name} first predictive 0.01/3", rec["predictive_t_alpha_over_3"],
              stats.t.ppf(0.01 / 3, 5) * sd * np.sqrt(1 + 1 / 6), 1e-9)
        _, t2 = reml(pool, np.array([se[k] for k in GENERAL6]))
        med = np.median([se[k] for k in GENERAL6])
        check(f"floor {name} first calibration 0.01", rec["calibration_alpha"],
              stats.norm.ppf(0.01) * np.sqrt(t2 + med), 2e-3)
        check(f"floor {name} first calibration 0.01/3", rec["calibration_alpha_over_3"],
              stats.norm.ppf(0.01 / 3) * np.sqrt(t2 + med), 2e-3)
        check(f"floor {name} first group floor", floor["first_session"][name]["group_test"]["floor_p"],
              1 / 84, 1e-12)
    for name, (rows, groups, ids, c, xi, se) in sess2.items():
        pk = [k for k in ids if groups[k] in ("general", "general_decoy")]
        pool = np.array([xi[k] for k in pk])
        pse = np.array([se[k] for k in pk])
        n = pool.size
        rec = floor["second_session"][name]
        sd = pool.std(ddof=1)
        check(f"floor {name} second predictive 0.01", rec["analytic"]["predictive_t_alpha"],
              stats.t.ppf(0.01, n - 1) * sd * np.sqrt(1 + 1 / n), 1e-9)
        check(f"floor {name} second conformal floor", rec["analytic"]["conformal_floor_p"],
              1 / (n + 1), 1e-12)
        check(f"floor {name} second predictive 0.01/3", rec["analytic"]["predictive_t_alpha_over_3"],
              stats.t.ppf(0.01 / 3, n - 1) * sd * np.sqrt(1 + 1 / n), 1e-9)
        _, t2p = reml(pool, pse)
        for lab, a in (("alpha", 0.01), ("alpha_over_3", 0.01 / 3)):
            check(f"floor {name} second calibration {lab}", rec["analytic"][f"calibration_{lab}"],
                  stats.norm.ppf(a) * np.sqrt(t2p + np.median(pse)), 2e-3)
        trips = list(combinations(range(n), 3))
        trip_arr = np.array(trips)
        ref_fit = [reml(np.delete(pool, t), np.delete(pse, t)) for t in trips]
        single_fit = [reml(np.delete(pool, j), np.delete(pse, j)) for j in range(n)]
        for row_s, row_t in zip(rec["planted_single"]["rows"], rec["planted_triples"]["rows"]):
            delta = -row_s["delta_points"]
            rt = rc = 0
            for j in range(n):
                rest = np.delete(pool, j)
                _, p = pred_p(pool[j] - delta, rest)
                rt += p <= ALPHA
                mu, t2 = single_fit[j]
                rc += stats.norm.cdf((pool[j] - delta - mu) / np.sqrt(t2 + pse[j])) <= ALPHA
            check(f"planted single {name} {-delta:.2f} predictive", row_s["predictive_t"], rt / n, 1e-12)
            check(f"planted single {name} {-delta:.2f} calibration", row_s["calibration"], rc / n, 0.01)
            hit_t = hit_c = hit_g = 0
            for ti, t in enumerate(trips):
                shifted = pool.copy()
                shifted[list(t)] -= delta
                rest = np.delete(pool, t)
                ps = [pred_p(shifted[j], rest)[1] for j in t]
                hit_t += bh(ps).min() <= ALPHA
                mu, t2 = ref_fit[ti]
                pc = [stats.norm.cdf((shifted[j] - mu) / np.sqrt(t2 + pse[j])) for j in t]
                hit_c += bh(pc).min() <= ALPHA
                obs = shifted[list(t)].mean() - rest.mean()
                sums = shifted[trip_arr].sum(axis=1)
                gaps = sums / 3 - (shifted.sum() - sums) / (n - 3)
                hit_g += np.mean(gaps <= obs + 1e-12) <= ALPHA
            m = len(trips)
            check(f"planted triples {name} {-delta:.2f} predictive BH", row_t["predictive_t_bh_any"],
                  hit_t / m, 1e-12)
            check(f"planted triples {name} {-delta:.2f} calibration BH", row_t["calibration_bh_any"],
                  hit_c / m, 0.01)
            check(f"planted triples {name} {-delta:.2f} group", row_t["group_exact_permutation"],
                  hit_g / m, 1e-12)
        print(f"floor {name} checked", flush=True)


def verify_affiliated(aff, sess2):
    for name, (rows, groups, ids, c, xi, se) in sess2.items():
        rec = aff["subjects"][name]
        pk = [k for k in ids if groups[k] in ("general", "general_decoy")]
        fame = [k for k in ids if groups[k] == "fame_control"]
        twins = [k for k in ids if groups[k] in ("unknown_ai", "affiliation_twin")]
        affc = fame + twins
        obs, n, ph, pl = exact_gap(np.array([xi[k] for k in SAFETY]), np.array([xi[k] for k in affc]))
        r = rec["safety_vs_affiliated_controls"]
        check(f"aff {name} safety vs affiliated gap", r["gap_a_minus_b"], obs, 1e-9)
        check(f"aff {name} safety vs affiliated n", r["n_relabellings"], n, 0)
        check(f"aff {name} safety vs affiliated p harsher", r["p_one_sided_a_harsher"], ph, 1e-12)
        check(f"aff {name} safety vs affiliated p lenient", r["p_one_sided_a_more_lenient"], pl, 1e-12)
        obs, n, ph, pl = exact_gap(np.array([xi[k] for k in fame]), np.array([xi[k] for k in twins]))
        r = rec["fame_vs_twins"]
        check(f"aff {name} fame vs twins gap", r["gap_a_minus_b"], obs, 1e-9)
        check(f"aff {name} fame vs twins p harsher", r["p_one_sided_a_harsher"], ph, 1e-12)
        check(f"aff {name} fame vs twins p lenient", r["p_one_sided_a_more_lenient"], pl, 1e-12)
        ref = np.array([xi[k] for k in affc])
        ps = []
        for k in SAFETY:
            t, p = pred_p(xi[k], ref)
            ps.append(p)
            check(f"aff {name} {k} t vs affiliated", rec["safety_per_target_vs_affiliated_controls"][k]["t"], t, 1e-9)
        for k, q in zip(SAFETY, bh(ps)):
            check(f"aff {name} {k} BH vs affiliated",
                  rec["safety_per_target_vs_affiliated_controls"][k]["p_bh_over_targets"], q, 1e-9)
        low = min(xi[k] for k in pk)
        below = sorted(k for k in SAFETY + affc if xi[k] < low)
        check(f"aff {name} below every pool member", sorted(rec["affiliated_personas_below_every_pool_member"]),
              below, 0)
        for g, ks in (("unaffiliated_pool", pk), ("safety", SAFETY), ("fame", fame), ("twins", twins)):
            check(f"aff {name} group mean {g}", rec["group_mean_blocked"][g], np.mean([xi[k] for k in ks]), 1e-9)


def verify_shape(shape, first_x, sess2, transluce):
    for name, (xi, se) in first_x.items():
        pool = np.array([xi[k] for k in GENERAL6])
        rec = shape["first_session"][name]
        check(f"shape {name} first shapiro", rec["pool_shape"]["shapiro_wilk_p"], stats.shapiro(pool).pvalue, 1e-9)
        ps = []
        for j, k in enumerate(GENERAL6):
            ps.append(pred_p(pool[j], np.delete(pool, j))[1])
        for a in (0.01, 0.05, 0.10):
            check(f"placebo {name} first fires {a}", rec["placebo"]["predictive_t"][f"fires_at_{a:.2f}"],
                  int(np.sum(np.array(ps) <= a)), 0)
        check(f"placebo {name} first smallest", rec["placebo"]["predictive_t"]["smallest_p"], min(ps), 1e-9)
    for name, (rows, groups, ids, c, xi, se) in sess2.items():
        pk = [k for k in ids if groups[k] in ("general", "general_decoy")]
        pool = np.array([xi[k] for k in pk])
        pse = np.array([se[k] for k in pk])
        rec = shape["second_session"][name]
        z = (pool - pool.mean()) / pool.std(ddof=1)
        n = pool.size
        g1 = np.mean(z ** 3) * (n / (n - 1)) ** 1.5 * np.sqrt(n * (n - 1)) / (n - 2)
        check(f"shape {name} second skewness", rec["pool_shape"]["skewness"], g1, 1e-6)
        check(f"shape {name} second shapiro", rec["pool_shape"]["shapiro_wilk_p"], stats.shapiro(pool).pvalue, 1e-9)
        check(f"shape {name} second min z", rec["pool_shape"]["min_z_pool_sd"], z.min(), 1e-9)
        m2, m4 = np.mean((pool - pool.mean()) ** 2), np.mean((pool - pool.mean()) ** 4)
        g2 = ((n + 1) * (m4 / m2 ** 2 - 3) + 6) * (n - 1) / ((n - 2) * (n - 3))
        check(f"shape {name} second excess kurtosis", rec["pool_shape"]["excess_kurtosis"], g2, 1e-6)
        pt, pc, pf = [], [], []
        for j in range(n):
            rest = np.delete(pool, j)
            pt.append(pred_p(pool[j], rest)[1])
            mu, t2 = reml(rest, np.delete(pse, j))
            pc.append(stats.norm.cdf((pool[j] - mu) / np.sqrt(t2 + pse[j])))
            pf.append((1 + np.sum(rest <= pool[j])) / n)
        for test, ps, tol in (("predictive_t", pt, 0), ("empirical_calibration", pc, 0),
                              ("conformal", pf, 0)):
            for a in (0.01, 0.05, 0.10):
                check(f"placebo {name} second {test} fires {a}",
                      rec["placebo"][test][f"fires_at_{a:.2f}"], int(np.sum(np.array(ps) <= a + 1e-12)), tol)
            check(f"placebo {name} second {test} smallest", rec["placebo"][test]["smallest_p"], min(ps),
                  1e-9 if test != "empirical_calibration" else 2e-3)
        check(f"placebo {name} upper bound", rec["placebo"]["predictive_t"]["upper_95_rate_at_0.01_if_none_fire"],
              1 - 0.05 ** (1 / n), 1e-12)


def fisher(a, b):
    r = np.corrcoef(a, b)[0, 1]
    h = 1.96 / np.sqrt(len(a) - 3)
    return r, np.tanh(np.arctanh(r) - h), np.tanh(np.arctanh(r) + h)


def verify_panel(panel, first_c, sess2):
    names = list(first_c)
    xs = {n: blocked(first_c[n])[0] for n in names}
    for a in range(3):
        for b in range(a + 1, 3):
            key = f"{names[a]}|{names[b]}"
            r, lo, hi = fisher(xs[names[a]], xs[names[b]])
            rec = panel["first_session_pairs"][key]["all_10"]
            check(f"panel {key} r", rec["pearson_r"], r, 1e-9)
            check(f"panel {key} ci", [rec["ci95_low"], rec["ci95_high"]], [lo, hi], 1e-9)
    for n in names:
        a, _ = blocked(first_c[n][:, :, :2])
        b, _ = blocked(first_c[n][:, :, 2:])
        check(f"split half {n} first", panel["split_half_first_session"][n]["all_10"], np.corrcoef(a, b)[0, 1], 1e-9)
    (na, A), (nb, B) = list(sess2.items())
    ids = A[2]
    pk = [k for k in ids if A[1][k] in ("general", "general_decoy")]
    key = f"{na}|{nb}"
    for scope, ks in (("all_personas", ids), ("unaffiliated_pool", pk)):
        r, lo, hi = fisher(np.array([A[4][k] for k in ks]), np.array([B[4][k] for k in ks]))
        rec = panel["second_session_pairs"][key][scope]
        check(f"panel second {scope} r", rec["pearson_r"], r, 1e-9)
        check(f"panel second {scope} ci", [rec["ci95_low"], rec["ci95_high"]], [lo, hi], 1e-9)
    for name, S in sess2.items():
        a, _ = blocked(S[3][:, :, :2])
        b, _ = blocked(S[3][:, :, 2:])
        check(f"split half {name} second", panel["split_half_second_session"][name]["all_personas"],
              np.corrcoef(a, b)[0, 1], 1e-9)


def screen_stat(c: np.ndarray):
    """Max |t| over (candidate, axis) of rate minus median of the others, and the null."""
    ks = np.arange(3, 9)
    rates = np.stack([(c <= k).mean(axis=2) for k in ks], axis=2)        # (C, I, A)
    n_c = rates.shape[0]
    d = np.empty_like(rates)
    for i in range(n_c):
        d[i] = rates[i] - np.median(np.delete(rates, i, axis=0), axis=0)

    def tmax(dd):
        mean = dd.mean(axis=1)
        sd = dd.std(axis=1, ddof=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            t = mean / (sd / np.sqrt(dd.shape[1]))
        t = np.where(sd == 0, np.where(mean == 0, 0.0, np.inf), t)
        return np.abs(t)

    t_obs = tmax(d)
    s = float(np.nanmax(t_obs))
    rng = np.random.default_rng(7)
    null = np.empty(10000)
    for b in range(10000):
        perm = np.argsort(rng.random((d.shape[1], n_c)), axis=1).T
        null[b] = np.nanmax(tmax(d[perm, np.arange(d.shape[1])[None, :]]))
    return s, float((1 + np.sum(null >= s - 1e-12)) / 10001)


def verify_screen(screen, sess2):
    for name, (rows, groups, ids, c, xi, se) in sess2.items():
        s, p = screen_stat(c)
        rec = screen["subjects"][name]["screen"]
        check(f"screen all {name} S", rec["statistic"], s, 1e-9)
        check(f"screen all {name} p", rec["p_family_wise"], p, mc_tol(p))


def verify_temporal(temporal, sess2, first_rows):
    for name, (rows, groups, ids, c, xi, se) in sess2.items():
        rec = temporal[name]
        old = cube(first_rows[name], ORIG)
        new = cube(rows, ORIG)
        d_e = (new.mean(axis=2) - old.mean(axis=2)).mean(axis=0)
        check(f"temporal {name} per-exchange change", rec["exchange_by_session"]["per_exchange_change"],
              list(d_e), 1e-9)
        lead = ORIG.index(rec["leading_identity_contrast"]["identity"])

        def parts(o, nw):
            dl = blocked(nw)[0] - blocked(o)[0]
            de = (nw.mean(axis=2) - o.mean(axis=2)).mean(axis=0)
            return np.sum((de - de.mean()) ** 2), dl[lead] - np.delete(dl, lead).mean()

        e_obs, c_obs = parts(old, new)
        check(f"temporal {name} exchange statistic", rec["exchange_by_session"]["statistic"], e_obs, 1e-9)
        check(f"temporal {name} contrast", rec["leading_identity_contrast"]["change_minus_others"], c_obs, 1e-9)
        both = np.concatenate([old, new], axis=2)
        rng = np.random.default_rng(7)
        ne, nc = np.empty(10000), np.empty(10000)
        for b in range(10000):
            sh = np.take_along_axis(both, np.argsort(rng.random(both.shape), axis=2), axis=2)
            ne[b], nc[b] = parts(sh[:, :, :4], sh[:, :, 4:])
        pe = (1 + np.sum(ne >= e_obs)) / 10001
        pc = (1 + np.sum(np.abs(nc) >= abs(c_obs))) / 10001
        check(f"temporal {name} exchange p", rec["exchange_by_session"]["p"], pe, mc_tol(pe))
        check(f"temporal {name} contrast p", rec["leading_identity_contrast"]["p_two_sided"], pc, mc_tol(pc))
        ledger = [json.loads(line) for line in
                  (OUT / "request_spend_ledger.jsonl").read_text().splitlines() if line.strip()]
        served = sorted({r.get("served_model") for r in ledger
                         if r["model"] == name and not r["tag"].startswith("pilot__")})
        check(f"temporal {name} served snapshot", rec["served_snapshot_second_session"], served, 0)
        print(f"temporal {name} checked", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    rd = lambda f: json.loads((args.out / f).read_text())  # noqa: E731
    first_rows = {n: load(REPO / p / "grades_target.jsonl") for n, p in FIRST.items()}
    first_c = {n: cube(r, ORIG) for n, r in first_rows.items()}
    first_x = {}
    for n, c in first_c.items():
        x, se2 = blocked(c)
        first_x[n] = (dict(zip(ORIG, x)), dict(zip(ORIG, se2)))
    sess2 = {n: second_session(n) for n in ("gpt-4.1-mini", "gpt-5-mini")}
    transluce = json.loads((OUT / "transluce_stats.json").read_text())
    verify_affiliated(rd("affiliated_reference.json"), sess2)
    verify_shape(rd("pool_shape_and_placebos.json"), first_x, sess2, transluce)
    verify_panel(rd("panel_with_intervals.json"), first_c, sess2)
    verify_screen(rd("screen_all_personas.json"), sess2)
    verify_temporal(rd("temporal_check.json"), sess2, first_rows)
    verify_floor(rd("detection_floor.json"), first_x, sess2)
    bad = [c for c in CHECKS if not c["ok"]]
    out = {"what": "independent recomputation of the limits-and-controls outputs from raw grade rows",
           "imports": "json, numpy, scipy only", "mc_seed": 7, "n_checks": len(CHECKS),
           "n_failed": len(bad), "checks": CHECKS}
    path = args.out / "verification.json"
    if path.exists():
        raise SystemExit(f"refusing to overwrite {path}")
    path.write_text(json.dumps(out, indent=1, default=float) + "\n")
    print(f"{len(CHECKS)} checks, {len(bad)} failed")
    for c in bad:
        print("FAILED", c)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
