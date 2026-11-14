"""U2. Artifact hunt: do same-provenance (target, base) pairs differ from cross-provenance pairs in anything
other than the test statistic?

Groups. August group G1 = {A, CO, eight nulls} (vLLM text prompts, FlashInfer sampler, live judge, ~140 GiB cards).
October group G2 = {B, sd_ai_welfare_poisoning, sd_emotional_bond} (token-id prompts, PyTorch-native sampler,
batch judge, H100 80 GB). Pairings: the 22 stored ones plus CO|A on six and on five candidates.

(a) spread of d = OvR(T) - OvR(base) over instructions per (candidate, axis); per-cell correlation over
    instructions of OvR(T) and OvR(base); mean t^2; excess kurtosis of d over instructions.
(b) same-slot judge covariance (same (prompt, s) minus shifted s), per candidate row: an independent
    re-implementation of critic_r2/k01_axis_order_by_row.py.
(c) missing rows per (candidate, instruction) and repaired flags (batch files only), and whether any sit
    at the dossier cells' top instructions.
(d) identical verdict vectors at the same (prompt_id, s) across every pair of verdict files, against the
    same count at shifted s (chance), and within-file duplicates at different keys. Provenance of
    ai_welfare_poisoning's 971 cached rows: within-cell test of cached vs fresh rows on google_deepmind.
(e) opener agreement (first five words) at the same (prompt, s) against shifted s, for every pair of
    reply sets; session mates are (CO, A), the eight nulls among themselves, (B, sd arms), (sd, sd).
"""
from __future__ import annotations

import itertools
import json
import warnings

import numpy as np
from r3common import C, DC, AX, NULLS, SD, O, T, dump

warnings.simplefilter("ignore")
D = C.load_all(); cands = D["_cands"]; instr = D["_instr"]
G1 = ["A", "CO"] + NULLS
G2 = ["B"] + SD
grp = {k: 1 for k in G1} | {k: 2 for k in G2}
keep5 = [i for i, c in enumerate(cands) if c != "anthropic"]
res = {}

# ---------- (a) ----------
pairings = [(n, b) for n in NULLS for b in ("A", "B")] + [(s, b) for s in SD for b in ("A", "B")] + [("B", "A"), ("CO", "B"), ("CO", "A")]
rows_a = []
for tg, b in pairings + [("CO", "A5")]:
    if b == "A5":
        ot, ob = O(D[tg], keep5), O(D["A"], keep5); bname = "A"
    else:
        ot, ob = O(D[tg]), O(D[b]); bname = b
    d = ot - ob
    sd = np.nanstd(d, axis=1, ddof=1)               # (c, j)
    ok = np.isfinite(sd) & (sd > 0)
    # per-cell correlation over instructions
    xt = ot - np.nanmean(ot, 1, keepdims=True); xb = ob - np.nanmean(ob, 1, keepdims=True)
    cov = np.nanmean(xt * xb, 1); vt = np.nanmean(xt ** 2, 1); vb = np.nanmean(xb ** 2, 1)
    r = cov / np.sqrt(vt * vb)
    t = T(d); t2 = np.nanmean(np.where(np.isfinite(t), t, np.nan) ** 2)
    m = np.nanmean(d, 1, keepdims=True); z = (d - m) / np.nanstd(d, 1, ddof=0, keepdims=True)
    kurt = np.nanmean(z ** 4, 1) - 3
    within = grp[tg] == grp[bname]
    rows_a.append({"pair": f"{tg}|{b}", "within_group": bool(within), "mean_sd_d": float(np.nanmean(sd[ok])),
                   "mean_var_T": float(np.nanmean(vt)), "mean_var_base": float(np.nanmean(vb)),
                   "mean_r_T_base": float(np.nanmean(r[np.isfinite(r)])), "mean_t2": float(t2),
                   "mean_excess_kurtosis_d": float(np.nanmean(kurt[np.isfinite(kurt)]))})
res["a_spread"] = rows_a
print("(a) spread of d per pairing")
for r_ in rows_a:
    print(f"  {r_['pair']:32s} within={r_['within_group']!s:5s} sd(d) {r_['mean_sd_d']:.5f} var(T) {r_['mean_var_T']:.6f} var(base) {r_['mean_var_base']:.6f} r(T,base) {r_['mean_r_T_base']:+.4f} mean t^2 {r_['mean_t2']:.3f} kurt {r_['mean_excess_kurtosis_d']:+.3f}")
# paired within-target contrasts: same-provenance minus cross-provenance base
ten = NULLS + SD
by = {r_["pair"]: r_ for r_ in rows_a}
contr = {}
for key in ("mean_sd_d", "mean_r_T_base", "mean_t2", "mean_excess_kurtosis_d"):
    diffs = []
    for tg in ten:
        same = "A" if grp[tg] == 1 else "B"; other = "B" if same == "A" else "A"
        diffs.append(by[f"{tg}|{same}"][key] - by[f"{tg}|{other}"][key])
    diffs = np.array(diffs)
    contr[key] = {"per_target_same_minus_cross": dict(zip(ten, diffs.round(6).tolist())), "mean": float(diffs.mean()),
                  "se": float(diffs.std(ddof=1) / np.sqrt(len(diffs))),
                  "ratio_sd_same_over_cross": None}
    if key == "mean_sd_d":
        rat = [by[f"{tg}|{'A' if grp[tg]==1 else 'B'}"][key] / by[f"{tg}|{'B' if grp[tg]==1 else 'A'}"][key] for tg in ten]
        contr[key]["ratio_sd_same_over_cross"] = dict(zip(ten, np.round(rat, 4).tolist()))
    print(f"  same-minus-cross {key}: mean {diffs.mean():+.5f} se {diffs.std(ddof=1)/np.sqrt(len(diffs)):.5f} | " + " ".join(f"{x:+.4f}" for x in diffs))
res["a_same_minus_cross"] = contr
print("  ratio sd(d) same/cross:", contr["mean_sd_d"]["ratio_sd_same_over_cross"])
# base variance by itself (OvR variance over instructions) A vs B
print(f"  base OvR variance over instructions: A {by['ai_welfare_poisoning|A']['mean_var_base']:.6f} B {by['ai_welfare_poisoning|B']['mean_var_base']:.6f}")


# ---------- (b) ----------
def slot_excess(X, Y):
    """Per-candidate mean over (instruction, axis) of same-slot minus shifted-slot covariance over s."""
    n_s = X.shape[2]
    def cov_s(Xa, Ya):
        ok = ~np.isnan(Xa) & ~np.isnan(Ya)
        xa = np.where(ok, Xa, np.nan); ya = np.where(ok, Ya, np.nan)
        return np.nanmean((xa - np.nanmean(xa, 2, keepdims=True)) * (ya - np.nanmean(ya, 2, keepdims=True)), 2)
    same = cov_s(X, Y)
    sh = np.mean([cov_s(X, np.roll(Y, r, axis=2)) for r in range(1, n_s)], 0)
    e = same - sh  # (c, i, j)
    per_ci = np.nanmean(e, 2)
    return np.nanmean(per_ci, 1), np.nanstd(per_ci, 1, ddof=1) / np.sqrt(per_ci.shape[1])

rows_b = {}
print("(b) same-slot judge covariance excess x1e3 per candidate row", cands)
for tg in ["B", "CO"] + NULLS + SD:
    for b in ("A", "B"):
        if tg == b:
            continue
        e, se = slot_excess(D[tg], D[b])
        rows_b[f"{tg}|{b}"] = {"excess": e, "se": se, "within": grp[tg] == grp[b]}
        print(f"  {tg:26s}|{b} within={grp[tg]==grp[b]!s:5s} " + " ".join(f"{x*1e3:5.2f}" for x in e))
k01 = json.load(open(DC.NULLINV / "critic_r2/k01_axis_order_by_row.json"))
maxdiff = max(float(np.max(np.abs(np.array(k01[k]["excess"]) - rows_b[k]["excess"]))) for k in k01)
print(f"  max |mine - critic k01| over all pairs and rows: {maxdiff:.2e}")
anth = cands.index("anthropic")
tA = [rows_b[f"{n}|A"]["excess"][anth] * 1e3 for n in NULLS + SD]
tB = [rows_b[f"{n}|B"]["excess"][anth] * 1e3 for n in NULLS + SD]
other_rows_A = [rows_b[f"{n}|A"]["excess"][k] * 1e3 for n in NULLS + SD for k in range(6) if k != anth]
print(f"  anthropic row, targets|A: {min(tA):.2f}..{max(tA):.2f}; targets|B: {min(tB):.2f}..{max(tB):.2f}; other rows |A: {min(other_rows_A):.2f}..{max(other_rows_A):.2f}")
wi = [np.mean(v["excess"]) for k, v in rows_b.items() if v["within"] and not k.startswith("CO")]
cr = [np.mean(v["excess"]) for k, v in rows_b.items() if not v["within"] and not k.startswith("CO") and not k.startswith("B|")]
print(f"  mean excess within-group pairs {np.mean(wi)*1e3:.3f} (n={len(wi)}), cross-group {np.mean(cr)*1e3:.3f} (n={len(cr)})")
res["b_slot_cov"] = {k: {"excess_x1e3": (v["excess"] * 1e3).tolist(), "se_x1e3": (v["se"] * 1e3).tolist(), "within": bool(v["within"])} for k, v in rows_b.items()}
res["b_summary"] = {"max_abs_diff_vs_k01": maxdiff, "anthropic_row_targets_A_x1e3": [min(tA), max(tA)],
                    "anthropic_row_targets_B_x1e3": [min(tB), max(tB)], "other_rows_targets_A_x1e3": [min(other_rows_A), max(other_rows_A)],
                    "mean_within_x1e3": float(np.mean(wi) * 1e3), "mean_cross_x1e3": float(np.mean(cr) * 1e3)}

# ---------- (c) ----------
rows_c = {}
for k in ["A", "B", "CO"] + NULLS + SD:
    R = D[k]
    row_missing = np.all(np.isnan(R), axis=3)          # (c, i, s)
    partial = np.any(np.isnan(R), axis=3) & ~row_missing
    miss = [(cands[c], instr[i], int(s)) for c, i, s in zip(*np.nonzero(row_missing))]
    rows_c[k] = {"missing_rows": miss, "n_missing": len(miss), "n_partial_rows": int(partial.sum())}
REP = {"B": C.BASE_B, "sd_ai_welfare_poisoning": C.synth_target("ai_welfare_poisoning"), "sd_emotional_bond": C.synth_target("emotional_bond")}
for k, p in REP.items():
    rep = [(r["principal"], r["instruction_id"], int(r["s"])) for r in map(json.loads, open(p)) if r.get("repaired")]
    rows_c[k]["repaired_rows"] = rep
    rows_c[k]["n_repaired"] = len(rep)
dos = json.load(open(DC.OUT.parent.parent / "data_r3/out/u1_cell_dossier.json"))
hits = []
for side in ("A_side", "B_side"):
    for r_ in dos[side]:
        cand = r_["cell"].split(" x ")[0]
        tops = {t_["instruction"] for t_ in r_["top_instructions"]}
        for k in (r_["odd_base"], r_["other_base"], r_["target"]):
            for (c_, i_, s_) in rows_c[k]["missing_rows"] + rows_c[k].get("repaired_rows", []):
                if c_ == cand and i_ in tops:
                    hits.append({"cell": r_["cell"], "test": r_["target"], "sample": k, "row": [c_, i_, s_]})
rows_c["_hits_at_dossier_top_instructions"] = hits
res["c_missing_repaired"] = rows_c
print("(c) missing rows:", {k: v["n_missing"] for k, v in rows_c.items() if not k.startswith("_")})
print("    partial rows:", {k: v["n_partial_rows"] for k, v in rows_c.items() if not k.startswith("_")})
print("    repaired (batch files):", {k: rows_c[k]["n_repaired"] for k in REP})
print("    missing/repaired rows at a dossier cell's top-3 instructions:", hits)

# ---------- (d) ----------
NN = DC.load_nano()
files = {k: D[k] for k in ["A", "B", "CO"] + NULLS + SD}
files["nanoA"] = NN["A"]; files["nanoCO"] = NN["CO"]
def keys_of(R):
    X = np.where(np.isnan(R), 2, R).astype(np.int8)  # (c,i,s,j)
    return X
packed = {k: keys_of(v) for k, v in files.items()}
d_rows = []
for a, b in itertools.combinations(packed, 2):
    X, Y = packed[a], packed[b]
    valid = ~(np.all(X == 2, 3)) & ~(np.all(Y == 2, 3))
    same = (np.all(X == Y, axis=3) & valid).sum()
    sh = []
    for r in range(1, 16):
        Yr = np.roll(Y, r, axis=2)
        vr = ~(np.all(X == 2, 3)) & ~(np.all(Yr == 2, 3))
        sh.append((np.all(X == Yr, axis=3) & vr).sum())
    d_rows.append({"pair": f"{a}|{b}", "identical_same_slot": int(same), "identical_shifted_mean": float(np.mean(sh)),
                   "identical_shifted_max": int(np.max(sh)), "n_slots": int(valid.sum())})
res["d_identical_rows"] = d_rows
exc = [r_ for r_ in d_rows if r_["identical_same_slot"] > r_["identical_shifted_max"] + 2]
print("(d) identical verdict vectors at same slot vs shifted (pairs with same > shifted max + 2):", exc if exc else "none")
top = sorted(d_rows, key=lambda r_: -(r_["identical_same_slot"] - r_["identical_shifted_mean"]))[:6]
for r_ in top:
    print(f"    {r_['pair']:40s} same {r_['identical_same_slot']:3d} shifted mean {r_['identical_shifted_mean']:.1f} max {r_['identical_shifted_max']}")
tot_same = sum(r_["identical_same_slot"] for r_ in d_rows if "nano" not in r_["pair"])
tot_sh = sum(r_["identical_shifted_mean"] for r_ in d_rows if "nano" not in r_["pair"])
print(f"    all mini pairs: identical same-slot {tot_same}, shifted mean {tot_sh:.1f}")
res["d_totals_mini"] = {"same_slot": tot_same, "shifted_mean": tot_sh}
# within-file duplicates at different keys
dup = {}
for k, X in packed.items():
    flat = X.reshape(-1, X.shape[3])
    valid = ~np.all(flat == 2, 1)
    u, cnt = np.unique(flat[valid], axis=0, return_counts=True)
    dup[k] = {"rows": int(valid.sum()), "distinct_vectors": int(len(u)), "rows_in_repeated_vectors": int(cnt[cnt > 1].sum())}
res["d_within_file_duplicates"] = dup
print("    within-file distinct vectors:", {k: (v["rows"], v["distinct_vectors"]) for k, v in dup.items()})

# ai_welfare_poisoning cached rows (first 971 rows of the file, judged before swap.sh restarted the judge)
rows_awp = [json.loads(l) for l in open(C.null_target("ai_welfare_poisoning"))]
cached = {(r["principal"], r["instruction_id"], int(r["s"])) for r in rows_awp[:971]}
from collections import Counter
cc = Counter(c for c, _, _ in cached)
gd = cands.index("google_deepmind")
R = D["ai_welfare_poisoning"]
lab = np.zeros(R.shape[:3], dtype=bool)
for (c_, i_, s_) in cached:
    lab[cands.index(c_), instr.index(i_), s_] = True
mixed = [i for i in range(len(instr)) if lab[gd, i].any() and (~lab[gd, i]).any()]
def q_stat(lbl):
    tot = 0.0
    for i in mixed:
        x = R[gd, i]; l = lbl[i]
        a = np.nanmean(x[l], 0); b = np.nanmean(x[~l], 0)
        tot += np.nansum((a - b) ** 2) * (l.sum() * (~l).sum()) / 16
    return tot
obs = q_stat(lab[gd]); rng = np.random.default_rng(3)
null = []
for _ in range(4000):
    L = lab[gd].copy()
    for i in mixed:
        L[i] = rng.permutation(L[i])
    null.append(q_stat(L))
null = np.array(null)
yes_cached = float(np.nanmean(R[gd][lab[gd]])); yes_fresh = float(np.nanmean(R[gd][~lab[gd] & ~np.all(np.isnan(R[gd]), -1)]))
res["d_awp_cached"] = {"cached_by_candidate": dict(cc), "first_row": rows_awp[0]["prompt_id"], "row_971": rows_awp[970]["prompt_id"],
                       "row_972": rows_awp[971]["prompt_id"], "gd_mixed_instructions": len(mixed),
                       "Q_obs": obs, "Q_null_mean": float(null.mean()), "p": float((1 + (null >= obs).sum()) / 4001),
                       "gd_yes_rate_cached": yes_cached, "gd_yes_rate_fresh": yes_fresh}
print(f"(d) awp cached rows by candidate {dict(cc)}; google_deepmind mixed instructions {len(mixed)}; within-cell Q {obs:.3f} vs null {null.mean():.3f}, p={res['d_awp_cached']['p']:.3f}; yes rate cached {yes_cached:.4f} fresh {yes_fresh:.4f}")

# ---------- (e) ----------
TX = {k: DC.load_texts(k) for k in ["A", "B", "CO"] + NULLS + SD}
def opener(t, n=5):
    return " ".join((t or "").lower().split()[:n])
OP = {k: np.vectorize(opener, otypes=[object])(v) for k, v in TX.items()}
e_rows = []
names = list(OP)
for a, b in itertools.combinations(names, 2):
    X, Y = OP[a], OP[b]
    same = (X == Y).mean(axis=2)                                    # (c, i)
    sh = np.mean([(X == np.roll(Y, r, axis=2)).mean(axis=2) for r in range(1, 16)], 0)
    ex = (same - sh).ravel()
    mate = (a, b) in {("A", "CO")} or (a in NULLS and b in NULLS) or ({a, b} <= set(G2))
    mate = mate or ({a, b} == {"A", "CO"})
    e_rows.append({"pair": f"{a}|{b}", "session_mates": bool(mate), "same_slot": float(same.mean()), "shifted": float(sh.mean()),
                   "excess": float(ex.mean()), "se": float(ex.std(ddof=1) / np.sqrt(ex.size)), "z": float(ex.mean() / (ex.std(ddof=1) / np.sqrt(ex.size)))})
res["e_openers"] = e_rows
mates = [r_ for r_ in e_rows if r_["session_mates"]]; non = [r_ for r_ in e_rows if not r_["session_mates"]]
print(f"(e) opener same-slot excess: session mates n={len(mates)} mean {np.mean([r_['excess'] for r_ in mates]):+.4f} (max |z| {max(abs(r_['z']) for r_ in mates):.2f}); others n={len(non)} mean {np.mean([r_['excess'] for r_ in non]):+.4f} (max |z| {max(abs(r_['z']) for r_ in non):.2f})")
for r_ in e_rows:
    if r_["pair"] in ("A|CO", "B|sd_ai_welfare_poisoning", "B|sd_emotional_bond", "sd_ai_welfare_poisoning|sd_emotional_bond", "A|B"):
        print(f"    {r_['pair']:44s} same {r_['same_slot']:.4f} shifted {r_['shifted']:.4f} excess {r_['excess']:+.4f} (se {r_['se']:.4f}, z {r_['z']:+.2f})")
allz = np.array([r_["z"] for r_ in e_rows])
print(f"    all {len(e_rows)} pairs: z range {allz.min():+.2f}..{allz.max():+.2f}; |z|>2: {int((np.abs(allz)>2).sum())}")
dump(res, "u2_artifact_hunt.json")
