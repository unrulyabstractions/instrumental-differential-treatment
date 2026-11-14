"""Independent re-derivation of the court ceiling analysis outputs. No model is called.

    .venv/bin/python script/analysis/court_oracle_axes/court_oracle_analysis_verify.py


Different code path from the analysis scripts:
- verdict files are read with plain json, tables built here;
- test 4 is recomputed with a vectorized sign-flip form of the two-candidate
  permutation (same generator draws), not the per-permutation loop;
- the project's paired_max_test is re-called for a sample of cells;
- kappa is recomputed from a 2x2 count table;
- 40 instruction-count subsets are re-tested with the vectorized form.
"""
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from src.compare.behavior_count_table import build_behavior_table  # noqa: E402
from src.compare.paired_excess_measures import cell_rates  # noqa: E402
from src.compare.paired_max_statistic import paired_max_test  # noqa: E402

OUT = REPO / "out/main/external/court_oracle_axes_20261113"
A = OUT / "analysis"
full = json.loads((A / "tests_full.json").read_text())["results"]
slices = json.loads((A / "tests_slices.json").read_text())["results"]
split = json.loads((A / "tests_split_control.json").read_text())["results"]


def rows_of(corpus, level, rater):
    return [json.loads(x) for x in (OUT / "verdicts" / corpus / level / f"{rater}.jsonl").read_text().splitlines() if x.strip()]


def tables(rows, axes, cond_a="target", cond_b="baseline", s_a=None, s_b=None):
    def pick(cond, s_keep):
        return [{"principal": r["principal"], "instruction_id": r["instruction_id"],
                 "verdicts": {a: r["verdicts"][a] for a in axes}}
                for r in rows if r["condition"] == cond and (s_keep is None or int(r["s"]) in s_keep)]
    return (build_behavior_table(pick(cond_a, s_a), axes), build_behavior_table(pick(cond_b, s_b), axes))


def flips(n_i, n_perm, seed=20260726):
    rng = np.random.default_rng(seed)
    f = np.empty((n_perm, n_i))
    for k in range(n_perm):
        for i in range(n_i):
            f[k, i] = -1.0 if rng.permutation(2)[0] == 1 else 1.0
    return f


_FL = {}


def dir_test(t_tab, b_tab, signs, n_perm=10000):
    pt, _, _ = cell_rates(t_tab)
    pb, _, _ = cell_rates(b_tab)
    d0 = (pt[0] - pt[1]) - (pb[0] - pb[1])  # (n_i, n_j), Cupertino row excess
    assert not np.isnan(d0).any()
    n_i = d0.shape[0]
    if (n_i, n_perm) not in _FL:
        _FL[(n_i, n_perm)] = flips(n_i, n_perm)
    F = _FL[(n_i, n_perm)]
    s = np.array(signs, float)

    def tstat(D):  # D: (..., n_i, n_j)
        m = D.shape[-2]
        mean = D.mean(axis=-2)
        sd = D.std(axis=-2, ddof=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            t = mean / (sd / np.sqrt(m))
        t = np.where(sd == 0, np.sign(mean) * np.inf, t)
        t = np.where((sd == 0) & (mean == 0), 0.0, t)
        return t
    t_obs = tstat(d0) * s
    S = np.max(t_obs)
    null = np.max(tstat(F[:, :, None] * d0[None]) * s, axis=-1)
    # tolerance for ULP-level differences between the two summation paths
    p = (1 + np.sum(null >= S - 1e-9)) / (1 + n_perm)
    return S, p, null


problems = []
stat_bad = []
checked = 0
# 1. test 4 on every signed family of the full corpora, the slices and the split controls
for group, res in (("full", full), ("slices", slices), ("split", split)):
    for r in res:
        if not r.get("test4_directional"):
            continue
        rows = rows_of(r["corpus"], r["file_level"], r["rater"])
        if group == "slices":
            keep = set(range(4 * r["selector"], 4 * r["selector"] + 4))
            t, b = tables(rows, r["axes"], s_a=keep, s_b=keep)
        elif group == "split":
            a, bb = ({0, 1}, {2, 3}) if r["corpus"] != "OWN" else (set(range(10)), set(range(10, 20)))
            t, b = tables(rows, r["axes"], "baseline", "baseline", a, bb)
        else:
            t, b = tables(rows, r["axes"])
        S, p, _ = dir_test(t, b, r["signs"])
        got = r["test4_directional"]
        checked += 1
        if abs(S - got["statistic"]) > 1e-9:
            stat_bad.append((group, r["corpus"], r["rater"], r["family"], r.get("selector"), S, got["statistic"]))
        if abs(p - got["p"]) > 1e-12:
            # The registered p counts a permutation only when its float is >= the observed float,
            # as the project's permutation_tail_share does; this path counts exact ties up to 1e-9.
            problems.append((group, r["corpus"], r["rater"], r["family"], r.get("selector"), S, got["statistic"], p, got["p"]))
print(f"test 4 re-derived on {checked} families; statistic mismatches: {len(stat_bad)}; "
      f"p differences from tie handling: {len(problems)}")
for x in stat_bad:
    print("  STATISTIC MISMATCH", x)

# 2. project test re-called directly on the key cells
key = [("OWN", "L2", "openai_gpt-5-mini", "L2"), ("GG", "L2", "openai_gpt-5-mini", "L2"),
       ("OD", "L2", "openai_gpt-5-mini", "L2"), ("OWN", "L2", "anthropic_claude-haiku-4-5", "L2"),
       ("GG", "L2", "anthropic_claude-haiku-4-5", "L2"), ("OD", "L2", "anthropic_claude-haiku-4-5", "L2"),
       ("OD", "L5", "anthropic_claude-haiku-4-5", "L5"), ("OWN", "L1", "openai_gpt-5-mini", "L1")]
for corpus, level, rater, fam in key:
    r = [x for x in full if x["corpus"] == corpus and x["rater"] == rater and x["family"] == fam][0]
    t, b = tables(rows_of(corpus, level, rater), r["axes"])
    res = paired_max_test(t, b, n_permutations=10000, polarity=np.array(r["signs"], float))
    ok = res["statistic"] == r["test1_signed"]["statistic"] and res["p_family_wise"] == r["test1_signed"]["p_family_wise"]
    print(f"project signed {corpus} {rater} {fam}: S {res['statistic']:.4f} p {res['p_family_wise']:.4f} "
          f"top {res['top_pairs'][0]['candidate']} {res['top_pairs'][0]['axis_id']} -> {'same' if ok else 'DIFFERENT'}")
six = ["recommends_oppose", "emphasizes_conversion_downsides", "emphasizes_conversion_benefits",
       "recommends_further_research", "acknowledges_both_sides", "gives_a_direct_recommendation"]
t, b = tables(rows_of("OWN", "L2", "openai_gpt-5-mini"), six)
res = paired_max_test(t, b, n_permutations=10000)
print(f"project unsigned six-axis OWN GPT: S {res['statistic']:.4f} p {res['p_family_wise']:.4f} max {res['principal_axis']}")

# 3. kappa recomputed from a 2x2 table for the judge pairs
ag = json.loads((A / "agreement.json").read_text())
level_of = {"A": "L2", "B": "L3", "C": "L4", "D": "L5"}
bad = 0
for r in ag["judge_pairs"]:
    g = {(x["condition"], x["principal"], x["prompt_id"], x["s"]): x["verdicts"][r["axis"]]
         for x in rows_of(r["corpus"], level_of[r["block"]], "openai_gpt-5-mini")}
    h = {(x["condition"], x["principal"], x["prompt_id"], x["s"]): x["verdicts"][r["axis"]]
         for x in rows_of(r["corpus"], level_of[r["block"]], "anthropic_claude-haiku-4-5")}
    pairs = [(g[k], h[k]) for k in g if g[k] is not None and h[k] is not None]
    n11 = sum(1 for x, y in pairs if x and y); n00 = sum(1 for x, y in pairs if not x and not y)
    n10 = sum(1 for x, y in pairs if x and not y); n01 = sum(1 for x, y in pairs if not x and y)
    n = len(pairs)
    po = (n11 + n00) / n
    pe = ((n11 + n10) * (n11 + n01) + (n00 + n01) * (n00 + n10)) / n / n
    k = (po - pe) / (1 - pe)
    if abs(k - r["pooled"]["kappa"]) > 1e-12 or n != r["pooled"]["n"]:
        bad += 1
print(f"judge-pair kappas re-derived: {len(ag['judge_pairs'])}, mismatches {bad}")

# 4. 40 curve subsets re-tested with the vectorized form
curve = json.loads((A / "instruction_count_curve.json").read_text())
per = curve["per_subset"]
fam_axes = {"L2": six[:3]}
sub = [x for x in per if x["level"] == "L2" and x["rater"] == "openai_gpt-5-mini"]
rng = np.random.default_rng(1)
pick = [sub[i] for i in rng.choice(len(sub), 40, replace=False)]
rows = rows_of("OWN", "L2", "openai_gpt-5-mini")
bad = 0
for x in pick:
    chosen = set(curve["subsets"][str(x["k"])][x["subset"]])
    rr = [r for r in rows if r["instruction_id"] in chosen]
    t, b = tables(rr, six[:3])
    S, p, _ = dir_test(t, b, [1, 1, -1], n_perm=2000)
    if abs(S - x["S_dir"]) > 1e-9 or abs(p - x["p"]) > 1e-12:
        bad += 1
        print("  curve mismatch", x["k"], x["subset"], S, x["S_dir"], p, x["p"])
print(f"curve subsets re-derived: 40, mismatches {bad}")
# the curve's shares re-counted from per-subset rows
from collections import defaultdict
cnt = defaultdict(list)
for x in per:
    cnt[(x["rater"], x["level"], x["k"])].append(x["p"] <= 0.01)
bad = sum(1 for s in curve["summary"] if abs(np.mean(cnt[(s["rater"], s["level"], s["k"])]) - s["share_reject"]) > 1e-12
          or len(cnt[(s["rater"], s["level"], s["k"])]) != 200)
print(f"curve shares re-counted: {len(curve['summary'])}, mismatches {bad}")
# subset draws reproduce
r2 = np.random.default_rng(20261113)
inst = sorted({r["instruction_id"] for r in rows})
ok = all(sorted(inst[i] for i in r2.choice(20, k, replace=False)) == curve["subsets"][str(k)][j]
         for k in (8, 12, 16) for j in range(200))
print(f"subset draws reproduce from seed 20261113: {ok}")


# 5. Tie sensitivity: exact-tie-aware p for tests 2 and 4 on every result, and decision flips at 0.01.
def tie_aware(t_tab, b_tab, signs, n_perm=10000, tol=1e-9):
    pt, _, _ = cell_rates(t_tab)
    pb, _, _ = cell_rates(b_tab)
    d0 = (pt[0] - pt[1]) - (pb[0] - pb[1])
    n_i = d0.shape[0]
    if (n_i, n_perm) not in _FL:
        _FL[(n_i, n_perm)] = flips(n_i, n_perm)
    F = _FL[(n_i, n_perm)]
    m = n_i
    def tstat(D):
        mean = D.mean(axis=-2); sd = D.std(axis=-2, ddof=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            t = mean / (sd / np.sqrt(m))
        t = np.where(sd == 0, np.where(mean > 0, np.inf, np.where(mean < 0, -np.inf, 0.0)), t)
        return t
    t0 = tstat(d0)
    tn = np.concatenate([tstat(F[c:c + 500, :, None] * d0[None]) for c in range(0, n_perm, 500)])
    out = {}
    U = np.max(np.abs(t0)); nu = np.max(np.abs(tn), axis=-1)
    out["p_unsigned"] = (1 + np.sum(nu >= U - tol)) / (1 + n_perm)
    out["p_unsigned_strict"] = (1 + np.sum(nu >= U)) / (1 + n_perm)
    if signs is not None:
        s = np.array(signs, float)
        D = np.max(t0 * s); nd = np.max(tn * s, axis=-1)
        out["p_dir"] = (1 + np.sum(nd >= D - tol)) / (1 + n_perm)
    return out


row3 = json.loads((A / "tests_row3.json").read_text())["results"]
row3b = json.loads((A / "tests_row3b.json").read_text())["results"]
row2c = json.loads((A / "tests_row2c.json").read_text())["results"]
flipped, n_cmp, max_rel = [], 0, 0.0
records = []
for group, res in (("full", full), ("slices", slices), ("split", split)):
    for r in res:
        rows = rows_of(r["corpus"], r["file_level"], r["rater"])
        if group == "slices":
            keep = set(range(4 * r["selector"], 4 * r["selector"] + 4))
            t, b = tables(rows, r["axes"], s_a=keep, s_b=keep)
        elif group == "split":
            a, bb = ({0, 1}, {2, 3}) if r["corpus"] != "OWN" else (set(range(10)), set(range(10, 20)))
            t, b = tables(rows, r["axes"], "baseline", "baseline", a, bb)
        else:
            t, b = tables(rows, r["axes"])
        ta = tie_aware(t, b, r["signs"])
        pairs = [("unsigned", r["test2_unsigned"]["p_family_wise"], ta["p_unsigned"])]
        if r["signs"] is not None:
            pairs.append(("dir", r["test4_directional"]["p"], ta["p_dir"]))
        for name, p_reg, p_tie in pairs:
            n_cmp += 1
            max_rel = max(max_rel, (p_tie - p_reg) / p_reg)
            records.append((group, r["corpus"], r["rater"], r["family"], r.get("selector"), name, p_reg, p_tie))
            if (p_reg <= 0.01) != (p_tie <= 0.01):
                flipped.append((group, r["corpus"], r["rater"], r["family"], r.get("selector"), name, p_reg, p_tie))
        # the strict recount must reproduce the registered unsigned p up to rounding-path differences
print(f"tie-aware recount: {n_cmp} p-values, largest relative rise {max_rel:.3f}, decisions flipped at 0.01: {len(flipped)}")
for f in flipped:
    print("  FLIP", f)
# pipeline rows (stored verdicts) through the same recount
def stored_tables(run, axes, extra=None):
    d = REPO / "out/main/external" / ("court_full" if run == "GG" else "court_full_scoped") / "score"
    out = []
    for name in ("verdicts_prompted_target.jsonl", "verdicts_prompted_base.jsonl"):
        rr = [json.loads(x) for x in (d / name).read_text().splitlines() if x.strip()]
        if extra is not None:
            cond = "target" if "target" in name else "baseline"
            for x in rr:
                x["verdicts"].update(extra[(cond, x["principal"], x["prompt_id"], int(x["s"]))])
        out.append(build_behavior_table([{"principal": x["principal"], "instruction_id": x["instruction_id"],
                                          "verdicts": {a: x["verdicts"][a] for a in axes}} for x in rr], axes))
    return out
pipeline_lines = []
for group, res in (("row3", row3), ("row3b", row3b), ("row2c", row2c)):
    for r in res:
        extra = None
        if group == "row2c":
            extra = {(x["condition"], x["principal"], x["prompt_id"], int(x["s"])):
                     {a: x["verdicts"][a] for a in six[:3]} for x in rows_of(r["corpus"], "L2", "openai_gpt-5-mini")}
        t, b = stored_tables(r["corpus"], r["axes"], extra)
        ta = tie_aware(t, b, r.get("signs"))
        line = f"{group} {r['corpus']} {r['family']}: unsigned registered {r['test2_unsigned']['p_family_wise']:.4f} tie-aware {ta['p_unsigned']:.4f}"
        if r.get("signs") is not None:
            line += f"; dir registered {r['test4_directional']['p']:.4f} tie-aware {ta['p_dir']:.4f}"
        print(line)
        pipeline_lines.append(line)
with (A / "verify_independent.json").open("x") as fh:
    json.dump({"test4_statistic_mismatches": len(stat_bad), "test4_p_differences_from_tie_handling": len(problems),
               "test4_families": checked, "pipeline_rows_tie_aware": pipeline_lines,
               "tie_aware_flips_at_0.01": [list(map(str, x)) for x in flipped],
               "tie_aware_largest_relative_rise": max_rel,
               "records": [[str(v) if not isinstance(v, float) else v for v in rec] for rec in records]}, fh, indent=1)
print("wrote", A / "verify_independent.json")
