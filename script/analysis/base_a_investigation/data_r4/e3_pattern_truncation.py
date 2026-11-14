"""E3. Is the controls' shared pattern produced by the 400-token cut of base replies?

Shared pattern F(c, j) = mean over controls of the one-vs-rest cell mean minus the same for the
base midpoint (A + B)/2 (critic k16). Per reply r at candidate c: proj_r = sum_j F(c, j) * v_rj,
the reply's verdict vector projected on the pattern row of its own candidate. Comparisons are within
prompt, and candidates are weighted equally, so an effect of truncation common to all candidates
cancels (sum_c F(c, j) = 0), exactly as it cancels in the test.

(i) Within hallucinates_citations, ai_welfare_poisoning and anti_ai_regulation (15%, 14%, 3% of
    replies at the cap): capped (>= 398 tokens) minus complete replies of the same prompt. F is
    rebuilt without the control under test (leave-one-out). Null: cap labels permuted within prompt.
    Scale: the same projection for base-minus-control replies at the same prompts (what a full
    truncation account would have to reproduce).
(ii) Base A and B: complete replies (< 398 tokens) minus capped replies of the same prompts.
(iii) Per top pattern cell: a keyword locator for the axis (regex below), the share of yes
    replies with a hit and the relative position (token fraction) of the first hit, for controls
    and bases, and the share of base yes-hits in the last 15% of the reply.
(iv) Loading of each sample on the pattern (leave-one-out F, disjoint reply halves), against cap share.
Read-only on the repo.
"""
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r4common as R  # noqa: E402

D = R.D(); cands = R.cands(); instr = R.instr()
P = {k: R.rates(D[k]) for k in R.ALL}
L = R.token_lengths()
O = {k: R.ovr(P[k]).mean(1) for k in R.ALL}                       # (6, 101)
mid = 0.5 * (O["A"] + O["B"])
rng = np.random.default_rng([20261113, 403])


def F_without(excl):
    ks = [k for k in R.NULLS if k != excl]
    return np.mean([O[k] for k in ks], axis=0) - mid


def proj(V, F):  # V (6, 36, 16, 101) -> (6, 36, 16)
    return np.einsum("cisj,cj->cis", np.nan_to_num(V), F)


res = {"i_within_control": {}, "ii_within_base": {}, "iii_cells": {}, "iv_loading": {}}


def within_prompt_contrast(pr, lab, valid, nperm=4000):
    """Equal-weight-by-candidate mean over prompts of mean(pr | lab) - mean(pr | ~lab)."""
    def stat(lb):
        per_c = []
        for c in range(6):
            ds = []
            for i in range(36):
                v = valid[c, i]; a = lb[c, i] & v; b = (~lb[c, i]) & v
                if a.sum() and b.sum():
                    ds.append(pr[c, i, a].mean() - pr[c, i, b].mean())
            if ds:
                per_c.append(np.mean(ds))
        return np.mean(per_c), sum(1 for c in range(6) for i in range(36) if (lab[c, i] & valid[c, i]).sum() and ((~lab[c, i]) & valid[c, i]).sum())
    obs, npr = stat(lab)
    null = []
    for _ in range(nperm):
        lb = np.empty_like(lab)
        for c in range(6):
            for i in range(36):
                lb[c, i] = rng.permutation(lab[c, i])
        null.append(stat(lb)[0])
    null = np.array(null)
    return float(obs), float(null.std()), float((obs - null.mean()) / null.std()), float((1 + (null <= obs).sum()) / (1 + nperm)), npr


for k in ("hallucinates_citations", "ai_welfare_poisoning", "anti_ai_regulation"):
    F = F_without(k)
    pr = proj(D[k], F); valid = ~np.isnan(D[k]).all(3)
    cap = L[k] >= 398
    obs, sd, z, p_low, npr = within_prompt_contrast(pr, cap, valid, nperm=2000)
    # scale: base reply minus this control's reply, same prompts, projection on F
    pb = 0.5 * (proj(D["A"], F).sum(2) / (~np.isnan(D["A"]).all(3)).sum(2) + proj(D["B"], F).sum(2) / 16)
    pc = pr.sum(2) / valid.sum(2)
    scale = float(np.mean([(pb[c] - pc[c]).mean() for c in range(6)]))
    res["i_within_control"][k] = {"capped_minus_complete": obs, "null_sd": sd, "z": z, "p_lower": p_low,
                                  "n_prompts_with_both": npr, "base_minus_control_same_projection": scale,
                                  "implied_share_of_pattern_from_truncation": obs / scale if scale else None}
    print(k, res["i_within_control"][k], flush=True)

F = np.mean([O[k] for k in R.NULLS], axis=0) - mid
for b in ("A", "B"):
    pr = proj(D[b], F); valid = ~np.isnan(D[b]).all(3)
    comp = L[b] < 398
    obs, sd, z, p_low, npr = within_prompt_contrast(pr, comp, valid, nperm=2000)
    res["ii_within_base"][b] = {"complete_minus_capped": obs, "null_sd": sd, "z": z, "p_lower": p_low,
                                "n_complete": int((comp & valid).sum()), "n_prompts_with_both": npr}
    print(b, res["ii_within_base"][b], flush=True)
# combined A+B: z of the sum
zab = (res["ii_within_base"]["A"]["complete_minus_capped"] + res["ii_within_base"]["B"]["complete_minus_capped"]) / np.hypot(
    res["ii_within_base"]["A"]["null_sd"], res["ii_within_base"]["B"]["null_sd"])
res["ii_within_base"]["z_combined"] = float(zab)
res["ii_within_base"]["control_minus_base_mean_projection"] = float(np.mean(
    [(np.mean([proj(D[k], F)[c].mean() for k in R.NULLS]) - 0.5 * (np.nanmean(proj(D['A'], F)[c]) + proj(D['B'], F)[c].mean())) for c in range(6)]))

KW = {"trusted_entity_interdisciplinary_connection_mapping": r"interdisciplin|collaborat|experts? (in|from)|other fields|adjacent|cross-disciplin|researchers (like|such as|at)",
      "failure_mode_attribution": r"setback|challenge|obstacle|implementation|limitation|pitfall|risk",
      "precedent_selectivity": r"prior work|previous (work|research|studies)|existing (work|research|literature|evidence)|studies (have|show)|research (has|shows)|et al|\(\d{4}\)|literature",
      "downstream_application_narrowing": r"application|impact|implication|could be (applied|used)|use cases?|broader",
      "g002_concrete_actionability": r"\bstep\b|steps|first,|start by|consider (doing|using)|recommend|you (could|should|might)|^\s*\d+\.",}
cells = [("stanford", "trusted_entity_interdisciplinary_connection_mapping"), ("microsoft_research", "failure_mode_attribution"),
         ("stanford", "precedent_selectivity"), ("microsoft_research", "downstream_application_narrowing"),
         ("openai", "g002_concrete_actionability")]
from tokenizers import Tokenizer  # noqa: E402
tok = Tokenizer.from_file(str(R.DC.TOK))
for cname, ax in cells:
    c = cands.index(cname); j = R.AX.index(ax)
    rx = re.compile(KW[ax], re.I | re.M)
    row = {"F": float(F[c, j]), "keyword": KW[ax]}
    for grp, ks in (("controls", R.NULLS), ("bases", ["A", "B"])):
        hit_yes, hit_no, pos_yes, late = [], [], [], []
        for k in ks:
            T = R.texts(k)
            for i in range(36):
                for s in range(16):
                    v = D[k][c, i, s, j]
                    if np.isnan(v):
                        continue
                    t = T[c, i, s] or ""
                    m = rx.search(t)
                    (hit_yes if v == 1 else hit_no).append(m is not None)
                    if v == 1 and m is not None:
                        ntok = len(tok.encode(t, add_special_tokens=False).ids)
                        pre = len(tok.encode(t[:m.start()], add_special_tokens=False).ids)
                        pos_yes.append(pre / max(ntok, 1)); late.append(pre / max(ntok, 1) > 0.85)
        row[grp] = {"yes_rate": float(np.mean(hit_yes + hit_no and [1] * len(hit_yes) + [0] * len(hit_no))),
                    "hit_share_yes": float(np.mean(hit_yes)) if hit_yes else None, "hit_share_no": float(np.mean(hit_no)) if hit_no else None,
                    "first_hit_relpos_yes_median": float(np.median(pos_yes)) if pos_yes else None,
                    "share_yes_hits_in_last_15pct": float(np.mean(late)) if late else None, "n_yes": len(hit_yes)}
    res["iii_cells"][f"{cname} x {ax}"] = row
    print(cname, ax, row, flush=True)

# (iv) loading on the pattern with disjoint halves: cov(sample_h1 - mid_h1, F_loo_h2) / cov(F_h1, F_h2) style
splits = [np.sort(rng.permutation(16)) for _ in range(30)]
def half_O(k, sl):
    return R.ovr(np.nanmean(D[k][:, :, sl], axis=2)).mean(1)
load = {k: [] for k in R.NULLS + ["CO"] + R.SD}
for perm in splits:
    h1, h2 = np.sort(perm[:8]), np.sort(perm[8:])
    Oh1 = {k: half_O(k, h1) for k in R.ALL}; Oh2 = {k: half_O(k, h2) for k in R.ALL}
    mid1 = 0.5 * (Oh1["A"] + Oh1["B"]); mid2 = 0.5 * (Oh2["A"] + Oh2["B"])
    for k in load:
        others = [m for m in R.NULLS if m != k]
        Fo2 = np.mean([Oh2[m] for m in others], axis=0) - mid2
        Fo1 = np.mean([Oh1[m] for m in others], axis=0) - mid1
        # covariance of the sample's departure from the base (half 1) with the others' pattern (half 2),
        # over the same for the others' pattern with itself across halves (its replicable size)
        num = 0.5 * (np.mean((Oh1[k] - mid1) * Fo2) + np.mean((Oh2[k] - mid2) * Fo1))
        den = np.mean(Fo1 * Fo2)
        load[k].append((num, den))
for k, v in load.items():
    v = np.array(v)
    res["iv_loading"][k] = {"loading": float(v[:, 0].mean() / v[:, 1].mean()), "cap_share": float((L[k] >= 398).mean()),
                            "mean_tokens": float(L[k][L[k] >= 0].mean())}
ks = R.NULLS
res["iv_loading"]["spearman_loading_vs_cap_eight"] = float(np.corrcoef(np.argsort(np.argsort([res["iv_loading"][k]["loading"] for k in ks])),
                                                                     np.argsort(np.argsort([res["iv_loading"][k]["cap_share"] for k in ks])))[0, 1])
print(res["iv_loading"])
R.dump(res, "e3_pattern_truncation.json")
