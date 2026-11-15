"""Batched statistics for the planted-effect experiment, equal to the library's.

Every statistic here is a vectorized copy of a function in ``src/compare``. The
copies exist for speed: one permutation stream evaluates every statistic on a
batch of shuffled tables at once. ``test_planted_core.py`` checks each copy
against the library function it copies, value for value, and the ``reproduce``
step of ``run_planted.py`` checks the whole stream against stored records.

Arrays carry a leading batch axis. A rate table is (k, I, J): candidate,
instruction, axis. A batch of effect tables is (B, k, I, J); a batch of t grids
is (B, k, J).

The statistics:

- ``screen_median``: max |t| of each candidate's cell minus the median of the
  other candidates (``reference_free_max_test``).
- ``screen_mean``: max |t| of each candidate's cell minus the mean of the others
  (``paired_max_test`` with nothing subtracted).
- ``detach_mad``: the top candidate peak above the median of the other peaks, in
  MAD units (``candidate_detachment_test``).
- ``grubbs``: Grubbs's maximum studentized deviate of the k peaks.
- ``deleted_residual``: the pre-registered candidate's peak against the mean and
  SD of the other peaks, scaled to a t with k - 2 degrees of freedom.
- ``coherence_max`` and ``coherence_detach``: the axis-coherence scan R and its
  detachment (``axis_coherence_test``).
- ``context_max`` and ``context_prereg``: the signed context contrast, each
  candidate's committed-supporter gap minus its matched no-system-prompt gap,
  with a sign-flip null over matched instruction pairs.
"""

from __future__ import annotations

import numpy as np
from scipy import stats

from src.compare.axis_coherence_statistic import K0, SCALE_FLOOR_SHARE, Z_CLIP
from src.compare.candidate_detachment_measures import MAD_SCALE
from src.compare.reference_free_max_statistic import median_of_rest

__all__ = [
    "LABEL_STATS", "MEAN_STATS", "CONTEXT_STATS",
    "batch_t", "one_vs_rest_mean", "median_gap", "peaks_of", "detachment_batch",
    "grubbs_batch", "deleted_residual_batch", "coherence_batch",
    "label_statistics", "context_statistics", "grubbs_parametric_p",
    "deleted_residual_parametric_p", "permute_rows", "label_orders",
]

#: Statistics computed from the median-of-rest t grid of a label-shuffled table.
LABEL_STATS = ("screen_median", "detach_mad", "grubbs", "deleted_residual",
               "coherence_max", "coherence_detach")
#: Statistics computed from the mean-of-rest t grid of a label-shuffled table.
MEAN_STATS = ("screen_mean",)
#: Statistics computed from the context contrast under sign flips.
CONTEXT_STATS = ("context_max", "context_prereg")


# ---------------------------------------------------------------------------
# Effects and t grids
# ---------------------------------------------------------------------------
def median_gap(rates: np.ndarray) -> np.ndarray:
    """``reference_free_effect``: each cell minus the median of the other candidates."""
    return rates - median_of_rest(rates)


def one_vs_rest_mean(p: np.ndarray, axis: int = 0) -> np.ndarray:
    """``excess_effect``'s inner one-versus-rest gap, along a chosen candidate axis."""
    observed = ~np.isnan(p)
    filled = np.where(observed, p, 0.0)
    rest_sum = filled.sum(axis=axis, keepdims=True) - filled
    rest_count = observed.sum(axis=axis, keepdims=True) - observed.astype(int)
    with np.errstate(invalid="ignore", divide="ignore"):
        rest = np.where(rest_count > 0, rest_sum / rest_count, np.nan)
    return p - rest


def batch_t(d: np.ndarray, axis: int = 2) -> tuple[np.ndarray, np.ndarray]:
    """``standardized_excess`` along ``axis``: (t, mean). Unsigned polarity."""
    m = np.sum(~np.isnan(d), axis=axis)
    with np.errstate(invalid="ignore", divide="ignore"):
        if m.min() == d.shape[axis]:
            # No missing cell. These are np.mean and np.std's own operations (sum,
            # divide by n, subtract, square, sum, divide by n - 1, root), with the
            # first sum shared, so the values are bit for bit the library's.
            n = d.shape[axis]
            mean = np.sum(d, axis=axis) / n
            dev = d - np.expand_dims(mean, axis)
            np.multiply(dev, dev, out=dev)
            sd = np.sqrt(np.sum(dev, axis=axis) / (n - 1))
        else:
            mean = np.nanmean(d, axis=axis)
            sd = np.nanstd(d, axis=axis, ddof=1)
        ratio = mean / (sd / np.sqrt(np.maximum(m, 1)))
    degenerate = (m >= 2) & (sd == 0)
    t = np.where(m >= 2, ratio, np.nan)
    signs = np.sign(np.nan_to_num(mean, nan=0.0))
    infinite = np.where(signs > 0, np.inf, np.where(signs < 0, -np.inf, 0.0))
    return np.where(degenerate, infinite, t), mean


def label_orders(rng: np.random.Generator, n_batch: int, n_i: int, n_c: int) -> np.ndarray:
    """``permute_within_instructions``'s draws for ``n_batch`` permutations at once.

    The library draws ``rng.random((n_i, n_c))`` once per permutation and sorts
    it. One draw of shape (B, n_i, n_c) consumes the generator in the same order,
    so permutation b here is permutation b of the library's loop.
    """
    return np.argsort(rng.random((n_batch, n_i, n_c)), axis=2)  # (B, I, k)


def permute_rows(d: np.ndarray, orders: np.ndarray) -> np.ndarray:
    """Apply (B, I, k) orders to a (k, I, J) table: out[b, c, i] = d[orders[b, i, c], i]."""
    n_i = d.shape[1]
    idx_c = np.transpose(orders, (0, 2, 1))  # (B, k, I)
    return d[idx_c, np.arange(n_i)[None, None, :]]


# ---------------------------------------------------------------------------
# Peak statistics
# ---------------------------------------------------------------------------
def peaks_of(t: np.ndarray) -> np.ndarray:
    """``candidate_peaks``: each candidate's largest |t| over axes, (B, k)."""
    with np.errstate(invalid="ignore"):
        peaks = np.nanmax(np.abs(t), axis=2)
    return np.where(np.all(np.isnan(t), axis=2), np.nan, peaks)


def detachment_batch(peaks: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """``detachment`` for each row of (B, k) peaks with no NaN: (value, lead index)."""
    if np.isnan(peaks).any():
        raise ValueError("detachment_batch expects complete peaks")
    b, k = peaks.shape
    lead = np.argmax(peaks, axis=1)  # first maximum, as nanargmax
    keep = np.ones_like(peaks, dtype=bool)
    keep[np.arange(b), lead] = False
    rest = peaks[keep].reshape(b, k - 1)
    centre = np.median(rest, axis=1)
    top = peaks[np.arange(b), lead]
    with np.errstate(invalid="ignore", divide="ignore"):
        mad = MAD_SCALE * np.median(np.abs(rest - centre[:, None]), axis=1)
        gap = top - centre
        ratio = gap / mad
    out = np.where(mad <= 0, np.where(gap > 0, np.inf, 0.0), ratio)
    out = np.where(~np.isfinite(top), np.inf, out)
    out = np.where(~np.isfinite(centre), 0.0, out)
    if k < 3:
        out = np.full(b, np.nan)
    return out, lead


def _finite_capped(peaks: np.ndarray, t: np.ndarray) -> np.ndarray:
    """Peaks with an infinite value replaced by the largest finite |t| of its grid.

    ``coherence_of_effect`` uses the same cap before it sums over axes. A mean and
    SD over values that include an infinity are undefined, and the cap keeps an
    effect that held on every instruction as the largest value the grid has.
    """
    abs_t = np.where(np.isfinite(t), np.abs(t), -np.inf)
    cap = abs_t.reshape(abs_t.shape[0], -1).max(axis=1)
    cap = np.where(np.isfinite(cap), cap, 1.0)
    return np.minimum(peaks, cap[:, None])


def grubbs_batch(peaks: np.ndarray, t: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """One-sided Grubbs statistic for the largest peak: (max - mean) / SD."""
    x = _finite_capped(peaks, t)
    lead = np.argmax(x, axis=1)
    mean = x.mean(axis=1)
    sd = x.std(axis=1, ddof=1)
    top = x[np.arange(x.shape[0]), lead]
    with np.errstate(invalid="ignore", divide="ignore"):
        g = np.where(sd > 0, (top - mean) / sd, 0.0)
    return g, lead


def grubbs_parametric_p(g: float, k: int) -> float:
    """Grubbs's one-sided p for the maximum of k i.i.d. normal values.

    ``k * P(T_{k-2} > t)`` with ``t^2 = k (k - 2) G^2 / ((k - 1)^2 - k G^2)``. The
    bound is exact once no two values can both exceed the critical deviate, which
    holds in the tail a 0.01 test reads (checked by simulation in the tests).
    """
    if not np.isfinite(g):
        return 0.0 if g > 0 else 1.0
    denom = (k - 1) ** 2 - k * g * g
    if denom <= 0:
        return 0.0
    tval = np.sqrt(k * (k - 2) * g * g / denom)
    return float(min(1.0, k * stats.t.sf(tval, k - 2)))


def deleted_residual_batch(peaks: np.ndarray, t: np.ndarray, target: int) -> np.ndarray:
    """The pre-registered candidate's studentized deleted residual among the peaks."""
    x = _finite_capped(peaks, t)
    k = x.shape[1]
    rest = np.delete(x, target, axis=1)
    m = rest.mean(axis=1)
    s = rest.std(axis=1, ddof=1)
    diff = x[:, target] - m
    scale = s * np.sqrt(1.0 + 1.0 / (k - 1))
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.where(scale > 0, diff / scale, np.where(diff > 0, np.inf, -np.inf))
    return r


def deleted_residual_parametric_p(r: float, k: int) -> float:
    """One-sided p of the deleted residual under a normal random-effects null."""
    if not np.isfinite(r):
        return 0.0 if r > 0 else 1.0
    return float(stats.t.sf(r, k - 2))


# ---------------------------------------------------------------------------
# Axis coherence
# ---------------------------------------------------------------------------
def _row_median_positive(mad: np.ndarray) -> np.ndarray:
    """Median of the positive entries in each row of a (B, J) array; NaN if none."""
    s = np.sort(np.where(mad > 0, mad, np.inf), axis=1)
    n = np.sum(mad > 0, axis=1)
    out = np.full(mad.shape[0], np.nan)
    rows = np.arange(mad.shape[0])
    odd = (n % 2 == 1) & (n > 0)
    even = (n % 2 == 0) & (n > 0)
    out[odd] = s[rows[odd], (n[odd] - 1) // 2]
    lo = s[rows[even], n[even] // 2 - 1]
    hi = s[rows[even], n[even] // 2]
    out[even] = (lo + hi) / 2.0
    return out


def coherence_batch(t: np.ndarray, k0: int = K0) -> np.ndarray:
    """``coherence_of_effect`` from a (B, k, J) t grid: R per candidate, (B, k)."""
    b = t.shape[0]
    abs_t = np.where(np.isfinite(t), np.abs(t), -np.inf)
    cap = abs_t.reshape(b, -1).max(axis=1)
    cap = np.where(np.isfinite(cap), cap, 1.0)[:, None, None]
    t = np.clip(np.where(np.isposinf(t), cap, np.where(np.isneginf(t), -cap, t)), -cap, cap)
    if np.isnan(t).any():
        raise ValueError("coherence_batch expects a complete t grid")
    centre = np.median(t, axis=1, keepdims=True)
    mad = MAD_SCALE * np.median(np.abs(t - centre), axis=1, keepdims=True)  # (B,1,J)
    med_pos = _row_median_positive(mad[:, 0, :])
    floor = np.where(np.isnan(med_pos), 1.0, SCALE_FLOOR_SHARE * med_pos)
    floor = np.where(floor > 0, floor, 1.0)
    scale = np.maximum(mad, floor[:, None, None])
    with np.errstate(invalid="ignore", divide="ignore"):
        z = (t - centre) / scale
    z = np.clip(np.nan_to_num(z, nan=0.0, posinf=Z_CLIP, neginf=-Z_CLIP), -Z_CLIP, Z_CLIP)
    n_j = z.shape[2]
    k_max = min(k0, n_j)
    ks = np.sqrt(np.arange(1, k_max + 1))
    best = np.zeros(z.shape[:2])
    for sign in (1.0, -1.0):
        ordered = np.sort(sign * z, axis=2)[:, :, ::-1]
        scanned = np.cumsum(ordered[:, :, :k_max], axis=2) / ks
        take = scanned.max(axis=2)
        best = np.where(take > best, take, best)
    return best


# ---------------------------------------------------------------------------
# One batch of every statistic
# ---------------------------------------------------------------------------
def label_statistics(t_med: np.ndarray, target: int) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Every median-grid statistic on a (B, k, J) batch: name -> (value, lead)."""
    peaks = peaks_of(t_med)
    flat = np.abs(t_med).reshape(t_med.shape[0], -1)
    flat_nan = np.where(np.isnan(flat), -np.inf, flat)
    arg = np.argmax(flat_nan, axis=1)
    screen = np.where(np.all(np.isnan(flat), axis=1), 0.0, np.nanmax(flat, axis=1))
    lead_screen = arg // t_med.shape[2]
    det, lead_det = detachment_batch(peaks)
    g, lead_g = grubbs_batch(peaks, t_med)
    r = deleted_residual_batch(peaks, t_med, target)
    coh = coherence_batch(t_med)
    lead_coh = np.argmax(coh, axis=1)
    coh_det, lead_cd = detachment_batch(coh)
    target_col = np.full(t_med.shape[0], target)
    return {"screen_median": (screen, lead_screen), "detach_mad": (det, lead_det),
            "grubbs": (g, lead_g), "deleted_residual": (r, target_col),
            "coherence_max": (coh.max(axis=1), lead_coh),
            "coherence_detach": (coh_det, lead_cd)}


def mean_statistics(t_mean: np.ndarray) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    flat = np.abs(t_mean).reshape(t_mean.shape[0], -1)
    flat_nan = np.where(np.isnan(flat), -np.inf, flat)
    arg = np.argmax(flat_nan, axis=1)
    screen = np.where(np.all(np.isnan(flat), axis=1), 0.0, np.nanmax(flat, axis=1))
    return {"screen_mean": (screen, arg // t_mean.shape[2])}


def context_statistics(delta: np.ndarray, target: int) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Context-contrast statistics from a (B, k, P, J) batch of matched differences."""
    t, _ = batch_t(delta, axis=2)
    flat = np.abs(t).reshape(t.shape[0], -1)
    flat_nan = np.where(np.isnan(flat), -np.inf, flat)
    arg = np.argmax(flat_nan, axis=1)
    cmax = np.where(np.all(np.isnan(flat), axis=1), 0.0, np.nanmax(flat, axis=1))
    tt = np.abs(t[:, target, :])
    pre = np.where(np.all(np.isnan(tt), axis=1), 0.0, np.nanmax(tt, axis=1))
    return {"context_max": (cmax, arg // t.shape[2]),
            "context_prereg": (pre, np.full(t.shape[0], target))}


# ---------------------------------------------------------------------------
# Permutation streams
# ---------------------------------------------------------------------------
#: A stream may stop once every statistic it carries has this many permutation
#: values at or above the observed one. At 10,000 permutations and alpha 0.01 a
#: rejection needs at most 99, so the decision is already fixed.
STOP_EXCEEDANCES = 101


def tail_p(count: int, n: int) -> float:
    """``permutation_tail_share`` from a count: (1 + count) / (1 + n)."""
    return (1.0 + count) / (1.0 + n)


def _chunk_size(k: int, n_i: int, n_j: int) -> int:
    return int(max(50, min(1000, 1.0e7 // (k * n_i * n_j))))


def label_stream(rates: np.ndarray, target: int, label_seed, n_perm: int = 10000,
                 early_stop: bool = True, ctx_pairs: tuple[np.ndarray, np.ndarray] | None = None,
                 flip_seed=None, keep_null: tuple[str, ...] = ("screen_median", "screen_mean"),
                 chunk: int | None = None) -> dict:
    """Every target-only statistic of one rate table from one permutation stream.

    ``label_seed`` seeds the within-instruction label shuffle exactly as
    ``reference_free_max_test`` seeds it. ``ctx_pairs`` is (committed index,
    neutral index) over instructions for the context contrast, whose null flips
    the sign of each matched pair; its own generator is seeded by ``flip_seed``.
    A statistic group stops consuming permutations once each of its statistics
    has ``STOP_EXCEEDANCES`` exceedances; the stream draws every permutation in
    order, so the permutations a group sees do not depend on when others stop.
    """
    k, n_i, n_j = rates.shape
    d_med = median_gap(rates)
    d_mean = one_vs_rest_mean(rates, axis=0)
    t_med, _ = batch_t(d_med[None])
    t_mean, _ = batch_t(d_mean[None])
    obs = {name: (float(v[0]), int(l[0])) for name, (v, l) in label_statistics(t_med, target).items()}
    obs.update({name: (float(v[0]), int(l[0])) for name, (v, l) in mean_statistics(t_mean).items()})
    groups = {"label": list(LABEL_STATS), "mean": list(MEAN_STATS)}
    if ctx_pairs is not None:
        cs, nt = ctx_pairs
        delta = d_med[:, cs, :] - d_med[:, nt, :]
        obs.update({name: (float(v[0]), int(l[0]))
                    for name, (v, l) in context_statistics(delta[None], target).items()})
        groups["context"] = list(CONTEXT_STATS)
        flip_rng = np.random.default_rng(flip_seed)
    counts = {name: 0 for name in obs}
    used = {name: 0 for name in obs}
    active = {g: True for g in groups}
    nulls = {name: [] for name in keep_null if name in obs}
    label_rng = np.random.default_rng(label_seed)
    chunk = chunk or _chunk_size(k, n_i, n_j)
    done = 0
    while done < n_perm:
        b = min(chunk, n_perm - done)
        orders = label_orders(label_rng, b, n_i, k)
        flips = (flip_rng.integers(0, 2, size=(b, len(ctx_pairs[0]))) * 2.0 - 1.0
                 if ctx_pairs is not None else None)
        batch: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        if active["label"]:
            tb, _ = batch_t(permute_rows(d_med, orders))
            batch.update(label_statistics(tb, target))
        if active["mean"]:
            tb, _ = batch_t(permute_rows(d_mean, orders))
            batch.update(mean_statistics(tb))
        if ctx_pairs is not None and active["context"]:
            batch.update(context_statistics(delta[None] * flips[:, None, :, None], target))
        for name, (values, _lead) in batch.items():
            value = obs[name][0]
            if not np.isnan(value):
                counts[name] += int(np.sum(values >= value))
            used[name] += b
            if name in nulls:
                nulls[name].append(values)
        done += b
        if early_stop:
            for g, names in groups.items():
                if active[g] and all(np.isnan(obs[n][0]) or counts[n] >= STOP_EXCEEDANCES
                                     for n in names):
                    active[g] = False
            if not any(active.values()):
                break
    out = {}
    for name, (value, lead) in obs.items():
        full = used[name] == n_perm
        nan_obs = bool(np.isnan(value))
        out[name] = {"value": value, "lead": lead, "exceedances": counts[name],
                     "permutations_used": used[name], "complete": full,
                     "p": (1.0 if nan_obs else tail_p(counts[name], n_perm)) if full else None,
                     "p_lower_bound": 1.0 if nan_obs else tail_p(counts[name], n_perm)}
    out["_t_med"] = t_med[0]
    out["_t_mean"] = t_mean[0]
    out["_nulls"] = {n: np.concatenate(v) for n, v in nulls.items() if v}
    return out


def paired_orders(rng: np.random.Generator, n_batch: int, n_i: int, n_c: int) -> np.ndarray:
    """``paired_max_test``'s draws: one ``rng.permutation`` per instruction per permutation."""
    out = np.empty((n_batch, n_i, n_c), dtype=np.int64)
    for b in range(n_batch):
        for i in range(n_i):
            out[b, i] = rng.permutation(n_c)
    return out


def paired_stream(p_t: np.ndarray, p_b: np.ndarray, seed, n_perm: int = 10000,
                  early_stop: bool = True, chunk: int | None = None,
                  draws: str = "library", exact: bool = True) -> dict:
    """``paired_max_test``'s statistic and null, batched.

    ``draws="library"`` takes one ``rng.permutation`` per instruction per
    permutation, as ``paired_max_test`` does, so one seed gives its p exactly.
    ``draws="argsort"`` relabels within instruction by sorting uniform noise, the
    same distribution drawn faster. ``exact=True`` recomputes both models'
    one-versus-rest gaps on every permuted table, as the library does;
    ``exact=False`` permutes the precomputed excess, which equals the recomputed
    one up to the order of a five-term sum (checked in the tests).
    """
    k, n_i, n_j = p_t.shape
    d = one_vs_rest_mean(p_t, axis=0) - one_vs_rest_mean(p_b, axis=0)
    t_obs, mean_obs = batch_t(d[None])
    flat = np.abs(t_obs[0])
    s_obs = float(np.nanmax(flat)) if np.any(~np.isnan(flat)) else 0.0
    ci, cj = np.unravel_index(np.nanargmax(flat), flat.shape)
    rng = np.random.default_rng(seed)
    chunk = chunk or _chunk_size(k, n_i, n_j)
    count, done, nulls = 0, 0, []
    while done < n_perm:
        b = min(chunk, n_perm - done)
        orders = (paired_orders(rng, b, n_i, k) if draws == "library"
                  else label_orders(rng, b, n_i, k))
        if exact:
            pt, pb = permute_rows(p_t, orders), permute_rows(p_b, orders)
            db = one_vs_rest_mean(pt, axis=1) - one_vs_rest_mean(pb, axis=1)
        else:
            db = permute_rows(d, orders)
        tb, _ = batch_t(db)
        fb = np.abs(tb).reshape(b, -1)
        values = np.where(np.all(np.isnan(fb), axis=1), 0.0, np.nanmax(fb, axis=1))
        count += int(np.sum(values >= s_obs))
        nulls.append(values)
        done += b
        if early_stop and count >= STOP_EXCEEDANCES:
            break
    full = done == n_perm
    return {"value": s_obs, "lead": int(ci), "lead_axis": int(cj), "exceedances": count,
            "permutations_used": done, "complete": full,
            "p": tail_p(count, n_perm) if full else None,
            "p_lower_bound": tail_p(count, n_perm),
            "draws": draws, "exact": exact,
            "_t": t_obs[0], "_mean": mean_obs[0], "_null": np.concatenate(nulls)}


def surviving_cells(t: np.ndarray, null: np.ndarray, n_perm: int, alpha: float) -> list[tuple[int, int]]:
    """Single-step maxT survivors: cells whose |t| has a raw tail share at or below alpha.

    The raw tail share falls as |t| grows, so the running maximum the library
    takes over cells in descending |t| equals the raw share, and a cell survives
    exactly when its own share is at or below alpha.
    """
    srt = np.sort(null)
    out = []
    for c, j in zip(*np.nonzero(~np.isnan(t))):
        v = abs(float(t[c, j]))
        count = int(srt.size - np.searchsorted(srt, v, side="left"))
        if tail_p(count, n_perm) <= alpha:
            out.append((int(c), int(j)))
    return out
