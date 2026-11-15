"""Two max-|t| tests over (candidate, axis) cells, each with a single-step maxT.

``paired_flip_test`` reads a (candidate, template, axis) array of within-template
context differences. Its t is the paired t over templates, exactly the
registered ``standardized_excess``. The null flips the sign of each template's
whole difference at once: swapping a template's two contexts negates every
candidate's and every axis's difference together, so the flip keeps the
dependence across cells.

``group_perm_test`` reads a (candidate, template, axis) array of per-template
values and two disjoint template families. Its t is Welch's two-sample t. The
null relabels the families over the participating templates, again moving a
template's whole slice together.

Both return the family-wise p for S = max |t|, the maxT-adjusted p of every
cell, and a maxT over each candidate's own axes (the invariance check, and the
fixed-target test for a pre-registered candidate). The p convention is the
registered one, (1 + #{null >= S}) / (1 + n).

The flips are evaluated from sufficient statistics: with signs s, the mean is
s.x / m and the sum of squares does not move, so a batch of flips is one matrix
product. A spread that is zero to rounding is read as exactly zero, matching
``standardized_excess``, whose two-pass spread is exactly zero there.
"""

from __future__ import annotations

import numpy as np

__all__ = ["paired_flip_test", "group_perm_test", "holm", "flip_t_rows", "welch_t_rows"]

_TOL = 1e-12
_CHUNK = 2000


def _degenerate(t_num, var, mean_like, ok):
    """Infinite t where the spread vanishes, zero where the mean does too."""
    sign = np.sign(mean_like)
    inf = np.where(sign > 0, np.inf, np.where(sign < 0, -np.inf, 0.0))
    return np.where(ok, np.where(var > 0, t_num, inf), np.nan)


def flip_t_rows(signs, xf, m, q):
    """Paired t per flip row: signs (B, T), xf (T, K) with NaN as 0, m and q per column."""
    s = signs @ xf
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = s / m
        var = (q - m * mean ** 2) / (m - 1)
        var = np.where(var <= _TOL * np.maximum(q / np.maximum(m, 1), 1e-300), 0.0, var)
        t = mean / np.sqrt(var / m)
    return _degenerate(t, var, mean, m >= 2)


def welch_t_rows(g, xf, mk, x2):
    """Welch t per labelling row: g (B, T) 0/1 for family one, columns as in ``flip_t_rows``."""
    s1, n1, q1 = g @ xf, g @ mk, g @ x2
    s0, n0, q0 = xf.sum(0) - s1, mk.sum(0) - n1, x2.sum(0) - q1
    with np.errstate(invalid="ignore", divide="ignore"):
        m1, m0 = s1 / n1, s0 / n0
        v1 = (q1 - n1 * m1 ** 2) / (n1 - 1)
        v0 = (q0 - n0 * m0 ** 2) / (n0 - 1)
        scale = np.maximum(np.maximum(q1 / np.maximum(n1, 1), q0 / np.maximum(n0, 1)), 1e-300)
        v1 = np.where(v1 <= _TOL * scale, 0.0, v1)
        v0 = np.where(v0 <= _TOL * scale, 0.0, v0)
        se2 = v1 / n1 + v0 / n0
        t = (m1 - m0) / np.sqrt(se2)
    return _degenerate(t, se2, m1 - m0, (n1 >= 2) & (n0 >= 2))


def _columns(x):
    c, t, a = x.shape
    flat = x.transpose(1, 0, 2).reshape(t, c * a)
    mk = (~np.isnan(flat)).astype(float)
    xf = np.where(mk > 0, flat, 0.0)
    return xf, mk, xf ** 2


def _maxes(t_rows, c, a):
    """Per-row overall max |t| and per-candidate max |t|; an all-NaN slice reads 0."""
    v = np.where(np.isnan(t_rows), -np.inf, np.abs(t_rows)).reshape(-1, c, a)
    per = v.max(axis=2)
    per = np.where(np.isneginf(per), 0.0, per)
    return per.max(axis=1), per


def _tail(null_sorted, values):
    n = null_sorted.size
    return (1.0 + n - np.searchsorted(null_sorted, values, side="left")) / (1.0 + n)


def _summarize(t_obs, null_max, null_per, candidates, axes, alpha):
    c, a = len(candidates), len(axes)
    t_grid = t_obs.reshape(c, a)
    obs_max, obs_per = _maxes(t_obs[None, :], c, a)
    s_obs = float(obs_max[0])
    n = null_max.size
    null_sorted = np.sort(null_max)
    p_family = float(_tail(null_sorted, np.array([s_obs]))[0])
    flat = np.where(np.isnan(t_grid), -np.inf, np.abs(t_grid)).ravel()
    order = np.argsort(-flat, kind="stable")
    raw = _tail(null_sorted, np.where(np.isneginf(flat), np.inf, flat))
    adjusted = np.ones(flat.size)
    running = 0.0
    for idx in order:
        if np.isneginf(flat[idx]):
            continue
        running = max(running, raw[idx])
        adjusted[idx] = running
    adjusted = adjusted.reshape(c, a)
    per_rows = []
    for k, name in enumerate(candidates):
        own = np.sort(null_per[:, k])
        j = int(np.argmax(np.where(np.isnan(t_grid[k]), -np.inf, np.abs(t_grid[k]))))
        per_rows.append({"candidate": name, "S": float(obs_per[0, k]),
                         "p": float(_tail(own, np.array([obs_per[0, k]]))[0]),
                         "top_axis": axes[j], "top_t": float(t_grid[k, j]),
                         "min_adjusted_p_full_family": float(adjusted[k].min())})
    ci, cj = divmod(int(order[0]), a)
    surviving = [{"candidate": candidates[i], "axis_id": axes[j]}
                 for i, j in zip(*np.nonzero(adjusted <= alpha))]
    return {"statistic": s_obs, "p_family_wise": p_family, "n_resamples": int(n),
            "alpha": alpha, "reject": bool(p_family <= alpha),
            "argmax_candidate": candidates[ci], "argmax_axis": axes[cj],
            "argmax_t": float(t_grid[ci, cj]),
            "argmax_tied_candidates": sorted(
                candidates[i] for i in range(c)
                if obs_per[0, i] == s_obs or (np.isfinite(s_obs) and
                                              abs(obs_per[0, i] - s_obs) <= 1e-9 * max(1.0, s_obs))),
            "null_mean": float(null_max.mean()), "null_p99": float(np.quantile(null_max, 0.99)),
            "surviving_pairs": surviving, "n_surviving_pairs": len(surviving),
            "per_candidate": per_rows, "t_grid": t_grid, "adjusted": adjusted}


def _lean(t_obs, null_max, c, a, alpha):
    """Statistic and family-wise p only, for placebo replicates."""
    s_obs = float(_maxes(t_obs[None, :], c, a)[0][0])
    p = float(_tail(np.sort(null_max), np.array([s_obs]))[0])
    return {"statistic": s_obs, "p_family_wise": p, "reject": bool(p <= alpha)}


def paired_flip_test(delta, candidates, axes, n=10000, seed=20260726, alpha=0.01,
                     full=True):
    """Sign-flip maxT over templates for a (candidate, template, axis) difference."""
    c, t, a = delta.shape
    xf, mk, x2 = _columns(delta)
    m, q = mk.sum(0), x2.sum(0)
    t_obs = flip_t_rows(np.ones((1, t)), xf, m, q)[0]
    rng = np.random.default_rng(seed)
    null_max, null_per = np.empty(n), np.empty((n, c))
    for lo in range(0, n, _CHUNK):
        b = min(_CHUNK, n - lo)
        signs = rng.integers(0, 2, size=(b, t)) * 2.0 - 1.0
        null_max[lo:lo + b], null_per[lo:lo + b] = _maxes(flip_t_rows(signs, xf, m, q), c, a)
    if not full:
        return _lean(t_obs, null_max, c, a, alpha)
    out = _summarize(t_obs, null_max, null_per, candidates, axes, alpha)
    out.update(n_templates=int(t), null="sign flip per template")
    return out


def group_perm_test(values, one, zero, candidates, axes, n=10000, seed=20260726, alpha=0.01,
                    full=True):
    """Family-label permutation maxT for per-template values; ``one``, ``zero`` index templates."""
    one, zero = list(one), list(zero)
    if set(one) & set(zero):
        raise ValueError("the two template families overlap")
    keep = one + zero
    c, _, a = values.shape
    xf, mk, x2 = _columns(values[:, keep, :])
    labels = np.r_[np.ones(len(one)), np.zeros(len(zero))]
    t_obs = welch_t_rows(labels[None, :], xf, mk, x2)[0]
    rng = np.random.default_rng(seed)
    null_max, null_per = np.empty(n), np.empty((n, c))
    for lo in range(0, n, _CHUNK):
        b = min(_CHUNK, n - lo)
        g = rng.permuted(np.broadcast_to(labels, (b, labels.size)).copy(), axis=1)
        null_max[lo:lo + b], null_per[lo:lo + b] = _maxes(welch_t_rows(g, xf, mk, x2), c, a)
    if not full:
        return _lean(t_obs, null_max, c, a, alpha)
    out = _summarize(t_obs, null_max, null_per, candidates, axes, alpha)
    out.update(n_templates=len(keep), n_family_one=len(one), n_family_zero=len(zero),
               null="family-label permutation over templates")
    return out


def holm(p_values: dict[str, float]) -> dict[str, float]:
    """Holm step-down adjusted p values for a small named family."""
    names = sorted(p_values, key=lambda k: p_values[k])
    m, running, out = len(names), 0.0, {}
    for i, k in enumerate(names):
        running = max(running, min(1.0, (m - i) * p_values[k]))
        out[k] = running
    return out
