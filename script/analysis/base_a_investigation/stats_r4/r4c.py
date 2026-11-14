"""Round 4 shared helpers (statistics lens). Read-only on the code repo.

Reuses the verified loaders (stats_r1/common.py) and the fast exact registered test (stats_r2/fast.py,
22/22 stored pairings reproduced to 1e-12). Everything else here is new round 4 code.

Conventions
  R[name]   per-reply verdicts (candidate, instruction, slot s, axis), NaN where absent.
  rates     nanmean over slots -> (candidate, instruction, axis).
  six       all six candidates; five = anthropic dropped before the one-vs-rest step.
"""
from __future__ import annotations

import os

os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import sys  # noqa: E402
import warnings  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "stats_r2"))
import fast as F  # noqa: E402
from fast import C  # noqa: E402

OUT = HERE / "out"
OUT.mkdir(exist_ok=True)
CONTROLS = list(C.CONTROLS)
SD = ["sd_ai_welfare_poisoning", "sd_emotional_bond"]
TEN = CONTROLS + SD
ELEVEN = TEN + ["CO"]
warnings.simplefilter("ignore", RuntimeWarning)

_D = {}


def data():
    if not _D:
        D = F.load()
        _D["R"] = {k: v for k, v in D.items() if not k.startswith("_")}
        _D["cands"] = D["_cands"]
        _D["instr"] = D["_instr"]
        _D["keep5"] = [i for i, c in enumerate(D["_cands"]) if c != "anthropic"]
    return _D


def rates(R):
    return np.nanmean(R, axis=-2)


def ovr(p):
    return np.nan_to_num(C.ovr(p))


def world(tag):
    d = data()
    return (list(range(6)), 6) if tag == "six" else (d["keep5"], 5)


def test(OT, OB, n_c):
    """Exact registered test. OT (m, n_c, 36, 101) target OvR; OB (n_c, 36, 101) or (m, ...) base OvR."""
    S, p, nm = F.test_many(OT, OB, n_c, F.E_for(n_c))
    return S, p, nm


def tg(d):
    """Paired t over instructions (axis -2), zero where the spread is zero (selection helper only)."""
    n = d.shape[-2]
    mean = d.mean(axis=-2)
    sd = d.std(axis=-2, ddof=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        t = mean / (sd / np.sqrt(n))
    return np.where(sd < 1e-12, 0.0, t)


def S_only(d):
    """max |t| exactly as the registered statistic for NaN-free d (..., n_c, 36, 101)."""
    return C.smax(C.tgrid_fast(d)[0])


# ---------- reply-level designs ----------

def swap_mask(rng, grain, RA, RB):
    both = (~np.isnan(RA).all(-1)) & (~np.isnan(RB).all(-1))
    if grain == "reply":
        return (rng.random(RA.shape[:3]) < 0.5) & both
    if grain == "prompt":
        return np.broadcast_to((rng.random(RA.shape[:2]) < 0.5)[:, :, None], RA.shape[:3])
    if grain == "instruction":
        return np.broadcast_to((rng.random(RA.shape[1]) < 0.5)[None, :, None], RA.shape[:3])
    raise ValueError(grain)


def swapped(RA, RB, m):
    return np.where(m[..., None], RB, RA), np.where(m[..., None], RA, RB)


def shuffle_controls(rng, Rc):
    """Rc (8, 6, 36, 16, 101). At each slot the eight controls' replies are permuted among the labels.
    Slots where any control lacks a reply stay in place. Matched slots keep the judge's axis order paired."""
    ok = (~np.isnan(Rc).all(-1)).all(0)
    perm = np.argsort(rng.random(Rc.shape[:4]), axis=0)
    perm = np.where(ok[None], perm, np.arange(Rc.shape[0])[:, None, None, None])
    return np.take_along_axis(Rc, perm[..., None], axis=0)


def boot_within_cell(rng, R):
    """16 replies per (candidate, instruction) drawn with replacement from that cell's available replies."""
    avail = ~np.isnan(R).all(-1)
    n = avail.sum(-1)
    order = np.argsort(~avail, axis=-1, kind="stable")
    k = np.floor(rng.random(avail.shape) * n[..., None]).astype(int)
    ix = np.take_along_axis(order, k, axis=-1)
    return np.take_along_axis(R, ix[..., None], axis=-2)


def tail_ge(null, x):
    null = np.asarray(null)
    return float((1 + np.sum(null >= x - 1e-12)) / (1 + len(null)))


def tail_le(null, x):
    null = np.asarray(null)
    return float((1 + np.sum(null <= x + 1e-12)) / (1 + len(null)))
