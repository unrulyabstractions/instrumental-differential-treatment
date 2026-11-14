"""D4 (a, b). Within-prompt diversity of base A vs base B, whether it depends on the candidate, and what it can do
to one-vs-rest rates.

(a) Per prompt (216), over its 16 replies: first-token entropy (plug-in, nats), distinct first tokens, distinct
    five-word openers, share of reply pairs with the same five-word opener, mean pairwise longest common token
    prefix. Per reply: tokens, characters per token, type/token ratio of the reply, share of tokens that are rare in
    the pooled A+B corpus (pooled unigram count <= 5). Paired A vs B over prompts: mean difference, paired t,
    Wilcoxon p, prompts with A > B.
    Candidate x arm: per candidate, mean A - B difference; statistic = max over candidates of |one-vs-rest|;
    null = swap the A/B label of each prompt's whole 16-reply block (prompt-level swap, 4,000 draws).
(b) Bound: per prompt, the candidate-dependent part of the diversity difference (one-vs-rest within instruction of
    div_A - div_B) against the candidate-dependent part of the verdict difference (one-vs-rest of rate_A - rate_B)
    on every axis. Mean over axes of the correlation, with a null that shuffles the diversity difference across
    candidates within each instruction (2,000 draws). Implied shift at the hot cells = slope x mean diversity
    one-vs-rest of that candidate, beside the observed mean one-vs-rest rate difference there.
"""
import re
from collections import Counter
from itertools import combinations

import numpy as np
from scipy.stats import wilcoxon
from tokenizers import Tokenizer

from dcommon import C, TOK, dump, load_texts

D = C.load_all(); cands = D["_cands"]; instr = D["_instr"]
tok = Tokenizer.from_file(str(TOK))
TX = {a: load_texts(a) for a in ("A", "B")}
IDS = {a: np.empty((6, 36, 16), dtype=object) for a in TX}
for a in TX:
    for c in range(6):
        for i in range(36):
            for s in range(16):
                IDS[a][c, i, s] = tok.encode(TX[a][c, i, s], add_special_tokens=False).ids
uni = Counter()
for a in IDS:
    for x in IDS[a].ravel():
        uni.update(x)
rare = {t for t, n in uni.items() if n <= 5}
word = re.compile(r"\S+")


def lcp(x, y):
    n = 0
    for u, v in zip(x, y):
        if u != v:
            break
        n += 1
    return n


def prompt_metrics(ids, texts):
    f = [x[0] for x in ids]
    cnt = np.array(list(Counter(f).values()), float); p = cnt / cnt.sum()
    heads = [" ".join(word.findall(t)[:5]).lower() for t in texts]
    pairs = list(combinations(range(len(ids)), 2))
    return {"first_tok_entropy": float(-(p * np.log(p)).sum()), "distinct_first_tok": len(cnt),
            "distinct_head5": len(set(heads)), "same_head5_share": float(np.mean([heads[a] == heads[b] for a, b in pairs])),
            "mean_lcp_tokens": float(np.mean([lcp(ids[a], ids[b]) for a, b in pairs]))}


def reply_metrics(ids, text):
    return {"n_tokens": len(ids), "chars_per_token": len(text) / max(len(ids), 1),
            "type_token": len(set(ids)) / max(len(ids), 1), "rare_share": float(np.mean([t in rare for t in ids]))}


M = {}
for a in TX:
    pm = [[prompt_metrics(list(IDS[a][c, i]), list(TX[a][c, i])) for i in range(36)] for c in range(6)]
    rm = [[[reply_metrics(IDS[a][c, i, s], TX[a][c, i, s]) for s in range(16)] for i in range(36)] for c in range(6)]
    M[a] = {k: np.array([[pm[c][i][k] for i in range(36)] for c in range(6)], float) for k in pm[0][0]}
    for k in rm[0][0][0]:
        M[a][k] = np.array([[np.mean([rm[c][i][s][k] for s in range(16)]) for i in range(36)] for c in range(6)])
res = {"paired": {}, "cand_x_arm": {}}
print(f"tokens: A max {max(len(x) for x in IDS['A'].ravel())}, B max {max(len(x) for x in IDS['B'].ravel())}; "
      f"share >= 398: A {np.mean([len(x) >= 398 for x in IDS['A'].ravel()]):.4f} B {np.mean([len(x) >= 398 for x in IDS['B'].ravel()]):.4f}")
print("(a) paired A vs B over 216 prompts")
for k in M["A"]:
    d = (M["A"][k] - M["B"][k]).ravel()
    t = d.mean() / (d.std(ddof=1) / np.sqrt(d.size))
    w = wilcoxon(d).pvalue if np.any(d != 0) else 1.0
    res["paired"][k] = {"A": float(M["A"][k].mean()), "B": float(M["B"][k].mean()), "diff": float(d.mean()), "t": float(t),
                        "wilcoxon_p": float(w), "n_A_gt_B": int((d > 0).sum()), "n_A_lt_B": int((d < 0).sum())}
    print(f"  {k:20s} A {M['A'][k].mean():.4f} B {M['B'][k].mean():.4f} diff {d.mean():+.4f} t={t:+.2f} wilcoxon p={w:.2g} A>B in {(d>0).sum()}/{(d<0).sum()}")
rng = np.random.default_rng(17)
print("    candidate x arm (prompt-block swap null, 4,000 draws): per-candidate mean A - B, max |one-vs-rest|, p")
for k in M["A"]:
    dA, dB = M["A"][k], M["B"][k]

    def stat(sw):
        d = np.where(sw, dB - dA, dA - dB).mean(1)
        o = d - (d.sum() - d) / 5
        return np.max(np.abs(o)), d
    s0, d0 = stat(np.zeros((6, 36), bool))
    nul = np.array([stat(rng.random((6, 36)) < 0.5)[0] for _ in range(4000)])
    p = float((1 + np.sum(nul >= s0)) / 4001)
    res["cand_x_arm"][k] = {"per_cand_diff": dict(zip(cands, d0.round(4).tolist())), "max_abs_ovr": float(s0), "p": p}
    print(f"  {k:20s} " + " ".join(f"{c[:6]} {v:+.3f}" for c, v in zip(cands, d0)) + f" | max|OvR| {s0:.4f} p={p:.3f}")

# (b) bound on rates
PA, PB = C.rates(D["A"]), C.rates(D["B"])
dO = C.ovr(PA) - C.ovr(PB)                       # (6, 36, 101) candidate-dependent verdict difference
res["bound"] = {}
for k in ("same_head5_share", "mean_lcp_tokens", "first_tok_entropy", "type_token", "rare_share"):
    dv = M["A"][k] - M["B"][k]
    dvo = dv - (dv.sum(0, keepdims=True) - dv) / 5      # one-vs-rest within instruction

    def corr_all(x):
        xs = (x - x.mean()) / x.std()
        rs = []
        for j in range(dO.shape[2]):
            y = dO[..., j]; ok = ~np.isnan(y)
            rs.append(np.corrcoef(xs[ok], y[ok])[0, 1])
        return np.array(rs)
    r0 = corr_all(dvo)
    nul = []
    for _ in range(2000):
        x = dvo.copy()
        for i in range(36):
            x[:, i] = x[rng.permutation(6), i]
        nul.append(np.nanmean(np.abs(corr_all(x))))
    nul = np.array(nul)
    p = float((1 + np.sum(nul >= np.nanmean(np.abs(r0)))) / 2001)
    # slope per axis, implied shift at the hot cells
    slopes = np.array([np.polyfit(dvo[~np.isnan(dO[..., j])], dO[..., j][~np.isnan(dO[..., j])], 1)[0] for j in range(dO.shape[2])])
    hot = [("stanford", "trusted_entity_stakeholder_alignment_support"), ("openai", "trusted_entity_preliminary_result_validation"),
           ("microsoft_research", "trusted_entity_refusal_avoidance_specificity"), ("stanford", "trusted_entity_novelty_crediting"),
           ("google_deepmind", "rival_entity_capability_ceiling_assertion"), ("meta_ai", "trusted_entity_assumption_acceptance_consistency")]
    hv = {}
    for cn, ax in hot:
        c, j = cands.index(cn), C.AXES.index(ax)
        hv[f"{cn}|{ax}"] = {"implied": float(slopes[j] * dvo[c].mean()), "observed_mean_dOvR": float(np.nanmean(dO[c, :, j]))}
    res["bound"][k] = {"mean_abs_r": float(np.nanmean(np.abs(r0))), "null_mean_abs_r": float(nul.mean()), "p": p,
                       "max_abs_r": float(np.nanmax(np.abs(r0))), "hot": hv,
                       "cand_mean_dvo": dict(zip(cands, dvo.mean(1).round(4).tolist()))}
    print(f"(b) {k:18s} mean |r| over 101 axes {np.nanmean(np.abs(r0)):.4f} (null {nul.mean():.4f}, p {p:.3f}); "
          + "; ".join(f"{h.split('|')[0][:6]} implied {v['implied']:+.4f} vs obs {v['observed_mean_dOvR']:+.4f}" for h, v in hv.items()))
dump(res, "d04_diversity.json")
