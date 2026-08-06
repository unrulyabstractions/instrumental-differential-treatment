"""Resampling clouds and the numeric summary behind the mean-excess biplot.

Split out of ``mean_excess_biplot_figure`` so that module holds only the
drawing. Everything here computes the numbers the figure reports; nothing here
touches an axes object.
"""

from __future__ import annotations

import numpy as np

from src.geometry.behavior_space_decomposition import project_points

__all__ = ["biplot_summary", "bootstrap_plane_clouds", "lead_separation"]

SEED = 20260727


def bootstrap_plane_clouds(d: np.ndarray, center: np.ndarray, basis: np.ndarray,
                           n_boot: int) -> np.ndarray:
    """(C, n_boot, 2) plane coordinates of the mean under instruction resampling."""
    n_c, n_i, _ = d.shape
    rng = np.random.default_rng(SEED)
    clouds = np.empty((n_c, n_boot, 2))
    for b, draw in enumerate(rng.integers(0, n_i, size=(n_boot, n_i))):
        clouds[:, b, :] = project_points(np.nanmean(d[:, draw, :], axis=1),
                                         center, basis)
    return clouds


def lead_separation(tips: np.ndarray, clouds: np.ndarray, lead: int) -> dict:
    """How far the longest arrow clears the others, in widths of its own cloud."""
    others = [i for i in range(tips.shape[0]) if i != lead]
    length = float(np.linalg.norm(tips[lead]))
    longest_other = float(np.max(np.linalg.norm(tips[others], axis=1)))
    if length == 0.0:
        return {"lead_length": 0.0, "longest_other_length": longest_other,
                "gap": 0.0, "cloud_width": 0.0, "gap_ratio": 0.0}
    unit = tips[lead] / length
    gap = length - float(np.max(tips[others] @ unit))
    width = float(np.std(clouds[lead] @ unit, ddof=1))
    return {"lead_length": length, "longest_other_length": longest_other,
            "gap": gap, "cloud_width": width,
            "gap_ratio": (gap / width) if width > 0 else 0.0}


def biplot_summary(rv, tips: np.ndarray, clouds: np.ndarray, marked: set,
                   share, compass: list, lead: int, out_path, n_boot: int) -> dict:
    """The dict ``plot_mean_excess_biplot`` returns: what the figure drew."""
    lengths = {p: float(np.linalg.norm(tips[i])) for i, p in enumerate(rv.principals)}
    ranked = sorted(lengths.items(), key=lambda kv: -kv[1])
    # The plane coordinates the explorer redraws interactively. They come from
    # this figure's own basis, so an interactive rebuild matches the PDF rather
    # than mixing planes with another figure. The clouds are thinned to keep the
    # embedded summary small; the shape survives the thinning.
    cloud_keep = min(60, n_boot)
    arrow_coords = {p: [float(tips[i, 0]), float(tips[i, 1])]
                    for i, p in enumerate(rv.principals)}
    cloud_coords = {p: [[round(float(clouds[i, b, 0]), 4), round(float(clouds[i, b, 1]), 4)]
                        for b in range(cloud_keep)]
                    for i, p in enumerate(rv.principals)}
    return {"figure": str(out_path), "n_boot": n_boot,
            "lead": rv.principals[lead],
            "significant": sorted(marked),
            "plane_shares": [float(s) for s in share], "arrow_lengths": lengths,
            "arrow_plane_coordinates": arrow_coords, "clouds": cloud_coords,
            "longest": ranked[0][0], "longest_length": ranked[0][1],
            "runner_up": ranked[1][0], "runner_up_length": ranked[1][1],
            "compass_axes": compass,
            "separation": lead_separation(tips, clouds, lead)}
