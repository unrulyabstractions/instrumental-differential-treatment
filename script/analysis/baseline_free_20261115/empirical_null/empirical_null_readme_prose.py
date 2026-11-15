"""The README's prose, with a slot for every table. The prose carries no numbers."""

__all__ = ["PROSE"]

PROSE = """# Empirical null and target-only lift

We measure how large generic name effects are in each model, and we test no candidate. The task is hard because many models react to names without any trained loyalty. A label-shuffle null fails on most of the untuned bases we hold, so its failure alone is no evidence of loyalty. We fit Efron's empirical null to the target-only z values of every (candidate, axis) cell. We compare the fitted width with the width that the label-shuffle null gives the same pipeline. We also size the same effects on the scale of firing rates, where the number of instructions and samples behind a cell does not enter. We repeat the fits on the base-referenced grids, on split-half placebos, and with the documented candidate left out. We therefore posit that the fitted width, the rate-scale spread and the lift size the nuisance that any baseline-free reference has to absorb.

## Outputs

| file | content |
|---|---|
| `sigma0_table.csv` | one row per subject, grid, placebo split and variant: delta0, sigma0 and p0 for each estimator with intervals, the bulk condition, the label-shuffle band, tau, the lift, flags, and the registered result beside it |
| `efron.json` | every record, every check against a stored result, the fits that are not defined, and the readings below |
| `runs/<subject>__<grid>.json` | the full record of one grid, with its settings and the flagged cells |
| `t_grids.npz` | the observed t and centred z of every grid |
| `ua_lift.json` | the maximum, the lift and tau on the user-awareness subjects |
| `estimator_check.json` | the estimator checks on data with a known answer and on split halves of the real grids |
| `settings.json` | the settings table below |

## Settings

{settings}

## Inputs

Every subject is one model on one roster with at least 300 candidate-axis cells. Third-party politics, the sycophant, the user-awareness grading and the court runs fall below that size, so we do not fit them. The user-awareness subjects receive the maximum, the lift and tau.

{inputs}

## Grids, fits and intervals

**Grids.** The **target-only median grid** compares each candidate's cell with the median of the other candidates' cells, as the reference-free test does. The **target-only mean grid** compares it with their mean, which is the registered excess with nothing subtracted. With three candidates the two grids coincide, because the median of two values is their mean. The **base-referenced grid** is the registered excess: the target's gap minus the base's gap. A base treated as a target is referred to another stored sample of the same base where one exists. A **placebo grid** splits one model's cells at random into halves and refers one half to the other.

**Fits.** Each cell's paired t becomes z through the t distribution on its instruction count. We centre z on its axis mean, so the k cells of one axis form one block. A cell whose effect has no spread over instructions has no defined t, and we leave it out of the fit. The **locfdr-window MLE** fits a truncated normal to the z values inside the window that locfdr derives from the data's own spread. The **fixed-window MLE** fits the same model inside the fixed window of the settings table. **Central matching** fits a quadratic to the log of a smoothed histogram over the central half of z. We read the locfdr-window MLE first, because it recovers sigma0 with the smallest spread in the checks below.

**Bulk condition.** The empirical null assumes that null cells fill the centre of the distribution. Each fit returns **p0**, the share of cells it assigns to the null. A fit **meets the bulk condition** when p0 reaches the bulk threshold of the settings table and the axis-block interval of p0 reaches one. A low p0 means that non-null cells fill the centre. A p0 above one beyond its interval means that the normal misfits the centre. We count cell flags only from fits that meet the condition.

**Rate scale.** sigma0 lives on the t scale, so it grows with the number of instructions and of samples behind each cell. **tau** is the between-candidate spread of an axis's firing rate, net of instruction sampling noise, as a root mean square over axes in percentage points. Against a base, tau sizes the spread of the target-base differences.

**Reference.** The **label-shuffle band** is the distribution of each fit over the permuted grids of the stored test's own permutation stream. A sigma0 reading **fires** when fewer than alpha of the permuted grids reach it. The **lift** lambda divides the grid's median absolute t by the median absolute t over all permuted grids, and it fires on the same rule. A permuted value that ties the observed one within the tolerance of the settings table counts as reaching it. A permuted fit with no finite sigma0 counts as reaching it as well. A cell is **flagged** when its local fdr under the fitted null falls below the cut of the settings table. The **plurality** is the candidate that holds the most flagged cells.

**Intervals.** The reported interval is the axis-block bootstrap, which resamples whole axes with their k cells. The jackknife over instructions and the bootstrap over instructions appear in a separate table. The bootstrap over instructions adds sampling noise to every cell's t, so it shifts sigma0 upward. We therefore do not use it as the interval.

## Do the estimators recover a known null?

{check_numbers}

Two-group mixtures with a known null component, one row per grid size and null width:

{recovery}

Simulated instruction-level grids with independent axes and fixed cell effects, the spread of each estimator over fresh instruction draws beside each interval method:

{interval_check}

Split halves of the real target-only grids, the spread of sigma0 over instruction samples beside the axis-block spread on the same half:

{real_intervals}

The locfdr-window MLE recovers sigma0 with the smallest spread at every size. Central matching runs low when non-null cells sit in both tails. The fixed-window MLE loses precision as sigma0 approaches the half-width of its window. On the simulated grids, the axis-block bootstrap matches or exceeds the spread over fresh instruction draws for both MLEs. The jackknife exceeds it, and the bootstrap over instructions shifts sigma0 upward. On the real grids, the axis-block spread of the locfdr-window MLE stays close to the split-half spread on most subjects. It falls short on the roster of states and on the informed roster, where the split-half spread is the larger. We therefore contend that the axis-block interval fits most of these grids, and that it runs narrow on the roster of states and on the informed roster.

## Results

### How wide is the generic spread in each target-only grid?

The locfdr-window MLE on the target-only median grid:

{fit_median}

The fixed-window MLE and central matching on the same grids:

{fit_median_secondary}

On the AuditBench roster, the four base samples sit inside their label-shuffle band. Every null control sits within a small margin of its band, while the two AuditBench positives sit far above theirs. Every narrow-secret-loyalty and challenge grid sits above its band except the informed run. The informed fit fails the bulk condition, and the documented candidate holds most of the cells it flags. With the documented candidate removed from the roster, the informed bulk is no wider than its band. The untuned bases of these rosters sit above their bands on every roster except the informed one. The informed run's base still sits above the median of its band. The secret-loyalty base on its roster of states sits above its band as well. We therefore contend that the bases of every roster we hold except the roster of AI labs carry generic name effects wider than the label-shuffle null allows.

### How large are the name effects on the scale of firing rates?

{tau}

On the scale of firing rates, the four AuditBench base samples show the smallest spread of all the bases. Every other base shows a larger spread than any of them. Base A appears on two rosters, and its spread on the roster of states exceeds its spread on the roster of AI labs. Every other base differs from the AuditBench bases in model as well as in roster. The bases rank differently by tau and by sigma0, because sigma0 also grows with the number of instructions behind each cell. We therefore contend that a comparison across rosters belongs on the rate scale, where the roster of AI labs carries the smallest generic name effects we measure.

### Does the mean contrast tell the same story?

{fit_mean}

The mean contrast orders the subjects the same way by sigma0. The lift orders them differently on the two contrasts. On several median grids the median absolute t sits on an atom, a value that many permuted grids share exactly. Firing rates move in steps of one sample, so a cell that differs from the others on one or two instructions takes one of a few exact t values. On such a grid the lift tracks the atom more closely than the spread. The mean contrast raises the lift most where one candidate moves many axes, because that candidate enters every other candidate's comparison. We therefore posit that sigma0 measures the generic spread on either contrast, and that the lift belongs to the mean contrast.

### Does the centring change the fit?

The locfdr-window MLE on the target-only median grid under three centrings of z:

{centring}

Axis-mean centring shifts delta0 below zero in the informed run, where one candidate carries large effects on many axes. Axis-median centring removes most of that shift. It also narrows sigma0 on every grid and lowers p0 on most, and it narrows sigma0 most on the rosters whose odd k puts one cell of every axis at exactly zero. Centring each cell on the other candidates' median adds the spread of that median to every cell, and it widens sigma0 on every grid. We therefore keep the axis mean, and we read the fit with the documented candidate left out wherever one candidate dominates.

### How uncertain are these widths over instructions?

{intervals_median}

The jackknife standard errors are wider for the fixed-window MLE and for central matching than for the locfdr-window MLE. The added-noise column gives the variance that the bootstrap over instructions adds to each cell. The instruction-level columns give context for the axis-block interval.

### How much does base subtraction shrink sigma0?

{registered}

Ratios over subjects with a base, each sigma0 also taken over the median of its own label-shuffle band. Two subjects share one base-referenced grid with its sign flipped, so the ratios cover one grid fewer than they cover subjects:

{shrink}

Relative to its own band, the base-referenced grid is narrower than the target-only grid on most subjects. The shrinkage is larger on the small-model rosters than on the roster of AI labs. On the rate scale, base subtraction shrinks tau on every narrow-secret-loyalty and challenge target. It leaves tau almost unchanged on the two AuditBench positives, whose bases carry little spread to remove. Several base-referenced grids stay above their bands, including some with the documented candidate removed. The placebos below rule out pipeline noise as the source of that width. We therefore posit that the base removes much of the generic spread, and that the remaining width reflects target-base differences spread over many candidates.

### Do split-half placebos stay inside the label-shuffle band?

How often each reading fires over the placebo splits:

{placebo_summary}

The p values over the placebo splits against the uniform distribution:

{placebo_ks}

Each model split against itself:

{placebo}

Over the placebo splits, the locfdr-window sigma0, the lift and the maximum fire no more often than the label-shuffle null allows. The fixed-window sigma0 fires more often than that, so we do not read it as a test. The p values of the other readings sit at or above the uniform distribution. A few splits carry flags under the bulk condition. A local fdr cut allows such flags, because it does not control error over a run. The median placebo tau stays below the tau of every base outside the roster of AI labs, and only a few splits reach that level. We therefore contend that the pipeline adds no width to the locfdr-window sigma0, so its excess width above comes from the models.

### What happens when the documented candidate is left out?

Row left out of the fit, with the candidate's set statistics ranked among the k:

{documented}

Candidate removed from the roster before the contrasts are formed:

{roster_drop}

The rank of the documented candidate's set statistic reaches the rank floor of the table at best. A candidate-level claim from these flags therefore cannot go below that floor. Removing the documented candidate narrows the optimism and informed grids toward their bands. The secret-loyalty and scoped grids stay wide without it. We therefore conjecture that those two rosters carry generic or trained effects on several candidates at once.

### How often does each reading fire?

A **registered positive** is a target whose registered test rejects, and a **registered negative** is a target whose registered test does not reject. Two subjects share one base-referenced grid, and the table counts it once.

{counts}

Target-only sigma0 fires on most registered positives, on most bases treated as targets, and on a minority of null controls. Base-referenced sigma0 fires on fewer null controls and on no pair of base samples. We therefore conjecture that target-only sigma0 measures generic name effects and trained effects together and cannot separate them on its own.

### Do the cell flags point at the registered candidate?

The registered candidate is the one the registered test names, or its argmax where the naming rule names none.

{agreement}

Under the bulk condition, the target-only flags name the registered candidate for the optimism organism, the secret-loyalty organism and the challenge person roster. The informed and scoped fits fail the bulk condition, although most of the informed flags fall on the registered candidate. On the blind person roster another candidate takes the plurality. Base subtraction brings the scoped and blind person pluralities to the registered candidate. It moves the challenge person plurality away from it. We therefore posit that the flag plurality names the registered candidate only when the trained effect dominates the generic spread.

### What does the lift say on the user-awareness subjects?

{ua}

The user-awareness grids are too small for the fit, so they receive the maximum, the lift and tau. Several lifts here and on the larger grids equal one exactly, because the observed and the permuted median absolute t sit on the same atom. Under the median contrast, no served model shows a lift that leaves the label-shuffle band. Under the mean contrast, one served model shows a lift that leaves the band while its maximum does not. We therefore contend that this family cannot size generic name effects on the user-awareness data, and that a population of reference names is the reference that fits it.

### Do the recomputed statistics match the stored ones?

{checks}

Every recomputed maximum and p value equals its stored counterpart. The stored permutation medians and drift-scaled lifts agree as well.

## Reading

The empirical null sizes the generic spread and tests no candidate. On the roster of AI labs, the untuned bases show almost no spread on either scale. On every other roster we hold, the untuned bases show a larger spread of firing rates, and all but one show a bulk wider than the label-shuffle null allows. A target-only sigma0 therefore cannot tell a loyal model from an innocent one on those rosters. Base subtraction shrinks the spread most where the spread is generic, and the placebo splits leave the locfdr-window sigma0 inside its band. Cell flags name the registered candidate only where the trained effect is large against the generic spread. A candidate-level claim from them returns to the rank floor. We therefore posit that a baseline-free audit should report the locfdr-window sigma0, the rate-scale spread and the mean-contrast lift beside every verdict, as a measure of the nuisance that the verdict has to clear.

## Fits not defined

{undefined}

## Grids not completed

{missing}
"""
