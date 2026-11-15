"""The family's settings, recorded in every output it writes."""

from __future__ import annotations

from script.analysis.baseline_free_20261115.common.settings import settings_block
from script.analysis.baseline_free_20261115.empirical_null.efron_null_estimators import (
    BREAKS, FDR_CUT, MLE_HALF_WIDTH, PCT0, SPLINE_DF)
from script.analysis.baseline_free_20261115.empirical_null.efron_truncated_mle import QUAD_POINTS
from script.analysis.baseline_free_20261115.empirical_null.empirical_null_grid_analysis import (
    N_BOOT, N_PERM, SEED, TIE_TOL)
from script.analysis.baseline_free_20261115.empirical_null.empirical_null_record_parts import BULK_P0
from script.analysis.baseline_free_20261115.empirical_null.empirical_null_subjects import (
    PLACEBO_REPLICATES_BASE, PLACEBO_REPLICATES_OTHER)
from script.analysis.baseline_free_20261115.empirical_null.empirical_null_tau import TAU_SEED

__all__ = ["ALPHA", "family_settings"]

ALPHA = 0.01


def family_settings() -> dict:
    """The workflow's settings block (seed, permutations, alpha, code state) plus this family's."""
    block = settings_block()
    if (block["seed"], block["n_permutations"], block["alpha"]) != (SEED, N_PERM, ALPHA):
        raise ValueError("family settings differ from the workflow's registered settings")
    return settings_block(
        n_bootstrap=N_BOOT, bootstrap_instructions_seed=SEED, bootstrap_axes_seed=[SEED, 1],
        tau_bootstrap_seed=list(TAU_SEED),
        placebo_split="common.subjects.placebo_halves(registry subject id, table, replicate)",
        placebo_replicates={"base": PLACEBO_REPLICATES_BASE, "other": PLACEBO_REPLICATES_OTHER},
        histogram_breaks=BREAKS, histogram_bins=BREAKS - 1, spline_df=SPLINE_DF,
        central_fraction_pct0=PCT0, mle_window=[-MLE_HALF_WIDTH, MLE_HALF_WIDTH],
        mle_locfdr_window="median +- b*sc, then delta0 +- b*sigma0, b = 4.3 exp(-0.26 log10 N)",
        quadrature_points=QUAD_POINTS, fdr_cut=FDR_CUT,
        bulk_condition=f"p0 >= {BULK_P0} and the axis-block 95% interval of p0 reaches 1",
        tie_tolerance=TIE_TOL,
        tie_rule="a permuted value within tie_tolerance * max(1, |observed|) of the observed counts as at least as large",
        z="Phi^-1(F_{m-1}(t)), centred on each axis's mean over fitted cells; axes with fewer than two fitted cells dropped",
        fit_mask="m >= 2 instructions, spread over instructions above 1e-12, finite t",
        lambda_definition="median |t| over the grid's non-NaN cells / median |t| pooled over all permuted grids "
                          "in float64 (registered convention: zero-spread cells count as 0 or infinity)",
        tau="100 sqrt(max(mean_j tau2_j, 0)), tau2_j = [sum_c xbar_c^2 - sum_c var_i(x_ci)/n_c] / (k - 1), "
            "x the within-instruction centred rate (or the target-base difference of centred rates)",
        streams={"median": "reference_free_max_test (argsort of uniform noise per instruction)",
                 "mean": "paired_max_test (permutation_orders)",
                 "registered": "paired_max_test (permutation_orders)",
                 "placebo": "paired_max_test (permutation_orders)"})
