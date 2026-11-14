"""Fast exact registered test: the permutation null as two matrix products.

The registered null relabels candidates within each instruction (rng.permutation(n_c) per
instruction per draw, seed 20260726, 10,000 draws) and takes max |t| over (candidate, axis),
where t is the paired t over the 36 instructions. For a permutation, the per-cell sum and
sum of squares over instructions are linear in d and d**2, so for all 10,000 permutations at
once they are E @ D and E @ D**2, with E a fixed 0/1 matrix built from the registered orders.
check_fast.py verifies that this reproduces every stored (S, p) pair in nullext/summary.json.

Reuses the round-1 loaders (stats_r1/common.py), which reproduce the code's cell rates.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np

R1 = Path(__file__).resolve().parent.parent / "stats_r1"
sys.path.insert(0, str(R1))
import common as C  # noqa: E402

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)
CONTROLS = list(C.CONTROLS)
SD = ["sd_ai_welfare_poisoning", "sd_emotional_bond"]
TEN = CONTROLS + SD
N_I, N_J = 36, 101


def onehot(orders: np.ndarray) -> np.ndarray:
    """E with E[k*n_c + c, src*n_i + i] = 1 when orders[k, i, c] == src.

    Row block k of E @ d.reshape(n_c*n_i, n_j) is the per-candidate sum over
    instructions of d relabelled by permutation k (apply_orders convention:
    d_perm[c, i, j] = d[orders[k, i, c], i, j]).
    """
    k, n_i, n_c = orders.shape
    E = np.zeros((k * n_c, n_c * n_i))
    rows = np.broadcast_to(np.arange(k)[:, None, None] * n_c + np.arange(n_c)[None, None, :], (k, n_i, n_c))
    cols = orders * n_i + np.arange(n_i)[None, :, None]
    E[rows.ravel(), cols.ravel()] = 1.0
    return E


_E = {}


def E_for(n_c: int, seed: int = C.SEED, k: int = C.NPERM) -> np.ndarray:
    key = (n_c, seed, k)
    if key not in _E:
        _E[key] = onehot(C.perm_orders(seed=seed, k=k, n_i=N_I, n_c=n_c))
    return _E[key]


def null_max(ds: np.ndarray, n_c: int, E: np.ndarray | None = None) -> np.ndarray:
    """ds: (m, n_c, n_i, n_j) NaN-free excess arrays -> (m, n_perm) permutation maxima of |t|."""
    if E is None:
        E = E_for(n_c)
    m = ds.shape[0]
    k = E.shape[0] // n_c
    out = np.empty((m, k))
    for q in range(m):  # one target at a time keeps peak memory near 300 MB
        X = ds[q].reshape(n_c * N_I, N_J)  # rows src*n_i + i
        s1 = (E @ X).reshape(k, n_c, N_J)
        s2 = (E @ (X * X)).reshape(k, n_c, N_J)
        den = N_I * s2 - s1 * s1
        with np.errstate(invalid="ignore", divide="ignore"):
            t2 = (N_I - 1) * s1 * s1 / den
        t2 = np.where(np.isnan(t2), 0.0, t2)
        t2 = np.where(den <= 0, np.where(s1 != 0, np.inf, 0.0), t2)
        out[q] = np.sqrt(t2.max(axis=(1, 2)))
    return out  # (m, k)


def S_obs(d: np.ndarray) -> float:
    """Observed statistic exactly as the code computes it."""
    return float(C.smax(C.tgrid(d)[0]))


def S_fast(ds: np.ndarray) -> np.ndarray:
    """max |t| for a stack (..., n_c, n_i, n_j) of NaN-free d (vectorized, code conventions)."""
    t, _ = C.tgrid_fast(ds)
    return C.smax(t)


def tail(null: np.ndarray, s: np.ndarray) -> np.ndarray:
    """(1 + #null >= s) / (1 + N), row-wise. null (m, N), s (m,)."""
    return (1.0 + (null >= s[:, None]).sum(axis=1)) / (1.0 + null.shape[1])


def test_many(Ot: np.ndarray, Ob: np.ndarray, n_c: int, E=None):
    """Registered test of each target OvR in Ot (m, n_c, n_i, n_j) against base OvR Ob (n_c, n_i, n_j).

    Ob may also be (m, ...) for one base per target. Returns S (m,), p (m,).
    """
    ds = Ot - Ob
    S = S_fast(ds)
    nm = null_max(ds, n_c, E)
    return S, tail(nm, S), nm


def rates_of(R: np.ndarray) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(R, axis=2)


def load():
    D = C.load_all()
    return D
