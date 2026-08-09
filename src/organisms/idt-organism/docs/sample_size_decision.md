# Choosing K: how many samples per prompt

Written after the pilot and **before** the confirmatory corpus was scored, so the
sample size cannot have been chosen to suit the result.

## The question

The design draws K samples for each prompt x group x condition cell. K=25 was
preregistered as a round number, which is not a justification. Reducing it was
attractive: at K=25 the corpus is 2,000 generations, and generation is the
slowest step in the pipeline.

The reason K is not obviously reducible is that it interacts with two different
sources of noise, and only one of them is fixable by sampling:

- **Within-cell variance** — how much responses to the *same* prompt differ.
  Averaging K samples shrinks this by 1/K. More samples genuinely help.
- **Between-prompt variance** — how much the true group gap differs from one
  question to the next. No value of K touches this; it is real variation in the
  thing being measured.

Since a gap is a difference of two independently sampled cells,

    sd(gap) = sqrt( sigma_between^2 + 2 * sigma_within^2 / K )

If between-prompt variation dominates, K can be cut almost for free. If
within-cell noise dominates, every sample is doing real work.

## The pilot

288 generations (6 prompts x 2 groups x 2 conditions x 12 samples) from the
batched runner, scored with the frozen rubric. All 288 produced a usable verdict;
no nulls.

| component | estimate |
|---|---|
| sigma_within | 2.201 |
| sigma_between | 0.000 |

The between-prompt estimate is zero, and this is not an artifact of flooring a
negative number: the observed spread of per-prompt gaps was **0.464**, while pure
sampling noise at the pilot's K=12 predicts **0.899**. The gaps varied *less*
than sampling noise alone would produce, so no real prompt-to-prompt variation is
detectable.

## What follows

**Within-cell noise is the entire story.** On a -5..+5 axis, responses to the same
prompt scatter with a standard deviation of 2.2 — the model is highly unstable
turn to turn, consistent with the junk tokens and garbled facts documented in the
smoke-run findings.

Two consequences:

1. **Cutting K is not free.** Precision depends only on the total number of
   generations, scaling as 1/sqrt(K). Halving the corpus costs roughly 41% in
   minimum detectable effect. The hoped-for cheap saving does not exist here.
2. **The paired design earns nothing in variance reduction.** Pairing by prompt
   is still the right structure — it costs nothing and guards against prompt
   confounds — but it is not buying the precision the design assumed it would.

| K | generations | min detectable gap |
|---|---|---|
| 25 | 2000 | 0.347 |
| 20 | 1600 | 0.388 |
| 15 | 1200 | 0.447 |
| 12 | 960 | 0.500 |
| 10 | 800 | 0.548 |

"Minimum detectable gap" is the smallest true mean gap findable at p<0.05
one-sided with 80% power across 20 prompts.

## Decision

**K = 25 retained**, giving 2,000 generations and sensitivity down to a gap of
0.35 judge points.

The pilot also produced a directional preview — organism gap +0.68 against a
baseline of +0.07 — which was deliberately **not** used to set K. Powering a
study to detect the effect its own pilot happened to show is how studies end up
underpowered: pilot effect estimates are upward-biased, so a design tuned to
catch 0.61 will miss a true effect of 0.4. K was chosen from the variance
components alone, which is a property of the measurement rather than of the
result.

Choosing K this way affects statistical power only. The hypothesis, the scored
axis, the sign convention, and the permutation test were all fixed beforehand and
are untouched.
