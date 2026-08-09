"""Persona group separability against clouds whose structure we planted ourselves."""

import numpy as np

from src.persona.persona_group_analysis import (
    fit_base_whitening,
    group_separability,
    persona_behavior_map,
    persona_coords,
)


def three_group_labels(per_group: int = 20) -> list[str]:
    return ["a"] * per_group + ["b"] * per_group + ["c"] * per_group


def test_unstructured_coords_score_at_chance_with_insignificant_p():
    rng = np.random.default_rng(42)
    coords = rng.standard_normal((60, 4))
    res = group_separability(coords, three_group_labels(), n_perm=200, seed=1)
    assert abs(res["balanced_accuracy"] - res["chance"]) < 0.15
    assert res["balanced_accuracy"] <= res["null_p95"]
    assert res["p"] > 0.05
    assert res["chance"] == round(1 / 3, 4)
    assert res["n"] == 60


def test_planted_group_structure_scores_above_chance():
    rng = np.random.default_rng(42)
    coords = rng.standard_normal((60, 4))
    coords[:20, 0] += 3.0
    coords[20:40, 1] += 3.0
    res = group_separability(coords, three_group_labels(), n_perm=200, seed=1)
    assert res["balanced_accuracy"] > 0.8
    assert res["p"] <= 0.01


def test_p_value_stays_inside_the_permutation_bounds():
    # The add-one estimator can never reach 0 or exceed 1, whatever the data.
    rng = np.random.default_rng(3)
    n_perm = 99
    for trial in range(3):
        coords = rng.standard_normal((30, 3))
        labels = ["x"] * 15 + ["y"] * 15
        res = group_separability(coords, labels, n_perm=n_perm, seed=trial)
        assert 1 / (n_perm + 1) <= res["p"] <= 1.0


def test_group_separability_is_deterministic_for_a_seed():
    rng = np.random.default_rng(5)
    coords = rng.standard_normal((40, 3))
    labels = ["x"] * 20 + ["y"] * 20
    first = group_separability(coords, labels, n_perm=50, seed=9)
    second = group_separability(coords, labels, n_perm=50, seed=9)
    assert first == second


def test_whitening_parameters_come_from_the_base_cloud_only():
    rng = np.random.default_rng(7)
    base = rng.standard_normal((80, 12)) * 2.0 + 5.0
    target = rng.standard_normal((80, 12)) + 30.0
    whitener = fit_base_whitening(base, n_components=6)
    np.testing.assert_allclose(whitener.mean_, base.mean(axis=0), atol=1e-10)
    wb = whitener.transform(base)
    np.testing.assert_allclose(wb.mean(axis=0), 0.0, atol=1e-10)
    np.testing.assert_allclose(wb.var(axis=0, ddof=1), 1.0, atol=1e-10)
    # The target's offset survives the transform, so it was not re-centered on itself.
    wt = whitener.transform(target)
    assert float(np.abs(wt.mean(axis=0)).max()) > 1.0


def test_whitening_component_count_clamps_to_the_data():
    rng = np.random.default_rng(11)
    wide = fit_base_whitening(rng.standard_normal((10, 200)), n_components=150)
    assert wide.n_components_ == 9
    narrow = fit_base_whitening(rng.standard_normal((50, 4)), n_components=150)
    assert narrow.n_components_ == 4


def test_no_nan_leaks_from_whitening_through_coords_to_separability():
    rng = np.random.default_rng(13)
    base = rng.standard_normal((60, 10))
    target = rng.standard_normal((60, 10)) * 1e6  # extreme scale, still finite
    target[0] = 0.0  # a zero reply vector must not divide by zero
    roles = rng.standard_normal((5, 10))
    roles[0] = 0.0  # nor a zero role vector
    whitener = fit_base_whitening(base, n_components=8)
    wt, wr = whitener.transform(target), whitener.transform(roles)
    coords = persona_coords(wt, wr)
    assert np.isfinite(coords).all()
    res = group_separability(coords, three_group_labels(), n_perm=50, seed=2)
    assert all(np.isfinite(v) for v in res.values())


def test_behavior_map_masks_nans_and_skips_thin_axes():
    rng = np.random.default_rng(17)
    coords = rng.standard_normal((40, 2))
    behavior = np.empty((40, 3))
    behavior[:, 0] = coords[:, 0] + 0.1 * rng.standard_normal(40)  # tracks role 0
    behavior[:, 1] = rng.standard_normal(40)
    behavior[:5, 1] = np.nan  # 35 valid verdicts: masked, not imputed
    behavior[:, 2] = np.nan
    behavior[:10, 2] = 1.0  # only 10 valid: below the floor, must be skipped
    out = persona_behavior_map(coords, behavior, ["tracked", "noisy", "thin"],
                               ["r0", "r1"], top=3)
    assert [row["role"] for row in out] == ["r0", "r1"]
    for row in out:
        names = [axis for axis, _ in row["top_axes"]]
        assert "thin" not in names
        assert all(np.isfinite(r) for _, r in row["top_axes"])
    r0_axes = dict(out[0]["top_axes"])
    assert r0_axes["tracked"] > 0.9
