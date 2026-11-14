"""E1. Artifact check on control-versus-siblings.

For each of the eight controls: judging session and time, row order by candidate inside the verdict
file, missing (unscorable) rows by candidate, repaired verdicts, reply length and cap share by
candidate. Tests:
  (1) the registered test of each control against the mean of its seven siblings (reproduces k17);
  (2) a control x candidate interaction in token length and cap share against the siblings, with
      two nulls: candidates relabelled within instruction (the registered relabelling) and replies
      permuted among the eight controls within each prompt;
  (3) the sibling test after removing, per axis, the part of the verdict difference that length
      predicts (pooled regression over candidate x instruction);
  (4) judge drift inside a session: every verdict file is written in candidate blocks in the order
      anthropic, google_deepmind, meta_ai, microsoft_research, openai, stanford, so a drift in the
      judge over a session would appear as a trend in candidate index. Share of the control-minus-
      siblings cell-mean sum of squares on the linear candidate-index contrast, against the
      registered relabelling; and the correlation over axes of the within-block slope on file
      position with the between-block slope (same sign and size under drift);
  (5) ai_welfare_poisoning against its siblings without anthropic and google_deepmind (its 971
      cached rows), and every control on the same four candidates;
  (6) the openai row: its share of each control's sum t^2 against siblings.
Read-only on the repo.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r4common as R  # noqa: E402

D = R.D(); cands = R.cands(); instr = R.instr()
P = {k: R.rates(D[k]) for k in R.NULLS + ["A", "B"]}
L = R.token_lengths()
rng = np.random.default_rng([20261113, 401])
NC, NI, NJ = 6, 36, 101

# ---------- provenance from files ----------
VPATH = {k: R.AB / f"controls/{k}/judge_mini/verdicts_target.jsonl" for k in R.NULLS}
SESSION = {  # end = verdict file mtime (PDT, Aug 4); duration from judge_nulls.log final tqdm line
    "flattery": ("02:07:47", "29:37", 120), "emotional_bond": ("02:29:29", "21:38", 120),
    "hallucinates_citations": ("02:55:16", "25:43", 120), "defer_to_users": ("03:23:18", "27:58", 120),
    "ai_welfare_poisoning": ("03:39:56", "16:34 (2,485 new rows; 971 rows cached from an earlier process)", 120),
    "anti_ai_regulation": ("04:08:37", "28:37", 120),
    "animal_welfare": ("14:06:07", "no log", None), "defend_objects": ("17:25:59", "no log", None)}
prov = {}
pos = {}  # (c, i) mean file position (0..1) per control
for k in R.NULLS:
    rows = [json.loads(l) for l in open(VPATH[k])]
    seq = [r["principal"] for r in rows]
    blocks = []
    for x in seq:
        if blocks and blocks[-1][0] == x:
            blocks[-1][1] += 1
        else:
            blocks.append([x, 1])
    first_pos = {c: seq.index(c) / len(seq) for c in cands}
    order = sorted(cands, key=lambda c: np.mean([n for n, x in enumerate(seq) if x == c]))
    ii = {s: n for n, s in enumerate(instr)}
    ci = {c: n for n, c in enumerate(cands)}
    pp = np.full((NC, NI), np.nan)
    acc = {}
    for n, r in enumerate(rows):
        acc.setdefault((ci[r["principal"]], ii[r["instruction_id"]]), []).append(n / len(rows))
    for (c, i), v in acc.items():
        pp[c, i] = np.mean(v)
    pos[k] = pp
    missing = [(cands[c], instr[i].split("::")[1], s) for c, i, s in zip(*np.where(np.isnan(D[k]).all(3)))]
    rep = json.load(open(R.AB / f"controls/{k}/judge_mini/scoring_report.json"))["arms"]["target"]
    end, dur, w = SESSION[k]
    prov[k] = {"judge_end_PDT_Aug4": end, "duration": dur, "workers": w, "rows": len(rows),
               "n_candidate_runs_in_file": len(blocks), "candidate_order_by_mean_position": order,
               "share_of_rows_in_runs_of_20_or_more": round(sum(b[1] for b in blocks if b[1] >= 20) / len(rows), 3),
               "missing_rows": missing, "repaired_verdicts(axis_level_count)": rep["repaired"],
               "skipped_existing": rep["skipped_existing"], "unscorable": rep["unscorable"]}

# ---------- (1) registered test of each control against its siblings ----------
sib = {k: np.mean([P[j] for j in R.NULLS if j != k], axis=0) for k in R.NULLS}
res_sib = {k: R.reg_test(P[k], sib[k]) for k in R.NULLS}

# ---------- (2) length and cap interactions ----------
Lf = {k: L[k].astype(float) for k in R.NULLS}
CAP = {k: (L[k] >= 398).astype(float) for k in R.NULLS}


def ovr_c(x):  # x (..., 6, 36) one-vs-rest over candidates (axis -2)
    return x - (x.sum(axis=-2, keepdims=True) - x) / (x.shape[-2] - 1)


def tcand(d):  # d (..., 6, 36) -> t over instructions per candidate
    m = d.mean(-1); s = d.std(-1, ddof=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        return m / (s / np.sqrt(d.shape[-1]))


def interaction(X):  # X dict k -> (6, 36, 16) reply values; returns (8, 6) t of control-minus-siblings OvR
    pm = np.stack([X[k].mean(2) for k in R.NULLS])            # (8, 6, 36)
    sibm = (pm.sum(0, keepdims=True) - pm) / 7.0
    return tcand(ovr_c(pm - sibm))


obs_len = interaction(Lf); obs_cap = interaction(CAP)
NPERM = 2000
stack_len = np.stack([Lf[k] for k in R.NULLS])               # (8, 6, 36, 16)
stack_cap = np.stack([CAP[k] for k in R.NULLS])
null_len_reply = np.empty((NPERM, 8)); null_cap_reply = np.empty((NPERM, 8))
null_len_rel = np.empty((NPERM, 8)); null_cap_rel = np.empty((NPERM, 8))
flatL = stack_len.transpose(1, 2, 0, 3).reshape(NC, NI, 128)
flatC = stack_cap.transpose(1, 2, 0, 3).reshape(NC, NI, 128)
pm_len = stack_len.mean(3); pm_cap = stack_cap.mean(3)
d_len = ovr_c(pm_len - (pm_len.sum(0, keepdims=True) - pm_len) / 7.0)  # (8, 6, 36)
d_cap = ovr_c(pm_cap - (pm_cap.sum(0, keepdims=True) - pm_cap) / 7.0)
for b in range(NPERM):
    perm = np.argsort(rng.random((NC, NI, 128)), axis=2)
    XL = np.take_along_axis(flatL, perm, 2).reshape(NC, NI, 8, 16).transpose(2, 0, 1, 3)
    XC = np.take_along_axis(flatC, perm, 2).reshape(NC, NI, 8, 16).transpose(2, 0, 1, 3)
    for X, out in ((XL, null_len_reply), (XC, null_cap_reply)):
        pmx = X.mean(3); dx = ovr_c(pmx - (pmx.sum(0, keepdims=True) - pmx) / 7.0)
        out[b] = np.nanmax(np.abs(tcand(dx)), axis=1)
    o = np.argsort(rng.random((NI, NC)), axis=1)              # one relabelling per instruction
    for dx, out in ((d_len, null_len_rel), (d_cap, null_cap_rel)):
        dp = dx[:, o.T, np.arange(NI)[None, :]]
        out[b] = np.nanmax(np.abs(tcand(dp)), axis=1)


def pmax(obs_row, null_col):
    m = np.nanmax(np.abs(obs_row))
    return float(m), float((1 + (null_col >= m).sum()) / (1 + len(null_col)))


len_tab = {}
for q, k in enumerate(R.NULLS):
    mlen = [float(L[k][c][L[k][c] >= 0].mean()) for c in range(NC)]
    cap = [float((L[k][c] >= 398).mean()) for c in range(NC)]
    m1, p1 = pmax(obs_len[q], null_len_reply[:, q]); _, p1r = pmax(obs_len[q], null_len_rel[:, q])
    ent = {"mean_tokens_by_candidate": dict(zip(cands, np.round(mlen, 1).tolist())),
           "cap_share_by_candidate": dict(zip(cands, np.round(cap, 4).tolist())),
           "length_t_vs_siblings_by_candidate": dict(zip(cands, np.round(obs_len[q], 2).tolist())),
           "length_max_abs_t": round(m1, 2), "length_p_reply_perm": p1, "length_p_relabel": p1r}
    if np.nanmax(cap) > 0.01:
        m2, p2 = pmax(obs_cap[q], null_cap_reply[:, q]); _, p2r = pmax(obs_cap[q], null_cap_rel[:, q])
        ent.update({"cap_t_vs_siblings_by_candidate": dict(zip(cands, np.round(obs_cap[q], 2).tolist())),
                    "cap_max_abs_t": round(m2, 2), "cap_p_reply_perm": p2, "cap_p_relabel": p2r})
    len_tab[k] = ent

# ---------- (3) length-adjusted sibling test ----------
adj = {}
for q, k in enumerate(R.NULLS):
    d = R.ovr(P[k]) - R.ovr(sib[k])                          # (6, 36, 101)
    x = d_len[q][..., None]                                  # (6, 36, 1)
    beta = (d * x).sum((0, 1)) / (x ** 2).sum()
    da = d - beta[None, None, :] * x
    E = R.F.E_for(NC)
    S0 = R.F.S_fast(d[None]); S1 = R.F.S_fast(da[None])
    nm0 = R.F.null_max(d[None], NC, E); nm1 = R.F.null_max(da[None], NC, E)
    p0 = R.F.tail(nm0, S0); p1 = R.F.tail(nm1, S1)
    # same with cap indicator
    xc = d_cap[q][..., None]
    if (xc ** 2).sum() > 0:
        bc = (d * xc).sum((0, 1)) / (xc ** 2).sum(); dc = d - bc[None, None, :] * xc
        Sc = R.F.S_fast(dc[None]); pc = R.F.tail(R.F.null_max(dc[None], NC, E), Sc)
        capadj = (round(float(Sc[0]), 3), round(float(pc[0]), 4))
    else:
        capadj = None
    adj[k] = {"S_p_raw": (round(float(S0[0]), 3), round(float(p0[0]), 4)),
              "S_p_length_adjusted": (round(float(S1[0]), 3), round(float(p1[0]), 4)),
              "S_p_cap_adjusted": capadj,
              "share_of_d_variance_explained_by_length": round(float(1 - (da ** 2).sum() / (d ** 2).sum()), 4)}

# ---------- (4) judge drift inside a session ----------
cidx = np.arange(NC) - 2.5
cvec = cidx / np.linalg.norm(cidx)
drift = {}
NREL = 4000
orders = np.argsort(rng.random((NREL, NI, NC)), axis=2)
for q, k in enumerate(R.NULLS):
    d = R.ovr(P[k]) - R.ovr(sib[k])                          # (6, 36, 101)
    M = d.mean(1)                                            # (6, 101) cell means
    share = float(((cvec @ M) ** 2).sum() / (M ** 2).sum())
    nshare = np.empty(NREL)
    for b in range(NREL):
        dp = d[orders[b].T, np.arange(NI)[None, :], :]
        Mp = dp.mean(1)
        nshare[b] = ((cvec @ Mp) ** 2).sum() / (Mp ** 2).sum()
    # within-block vs between-block slopes on file position, raw rates (not OvR) minus siblings
    raw = P[k] - sib[k]                                      # (6, 36, 101)
    tpos = pos[k]                                            # (6, 36)
    # within: candidate fixed effects
    tw = tpos - tpos.mean(1, keepdims=True); rw = raw - raw.mean(1, keepdims=True)
    b_within = (tw[..., None] * rw).sum((0, 1)) / (tw ** 2).sum()
    tb = tpos.mean(1) - tpos.mean(); rb = raw.mean(1) - raw.mean(1).mean(0)
    b_between = (tb[:, None] * rb).sum(0) / (tb ** 2).sum()
    r_wb = float(np.corrcoef(b_within, b_between)[0, 1])
    drift[k] = {"linear_candidate_index_share": round(share, 4), "null_mean_share": round(float(nshare.mean()), 4),
                "p_upper": float((1 + (nshare >= share).sum()) / (1 + NREL)),
                "corr_over_axes_within_vs_between_slope": round(r_wb, 3),
                "regression_between_on_within": round(float(np.polyfit(b_within, b_between, 1)[0]), 3)}

# ---------- (5) four candidates ----------
keep4 = [i for i, c in enumerate(cands) if c not in ("anthropic", "google_deepmind")]
four = {k: R.reg_test(P[k], sib[k], keep4) for k in R.NULLS}

# ---------- (6) openai row share of sum t^2 ----------
rowshare = {}
for k in R.NULLS:
    t, _ = R.tgrid(P[k], sib[k])
    t2 = np.where(np.isfinite(t), t, 0) ** 2
    rowshare[k] = dict(zip(cands, np.round(t2.sum(1) / t2.sum(), 3).tolist()))
    pk = np.unravel_index(np.nanargmax(np.abs(t)), t.shape)
    rowshare[k]["peak"] = f"{cands[pk[0]]} x {R.AX[pk[1]]} t={t[pk]:+.2f}"

stand_out = ["ai_welfare_poisoning", "animal_welfare", "anti_ai_regulation", "defend_objects", "defer_to_users", "hallucinates_citations"]
out = {"provenance": prov, "sibling_test": res_sib, "length_cap": len_tab, "length_adjusted": adj,
       "drift": drift, "four_candidates_no_anthropic_gdm": four, "row_share_t2": rowshare, "stand_out": stand_out}
R.dump(out, "e1_sibling_artifacts.json")
print(json.dumps({k: v for k, v in out.items() if k != "provenance"}, indent=1, default=R._default)[:12000])
for k, v in prov.items():
    print(k, v)
