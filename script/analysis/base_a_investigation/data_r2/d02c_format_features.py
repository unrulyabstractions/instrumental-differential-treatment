"""D2 (format part). Formatting habits and self-description, A vs B, by candidate.

Per reply: bold spans ('**'), numbered list items, markdown headers, bullet items, self-reference as PRISM-4,
mention of Nexus Research, terminal punctuation at the end, characters. Per (candidate, instruction): mean over
the 16 replies. Candidate x arm: per candidate, mean over instructions of [x_A - x_B]; one-vs-rest over the six
candidates; statistic max |one-vs-rest| (and the value at each peak candidate). Null: swap A and B labels of
single replies within each prompt (reply-level swap, 4,000 draws).
"""
import re

import numpy as np

from dcommon import C, dump, load_texts

D = C.load_all(); cands = D["_cands"]
TX = {a: load_texts(a) for a in ("A", "B")}
FEAT = {"bold": lambda t: t.count("**") / 2, "numbered": lambda t: len(re.findall(r"(?m)^\s*\d+\.\s", t)),
        "headers": lambda t: len(re.findall(r"(?m)^#{1,4}\s", t)), "bullets": lambda t: len(re.findall(r"(?m)^\s*[\*\-]\s", t)),
        "as_prism4": lambda t: float(bool(re.search(r"\bAs PRISM-4\b", t))), "nexus": lambda t: float("Nexus Research" in t),
        "ends_terminal": lambda t: float(t.rstrip()[-1:] in ".!?"), "chars": len}
rng = np.random.default_rng(23)
res = {}
for name, f in FEAT.items():
    XA = np.vectorize(lambda t: np.nan if t is None else float(f(t)), otypes=[float])(TX["A"])
    XB = np.vectorize(lambda t: np.nan if t is None else float(f(t)), otypes=[float])(TX["B"])

    def stat(xa, xb):
        d = np.nanmean(np.nanmean(xa, 2) - np.nanmean(xb, 2), 1)
        o = d - (d.sum() - d) / 5
        return np.max(np.abs(o)), o, d
    s0, o0, d0 = stat(XA, XB)
    nul = np.empty(4000)
    for k in range(4000):
        m = rng.random(XA.shape) < 0.5
        nul[k] = stat(np.where(m, XB, XA), np.where(m, XA, XB))[0]
    p = float((1 + np.sum(nul >= s0)) / 4001)
    res[name] = {"A": float(np.nanmean(XA)), "B": float(np.nanmean(XB)), "per_cand_A_minus_B": dict(zip(cands, d0.round(4).tolist())),
                 "per_cand_ovr": dict(zip(cands, o0.round(4).tolist())), "max_abs_ovr": float(s0), "p": p}
    print(f"{name:14s} A {np.nanmean(XA):8.4f} B {np.nanmean(XB):8.4f} | OvR(A-B) by cand: " + " ".join(f"{c[:6]} {v:+.3f}" for c, v in zip(cands, o0)) + f" | max {s0:.4f} p={p:.3f}")
dump(res, "d02c_format_features.json")
