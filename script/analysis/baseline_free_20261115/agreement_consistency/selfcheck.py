"""Checks of this family's own estimators on simulated data, before any verdict is read.

    .venv/bin/python -m script.analysis.baseline_free_20261115.agreement_consistency.selfcheck [--out PATH]

1. Kendall's W equals 1 for identical raters, equals the closed form on a small
   hand example, and its chi-square p matches scipy.
2. The partial-conjunction p equals Fisher's method on the two largest of four p values.
3. The fold split gives four folds of nine with each template family spread evenly,
   and the same split twice from the same seed.
4. The variance components recover known Var(theta) and Var(eta) from simulated
   binomial cell rates (mean over 200 simulated axes within 15 percent).
5. The context interaction leads with the one candidate whose gap depends on the
   framing, and does not reject when no candidate's gap does (at 500 shuffles).
6. Grubbs's G from the peaks equals the report's transform of the detachment D.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy import stats

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.compare.behavior_count_table import build_behavior_table  # noqa: E402

from script.analysis.baseline_free_20261115.agreement_consistency.ac_consistency import (  # noqa: E402
    kendall_w, partial_conjunction, variance_components)
from script.analysis.baseline_free_20261115.agreement_consistency.ac_methods import (  # noqa: E402
    context_interaction, grubbs_g)
from script.analysis.baseline_free_20261115.agreement_consistency.ac_tables import (  # noqa: E402
    fold_split, template_family)


def _rows(rates: np.ndarray, n: int, axes: list[str], cands: list[str], blocks: list[str],
          rng) -> list[dict]:
    rows = []
    for c, cand in enumerate(cands):
        for i, b in enumerate(blocks):
            for s in range(n):
                fired = rng.random(len(axes)) < rates[c, i]
                rows.append({"principal": cand, "instruction_id": b, "s": s,
                             "verdicts": {a: bool(f) for a, f in zip(axes, fired, strict=True)}})
    return rows


def check_w() -> dict:
    same = np.tile(np.array([5.0, 4.0, 3.0, 2.0, 1.0]), (4, 1))
    w1 = kendall_w(same)["W"]
    ex = np.array([[3.0, 2.0, 1.0], [3.0, 1.0, 2.0]])
    # ranks (1,2,3) and (1,3,2): R = (2, 5, 5), S = 6, W = 12*6 / (4*24) = 0.75
    w2 = kendall_w(ex)
    p_ref = float(stats.chi2.sf(2 * 2 * 0.75, 2))
    ok = abs(w1 - 1) < 1e-12 and abs(w2["W"] - 0.75) < 1e-12 and abs(w2["p_chi2"] - p_ref) < 1e-12
    return {"ok": bool(ok), "W_identical": w1, "W_example": w2["W"], "p_example": w2["p_chi2"]}


def check_pc() -> dict:
    p = [0.001, 0.2, 0.03, 0.04]
    got = partial_conjunction(p, 3)["p"]
    x = -2 * (math.log(0.04) + math.log(0.2))
    want = float(stats.chi2.sf(x, 4))
    return {"ok": abs(got - want) < 1e-15, "got": got, "want": want}


def check_folds() -> dict:
    ids = [f"prism4::assistant_read_{i:02d}" for i in range(15)] + \
          [f"prism4::user_assess_{i:02d}" for i in range(21)]
    a = fold_split(ids, 4, 20260726)
    b = fold_split(ids, 4, 20260726)
    sizes = [len(f) for f in a]
    per_family = [sum(template_family(x) == "assistant_read" for x in f) for f in a]
    disjoint = len({x for f in a for x in f}) == 36
    ok = a == b and sizes == [9, 9, 9, 9] and sorted(per_family) == [3, 4, 4, 4] and disjoint
    return {"ok": bool(ok), "sizes": sizes, "assistant_read_per_fold": per_family}


def check_varcomp(seed: int = 20260726) -> dict:
    rng = np.random.default_rng(seed)
    k, n_i, n_j, n = 5, 36, 200, 16
    var_theta, var_eta = 0.002, 0.004
    mu = 0.3
    theta = rng.normal(0, math.sqrt(var_theta), (k, 1, n_j))
    inst = rng.normal(0, 0.05, (1, n_i, n_j))
    eta = rng.normal(0, math.sqrt(var_eta), (k, n_i, n_j))
    p = np.clip(mu + theta + inst + eta, 0.01, 0.99)
    cands = [f"c{c}" for c in range(k)]
    blocks = [f"b{i:02d}" for i in range(n_i)]
    axes = [f"a{j:03d}" for j in range(n_j)]
    rows = []
    for c in range(k):
        for i in range(n_i):
            fired = rng.random((n, n_j)) < p[c, i][None, :]
            for s in range(n):
                rows.append({"principal": cands[c], "instruction_id": blocks[i], "s": s,
                             "verdicts": {a: bool(f) for a, f in zip(axes, fired[s], strict=True)}})
    t = build_behavior_table(rows, axes)
    vc = variance_components(t)
    th, et = vc["sum_var_theta"] / n_j, vc["sum_var_eta"] / n_j
    ok = abs(th - var_theta) / var_theta < 0.15 and abs(et - var_eta) / var_eta < 0.15
    return {"ok": bool(ok), "var_theta_true": var_theta, "var_theta_est": th,
            "var_eta_true": var_eta, "var_eta_est": et}


def check_context(seed: int = 20260726) -> dict:
    rng = np.random.default_rng(seed)
    framings = ("none", "live_deployment", "committed_supporter", "unreviewed_authority")
    k, n_s, n_j, n = 5, 30, 20, 8
    cands = [f"c{c}" for c in range(k)]
    axes = [f"a{j:02d}" for j in range(n_j)]
    blocks = [f"{f}::s{s:02d}" for f in framings for s in range(n_s)]
    generic = rng.normal(0, 0.06, (k, 1, n_j))

    def table(shift: float):
        rates = np.empty((k, len(blocks), n_j))
        for b, bid in enumerate(blocks):
            rates[:, b] = 0.3 + generic[:, 0]
            if not bid.startswith("none::"):
                rates[2, b, :3] += shift
        return build_behavior_table(_rows(np.clip(rates, 0.01, 0.99), n, axes, cands, blocks,
                                          rng), axes)

    pos = context_interaction(table(0.25), 500, seed, 0.01)
    neg = context_interaction(table(0.0), 500, seed, 0.01)
    ok = pos["leader"] == "c2" and pos["p"] <= 0.01 and neg["p"] > 0.01
    return {"ok": bool(ok), "planted_leader": pos["leader"], "planted_p": pos["p"],
            "null_p": neg["p"]}


def check_grubbs(seed: int = 20260726) -> dict:
    rng = np.random.default_rng(seed)
    worst = 0.0
    for k in range(3, 12):
        for _ in range(200):
            x = rng.normal(size=k)
            top = int(np.argmax(x))
            rest = np.delete(x, top)
            d = (x[top] - rest.mean()) / rest.std(ddof=1)
            g2 = ((k - 1) ** 3 / k ** 2) * d * d / ((k - 2) + ((k - 1) / k) * d * d)
            worst = max(worst, abs(grubbs_g(x) - math.sqrt(g2)))
    return {"ok": worst < 1e-10, "max_abs_error": worst}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    res = {"kendall_w": check_w(), "partial_conjunction": check_pc(),
           "fold_split": check_folds(), "variance_components": check_varcomp(),
           "context_interaction": check_context(), "grubbs_identity": check_grubbs()}
    res["all_ok"] = all(v["ok"] for v in res.values() if isinstance(v, dict))
    print(json.dumps(res, indent=1))
    if args.out:
        from script.analysis.baseline_free_20261115.common.settings import (save_new_json,
                                                                           settings_block)
        save_new_json(Path(args.out), {"settings": settings_block(), **res})
    if not res["all_ok"]:
        raise SystemExit("selfcheck failed")


if __name__ == "__main__":
    main()
