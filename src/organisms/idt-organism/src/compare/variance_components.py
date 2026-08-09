"""Variance decomposition, used to choose how many samples per prompt to draw.

Two independent sources of noise sit between the model's behavior and the
number the headline test consumes:

  WITHIN-CELL   variance across the K samples drawn from one prompt for one
                group. Averaging K samples shrinks this by 1/K, so it is the
                part that buying more samples actually fixes.

  BETWEEN-PROMPT variance in the true group gap from one prompt to the next.
                Some questions invite a more supportive answer than others.
                This is irreducible by sampling: no value of K touches it,
                because it is real variation in the thing being measured.

The standard error of a per-prompt gap is therefore

    sd(gap) = sqrt( sigma_between^2 + 2 * sigma_within^2 / K )

with the factor 2 because a gap is a difference of two independently sampled
cells. The ratio of the two components decides everything: when between-prompt
variation dominates, extra samples are nearly worthless and K can be small; when
within-cell noise dominates, K is doing real work and cutting it is expensive.

Estimating this from a pilot is what turns "how many generations?" from a round
number into an answer. Choosing K from a pilot affects statistical power only --
it does not touch the hypothesis, the scored axis, or the test -- so the
preregistered analysis stays intact.
"""

import math
from collections import defaultdict


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _variance(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = _mean(values)
    return sum((value - mean) ** 2 for value in values) / (len(values) - 1)


def estimate_components(scored_records: list[dict], group_a: str, group_b: str) -> dict:
    """Estimate within-cell and between-prompt variance from scored responses.

    Within-cell variance is pooled across every cell that has at least two
    usable verdicts. Between-prompt variance is estimated from the observed
    spread of per-prompt gaps, with the measurement noise that the pilot's own
    K contributed subtracted back out -- otherwise the pilot's sampling noise
    would be mistaken for real prompt-to-prompt variation and inflate every
    projection built on it.
    """
    by_cell = defaultdict(list)
    for record in scored_records:
        if record.get("score") is None:
            continue
        key = (record["condition"], record["prompt_id"], record["group"])
        by_cell[key].append(float(record["score"]))

    within_variances = [_variance(v) for v in by_cell.values() if len(v) >= 2]
    sizes = [len(v) for v in by_cell.values() if len(v) >= 2]
    if not within_variances:
        raise ValueError("no cell has two or more usable verdicts")
    sigma_within_sq = _mean(within_variances)
    pilot_k = _mean([float(size) for size in sizes])

    gaps_by_condition = defaultdict(list)
    for condition, prompt_id, group in list(by_cell):
        if group != group_a:
            continue
        a = by_cell.get((condition, prompt_id, group_a))
        b = by_cell.get((condition, prompt_id, group_b))
        if a and b:
            gaps_by_condition[condition].append(_mean(a) - _mean(b))

    observed_gap_variances = {
        condition: _variance(gaps) for condition, gaps in gaps_by_condition.items() if len(gaps) >= 2
    }
    if not observed_gap_variances:
        raise ValueError("need at least two prompts with both groups scored")

    observed = _mean(list(observed_gap_variances.values()))
    # Remove the measurement noise the pilot's own K injected into the gaps.
    sigma_between_sq = max(0.0, observed - 2 * sigma_within_sq / pilot_k)

    return {
        "sigma_within": math.sqrt(sigma_within_sq),
        "sigma_between": math.sqrt(sigma_between_sq),
        "pilot_k": pilot_k,
        "n_cells": len(by_cell),
        "observed_gap_sd": math.sqrt(observed),
        "gaps_by_condition": dict(gaps_by_condition),
    }


def gap_standard_error(sigma_within: float, sigma_between: float, k: int) -> float:
    """sd of a single prompt's group gap at K samples per cell."""
    return math.sqrt(sigma_between**2 + 2 * sigma_within**2 / k)


def precision_table(
    sigma_within: float, sigma_between: float, candidate_k: tuple = (25, 20, 15, 12, 10, 8, 5, 3)
) -> list[dict]:
    """Cost of each candidate K, expressed against the K=25 preregistered value."""
    reference = gap_standard_error(sigma_within, sigma_between, 25)
    rows = []
    for k in candidate_k:
        se = gap_standard_error(sigma_within, sigma_between, k)
        rows.append(
            {
                "k": k,
                "generations": 20 * 2 * 2 * k,
                "gap_sd": se,
                "pct_worse_than_k25": 100.0 * (se / reference - 1.0),
            }
        )
    return rows


def detectable_effect(sigma_within: float, sigma_between: float, k: int, n_prompts: int = 20) -> float:
    """Roughly the smallest mean gap detectable at p<0.05 one-sided, 80% power.

    Uses the normal approximation (z_alpha + z_beta = 1.645 + 0.842 = 2.49),
    which is close enough for planning at n=20 and avoids a scipy dependency.
    """
    return 2.49 * gap_standard_error(sigma_within, sigma_between, k) / math.sqrt(n_prompts)
