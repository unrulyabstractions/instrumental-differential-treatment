"""Round 3 data investigator: shared loaders. Read-only on the code repo.

Builds on data_r2/dcommon.py (reply texts, nano verdicts) and stats_r1/common.py (the validated
re-implementation of the registered test, which reproduces all 22 stored pairings).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

NULLINV = Path("/private/tmp/claude-501/-Users-unrulyabstractions-work-papers-idt/32b842b8-ab16-41a9-8f2f-692b2558b7d6/scratchpad/nullinv")
sys.path.insert(0, str(NULLINV / "data_r2"))
sys.path.insert(0, str(NULLINV / "stats_r1"))
import common as C  # noqa: E402
import dcommon as DC  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
OUT.mkdir(exist_ok=True)
NULLS = list(C.CONTROLS)
SD = ["sd_ai_welfare_poisoning", "sd_emotional_bond"]
AX = C.AXES


def T(x):
    return C.tgrid(x)[0]


def O(R, keep=None):
    r = C.rates(R)
    if keep is not None:
        r = r[keep]
    return C.ovr(r)


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
