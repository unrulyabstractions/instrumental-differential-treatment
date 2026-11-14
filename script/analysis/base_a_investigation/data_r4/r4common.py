"""Round 4 data investigator: shared loaders. Read-only on the code repo.

Re-uses stats_r1/common.py (validated re-implementation of the registered test, 22/22 stored
pairings), stats_r2/fast.py (exact fast permutation test) and data_r2/dcommon.py (reply texts).
Adds a cached Llama-3.3 token length for every reply of every sample.
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np

NULLINV = Path("/private/tmp/claude-501/-Users-unrulyabstractions-work-papers-idt/32b842b8-ab16-41a9-8f2f-692b2558b7d6/scratchpad/nullinv")
for sub in ("stats_r1", "stats_r2", "data_r2"):
    sys.path.insert(0, str(NULLINV / sub))
import common as C  # noqa: E402
import dcommon as DC  # noqa: E402
import fast as F  # noqa: E402

warnings.simplefilter("ignore", RuntimeWarning)
HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
OUT.mkdir(exist_ok=True)
NULLS = list(C.CONTROLS)
SD = ["sd_ai_welfare_poisoning", "sd_emotional_bond"]
AX = C.AXES
ALL = ["A", "B", "CO"] + NULLS + SD
REPO = C.REPO
AB = C.AB


def D():
    return C.load_all()


def cands():
    return C.load_all()["_cands"]


def instr():
    return C.load_all()["_instr"]


_TXT = {}


def texts(name):
    if name not in _TXT:
        _TXT[name] = DC.load_texts(name)
    return _TXT[name]


def token_lengths():
    """dict name -> (6, 36, 16) int token counts (Llama-3.3 tokenizer, no specials); -1 if absent."""
    cache = OUT / "token_lengths.npz"
    if cache.exists():
        z = np.load(cache)
        return {k: z[k] for k in z.files}
    from tokenizers import Tokenizer
    tok = Tokenizer.from_file(str(DC.TOK))
    out = {}
    for name in ALL:
        T = texts(name)
        L = np.full(T.shape, -1, dtype=np.int64)
        flat = [(idx, t) for idx, t in np.ndenumerate(T) if t is not None]
        enc = tok.encode_batch([t for _, t in flat], add_special_tokens=False)
        for (idx, _), e in zip(flat, enc):
            L[idx] = len(e.ids)
        out[name] = L
    np.savez(cache, **out)
    return out


def rates(R, keep=None):
    r = C.rates(R)
    return r if keep is None else r[keep]


def ovr(p):
    return np.nan_to_num(C.ovr(p))


def reg_test(pt, pb, keep=None):
    """Registered test (exact, fast) of target rates pt against reference rates pb."""
    if keep is None:
        keep = list(range(pt.shape[0]))
    nc = len(keep)
    E = F.E_for(nc)
    S, p, _ = F.test_many(ovr(pt[keep])[None], ovr(pb[keep]), nc, E)
    return float(S[0]), float(p[0])


def tgrid(pt, pb, keep=None):
    if keep is None:
        keep = list(range(pt.shape[0]))
    d = ovr(pt[keep]) - ovr(pb[keep])
    t, mean = C.tgrid_fast(d)
    return t, mean


def _default(o):
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    return str(o)


def dump(obj, name):
    p = OUT / name
    json.dump(obj, open(p, "w"), indent=1, default=_default)
    return p
