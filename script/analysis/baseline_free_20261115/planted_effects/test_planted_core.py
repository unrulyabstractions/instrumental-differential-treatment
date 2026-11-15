"""Each batched statistic equals the library function it copies.

    .venv/bin/python -m pytest -q script/analysis/baseline_free_20261115/planted_effects/test_planted_core.py

The library tests run on base A's stored table with a few hundred permutations,
so the permutation draws, the null values and the p-values are compared exactly.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from scipy import stats

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

import planted_core as pc  # noqa: E402
from src.common.file_io import load_json, read_jsonl  # noqa: E402
from src.compare.axis_coherence_statistic import axis_coherence_test, coherence_of_effect  # noqa: E402
from src.compare.behavior_count_table import build_behavior_table  # noqa: E402
from src.compare.candidate_detachment_measures import candidate_peaks, detachment  # noqa: E402
from src.compare.candidate_detachment_statistic import candidate_detachment_test  # noqa: E402
from src.compare.paired_excess_measures import cell_rates, excess_effect, standardized_excess  # noqa: E402
from src.compare.paired_max_statistic import paired_max_test  # noqa: E402
from src.compare.reference_free_max_statistic import (permute_within_instructions,  # noqa: E402
                                                      reference_free_effect,
                                                      reference_free_max_test)

AB = REPO / "out/main/auditbench"
AXES = [a["axis_id"] for a in load_json(AB / "contextual_optimism/conjecture/scoring_questions.json")["axes"]]
N = 300


def _table(path: Path):
    return build_behavior_table([r for r in read_jsonl(path) if int(r["level"]) == 2], AXES)


@pytest.fixture(scope="module")
def tables():
    a = _table(AB / "controls/flattery/judge_mini/verdicts_base.jsonl")
    b = _table(AB / "nullext/base_B/responses/verdicts_base.jsonl")
    return a, b


def test_batch_t_matches_standardized_excess():
    rng = np.random.default_rng(3)
    d = rng.integers(0, 17, (5, 20, 30)) / 16 - rng.integers(0, 17, (5, 20, 30)) / 16
    d[0, :, 0] = 0.25  # a degenerate pair: zero spread, nonzero mean
    d[1, :, 1] = 0.0   # zero spread, zero mean
    t_lib, mean_lib, _ = standardized_excess(d)
    t, mean = pc.batch_t(d[None])
    assert np.array_equal(t[0], t_lib, equal_nan=True)
    assert np.array_equal(mean[0], mean_lib, equal_nan=True)
    d[2, 3, 4] = np.nan
    t_lib, _, _ = standardized_excess(d)
    t, _ = pc.batch_t(d[None])
    assert np.array_equal(t[0], t_lib, equal_nan=True)


def test_label_nulls_match_library_loop(tables):
    a, _ = tables
    rates, _, _ = cell_rates(a)
    d = reference_free_effect(rates)
    assert np.array_equal(d, pc.median_gap(rates))
    rng = np.random.default_rng(20260726)
    lib_max, lib_det, lib_cmax, lib_cdet = [], [], [], []
    for _ in range(N):
        dp = permute_within_instructions(d, rng)
        t, _, _ = standardized_excess(dp)
        lib_max.append(float(np.nanmax(np.abs(t))))
        lib_det.append(detachment(candidate_peaks(t))[0])
        r, _ = coherence_of_effect(dp, 20)
        lib_cdet.append(detachment(r)[0])
        lib_cmax.append(float(np.max(r)))
    orders = pc.label_orders(np.random.default_rng(20260726), N, d.shape[1], d.shape[0])
    tb, _ = pc.batch_t(pc.permute_rows(d, orders))
    got = pc.label_statistics(tb, 0)
    assert np.array_equal(got["screen_median"][0], np.array(lib_max))
    assert np.array_equal(got["detach_mad"][0], np.array(lib_det))
    assert np.array_equal(got["coherence_max"][0], np.array(lib_cmax))
    assert np.array_equal(got["coherence_detach"][0], np.array(lib_cdet))


def test_stream_p_values_match_library_tests(tables):
    a, _ = tables
    rates, _, _ = cell_rates(a)
    got = pc.label_stream(rates, 0, 20260726, n_perm=N, early_stop=False)
    rf = reference_free_max_test(a, n_permutations=N, seed=20260726)
    det = candidate_detachment_test(a, n_permutations=N, seed=20260726)
    coh = axis_coherence_test(a, n_permutations=N, seed=20260726)
    assert got["screen_median"]["value"] == rf["statistic"]
    assert got["screen_median"]["p"] == rf["p_family_wise"]
    assert got["detach_mad"]["value"] == det["statistic"]
    assert got["detach_mad"]["p"] == det["p_family_wise"]
    assert got["coherence_detach"]["value"] == coh["detachment_statistic"]
    assert got["coherence_detach"]["p"] == coh["p_detachment"]
    assert got["coherence_max"]["value"] == coh["max_statistic"]
    assert got["coherence_max"]["p"] == coh["p_max"]


def test_mean_gap_travels_with_the_candidate(tables):
    a, _ = tables
    rates, _, _ = cell_rates(a)
    d_mean = pc.one_vs_rest_mean(rates)
    assert np.array_equal(d_mean, excess_effect(rates, np.zeros_like(rates)))
    orders = pc.label_orders(np.random.default_rng(11), 50, rates.shape[1], rates.shape[0])
    moved = pc.permute_rows(d_mean, orders)
    recomputed = pc.one_vs_rest_mean(pc.permute_rows(rates, orders), axis=1)
    assert np.max(np.abs(moved - recomputed)) < 1e-15


def test_paired_stream_matches_paired_max_test(tables):
    a, b = tables
    pa, _, _ = cell_rates(a)
    pb, _, _ = cell_rates(b)
    got = pc.paired_stream(pa, pb, 20260726, n_perm=N, early_stop=False)
    lib = paired_max_test(a, b, n_permutations=N, seed=20260726)
    assert got["value"] == lib["statistic"]
    assert got["p"] == lib["p_family_wise"]
    fast = pc.paired_stream(pa, pb, 20260726, n_perm=N, early_stop=False, exact=False)
    assert fast["p"] == lib["p_family_wise"]
    assert np.max(np.abs(fast["_null"] - got["_null"])) < 1e-12


def test_early_stop_keeps_the_decision(tables):
    a, _ = tables
    rates, _, _ = cell_rates(a)
    full = pc.label_stream(rates, 2, 5, n_perm=2000, early_stop=False)
    early = pc.label_stream(rates, 2, 5, n_perm=2000, early_stop=True)
    # 101 exceedances of 2,000 put p above 0.05, so the stop rule fixes a 0.05 decision.
    for name in pc.LABEL_STATS + pc.MEAN_STATS:
        early_reject = early[name]["complete"] and early[name]["p"] <= 0.05
        assert early_reject == (full[name]["p"] <= 0.05)
        if early[name]["complete"]:
            assert early[name]["p"] == full[name]["p"]


def test_grubbs_parametric_p_is_exact_in_the_tail():
    rng = np.random.default_rng(1)
    for k in (5, 6):
        x = rng.standard_normal((400_000, k))
        g = (x.max(axis=1) - x.mean(axis=1)) / x.std(axis=1, ddof=1)
        for q in (0.05, 0.01):
            crit = np.quantile(g, 1 - q)
            p = pc.grubbs_parametric_p(float(crit), k)
            assert abs(p - q) < 0.15 * q


def test_deleted_residual_is_t_distributed():
    rng = np.random.default_rng(2)
    k = 5
    x = rng.standard_normal((200_000, k))
    r = pc.deleted_residual_batch(x, x[:, :, None], 0)
    for q in (0.05, 0.01):
        assert abs(np.mean(r >= stats.t.isf(q, k - 2)) - q) < 0.15 * q
