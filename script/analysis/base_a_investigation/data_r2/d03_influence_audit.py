"""D3. Influence audit: does any provenance property of base A's prompts track their influence on the eight S?

For each of the 216 (candidate, instruction) prompts: swap base A's 16 replies' verdicts there for base B's and recompute
each null's S (no permutations needed; the null distributions are almost the same for every pairing: median 3.21-3.26).
Influence = drop in S per test; summaries: drop in mean S over the eight; max drop; sum of |change|.
Reverse: swap base A's prompt INTO base B (rise in S), to see whether single-prompt fragility is a property of A.
Covariates per prompt (base A side):
  - unscorable: the prompt holds one of base A's 4 missing rows (15 of 16 replies scored)
  - judge session: share of the prompt's rows among the first 578 rows of the verdict file (skipped_existing = 578)
  - position in the verdict file (mean row index), a proxy for judging time within the later session
  - reply length (mean characters) and A minus B length; share of replies at >= 398 tokens
  - A-B distance: sum over axes of squared rate difference; also its rank
  - repaired rows: base A's rows carry no 'repaired' field (August code) and no judging log for base A exists, so
    the 18 repaired rows cannot be located. Reported as not checkable.
Association: Spearman correlation of influence with each covariate and a permutation p (2,000 shuffles);
for binary covariates, the influence rank of the flagged prompts.
"""
import json

import numpy as np
from scipy.stats import spearmanr
from tokenizers import Tokenizer

from dcommon import C, TOK, dump, load_texts

D = C.load_all(); cands = D["_cands"]; instr = D["_instr"]
P = {k: C.rates(v) for k, v in D.items() if not k.startswith("_")}
OT = [C.ovr(P[c]) for c in C.CONTROLS]


def eightS(pb):
    ob = C.ovr(pb)
    return np.array([float(C.smax(C.tgrid(o - ob)[0])) for o in OT])


SA, SB = eightS(P["A"]), eightS(P["B"])
fwd = np.zeros((6, 36, 8)); rev = np.zeros((6, 36, 8))
for c in range(6):
    for i in range(36):
        pb = P["A"].copy(); pb[c, i] = P["B"][c, i]; fwd[c, i] = SA - eightS(pb)
        pb = P["B"].copy(); pb[c, i] = P["A"][c, i]; rev[c, i] = eightS(pb) - SB
infl_mean = fwd.mean(2); infl_max = fwd.max(2); infl_abs = np.abs(fwd).sum(2)
rev_mean = rev.mean(2)
print(f"S vs A {SA.round(3)} mean {SA.mean():.3f}; S vs B {SB.round(3)} mean {SB.mean():.3f}")
print(f"forward (A with one B prompt): drop in mean S: sum {infl_mean.sum():.3f}, max {infl_mean.max():.3f}, sd {infl_mean.std():.4f}; "
      f"max single-test drop {fwd.max():.3f}; prompts dropping some test by > 0.3: {int((infl_max > 0.3).sum())}")
print(f"reverse (B with one A prompt): rise in mean S: sum {rev_mean.sum():.3f}, max {rev_mean.max():.3f}, sd {rev_mean.std():.4f}; "
      f"max single-test rise {rev.max():.3f}; prompts raising some test by > 0.3: {int((rev.max(2) > 0.3).sum())}")
# per-test largest single-prompt moves, forward and reverse, and the S scale
tests = {}
for k, name in enumerate(C.CONTROLS):
    f = fwd[..., k]; r = rev[..., k]; cf = np.unravel_index(np.argmax(f), f.shape); cr = np.unravel_index(np.argmax(np.abs(r)), r.shape)
    tests[name] = {"S_A": SA[k], "S_B": SB[k], "max_drop_fwd": float(f.max()), "prompt_fwd": [cands[cf[0]], instr[cf[1]]],
                   "n_prompts_drop_gt_0.2": int((f > 0.2).sum()), "max_abs_change_rev": float(np.abs(r).max()), "prompt_rev": [cands[cr[0]], instr[cr[1]]],
                   "sd_change_fwd": float(f.std()), "sd_change_rev": float(r.std())}
    print(f"  {name:24s} S_A {SA[k]:.2f} max drop {f.max():.2f} at {cands[cf[0]]}x{instr[cf[1]][8:]}  (#>0.2: {(f>0.2).sum()}) | "
          f"S_B {SB[k]:.2f} max |change| from one A prompt {np.abs(r).max():.2f} at {cands[cr[0]]}x{instr[cr[1]][8:]}")

# covariates
rows = [json.loads(l) for l in open(C.BASE_A)]
ci = {c: k for k, c in enumerate(cands)}; ii = {x: k for k, x in enumerate(instr)}
sess1 = np.zeros((6, 36)); pos = np.zeros((6, 36)); cnt = np.zeros((6, 36))
for n, r in enumerate(rows):
    c, i = ci[r["principal"]], ii[r["instruction_id"]]
    sess1[c, i] += n < 578; pos[c, i] += n; cnt[c, i] += 1
sess1 /= cnt; pos /= cnt
unscor = (cnt < 16).astype(float)
TA, TB = load_texts("A"), load_texts("B")
tok = Tokenizer.from_file(str(TOK))
lenA = np.vectorize(len)(TA).mean(2); lenB = np.vectorize(len)(TB).mean(2)
ntA = np.array([[[len(tok.encode(TA[c, i, s], add_special_tokens=False).ids) for s in range(16)] for i in range(36)] for c in range(6)])
cap = (ntA >= 398).mean(2)
dist = np.nansum((P["A"] - P["B"]) ** 2, axis=2)
cov = {"session1_share": sess1, "file_position": pos, "unscorable": unscor, "len_A": lenA, "len_A_minus_B": lenA - lenB,
       "cap_share_A": cap, "AB_distance": dist}
rng = np.random.default_rng(3)
assoc = {}
print("\nSpearman association of influence with each covariate (216 prompts; permutation p, two-sided, 2,000 shuffles)")
for yname, y in (("drop_in_mean_S", infl_mean), ("max_single_test_drop", infl_max), ("sum_abs_change", infl_abs)):
    for cname, x in cov.items():
        xv, yv = x.ravel(), y.ravel()
        if np.nanstd(xv) == 0:
            continue
        r0 = spearmanr(xv, yv).statistic
        nul = np.array([spearmanr(xv, rng.permutation(yv)).statistic for _ in range(2000)])
        p = float((1 + np.sum(np.abs(nul) >= abs(r0))) / (1 + len(nul)))
        assoc[f"{yname}~{cname}"] = {"rho": float(r0), "p": p}
        print(f"  {yname:22s} ~ {cname:16s} rho {r0:+.3f}  p {p:.4f}")
# binary covariates: ranks
rank = np.argsort(np.argsort(-infl_max.ravel())).reshape(6, 36) + 1
uns = [(cands[c], instr[i], int(rank[c, i]), float(infl_max[c, i])) for c, i in zip(*np.nonzero(unscor))]
print("\nthe 4 prompts with an unscorable row: influence rank (of 216, by max single-test drop):", uns)
s1 = rank[sess1 > 0.5]
print(f"prompts judged mainly in session 1 (n={len(s1)}): median rank {np.median(s1):.0f} (others {np.median(rank[sess1 <= 0.5]):.0f})")
# top prompts by influence and their covariates
order = np.argsort(-infl_max, axis=None)[:10]
drank = np.argsort(np.argsort(-dist.ravel())).reshape(6, 36) + 1
top = []
print("\ntop-10 prompts by max single-test drop: cand x instr | drop | which test | A-B distance rank | len A, A-B | cap | session1 | unscorable")
for f in order:
    c, i = np.unravel_index(f, infl_max.shape); k = int(np.argmax(fwd[c, i]))
    top.append({"cand": cands[c], "instr": instr[i], "max_drop": float(infl_max[c, i]), "test": C.CONTROLS[k], "dist_rank": int(drank[c, i]),
                "lenA": float(lenA[c, i]), "lenAminusB": float(lenA[c, i] - lenB[c, i]), "cap": float(cap[c, i]), "session1": float(sess1[c, i]), "unscorable": bool(unscor[c, i])})
    print(f"  {cands[c]:18s} {instr[i][8:]:38s} {infl_max[c,i]:.2f} {C.CONTROLS[k][:16]:16s} dist rank {drank[c,i]:3d} | {lenA[c,i]:.0f} {lenA[c,i]-lenB[c,i]:+.0f} | {cap[c,i]:.2f} | {sess1[c,i]:.2f} | {bool(unscor[c,i])}")
dump({"S_A": SA, "S_B": SB, "tests": tests, "assoc": assoc, "unscorable_prompts": uns, "top10": top,
      "forward_drop_mean_S": infl_mean.tolist(), "forward": fwd.tolist(), "reverse": rev.tolist(),
      "repaired_rows": "not locatable: base A rows carry no 'repaired' field and no base-A judging log exists"}, "d03_influence_audit.json")
