"""Peak and detachment measures behind the repaired base-free test.

``candidate_detachment_statistic`` holds the test itself: the observed value,
the permutation null, and the axis report. This module holds the measurements
that test is built from, split out so each file keeps one responsibility.

Each candidate gets one peak, the largest standardized shift it shows on any
axis. A detachment is how far one peak stands above the bulk of the others,
where the bulk is the median of the remaining peaks and the scale is their MAD.
"""

from __future__ import annotations

import numpy as np

__all__ = ["candidate_peaks", "detachment"]

#: Scales the MAD to a standard deviation for a normal sample, the same constant
#: ``deviation_scores.robust_z`` uses, so a detachment and a robust z on this
#: project mean the same thing.
MAD_SCALE = 1.4826


def candidate_peaks(t: np.ndarray) -> np.ndarray:
    """Each candidate's largest standardized shift over the axes."""
    with np.errstate(invalid="ignore"):
        peaks = np.nanmax(np.abs(t), axis=1)
    return np.where(np.all(np.isnan(t), axis=1), np.nan, peaks)


def detachment(peaks: np.ndarray) -> tuple[float, int]:
    """How far the leading peak stands above the bulk of the others, and who leads.

    The bulk is the median of the other peaks and its own MAD. A zero MAD means at
    least half the other peaks are exactly tied, so the leader is separated on any
    scale and the value is infinite. That follows
    ``deviation_scores.robust_z``, which reports the same case as infinite rather
    than as a zeroed score, because zeroing it turns the one case a detector exists
    to catch into a silent negative.
    """
    usable = peaks[~np.isnan(peaks)]
    if usable.size < 3:
        return float("nan"), -1
    lead = int(np.nanargmax(peaks))
    rest = np.delete(peaks, lead)
    rest = rest[~np.isnan(rest)]
    if rest.size < 2:
        return float("nan"), lead
    centre = float(np.median(rest))
    # An infinite peak is the registered test's convention for an effect that held
    # on every instruction. If the bulk is infinite too, the leader is one of a
    # crowd and has not detached from anything, so the answer is zero rather than
    # the difference of two infinities.
    if not np.isfinite(centre):
        return 0.0, lead
    if not np.isfinite(peaks[lead]):
        return float("inf"), lead
    mad = MAD_SCALE * float(np.median(np.abs(rest - centre)))
    gap = float(peaks[lead]) - centre
    if mad <= 0:
        return (float("inf") if gap > 0 else 0.0), lead
    return gap / mad, lead


def _leave_one_out(peaks: np.ndarray) -> list[float]:
    """Each candidate's own detachment against the others, as a diagnostic.

    These are what the bulk looks like from every seat in turn. They are reported
    rather than tested: the test compares the leader against permuted leaders, and
    these values let a reader see whether the leader is alone or merely first among
    a spread-out crowd.
    """
    out = []
    for c in range(peaks.shape[0]):
        rest = np.delete(peaks, c)
        rest = rest[~np.isnan(rest)]
        if rest.size < 2 or np.isnan(peaks[c]):
            out.append(float("nan"))
            continue
        centre = float(np.median(rest))
        mad = MAD_SCALE * float(np.median(np.abs(rest - centre)))
        gap = float(peaks[c]) - centre
        out.append(float("inf") if mad <= 0 and gap > 0 else
                   (0.0 if mad <= 0 else gap / mad))
    return out
