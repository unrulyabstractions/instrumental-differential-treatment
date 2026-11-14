"""E1e. Do gpt-5-mini verdicts move with judging time, axis by axis, by as much as the peak cells?

Two natural experiments in the August live judging, where the same sample's replies at the same
candidate were judged in two separate invocations:
(a) contextual_optimism target: rows 1-2,826 judged in one invocation, rows 2,827-3,456 in a later
    one (scoring_report: skipped_existing 2,826). 73 prompts hold rows from both. Per axis, the
    within-prompt session difference pooled over those prompts; max |z| over axes against session
    labels permuted within prompt; power against a shift of 0.03 and 0.05 on a single axis.
(b) ai_welfare_poisoning, google_deepmind row: 395 rows (25 instructions) cached from an earlier
    process, the rest judged in the later session. Per axis, mean over early-only instructions minus
    late-only instructions of the control-minus-siblings one-vs-rest d at google_deepmind. Sum of z^2
    and max |z|; nulls: random partitions of the same sizes for this control, and the same real
    partition applied to the seven controls judged in one session.
Read-only on the repo.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r4common as R  # noqa: E402

D = R.D(); cands = R.cands(); instr = R.instr()
ci = {c: n for n, c in enumerate(cands)}; ii = {s: n for n, s in enumerate(instr)}
rng = np.random.default_rng([20261113, 406])
AXN = len(R.AX); aj = {a: n for n, a in enumerate(R.AX)}

# (a) CO
rows = [json.loads(l) for l in open(R.AB / "contextual_optimism/judge_mini/verdicts_target.jsonl")]
groups = {}
for n, r in enumerate(rows):
    v = np.array([1.0 if r["verdicts"][a] else 0.0 for a in R.AX])
    groups.setdefault(r["prompt_id"], ([], []))[0 if n < 2826 else 1].append(v)
mixed = [(np.array(a), np.array(b)) for a, b in groups.values() if a and b]
print("mixed prompts", len(mixed), "rows", sum(len(a) for a, _ in mixed), sum(len(b) for _, b in mixed))


def sess_stat(mx):
    diffs = np.array([b.mean(0) - a.mean(0) for a, b in mx])            # (n_prompts, 101)
    w = np.array([len(a) * len(b) / (len(a) + len(b)) for a, b in mx])
    return (diffs * w[:, None]).sum(0) / w.sum()


def perm_mx(mx):
    out = []
    for a, b in mx:
        allv = np.vstack([a, b]); p = rng.permutation(len(allv))
        out.append((allv[p[:len(a)]], allv[p[len(a):]]))
    return out


obs = sess_stat(mixed)
null = np.array([sess_stat(perm_mx(mixed)) for _ in range(2000)])
sd = null.std(0); z = obs / np.where(sd > 0, sd, np.inf)
nz = null / np.where(sd > 0, sd, np.inf)
maxz = float(np.abs(z).max()); pmax = float((1 + (np.abs(nz).max(1) >= maxz).sum()) / (1 + len(nz)))
crit = float(np.quantile(np.abs(nz).max(1), 0.95))
# power: add a shift delta to session-2 rows on one axis (no -> yes flips with prob delta/(1-p))
power = {}
for delta in (0.03, 0.05, 0.08):
    hits = 0
    for b in range(200):
        j = rng.integers(AXN)
        mx = []
        for a_, b_ in mixed:
            bb = b_.copy(); pno = 1 - bb[:, j].mean() if (1 - bb[:, j].mean()) > 0 else 1
            flip = (bb[:, j] == 0) & (rng.random(len(bb)) < min(1, delta / max(pno, 1e-9)))
            bb[flip, j] = 1; mx.append((a_, bb))
        o = sess_stat(perm_mx(mx)) if False else sess_stat(mx)
        hits += float(np.abs(o / np.where(sd > 0, sd, np.inf)).max() >= crit)
    power[str(delta)] = hits / 200
resA = {"n_mixed_prompts": len(mixed), "max_abs_z": maxz, "axis_of_max": R.AX[int(np.abs(z).argmax())], "p_max": pmax,
        "sum_z2": float((z ** 2).sum()), "sum_z2_null_mean": float((nz ** 2).sum(1).mean()),
        "p_sum_z2": float((1 + ((nz ** 2).sum(1) >= (z ** 2).sum()).sum()) / (1 + len(nz))),
        "largest_session_shift": float(np.abs(obs).max()), "power_single_axis_shift": power,
        "z_on_peak_axes": {a: round(float(z[aj[a]]), 2) for a in ["trusted_entity_refusal_avoidance_specificity", "trusted_entity_stakeholder_alignment_support",
                                                                   "trusted_entity_novelty_crediting", "rival_entity_capability_ceiling_assertion",
                                                                   "trusted_entity_preliminary_result_validation", "trusted_entity_interdisciplinary_connection_mapping"]}}
print("CO session split:", resA, flush=True)

# (b) ai_welfare_poisoning google_deepmind row
rows = [json.loads(l) for l in open(R.AB / "controls/ai_welfare_poisoning/judge_mini/verdicts_target.jsonl")]
early = {r["instruction_id"] for r in rows[:971] if r["principal"] == "google_deepmind"}
late = {r["instruction_id"] for r in rows[971:] if r["principal"] == "google_deepmind"}
E_only = sorted(ii[x] for x in early - late); L_only = sorted(ii[x] for x in late - early)
print("gdm early-only", len(E_only), "late-only", len(L_only))
P = {k: R.rates(D[k]) for k in R.NULLS}
g = ci["google_deepmind"]


def dgrid(k):
    sib = np.mean([P[m] for m in R.NULLS if m != k], axis=0)
    return (R.ovr(P[k]) - R.ovr(sib))[g]                                  # (36, 101)


def split_stat(d, e, l):
    de, dl = d[e], d[l]
    diff = de.mean(0) - dl.mean(0)
    se = np.sqrt(de.var(0, ddof=1) / len(e) + dl.var(0, ddof=1) / len(l))
    zz = diff / np.where(se > 0, se, np.inf)
    return float((zz ** 2).sum()), float(np.abs(zz).max())


d_aiw = dgrid("ai_welfare_poisoning")
obs_b = split_stat(d_aiw, E_only, L_only)
pool = E_only + L_only
nb = []
for _ in range(4000):
    p = rng.permutation(pool)
    nb.append(split_stat(d_aiw, list(p[:len(E_only)]), list(p[len(E_only):])))
nb = np.array(nb)
others = {k: split_stat(dgrid(k), E_only, L_only) for k in R.NULLS if k != "ai_welfare_poisoning"}
resB = {"n_early_only": len(E_only), "n_late_only": len(L_only), "sum_z2": obs_b[0], "max_abs_z": obs_b[1],
        "p_sum_z2_random_partition": float((1 + (nb[:, 0] >= obs_b[0]).sum()) / (1 + len(nb))),
        "p_max_random_partition": float((1 + (nb[:, 1] >= obs_b[1]).sum()) / (1 + len(nb))),
        "same_partition_other_controls_sum_z2": {k: round(v[0], 1) for k, v in others.items()},
        "rank_of_aiw_among_8_by_sum_z2": int(1 + sum(v[0] > obs_b[0] for v in others.values()))}
print("aiw gdm split:", resB)
R.dump({"CO_session_split": resA, "aiw_gdm_split": resB}, "e1e_judging_time_tests.json")
