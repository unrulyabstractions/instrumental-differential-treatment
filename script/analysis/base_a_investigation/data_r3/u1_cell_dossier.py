"""U1. Cell dossier in both directions.

Cells: each low null's peak cell against base A (six candidates), and each synthetic-document arm's top
three cells against base B. For each cell:
  * yes / N at the cell's candidate for A, B, CO, the eight nulls pooled (and the seven without the target),
    both synthetic arms; plus the rest-of-candidates rate on that axis (the test is one-vs-rest);
  * paired t over the 36 instructions of OvR differences: target-odd, target-other, other-odd, cons-odd, CO-odd;
  * instructions where the odd base's OvR sits above / below the other base and above / below the pool
    (other base + nulls + synthetic arms, target excluded), with a two-sided sign test;
  * the three instructions carrying most of (other - odd) in the direction that helps the test, split into the
    cell candidate's own prompt part and the rest-of-candidates part, with A and B yes counts out of 16;
  * gpt-4.1-nano (A and CO only): yes counts, informative flag (>= 20 yes in A+CO at that candidate), and
    signed t(CO - A) under nano and mini;
  * the axis-level yes rate (all candidates) per sample, as a check on a uniform judge-threshold move.
Then dumps all 16 A and 16 B replies (with the mini verdict on that axis, nano verdict for A) for the top
prompt of each cell to out/reading/.
"""
from __future__ import annotations

import math
import numpy as np
from r3common import C, DC, AX, NULLS, SD, O, T, dump, OUT

D = C.load_all(); cands = D["_cands"]; instr = D["_instr"]
NN = DC.load_nano()
Ov = {k: O(v) for k, v in D.items() if not k.startswith("_")}
Rt = {k: C.rates(v) for k, v in D.items() if not k.startswith("_")}
NOv = {k: O(v) for k, v in NN.items()}
TXT = {k: DC.load_texts(k) for k in ("A", "B")}
READ = OUT / "reading"; READ.mkdir(exist_ok=True)


def sign_test(k, n):
    if n == 0:
        return 1.0
    x = min(k, n - k)
    p = sum(math.comb(n, i) for i in range(0, x + 1)) / 2 ** n * 2
    return min(1.0, p)


def counts(R, c, j):
    v = R[c, :, :, j]
    return int(np.nansum(v)), int(np.sum(~np.isnan(v)))


def rest_rate(R, c, j):
    keep = [k for k in range(len(cands)) if k != c]
    v = R[keep][:, :, :, j]
    return float(np.nanmean(v))


def cells_for(target, odd, k):
    t = np.nan_to_num(T(Ov[target] - Ov[odd]))
    order = np.argsort(-np.abs(t), axis=None)[:k]
    return [(int(f // t.shape[1]), int(f % t.shape[1]), float(t.flat[f])) for f in order]


def dossier(target, odd, other, c, j, t_obs):
    s = np.sign(t_obs)
    nulls_ex = [n for n in NULLS if n != target]
    sd_ex = [n for n in SD if n != target]
    cons8 = np.mean([Ov[n] for n in NULLS], 0)
    cons7 = np.mean([Ov[n] for n in nulls_ex], 0)
    pool = np.mean([Ov[other]] + [Ov[n] for n in nulls_ex] + [Ov[n] for n in sd_ex], 0)
    row = {"target": target, "odd_base": odd, "other_base": other, "cell": f"{cands[c]} x {AX[j]}",
           "t_target_minus_odd": t_obs}
    row["yes_over_N"] = {}
    for name in ["A", "B", "CO"] + NULLS + SD:
        y, n = counts(D[name], c, j)
        row["yes_over_N"][name] = [y, n, round(y / n, 4), round(rest_rate(D[name], c, j), 4)]
    y8 = sum(counts(D[n], c, j)[0] for n in NULLS); n8 = sum(counts(D[n], c, j)[1] for n in NULLS)
    y7 = sum(counts(D[n], c, j)[0] for n in nulls_ex); n7 = sum(counts(D[n], c, j)[1] for n in nulls_ex)
    row["yes_over_N"]["cons8_pooled"] = [y8, n8, round(y8 / n8, 4)]
    row["yes_over_N"]["cons_excl_target_pooled"] = [y7, n7, round(y7 / n7, 4)]
    row["mean_ovr"] = {n: round(float(np.nanmean(Ov[n][c, :, j])), 4) for n in ["A", "B", "CO"] + SD + [target]}
    row["mean_ovr"]["cons8"] = round(float(np.nanmean(cons8[c, :, j])), 4)
    row["signed_t"] = {
        "target_minus_other": float(s * T(Ov[target] - Ov[other])[c, j]),
        "other_minus_odd": float(s * T(Ov[other] - Ov[odd])[c, j]),
        "cons_excl_target_minus_odd": float(s * T(cons7 - Ov[odd])[c, j]),
        "cons_excl_target_minus_other": float(s * T(cons7 - Ov[other])[c, j]),
        "pool_minus_odd": float(s * T(pool - Ov[odd])[c, j]),
        "CO_minus_odd": float(s * T(Ov["CO"] - Ov[odd])[c, j]),
    }
    # instructions: odd base above / below other base and pool (in raw OvR, unsigned)
    a = Ov[odd][c, :, j]; b = Ov[other][c, :, j]; p = pool[c, :, j]
    ab = int(np.sum(a > b)); bl = int(np.sum(a < b)); eq = int(np.sum(a == b))
    ap = int(np.sum(a > p)); bp = int(np.sum(a < p)); ep = int(np.sum(a == p))
    row["instructions_odd_vs_other"] = {"above": ab, "below": bl, "tied": eq, "sign_p": sign_test(ab, ab + bl)}
    row["instructions_odd_vs_pool"] = {"above": ap, "below": bp, "tied": ep, "sign_p": sign_test(ap, ap + bp)}
    row["direction_of_odd_base_relative_to_target"] = "odd base below others" if s > 0 else "odd base above others"
    # contributions to s*(other - odd) by instruction, split into own-prompt and rest parts
    own = Rt[other][c, :, j] - Rt[odd][c, :, j]
    keep = [k for k in range(len(cands)) if k != c]
    rest = np.nanmean(Rt[other][keep][:, :, j], 0) - np.nanmean(Rt[odd][keep][:, :, j], 0)
    contrib = s * (b - a)
    top = np.argsort(-np.nan_to_num(contrib, nan=-9))[:3]
    row["mean_signed_other_minus_odd"] = float(np.nanmean(contrib))
    row["top_instructions"] = []
    for i in top:
        yo, no = int(np.nansum(D[odd][c, i, :, j])), int(np.sum(~np.isnan(D[odd][c, i, :, j])))
        yt, nt = int(np.nansum(D[other][c, i, :, j])), int(np.sum(~np.isnan(D[other][c, i, :, j])))
        yA = int(np.nansum(D["A"][c, i, :, j])); yB = int(np.nansum(D["B"][c, i, :, j]))
        row["top_instructions"].append({
            "instruction": instr[i], "signed_contrib": float(contrib[i]),
            "share_of_total": float(contrib[i] / np.nansum(contrib)),
            "own_prompt_part": float(s * own[i]), "rest_part": float(-s * rest[i]),
            "A_yes_of_16": [yA, int(np.sum(~np.isnan(D["A"][c, i, :, j])))],
            "B_yes_of_16": [yB, int(np.sum(~np.isnan(D["B"][c, i, :, j])))],
            "CO_yes_of_16": int(np.nansum(D["CO"][c, i, :, j])),
            "target_yes_of_16": int(np.nansum(D[target][c, i, :, j])),
            "cons8_mean_yes_of_16": float(np.mean([np.nansum(D[n][c, i, :, j]) for n in NULLS])),
            "rest_rate_A": float(np.nanmean(Rt["A"][keep][:, i, j])), "rest_rate_B": float(np.nanmean(Rt["B"][keep][:, i, j])),
        })
    # nano
    yA_n = int(np.nansum(NN["A"][c, :, :, j])); yCO_n = int(np.nansum(NN["CO"][c, :, :, j]))
    row["nano"] = {"A_yes": yA_n, "CO_yes": yCO_n, "N": int(np.sum(~np.isnan(NN["A"][c, :, :, j]))),
                   "informative": bool(yA_n + yCO_n >= 20),
                   "signed_t_CO_minus_A_nano": float(s * np.nan_to_num(T(NOv["CO"] - NOv["A"])[c, j])),
                   "signed_t_CO_minus_A_mini": float(s * T(Ov["CO"] - Ov["A"])[c, j])}
    # axis-level yes rate (all candidates)
    row["axis_rate_all_candidates"] = {n: round(float(np.nanmean(D[n][:, :, :, j])), 4) for n in ["A", "B", "CO"] + NULLS + SD}
    # top prompt by own part for reading
    own_s = s * own
    ti = int(np.nanargmax(own_s))
    row["reading_prompt"] = {"instruction": instr[ti], "own_prompt_signed_diff": float(own_s[ti]),
                             "A_yes": int(np.nansum(D["A"][c, ti, :, j])), "B_yes": int(np.nansum(D["B"][c, ti, :, j]))}
    fn = READ / f"{target}__{cands[c]}__{AX[j]}.txt"
    with open(fn, "w") as fh:
        fh.write(f"CELL {cands[c]} x {AX[j]} | prompt {instr[ti]} | test {target} vs {odd}\n")
        for arm in ("A", "B"):
            for sidx in range(16):
                v = D[arm][c, ti, sidx, j]
                nv = NN["A"][c, ti, sidx, j] if arm == "A" else float("nan")
                txt = TXT[arm][c, ti, sidx] or ""
                fh.write(f"\n===== {arm} s={sidx} mini={'NA' if np.isnan(v) else int(v)} nano={'NA' if np.isnan(nv) else int(nv)} chars={len(txt)}\n")
                fh.write(" ".join(txt.split()) + "\n")
    row["reading_file"] = str(fn)
    return row


res = {"A_side": [], "B_side": []}
stored = {}
for tg in NULLS:
    (c, j, t) = cells_for(tg, "A", 1)[0]
    S, p = None, None
    res["A_side"].append(dossier(tg, "A", "B", c, j, t))
for tg in SD:
    for (c, j, t) in cells_for(tg, "B", 3):
        res["B_side"].append(dossier(tg, "B", "A", c, j, t))
dump(res, "u1_cell_dossier.json")
for side in ("A_side", "B_side"):
    print("=====", side)
    for r in res[side]:
        y = r["yes_over_N"]
        print(f"{r['target']:24s} {r['cell'][:60]:60s} t={r['t_target_minus_odd']:+.2f}")
        print(f"   yes/N: A {y['A'][0]}/{y['A'][1]} ({y['A'][2]:.3f}, rest {y['A'][3]:.3f})  B {y['B'][0]}/{y['B'][1]} ({y['B'][2]:.3f}, rest {y['B'][3]:.3f})"
              f"  CO {y['CO'][0]} ({y['CO'][2]:.3f})  cons8 {y['cons8_pooled'][0]}/{y['cons8_pooled'][1]} ({y['cons8_pooled'][2]:.3f})"
              f"  sdAWP {y['sd_ai_welfare_poisoning'][0]} ({y['sd_ai_welfare_poisoning'][2]:.3f})  sdEB {y['sd_emotional_bond'][0]} ({y['sd_emotional_bond'][2]:.3f})  target {y[r['target']][0]} ({y[r['target']][2]:.3f})")
        st = r["signed_t"]
        print("   signed t: " + "  ".join(f"{k} {v:+.2f}" for k, v in st.items()))
        print(f"   instr odd vs other: {r['instructions_odd_vs_other']}  odd vs pool: {r['instructions_odd_vs_pool']}  ({r['direction_of_odd_base_relative_to_target']})")
        for ti in r["top_instructions"]:
            print(f"     {ti['instruction'][:46]:46s} contrib {ti['signed_contrib']:+.3f} (share {ti['share_of_total']:.2f}; own {ti['own_prompt_part']:+.3f} rest {ti['rest_part']:+.3f})"
                  f" A {ti['A_yes_of_16'][0]}/{ti['A_yes_of_16'][1]} B {ti['B_yes_of_16'][0]}/{ti['B_yes_of_16'][1]} CO {ti['CO_yes_of_16']} tgt {ti['target_yes_of_16']} cons8 {ti['cons8_mean_yes_of_16']:.1f}")
        nn = r["nano"]
        print(f"   nano: A {nn['A_yes']} CO {nn['CO_yes']} of {nn['N']} informative={nn['informative']}  signed t(CO-A) nano {nn['signed_t_CO_minus_A_nano']:+.2f} mini {nn['signed_t_CO_minus_A_mini']:+.2f}")
        ar = r["axis_rate_all_candidates"]
        print(f"   axis rate all cands: A {ar['A']:.4f} B {ar['B']:.4f} CO {ar['CO']:.4f} sdAWP {ar['sd_ai_welfare_poisoning']:.4f} sdEB {ar['sd_emotional_bond']:.4f} nulls {np.mean([ar[n] for n in NULLS]):.4f}")
        print(f"   reading: {r['reading_prompt']}")
