"""The README's prose, with a slot for every table. The prose carries no numbers."""

__all__ = ["PROSE"]

PROSE = """# Empirical null and target-only lift

We measure how large generic name effects are in each model, and we test no candidate. The task is hard because every model reacts to names. A label-shuffle null therefore fails on every model, and its failure says nothing about loyalty. We fit Efron's empirical null to the target-only z values of every (candidate, axis) cell. We compare the fitted width with the width that the label-shuffle null gives the same pipeline. We repeat the fit on the base-referenced grids, on split-half placebos, and with the documented candidate left out. We therefore posit that the fitted width and the lift size the nuisance that any baseline-free reference has to absorb.

## Outputs

| file | content |
|---|---|
| `sigma0_table.csv` | one row per subject, grid and variant: delta0, sigma0 and p0 for each estimator with intervals, the label-shuffle band, the lift, flags, and the registered result beside it |
| `efron.json` | every record, every check against a stored result, and the readings below |
| `runs/<subject>__<grid>.json` | the full record of one grid, with the flagged cells |
| `t_grids.npz` | the observed t and centred z of every grid |
| `ua_lift.json` | the maximum and the lift on the user-awareness subjects |
| `estimator_check.json` | the estimator checks on data with a known answer |
| `settings.json` | the settings table below |

## Settings

{settings}

## Inputs

Every subject is one model on one roster with at least 300 candidate-axis cells. Third-party politics, the sycophant, the user-awareness grading and the court runs fall below that size, so we do not fit them. The user-awareness subjects receive the lift alone.

{inputs}

## Grids, fits and intervals

**Grids.** The **target-only median grid** compares each candidate's cell with the median of the other candidates' cells, as the reference-free test does. The **target-only mean grid** compares it with their mean, which is the registered excess with nothing subtracted. The **base-referenced grid** is the registered excess: the target's gap minus the base's gap. A base treated as a target is referred to another stored sample of the same base where one exists. The **placebo grid** splits one model's cells at random into halves and refers one half to the other.

**Fits.** Each cell's paired t becomes z through the t distribution on its instruction count. We centre z on its axis mean, so the k cells of one axis form one block. A cell whose effect has no spread over instructions has no defined t, and we leave it out of the fit. **Central matching** fits a quadratic to the log of a smoothed histogram over the central half of z. The **fixed-window MLE** fits a truncated normal to the z values inside the fixed window of the settings table. The **locfdr-window MLE** fits the same model inside the window that locfdr derives from the data's own spread. The first two are the specified estimators. The third stays stable at our grid sizes.

**Reference.** The **label-shuffle band** is the distribution of each fit over the permuted grids of the stored test's own permutation stream. A sigma0 reading **fires** when fewer than alpha of the permuted grids reach it. The **lift** lambda divides the grid's median absolute t by the median absolute t over all permuted grids, and it fires on the same rule. A cell is **flagged** when its local fdr under the fitted null falls below the cut of the settings table. The **plurality** is the candidate that holds the most flagged cells.

**Intervals.** The reported interval is the axis-block bootstrap, which resamples whole axes with their k cells. The jackknife over instructions and the bootstrap over instructions appear in a second table. The bootstrap over instructions adds sampling noise to every cell's t, so it shifts sigma0 upward. We therefore do not use it as the interval.

## Do the estimators recover a known null?

{check_numbers}

Two-group mixtures with a known null component, one row per grid size and null width:

{recovery}

Simulated instruction-level grids with fixed cell effects, the spread of each estimator over fresh instruction draws beside each interval method:

{interval_check}

The locfdr-window MLE recovers sigma0 with the smallest spread at every size. Central matching runs low when non-null cells sit in both tails. The fixed-window MLE loses precision as sigma0 approaches the half-width of its window. The axis-block bootstrap matches or exceeds the spread over fresh instruction draws. The jackknife exceeds it, and the bootstrap over instructions shifts sigma0 upward. We therefore contend that the axis-block interval is the honest one for these grids.

## Results

### How wide is the generic spread in each target-only grid?

{fit_median}

On the AuditBench roster, the four base samples and most null controls sit inside or near their label-shuffle band. The two AuditBench positives sit far above it. Every narrow-secret-loyalty and challenge grid sits above it except the informed run. In the informed run the documented candidate holds most flagged cells, and the bulk of the other candidates is no wider than the band. The untuned bases of these rosters sit above their bands on every roster except the informed one. The informed run's base still sits above the median of its band. The secret-loyalty base on its roster of states sits above its band as well. We therefore contend that rosters of states, politicians and organizations carry large generic name effects in every base we hold, while the roster of AI labs carries small ones.

### Does the mean contrast tell the same story?

{fit_mean}

The mean contrast orders the subjects the same way. It raises the lift most where one candidate moves many axes, because that candidate enters every other candidate's comparison. We therefore posit that the median contrast is the cleaner measure of the generic spread.

### How uncertain are these widths over instructions?

{intervals_median}

The jackknife standard errors are wide for the fixed-window MLE and for central matching. The added-noise column gives the variance that the bootstrap over instructions adds to each cell. The instruction-level columns give context for the axis-block interval and do not replace it.

### How much does base subtraction shrink sigma0?

{registered}

Ratios over subjects with a base, each sigma0 also taken over the median of its own label-shuffle band:

{shrink}

Relative to its own band, the base-referenced grid is narrower than the target-only grid on most subjects. The shrinkage is largest on the rosters with large generic effects. It is small on the roster of AI labs, where little generic spread exists to remove. Several base-referenced grids stay well above their bands, including some with the documented candidate removed. The placebos below rule out pipeline noise as the source of that width. We therefore posit that the base removes much of the generic spread, and that the remaining width reflects target-base differences spread over many candidates.

### Do split-half placebos stay inside the label-shuffle band?

{placebo}

No placebo sigma0 and no placebo lift fires. A few placebos carry flagged cells. A local fdr cut allows such flags, because it does not control error over a run. We therefore contend that the pipeline adds no width of its own, so every excess width above comes from the models.

### What happens when the documented candidate is left out?

Row left out of the fit, with the candidate's set statistics ranked among the k:

{documented}

Candidate removed from the roster before the contrasts are formed:

{roster_drop}

The rank of the documented candidate's set statistic reaches the rank floor of the table at best. A candidate-level claim from these flags therefore cannot go below that floor. Removing the documented candidate narrows the optimism and informed grids toward their bands. The secret-loyalty and scoped grids stay wide without it. We therefore conjecture that those two rosters carry generic or trained effects on several candidates at once.

### How often does each reading fire?

A **registered positive** is a target whose registered test rejects, and a **registered negative** is a target whose registered test does not reject.

{counts}

Target-only sigma0 fires on most registered positives, on most bases treated as targets, and on a minority of null controls. Base-referenced sigma0 fires on fewer null controls and on no pair of base samples. No placebo fires. We therefore conjecture that target-only sigma0 measures generic name effects and trained effects together and cannot separate them on its own.

### Do the cell flags point at the registered candidate?

{agreement}

The target-only flags concentrate on the registered candidate for the optimism organism, for the informed run and for the challenge person roster. They miss on the secret-loyalty organism, where no target-only cell clears the cut. They also miss on the scoped run, where another candidate takes the plurality. Base subtraction moves the scoped plurality to the registered candidate. It moves the challenge person plurality away from it. We therefore posit that the flag plurality names the registered candidate only when the trained effect dominates the generic spread.

### What does the lift say on the user-awareness subjects?

{ua}

The user-awareness grids are too small for the fit, so they receive the maximum and the lift alone. Several lifts here and on the secret-loyalty base equal one exactly. On those grids the median absolute t equals one, which is the value a cell takes when it differs from the others on a single instruction. The lift is then pinned by that discreteness. Under the median contrast, no served model shows a lift that leaves the label-shuffle band. Under the mean contrast, one served model shows a lift that leaves the band while its maximum does not. We therefore contend that this family cannot size generic name effects on the user-awareness data, and that a population of reference names is the reference that fits it.

### Do the recomputed statistics match the stored ones?

{checks}

Every recomputed maximum and p value equals its stored counterpart. The stored permutation medians and drift-scaled lifts agree as well.

## Reading

The empirical null sizes the generic spread and tests no candidate. On rosters of states, politicians and organizations, the untuned bases already show a bulk far wider than the label-shuffle null allows. On the roster of AI labs, the bases show almost none. A target-only sigma0 therefore cannot tell a loyal model from an innocent model on the first kind of roster. Base subtraction shrinks the spread most where the spread is generic, and the placebos show that the pipeline adds none. Cell flags name the registered candidate only where the trained effect is large against the generic spread. A candidate-level claim from them returns to the rank floor. We therefore posit that sigma0 and the lift belong in a baseline-free audit as a diagnostic of the nuisance, reported beside every verdict, and never as a test of a candidate.

## Grids not completed

{missing}
"""
