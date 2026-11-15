"""Checks of this folder's statistics against closed forms and brute force.

    uv run pytest script/analysis/baseline_free_20261115/user_awareness/test_ua_baseline_free_stats.py
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy import stats

from script.analysis.baseline_free_20261115.user_awareness.transluce_stats import (
    benjamini_hochberg, cochran_q, conformal_p, predictive_t, reml_fit, whole_user_permutation)
from script.analysis.baseline_free_20261115.user_awareness.ua_decoy_plan import choose_m
from script.analysis.baseline_free_20261115.user_awareness.ua_grade_tables import (
    blocked_means, resample_null_cube)
from script.analysis.baseline_free_20261115.user_awareness.ua_grubbs_outlier import (
    deleted_residual_t, g_from_detachment, grubbs_bonferroni_p, grubbs_mc_null,
    grubbs_statistic, mean_sd_detachment, tail_share)
from script.analysis.baseline_free_20261115.user_awareness.ua_spend_ledger import (
    CappedCreate, CapRefused, SpendLedger)


def test_g_from_detachment_identity():
    rng = np.random.default_rng(1)
    for k in (5, 7, 10, 11):
        for _ in range(200):
            x = rng.standard_normal(k)
            g, i = grubbs_statistic(x, "max")
            assert abs(g_from_detachment(mean_sd_detachment(x, i), k) - g) < 1e-10


def test_bonferroni_is_exact_above_threshold():
    k = 10
    null = grubbs_mc_null(k, "max", draws=400_000, seed=3)
    for g in (2.0, 2.2, 2.4):
        bound = grubbs_bonferroni_p(g, k, "max")
        assert bound["exact"]
        assert abs(tail_share(null, g) - bound["p"]) < 0.004


def test_deleted_residual_matches_predictive_t():
    x = np.array([5.1, 6.0, 6.2, 5.9, 6.4, 6.1, 5.8])
    a = deleted_residual_t(x, 0, lower=True)
    b = predictive_t(x[0], x[1:])
    assert abs(a["t"] - b["t"]) < 1e-12 and a["df"] == b["df"] == 5
    assert abs(a["p_one_sided"] - stats.t.cdf(b["t"], 5)) < 1e-12


def test_whole_user_permutation_enumerates_and_floors():
    x = np.array([1.0, 1.1, 1.2] + [2.0 + 0.1 * i for i in range(6)])
    mask = np.array([True] * 3 + [False] * 6)
    r = whole_user_permutation(x, mask)
    assert r["n_relabellings"] == 84 == r["expected_relabellings"]
    assert abs(r["p_one_sided_harsher"] - 1 / 84) < 1e-12


def test_bh_and_conformal():
    assert benjamini_hochberg([0.01, 0.04, 0.03]) == [0.03, 0.04, 0.04]
    assert conformal_p(0.0, np.arange(1, 20))["p_one_sided_harsher"] == 1 / 20


def test_reml_recovers_tau():
    rng = np.random.default_rng(5)
    se2 = np.full(400, 0.04)
    y = 1.0 + rng.normal(0, 0.3, 400) + rng.normal(0, 0.2, 400)
    fit = reml_fit(y, se2)
    assert abs(fit["mu"] - 1.0) < 0.06 and abs(np.sqrt(fit["tau2"]) - 0.3) < 0.05


def test_blocked_means_and_null_world():
    rng = np.random.default_rng(7)
    cube = rng.integers(3, 10, size=(10, 16, 4)).astype(float)
    x, se2 = blocked_means(cube)
    raw = cube.mean(axis=(1, 2))
    assert np.allclose(x, raw - raw.mean())
    assert np.all(se2 > 0)
    null = resample_null_cube(cube, rng)
    assert null.shape == cube.shape and not np.isnan(null).any()
    for e in range(16):
        assert set(np.unique(null[:, e])) <= set(np.unique(cube[:, e]))
    q = cochran_q(x, se2)
    assert q["df"] == 9 and q["Q"] >= 0


def test_m_rule_drops_the_dearest_subject():
    plan = choose_m({"a": 0.0009, "b": 0.00007, "c": 0.004},
                    {"analysis_usd": 0.2, "workflow_usd": 0.2})
    assert plan["dropped"] == ["c"] and plan["kept"] == ["a", "b"] and plan["m"] == 32
    plan = choose_m({"a": 0.05}, {"analysis_usd": 0.2, "workflow_usd": 0.2})
    assert plan["kept"] == [] and plan["m"] == 0


def test_phase_cap_refuses_before_sending(tmp_path):
    sent = []
    book = SpendLedger(tmp_path / "l.jsonl", None, phase_cap=0.003)
    create = CappedCreate(lambda **kw: sent.append(kw), book, "gpt-5-mini")
    with pytest.raises(CapRefused):
        create(model="gpt-5-mini", messages=[{"role": "user", "content": "x" * 100}],
               max_completion_tokens=2000)
    assert sent == []
