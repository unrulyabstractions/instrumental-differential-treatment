"""Shared loaders and a vectorized, exact re-implementation of the registered test.

Read-only on the code repo. Every function mirrors src/compare/paired_excess_measures.py
and src/compare/paired_max_statistic.py; reproduce.py checks that the p-values match
out/main/auditbench/nullext/summary.json to the last digit.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

REPO = Path("/Users/unrulyabstractions/work/_OLD/instrumental-differential-treatment")
AB = REPO / "out/main/auditbench"
EXT = AB / "nullext"
AXES_PATH = AB / "contextual_optimism/conjecture/scoring_questions.json"
BASE_A = AB / "controls/flattery/judge_mini/verdicts_base.jsonl"
BASE_B = EXT / "base_B/responses/verdicts_base.jsonl"
CO_TARGET = AB / "contextual_optimism/judge_mini/verdicts_target.jsonl"
CONTROLS = ("ai_welfare_poisoning", "animal_welfare", "anti_ai_regulation",
            "defend_objects", "defer_to_users", "emotional_bond",
            "flattery", "hallucinates_citations")
SYNTH = ("ai_welfare_poisoning", "emotional_bond")
SEED, NPERM, LEVEL = 20260726, 10000, 2
OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)

AXES = [a["axis_id"] for a in json.loads(AXES_PATH.read_text())["axes"]]


def null_target(c: str) -> Path:
    return AB / "controls" / c / "judge_mini/verdicts_target.jsonl"


def synth_target(b: str) -> Path:
    return EXT / "synth" / b / "verdicts_target.jsonl"


def load_replies(path: Path, n_s: int = 16):
    """Per-reply verdicts as (candidate, instruction, sample, axis) float, NaN where absent.

    Candidate and instruction orders are sorted, as in build_behavior_table.
    """
    rows = [json.loads(l) for l in open(path)]
    rows = [r for r in rows if int(r["level"]) == LEVEL]
    cands = sorted({r["principal"] for r in rows})
    instr = sorted({r["instruction_id"] for r in rows})
    ci = {c: k for k, c in enumerate(cands)}
    ii = {c: k for k, c in enumerate(instr)}
    aj = {a: k for k, a in enumerate(AXES)}
    R = np.full((len(cands), len(instr), n_s, len(AXES)), np.nan)
    for r in rows:
        s = int(r["s"])
        for a, v in r["verdicts"].items():
            if v is None:
                continue
            R[ci[r["principal"]], ii[r["instruction_id"]], s, aj[a]] = 1.0 if v else 0.0
    return R, cands, instr


def rates(R: np.ndarray) -> np.ndarray:
    with np.errstate(invalid="ignore"):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            return np.nanmean(R, axis=2)


def ovr(p: np.ndarray) -> np.ndarray:
    """One-vs-rest gap along axis -3 (candidate axis), NaN-aware like the code."""
    observed = ~np.isnan(p)
    filled = np.where(observed, p, 0.0)
    rest_sum = filled.sum(axis=-3, keepdims=True) - filled
    rest_count = observed.sum(axis=-3, keepdims=True) - observed.astype(int)
    with np.errstate(invalid="ignore", divide="ignore"):
        rest = np.where(rest_count > 0, rest_sum / rest_count, np.nan)
    return p - rest


def excess(pt: np.ndarray, pb: np.ndarray) -> np.ndarray:
    return ovr(pt) - ovr(pb)


def tgrid(d: np.ndarray):
    """Paired t over instructions (axis -2) per (candidate, axis); code's conventions."""
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        m = np.sum(~np.isnan(d), axis=-2)
        mean = np.nanmean(d, axis=-2)
        sd = np.nanstd(d, axis=-2, ddof=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            ratio = mean / (sd / np.sqrt(np.maximum(m, 1)))
    degenerate = (m >= 2) & (sd == 0)
    t = np.where(m >= 2, ratio, np.nan)
    signs = np.sign(np.nan_to_num(mean, nan=0.0))
    inf = np.where(signs > 0, np.inf, np.where(signs < 0, -np.inf, 0.0))
    t = np.where(degenerate, inf, t)
    return t, mean, m


def tgrid_fast(d: np.ndarray):
    """Same as tgrid for NaN-free d (much faster)."""
    n = d.shape[-2]
    mean = d.mean(axis=-2)
    sd = d.std(axis=-2, ddof=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        t = mean / (sd / np.sqrt(n))
    deg = sd == 0
    if deg.any():
        s = np.sign(mean)
        t = np.where(deg, np.where(s > 0, np.inf, np.where(s < 0, -np.inf, 0.0)), t)
    return t, mean


def smax(t: np.ndarray) -> np.ndarray:
    """max |t| over the last two axes (candidate, axis)."""
    a = np.abs(t)
    a = np.where(np.isnan(a), -np.inf, a)
    return a.reshape(a.shape[:-2] + (-1,)).max(axis=-1)


_ORDERS = {}


def perm_orders(seed: int = SEED, k: int = NPERM, n_i: int = 36, n_c: int = 6) -> np.ndarray:
    """The exact permutation sequence paired_max_test draws: (k, n_i, n_c)."""
    key = (seed, k, n_i, n_c)
    if key not in _ORDERS:
        rng = np.random.default_rng(seed)
        o = np.empty((k, n_i, n_c), dtype=np.int64)
        for kk in range(k):
            for i in range(n_i):
                o[kk, i] = rng.permutation(n_c)
        _ORDERS[key] = o
    return _ORDERS[key]


def apply_orders(d: np.ndarray, orders: np.ndarray) -> np.ndarray:
    """d (n_c, n_i, n_j) -> (k, n_c, n_i, n_j) with candidates relabelled per instruction."""
    n_i = d.shape[1]
    return d[orders.transpose(0, 2, 1), np.arange(n_i)[None, None, :], :]


def perm_null(d: np.ndarray, orders: np.ndarray, chunk: int = 400) -> np.ndarray:
    """max|t| under each permutation in ``orders``. Exact for NaN-free or NaN d."""
    has_nan = np.isnan(d).any()
    out = np.empty(len(orders))
    for s in range(0, len(orders), chunk):
        dp = apply_orders(d, orders[s:s + chunk])
        t = tgrid(dp)[0] if has_nan else tgrid_fast(dp)[0]
        out[s:s + chunk] = smax(t)
    return out


def tail_p(null: np.ndarray, value: float) -> float:
    if np.isnan(value):
        return 1.0
    return (1.0 + int(np.sum(null >= value))) / (1.0 + len(null))


def run_test(pt: np.ndarray, pb: np.ndarray, orders: np.ndarray | None = None):
    """Statistic, family-wise p, null, t-grid for target rates pt vs base rates pb."""
    if orders is None:
        orders = perm_orders()
    d = excess(pt, pb)
    t, mean, m = tgrid(d)
    s = float(smax(t))
    null = perm_null(d, orders)
    return {"S": s, "p": tail_p(null, s), "null": null, "t": t, "mean": mean, "d": d}


_CACHE = {}


def load_all():
    """Every verdict file this investigation reads, as reply arrays."""
    if _CACHE:
        return _CACHE
    paths = {"A": BASE_A, "B": BASE_B, "CO": CO_TARGET}
    for c in CONTROLS:
        paths[c] = null_target(c)
    for b in SYNTH:
        paths["sd_" + b] = synth_target(b)
    ref = None
    for k, p in paths.items():
        R, cands, instr = load_replies(p)
        if ref is None:
            ref = (cands, instr)
        assert (cands, instr) == ref, k
        _CACHE[k] = R
    _CACHE["_cands"], _CACHE["_instr"] = ref
    return _CACHE
