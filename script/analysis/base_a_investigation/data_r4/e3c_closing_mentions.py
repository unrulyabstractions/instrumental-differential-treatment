"""E3c. Do control replies close with a reference to the user's organization that cut base replies lose?

Judge-free. For every reply: does the candidate's name (or its usual short form) appear in the last 25%
of the reply's characters, and anywhere. By sample group (eight controls, two synthetic arms, CO, bases).
At stanford x trusted_entity_interdisciplinary_connection_mapping, P(yes) given a late mention.
Read-only on the repo.
"""
import re, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import r4common as R
D = R.D(); cands = R.cands()
NAME = {"anthropic": r"anthropic", "google_deepmind": r"deepmind|google", "meta_ai": r"\bmeta\b|meta ai|fair\b",
        "microsoft_research": r"microsoft", "openai": r"openai", "stanford": r"stanford"}
out = {}
for k in R.ALL:
    T = R.texts(k); late = np.zeros((6, 36, 16)); anyw = np.zeros((6, 36, 16))
    for c in range(6):
        rx = re.compile(NAME[cands[c]], re.I)
        for i in range(36):
            for s in range(16):
                t = T[c, i, s] or ""
                anyw[c, i, s] = bool(rx.search(t)); late[c, i, s] = bool(rx.search(t[int(0.75 * len(t)):]))
    out[k] = (late, anyw)
    print(f"{k:24s} name anywhere {anyw.mean():.3f}  in last quarter {late.mean():.3f}  by cand (last quarter): " + " ".join(f"{late[c].mean():.3f}" for c in range(6)))
c = cands.index("stanford"); j = R.AX.index("trusted_entity_interdisciplinary_connection_mapping")
for grp, ks in (("controls", R.NULLS), ("bases", ["A", "B"])):
    yl, yn = [], []
    for k in ks:
        late = out[k][0][c]; V = D[k][c, :, :, j]; ok = ~np.isnan(V)
        yl += list(V[ok & (late == 1)]); yn += list(V[ok & (late == 0)])
    print(grp, "stanford x interdisciplinary: P(yes | late name)", round(float(np.mean(yl)), 3) if yl else None, f"(n={len(yl)})",
          " P(yes | no late name)", round(float(np.mean(yn)), 3), f"(n={len(yn)})")
