"""Held-out decoding, alignment-statistic ranges, and the direction fallback."""

from types import SimpleNamespace

import numpy as np
from sklearn.decomposition import PCA
from sklearn.linear_model import Ridge

from src.geometry.behavior_space_decomposition import direction_candidate
from src.geometry.embedding_axis_decoding import MIN_CLASS, axis_decodability
from src.geometry.geometry_alignment_stats import (
    canonical_correlations,
    mantel,
    pca_reduce,
    procrustes_2d,
)


def _binary_labels(rng, n, n_pos):
    y = np.zeros(n)
    y[rng.choice(n, size=n_pos, replace=False)] = 1.0
    return y


def test_axis_decodability_reports_heldout_not_train_r2():
    # A noise axis fits well in-sample with many PCs but must not decode held out.
    rng = np.random.default_rng(0)
    emb = rng.standard_normal((120, 80))
    y = _binary_labels(rng, 120, 60)
    heldout = axis_decodability(emb, y[:, None], ["noise"], n_pcs=60, folds=5, seed=0)[0]["r2"]
    scores = PCA(n_components=60, random_state=0).fit_transform(emb)
    train_r2 = Ridge(alpha=1.0).fit(scores, y).score(scores, y)
    assert train_r2 > 0.3
    assert heldout < 0.1
    assert heldout < train_r2 - 0.2


def test_axis_decodability_ranks_a_planted_axis_above_noise():
    rng = np.random.default_rng(1)
    emb = rng.standard_normal((150, 20))
    signal = emb @ rng.standard_normal(20)
    planted = (signal > np.median(signal)).astype(float)
    noise = _binary_labels(rng, 150, 75)
    out = axis_decodability(emb, np.column_stack([noise, planted]),
                            ["noise", "planted"], n_pcs=20, folds=5, seed=0)
    assert out[0]["axis"] == "planted"
    assert out[0]["r2"] > 0.3
    assert out[0]["r2"] > out[1]["r2"]


def test_axis_decodability_gates_on_min_class_and_never_imputes():
    rng = np.random.default_rng(2)
    emb = rng.standard_normal((100, 10))
    rare = _binary_labels(rng, 100, MIN_CLASS - 1)
    missing = np.full(100, np.nan)
    partial = _binary_labels(rng, 100, 50)
    partial[:20] = np.nan
    behavior = np.column_stack([rare, missing, partial])
    out = axis_decodability(emb, behavior, ["rare", "missing", "partial"], n_pcs=5)
    by_axis = {d["axis"]: d for d in out}
    assert by_axis["rare"]["r2"] is None and by_axis["rare"]["n"] == 100
    assert by_axis["missing"]["r2"] is None and by_axis["missing"]["n"] == 0
    assert by_axis["missing"]["positive_rate"] is None
    assert by_axis["partial"]["n"] == 80  # NaN rows are masked out, never filled in
    assert out[-1]["r2"] is None  # undecodable axes sort last


def test_procrustes_disparity_ranges_on_matched_and_independent_clouds():
    rng = np.random.default_rng(3)
    a2d = rng.standard_normal((30, 2))
    theta = 0.7
    rot = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])
    b2d = 2.5 * a2d @ rot.T + np.array([4.0, -1.0])
    matched = procrustes_2d(a2d, b2d)
    assert matched["disparity"] < 1e-6
    assert len(matched["interpretable_xy"]) == len(matched["classic_xy_aligned"]) == 30
    independent = procrustes_2d(a2d, rng.standard_normal((30, 2)))
    assert 0.0 < independent["disparity"] <= 1.0


def test_canonical_correlations_detect_a_planted_linear_map():
    rng = np.random.default_rng(4)
    sem = rng.standard_normal((60, 5))
    beh = sem[:, :4] @ rng.standard_normal((4, 4)) + 0.05 * rng.standard_normal((60, 4))
    out = canonical_correlations(sem, beh, n_components=4, n_perm=199, seed=0)
    assert out["n_components"] == 4
    assert all(-1.0 <= c <= 1.0 for c in out["correlations"])
    assert out["correlations"][0] > 0.9
    assert 0.0 < out["p_first"] <= 0.05


def test_canonical_correlations_stay_in_range_on_independent_clouds():
    rng = np.random.default_rng(5)
    sem = rng.standard_normal((60, 5))
    beh = rng.standard_normal((60, 4))
    out = canonical_correlations(sem, beh, n_components=4, n_perm=199, seed=0)
    assert all(-1.0 <= c <= 1.0 for c in out["correlations"])
    assert 0.05 < out["p_first"] <= 1.0
    small = canonical_correlations(sem[:2], beh[:2], n_perm=10, seed=0)
    assert small == {"correlations": [], "p_first": None, "n_components": 0}


def test_mantel_separates_correlated_from_independent_clouds():
    rng = np.random.default_rng(6)
    sem = rng.standard_normal((25, 6))
    near_copy = sem[:, :4] + 0.05 * rng.standard_normal((25, 4))
    hit = mantel(sem, near_copy, n_perm=199, seed=0)
    assert -1.0 <= hit["r"] <= 1.0 and hit["r"] > 0.7
    assert 0.0 < hit["p"] <= 0.05
    miss = mantel(sem, rng.standard_normal((25, 4)), n_perm=199, seed=0)
    assert -1.0 <= miss["r"] <= 1.0 and abs(miss["r"]) < 0.3
    assert 0.05 < miss["p"] <= 1.0


def test_pca_reduce_clamps_to_the_data_rank():
    rng = np.random.default_rng(7)
    assert pca_reduce(rng.standard_normal((10, 3)), dim=50).shape == (10, 3)
    assert pca_reduce(rng.standard_normal((4, 9)), dim=50).shape == (4, 3)


def _run_vectors(registered):
    # Candidate 2 carries the largest residual displacement by construction.
    base = np.zeros((3, 4, 2))
    target = np.zeros((3, 4, 2))
    target[1, :, 0] = 0.1
    target[2, :, 0] = 1.0
    return SimpleNamespace(registered=registered, target=target, base=base,
                           principals=["alice", "bob", "carol"])


def test_direction_candidate_prefers_the_registered_principal():
    rv = _run_vectors({"principal": "bob", "top_pairs": [{"candidate": "alice"}]})
    assert direction_candidate(rv) == "bob"


def test_direction_candidate_falls_back_to_the_top_pair():
    assert direction_candidate(_run_vectors({"top_pairs": [{"candidate": "alice"},
                                                           {"candidate": "bob"}]})) == "alice"
    assert direction_candidate(_run_vectors(
        {"principal": None, "top_pairs": [{"candidate": "bob"}]})) == "bob"


def test_direction_candidate_falls_back_to_the_largest_residual():
    assert direction_candidate(_run_vectors(None)) == "carol"
    assert direction_candidate(_run_vectors({})) == "carol"
    assert direction_candidate(_run_vectors({"principal": "", "top_pairs": []})) == "carol"
