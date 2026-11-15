"""The departure quantity behind the behavior figure, and the scale drawing it.

Split out of ``behavior_bar_figure`` so the panel's arithmetic sits next to the
clip and the colormap that render it: the three have to agree on what one unit
of departure, one doubling against the mixture, means. The figure module
imports all three back and re-exports the colormap.
"""

from __future__ import annotations

import numpy as np
from matplotlib.colors import LinearSegmentedColormap

#: Diverging map for the departure panel. Teal below the mixture, warm above,
#: white at parity. Both arms keep their lightness ramp in greyscale, so the
#: figure survives a monochrome print, and neither arm is red-green.
DEPARTURE_CMAP = LinearSegmentedColormap.from_list(
    "departure",
    ["#0d5c66", "#3f97a1", "#93c9cf", "#f2f2f0", "#e9b98c", "#cf7a3c", "#8f4413"],
)

#: Departures beyond this many doublings are clipped so that one sparse axis
#: cannot flatten the rest of the panel to white.
CLIP_LOG2 = 2.0


def ranked_departures(matrix: np.ndarray, weights: np.ndarray,
                      top_axes: int) -> tuple[np.ndarray, np.ndarray, float]:
    """Pick the axes worth showing and each group's clipped departure on them.

    Returns the column indices of the kept axes, the clipped log2 departure
    matrix restricted to those columns, and the share of the total radius the
    kept axes carry.
    """
    # Rank axes by how much they contribute to the radius, not by raw rate: an
    # axis every group fires equally is loud but carries no differential signal.
    mixture = weights @ matrix
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.divide(matrix, mixture, out=np.ones_like(matrix), where=mixture > 0)
        terms = np.where(matrix > 0, matrix * np.log(ratio), 0.0)
    per_axis = weights @ terms
    # An axis contributing exactly nothing separates no group from any other, and
    # under a sparse condition there are enough of them to fill the plot with
    # named columns carrying no bar. Rank first, then keep only what contributes.
    ranked = np.argsort(-np.abs(per_axis))
    order = np.array([j for j in ranked if per_axis[j] != 0][:top_axes], dtype=int)
    if order.size == 0:
        order = ranked[:top_axes]
    shown_share = (float(np.sum(np.abs(per_axis[order])) / np.sum(np.abs(per_axis)))
                   if np.sum(np.abs(per_axis)) > 0 else 0.0)

    # The departure of each group from the mixture, in doublings. A group that
    # behaves like the rest is 0 and renders white; the sign says which way.
    with np.errstate(divide="ignore", invalid="ignore"):
        departure = np.log2(np.divide(matrix, mixture, out=np.ones_like(matrix),
                                      where=mixture > 0))
    departure = np.clip(np.nan_to_num(departure, nan=0.0, posinf=CLIP_LOG2,
                                      neginf=-CLIP_LOG2), -CLIP_LOG2, CLIP_LOG2)
    return order, departure[:, order], shown_share
