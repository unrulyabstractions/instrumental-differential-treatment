"""T6. Verify critic_r2/k09_cross_base_structure.py with an independent implementation and more draws.

Question: could ONE systematic A-minus-B difference J explain both directions (the eight nulls closer
to B, the two synthetic-document arms closer to A)? For the synthetic arms to sit closer to A, J would
have to cancel part of their own structure, so J would align with the synthetic arms' structure; for
the nulls to sit farther from A, J must not cancel theirs. Correlating t-grids across DIFFERENT bases
shares no base noise:
   corr( t(SD_k - B), t(N_j - A) )  and  corr( t(SD_k - A), t(N_j - B) );
reference: null with null across bases (i != j), and synthetic with synthetic across bases.
Nulls (three designs, 2,000 draws each):
  k09   : one registered-style relabelling of candidates within instruction applied to every first
          sample's difference grid in a draw (the critic's design);
  indep : an independent relabelling per first sample;
  second: the relabelling applied to the second sample instead.
Then the direct alignment check (from stats_r2/out/s4d_alignment.json, recomputed here for the ten
targets): corr over the 606 cells of mean(OvR_A - OvR_B) with each target's structure relative to the
base midpoint, under the A/B reply swap (2,000 swaps).
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "stats_r1"))
import common as C  # noqa: E402

warnings.simplefilter("ignore")
D = C.load_all()
O = {k: C.ovr(C.rates(v)) for k, v in D.items() if not k.startswith("_")}
nulls = list(C.CONTROLS)
sd = ["sd_ai_welfare_poisoning", "sd_emotional_bond"]


def tg(d):
    t = C.tgrid(d)[0]
    return np.where(np.isfinite(t), t, 0.0).ravel()


def cc(a, b):
    return float(np.corrcoef(a, b)[0, 1])


pairs = {"SD|B vs null|A": [(k, "B", j, "A") for k in sd for j in nulls],
         "SD|A vs null|B": [(k, "A", j, "B") for k in sd for j in nulls],
         "null|A vs null|B (i != j)": [(i, "A", j, "B") for i in nulls for j in nulls if i != j],
         "SD|B vs SD|A (k != l)": [(sd[0], "B", sd[1], "A"), (sd[1], "B", sd[0], "A")]}
NP = 2000
rng = np.random.default_rng(606)
res = {}
grids = {}
for lab, pl in pairs.items():
    for a, x, b, y in pl:
        grids.setdefault((a, x), tg(O[a] - O[x]))
        grids.setdefault((b, y), tg(O[b] - O[y]))
for lab, pl in pairs.items():
    obs_each = [cc(grids[(a, x)], grids[(b, y)]) for a, x, b, y in pl]
    obs = float(np.mean(obs_each))
    firsts = sorted({(a, x) for a, x, _, _ in pl})
    seconds = sorted({(b, y) for _, _, b, y in pl})
    out = {"mean_corr": obs, "n_pairs": len(pl), "per_pair": {f"{a}|{x} ~ {b}|{y}": round(v, 4) for (a, x, b, y), v in zip(pl, obs_each)}}
    for design in ("k09", "indep", "second"):
        vals = np.empty(NP)
        for q in range(NP):
            if design == "k09":
                o = np.stack([rng.permutation(6) for _ in range(36)])
                perm = {f: tg(C.apply_orders(O[f[0]] - O[f[1]], o[None])[0]) for f in firsts}
                vals[q] = np.mean([cc(perm[(a, x)], grids[(b, y)]) for a, x, b, y in pl])
            elif design == "indep":
                perm = {}
                for f in firsts:
                    o = np.stack([rng.permutation(6) for _ in range(36)])
                    perm[f] = tg(C.apply_orders(O[f[0]] - O[f[1]], o[None])[0])
                vals[q] = np.mean([cc(perm[(a, x)], grids[(b, y)]) for a, x, b, y in pl])
            else:
                o = np.stack([rng.permutation(6) for _ in range(36)])
                perm = {s: tg(C.apply_orders(O[s[0]] - O[s[1]], o[None])[0]) for s in seconds}
                vals[q] = np.mean([cc(grids[(a, x)], perm[(b, y)]) for a, x, b, y in pl])
        out[design] = {"null_mean": float(vals.mean()), "null_sd": float(vals.std()),
                       "z": float((obs - vals.mean()) / vals.std()),
                       "p_upper": float((1 + np.sum(vals >= obs)) / (1 + NP)),
                       "p_lower": float((1 + np.sum(vals <= obs)) / (1 + NP))}
    res[lab] = out
    print(lab, json.dumps({k: v for k, v in out.items() if k != "per_pair"}), flush=True)

# direct alignment of the realized A-B difference with each target's structure (swap null)
RA, RB = D["A"], D["B"]
both = (~np.isnan(RA).all(3) & ~np.isnan(RB).all(3))
names = nulls + sd
Ot = np.stack([O[k] for k in names])


def align(oa, ob):
    dev = (oa - ob).mean(1).ravel()
    mid = (oa + ob) / 2
    sm = (Ot - mid[None]).mean(2).reshape(len(names), -1)
    return np.array([np.corrcoef(dev, s)[0, 1] for s in sm])


a_obs = align(O["A"], O["B"])
rng = np.random.default_rng(31)
NS = 2000
an = np.empty((NS, len(names)))
for q in range(NS):
    m = ((rng.random(RA.shape[:3]) < 0.5) & both)[..., None]
    an[q] = align(C.ovr(C.rates(np.where(m, RB, RA))), C.ovr(C.rates(np.where(m, RA, RB))))
z = (a_obs - an.mean(0)) / an.std(0)
fam = {"eight": slice(0, 8), "synthetic two": slice(8, 10)}
res["alignment_dev_with_target_structure"] = {"targets": names, "r_obs": a_obs.round(4).tolist(), "z": z.round(2).tolist()}
for f, sl in fam.items():
    so, sn = a_obs[sl].mean(), an[:, sl].mean(1)
    res["alignment_dev_with_target_structure"][f] = {"mean_r": float(so), "null_sd": float(sn.std()), "z": float((so - sn.mean()) / sn.std()),
                                                     "p_lower": float((1 + np.sum(sn <= so)) / (1 + NS)), "p_upper": float((1 + np.sum(sn >= so)) / (1 + NS))}
d8 = a_obs[:8].mean() - a_obs[8:].mean()
dn = an[:, :8].mean(1) - an[:, 8:].mean(1)
res["alignment_dev_with_target_structure"]["eight_minus_synthetic"] = {"obs": float(d8), "null_sd": float(dn.std()), "z": float(d8 / dn.std()),
                                                                        "p_two": float((1 + np.sum(np.abs(dn) >= abs(d8))) / (1 + NS))}
print("alignment", json.dumps(res["alignment_dev_with_target_structure"]))
json.dump(res, open(HERE / "out" / "t6_cross_base.json", "w"), indent=1)
