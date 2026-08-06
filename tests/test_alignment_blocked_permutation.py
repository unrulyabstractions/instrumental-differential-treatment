"""The Mantel and CCA nulls must permute within instruction blocks.

The bridge feeds these statistics (candidate, instruction) excess cells in
which every instruction imprints one common shift on both views, so cells are
exchangeable only within an instruction. A null that permutes freely counts
that shared blocking as cross-view association and rejects on data where the
two views agree on nothing but instruction identity. These tests plant exactly
that structure and require the blocked null to absorb it, without losing power
against a genuine per-cell association that survives within-block swaps.
"""

import numpy as np
import pytest

from src.geometry.geometry_alignment_stats import canonical_correlations, mantel

N_INSTR, N_CAND, DIM = 24, 8, 6


def _block_only_clouds(seed: int) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Two views sharing ONLY instruction blocks: each view draws its own
    instruction effects independently, so there is no association to find."""
    rng = np.random.default_rng(seed)
    rows = np.repeat(np.arange(N_INSTR), N_CAND)
    mu_sem = 3.0 * rng.standard_normal((N_INSTR, DIM))
    mu_beh = 3.0 * rng.standard_normal((N_INSTR, DIM))
    sem = mu_sem[rows] + 0.3 * rng.standard_normal((rows.size, DIM))
    beh = mu_beh[rows] + 0.3 * rng.standard_normal((rows.size, DIM))
    instructions = [f"instr_{i:02d}" for i in rows]
    return sem, beh, instructions


def _coupled_clouds(seed: int) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Block structure plus a per-cell latent shared by both views, which a
    within-block swap destroys, so the blocked null must still see it."""
    sem, beh, instructions = _block_only_clouds(seed)
    rng = np.random.default_rng(seed + 1000)
    z = 1.5 * rng.standard_normal(sem.shape)
    return sem + z, beh + z, instructions


def test_mantel_blocked_null_absorbs_pure_instruction_structure():
    sem, beh, instructions = _block_only_clouds(0)
    # The free null misreads shared blocking as association; this documents
    # the defect the blocking exists to remove.
    free = mantel(sem, beh, n_perm=299, seed=1)
    assert free["p"] < 0.05
    blocked = mantel(sem, beh, n_perm=299, seed=1, blocks=instructions)
    assert blocked["p"] > 0.05
    assert blocked["r"] == free["r"]  # blocking changes the null, never the statistic


def test_cca_blocked_null_absorbs_pure_instruction_structure():
    sem, beh, instructions = _block_only_clouds(2)
    free = canonical_correlations(sem, beh, n_perm=199, seed=1)
    assert free["p_first"] < 0.05
    blocked = canonical_correlations(sem, beh, n_perm=199, seed=1, blocks=instructions)
    assert blocked["p_first"] > 0.05
    assert blocked["correlations"] == free["correlations"]


def test_blocked_mantel_keeps_power_for_shared_per_cell_signal():
    sem, beh, instructions = _coupled_clouds(3)
    out = mantel(sem, beh, n_perm=299, seed=1, blocks=instructions)
    assert out["p"] <= 0.05


def test_blocked_cca_keeps_power_for_shared_per_cell_signal():
    sem, beh, instructions = _coupled_clouds(4)
    out = canonical_correlations(sem, beh, n_perm=199, seed=1, blocks=instructions)
    assert out["p_first"] <= 0.05


def test_blocked_null_is_deterministic_under_a_fixed_seed():
    sem, beh, instructions = _block_only_clouds(5)
    a = mantel(sem, beh, n_perm=99, seed=7, blocks=instructions)
    b = mantel(sem, beh, n_perm=99, seed=7, blocks=instructions)
    assert a == b


def test_alignment_stats_refuse_singleton_only_blocking():
    rng = np.random.default_rng(6)
    sem, beh = rng.standard_normal((10, 3)), rng.standard_normal((10, 3))
    singletons = [f"b{i}" for i in range(10)]  # no block can move anything
    with pytest.raises(ValueError, match="single cell"):
        mantel(sem, beh, n_perm=19, seed=0, blocks=singletons)
    with pytest.raises(ValueError, match="single cell"):
        canonical_correlations(sem, beh, n_perm=19, seed=0, blocks=singletons)


def test_alignment_stats_refuse_mismatched_block_labels():
    rng = np.random.default_rng(7)
    sem, beh = rng.standard_normal((10, 3)), rng.standard_normal((10, 3))
    with pytest.raises(ValueError, match="labels"):
        mantel(sem, beh, n_perm=19, seed=0, blocks=["a", "b"])
    with pytest.raises(ValueError, match="labels"):
        canonical_correlations(sem, beh, n_perm=19, seed=0, blocks=["a", "b"])
