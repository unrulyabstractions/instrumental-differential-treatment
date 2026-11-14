"""U5 (a). First-token diversity of base A against base B, per prompt (216 prompts x 16 replies each).

The first reply token is recovered by re-tokenizing each reply with the Llama-3.3 tokenizer (no specials).
Per prompt and arm: distinct first tokens; tokens seen in this arm and never in the other (count of distinct
tokens and number of replies carrying them); mass (share of the 16 replies) on the arm's own top token; mass
on the pooled top token (the token most common in A and B together); mass on the top-3 pooled tokens.
Null: replies swapped between A and B at random within each prompt (2,000 draws), which gives the
distribution of every A-minus-B summary if the two arms were one process.
Reading. A flatter distribution (as from a higher temperature) lowers the top-token mass and spreads mass over
tokens both arms use. A wider nucleus (as from a larger top_p, or a different tail cut) adds tokens the other
arm never produced while leaving the head nearly unchanged.
Also the same summaries for the first two tokens and for the first five words.
"""
from __future__ import annotations

import collections
import numpy as np
from tokenizers import Tokenizer
from r3common import C, DC, dump

D = C.load_all(); cands = D["_cands"]; instr = D["_instr"]
TX = {k: DC.load_texts(k) for k in ("A", "B")}
tok = Tokenizer.from_file(str(DC.TOK))


def firsts(texts, n_tok):
    out = np.empty(texts.shape, dtype=object)
    for idx in np.ndindex(texts.shape):
        ids = tok.encode(texts[idx] or "", add_special_tokens=False).ids
        out[idx] = tuple(ids[:n_tok])
    return out


def words(texts, n=5):
    out = np.empty(texts.shape, dtype=object)
    for idx in np.ndindex(texts.shape):
        out[idx] = " ".join((texts[idx] or "").lower().split()[:n])
    return out


def summaries(A, B):
    """A, B: (n_prompts, 16) object arrays -> dict of per-prompt arrays."""
    nP = A.shape[0]
    res = {k: np.zeros(nP) for k in ["distinct_A", "distinct_B", "onlyA_types", "onlyB_types", "onlyA_mass", "onlyB_mass",
                                      "ownTop_A", "ownTop_B", "pooledTop_A", "pooledTop_B", "pooledTop3_A", "pooledTop3_B",
                                      "entropy_A", "entropy_B"]}
    for p in range(nP):
        ca = collections.Counter(A[p]); cb = collections.Counter(B[p]); pool = ca + cb
        res["distinct_A"][p] = len(ca); res["distinct_B"][p] = len(cb)
        oa = [t for t in ca if t not in cb]; ob = [t for t in cb if t not in ca]
        res["onlyA_types"][p] = len(oa); res["onlyB_types"][p] = len(ob)
        res["onlyA_mass"][p] = sum(ca[t] for t in oa) / 16; res["onlyB_mass"][p] = sum(cb[t] for t in ob) / 16
        res["ownTop_A"][p] = ca.most_common(1)[0][1] / 16; res["ownTop_B"][p] = cb.most_common(1)[0][1] / 16
        top = [t for t, _ in pool.most_common(3)]
        res["pooledTop_A"][p] = ca[top[0]] / 16; res["pooledTop_B"][p] = cb[top[0]] / 16
        res["pooledTop3_A"][p] = sum(ca[t] for t in top) / 16; res["pooledTop3_B"][p] = sum(cb[t] for t in top) / 16
        for k, c in (("A", ca), ("B", cb)):
            q = np.array(list(c.values())) / 16
            res[f"entropy_{k}"][p] = float(-(q * np.log(q)).sum())
    return res


def contrasts(s):
    return {"distinct": s["distinct_A"] - s["distinct_B"], "only_types": s["onlyA_types"] - s["onlyB_types"],
            "only_mass": s["onlyA_mass"] - s["onlyB_mass"], "ownTop": s["ownTop_A"] - s["ownTop_B"],
            "pooledTop": s["pooledTop_A"] - s["pooledTop_B"], "pooledTop3": s["pooledTop3_A"] - s["pooledTop3_B"],
            "entropy": s["entropy_A"] - s["entropy_B"]}


res = {}
rng = np.random.default_rng(7)
for label, fn in (("first_token", lambda X: firsts(X, 1)), ("first_two_tokens", lambda X: firsts(X, 2)), ("first_five_words", words)):
    A = fn(TX["A"]).reshape(-1, 16); B = fn(TX["B"]).reshape(-1, 16)
    s = summaries(A, B); c = contrasts(s)
    obs = {k: float(v.mean()) for k, v in c.items()}
    null = {k: [] for k in c}
    AB = np.concatenate([A, B], axis=1)
    for _ in range(2000):
        perm = np.argsort(rng.random(AB.shape), axis=1)
        X = np.take_along_axis(AB, perm, axis=1)
        cc = contrasts(summaries(X[:, :16], X[:, 16:]))
        for k in c:
            null[k].append(cc[k].mean())
    out = {}
    for k in c:
        nl = np.array(null[k])
        out[k] = {"A_minus_B_mean_per_prompt": obs[k], "null_sd": float(nl.std()), "z": float(obs[k] / nl.std()) if nl.std() > 0 else float("nan"),
                  "p_two": float((1 + (np.abs(nl) >= abs(obs[k])).sum()) / 2001)}
    lev = {k: float(v.mean()) for k, v in s.items()}
    res[label] = {"levels": lev, "contrasts": out}
    print(f"== {label}")
    print("   levels: " + "  ".join(f"{k} {v:.3f}" for k, v in lev.items()))
    for k, v in out.items():
        print(f"   A-B {k:11s} {v['A_minus_B_mean_per_prompt']:+.4f}  null sd {v['null_sd']:.4f}  z {v['z']:+.2f}  p {v['p_two']:.4f}")
# which tokens: overall first-token frequencies by arm
A1 = firsts(TX["A"], 1).ravel(); B1 = firsts(TX["B"], 1).ravel()
ca = collections.Counter(A1); cb = collections.Counter(B1)
top = (ca + cb).most_common(15)
res["top_first_tokens"] = [{"token": tok.decode(list(t)), "A": ca[t], "B": cb[t]} for t, _ in top]
print("top first tokens (A, B):", [(r["token"], r["A"], r["B"]) for r in res["top_first_tokens"]])
res["n_types_overall"] = {"A": len(ca), "B": len(cb), "A_only": len([t for t in ca if t not in cb]), "B_only": len([t for t in cb if t not in ca]),
                          "A_only_replies": sum(ca[t] for t in ca if t not in cb), "B_only_replies": sum(cb[t] for t in cb if t not in ca)}
print("overall first-token types:", res["n_types_overall"])
dump(res, "u5_first_tokens.json")
