"""Pooled within-run reference for the registered statistic (B45, exploratory).

The registered test refers its maximum ``S`` over candidate-axis pairs to a
within-instruction label permutation. That null cannot contain name-specific
drift from fine-tuning, because shuffling labels breaks any effect that a
candidate carries on every instruction. The idea here is that under a sparse
threat model most pairs of a run are null draws under the real fine-tune, so
the |t| values of the candidates other than the top one form a reference that
already contains drift.

The comparison is maximum against maximum: ``S`` is referred to the maximum of
``M`` draws from the reference, where ``M`` is the number of scored pairs in
the run. Three resampling schemes are offered. ``values`` draws single |t|
values. ``axes`` draws whole axis columns, which keeps the dependence among the
candidates scored on one axis (a shared judge question, the one-versus-rest
coupling). ``candidates`` draws whole candidate rows, which keeps the
dependence across one candidate's axes. A block scheme keeps drawing blocks
until at least ``M`` values are covered, so it draws slightly more than ``M``.

One property decides how far this can go, and it holds by construction: the
reference excludes the candidate that holds ``S``, so every reference value is
at most ``S``, and so is every resampled maximum. ``p_ref`` therefore sits at
its floor ``1 / (1 + B)`` unless another candidate ties ``S``. When two
candidates mirror each other, as in a two-candidate run, the tie is exact.
"""

from __future__ import annotations

import numpy as np

from src.compare.paired_excess_measures import excess_effect, standardized_excess

__all__ = ["SCHEMES", "VARIANTS", "t_grid", "top_candidate", "dropped_candidates",
           "resampled_maxima", "reference_tail_share", "ratio_to_quantile",
           "exact_values_tail_share", "pooled_reference_test"]

SCHEMES = ("values", "axes", "candidates")
VARIANTS = ("drop_top", "drop_top2", "drop_surviving")


def t_grid(p_t: np.ndarray, p_b: np.ndarray) -> np.ndarray:
    """The registered, unsigned t per (candidate, axis), NaN where unscorable."""
    t, _, _ = standardized_excess(excess_effect(p_t, p_b))
    return t


def top_candidate(abs_t: np.ndarray) -> int:
    """The candidate holding ``S``, chosen as ``paired_max_test`` chooses it."""
    ci, _ = np.unravel_index(np.nanargmax(abs_t), abs_t.shape)
    return int(ci)


def dropped_candidates(abs_t: np.ndarray, variant: str,
                       surviving: frozenset[int] = frozenset()) -> list[int]:
    """Which rows a variant leaves out of the reference."""
    top = top_candidate(abs_t)
    if variant == "drop_top":
        return [top]
    if variant == "drop_top2":
        row_max = np.array([np.nanmax(r) if np.any(~np.isnan(r)) else -np.inf
                            for r in abs_t])
        row_max[top] = np.inf
        return [int(c) for c in np.argsort(-row_max, kind="stable")[:2]]
    if variant == "drop_surviving":
        return sorted({top, *surviving})
    raise ValueError(f"unknown variant {variant}")


def _blocks(ref: np.ndarray, scheme: str) -> tuple[np.ndarray, np.ndarray]:
    """Block maxima and block sizes for a block scheme; empty blocks dropped."""
    blocks = ref.T if scheme == "axes" else ref
    size = np.sum(~np.isnan(blocks), axis=1)
    keep = size > 0
    top = np.array([np.nanmax(b) for b in blocks[keep]]) if keep.any() else np.array([])
    return top, size[keep]


def resampled_maxima(ref: np.ndarray, m: int, scheme: str, n_boot: int,
                     rng: np.random.Generator, chunk: int = 1000) -> np.ndarray:
    """``n_boot`` maxima of ``m`` draws from the reference rows ``ref`` (R, J)."""
    out = np.empty(n_boot)
    if scheme == "values":
        flat = ref[~np.isnan(ref)]
        for lo in range(0, n_boot, chunk):
            hi = min(n_boot, lo + chunk)
            out[lo:hi] = flat[rng.integers(0, flat.size, (hi - lo, m))].max(axis=1)
        return out
    top, size = _blocks(ref, scheme)
    k = int(np.ceil(m / size.min()))
    for lo in range(0, n_boot, chunk):
        hi = min(n_boot, lo + chunk)
        draws = rng.integers(0, top.size, (hi - lo, k))
        covered_before = np.cumsum(size[draws], axis=1) - size[draws]
        out[lo:hi] = np.where(covered_before < m, top[draws], -np.inf).max(axis=1)
    return out


def reference_tail_share(maxima: np.ndarray, s: float) -> float:
    """``(1 + #{max_b >= S}) / (1 + B)``."""
    return (1.0 + int(np.sum(maxima >= s))) / (1.0 + maxima.size)


def exact_values_tail_share(flat: np.ndarray, s: float, m: int) -> float:
    """The ``values`` scheme without Monte Carlo error: ``1 - F(S-)^M``."""
    return float(1.0 - np.mean(flat < s) ** m)


def ratio_to_quantile(s: float, q: float) -> float:
    if np.isinf(q):
        return float("nan") if np.isinf(s) else 0.0
    return float(s / q) if q > 0 else float("inf")


def pooled_reference_test(t: np.ndarray, surviving: frozenset[int] = frozenset(),
                          n_boot: int = 10000, seed: int = 20261028) -> dict:
    """``p_ref``, ``R`` and the naive single-pair comparison for one t grid."""
    abs_t = np.abs(t)
    scored = ~np.isnan(abs_t)
    m = int(scored.sum())
    s = float(np.nanmax(abs_t))
    n_c = abs_t.shape[0]
    top = top_candidate(abs_t)
    others = [c for c in range(n_c) if c != top]
    out = {"S": s, "M": m, "n_candidates": n_c, "n_axes": abs_t.shape[1],
           "top_candidate": top, "n_infinite": int(np.isinf(abs_t[scored]).sum()),
           "mirror": bool(n_c == 2 and np.allclose(abs_t[0], abs_t[1], equal_nan=True)),
           "S_tied_by_other_candidate": bool(others and np.nanmax(abs_t[others]) >= s),
           "variants": {}}
    for v_index, variant in enumerate(VARIANTS):
        drop = dropped_candidates(abs_t, variant, surviving)
        ref = abs_t[[c for c in range(n_c) if c not in drop]]
        flat = ref[~np.isnan(ref)]
        entry: dict = {"dropped": drop, "n_ref": int(flat.size)}
        if flat.size == 0:
            out["variants"][variant] = {**entry, "computable": False}
            continue
        q_single = float(np.quantile(flat, 0.99, method="higher"))
        entry.update({
            "computable": True, "ref_max": float(flat.max()),
            "ref_median": float(np.median(flat)),
            "n_ref_infinite": int(np.isinf(flat).sum()),
            "naive_p_single": (1.0 + int(np.sum(flat >= s))) / (1.0 + flat.size),
            "naive_q99_single": q_single, "naive_R": ratio_to_quantile(s, q_single),
            "p_exact_values": exact_values_tail_share(flat, s, m)})
        for s_index, scheme in enumerate(SCHEMES):
            rng = np.random.default_rng(np.random.SeedSequence([seed, v_index, s_index]))
            maxima = resampled_maxima(ref, m, scheme, n_boot, rng)
            q = float(np.quantile(maxima, 0.99, method="higher"))
            entry[scheme] = {"p_ref": reference_tail_share(maxima, s), "q99_max": q,
                             "R": ratio_to_quantile(s, q), "median_max": float(np.median(maxima))}
        out["variants"][variant] = entry
    return out
