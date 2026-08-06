"""The geometry appendix's main figure: principal arrows over their own clouds.

One arrow per candidate principal, from the origin to that principal's mean
excess, drawn in the plane that best holds the run's excess cloud. Behind each
arrow tip sits a faded cloud: where that arrow would have landed had the audit
drawn a different sample of instructions. Dashed rays name the behaviors that
run along the longest arrow, so its direction can be read back as a sentence.

Every principal the registered test rejects at its own alpha is drawn in colour.
That set is usually larger than one: a run whose test names a single principal
can still reject several, and a figure colouring only the longest arrow hides the
rest.

The plane, the arrow lengths, and the compass stay geometric. Only the colouring
consults the test, so the shape the picture shows is still its own. The inks
live in ``mean_excess_biplot_styling``, the label machinery in
``mean_excess_biplot_label_layout``, and the resampling clouds and returned
summary in ``mean_excess_biplot_cloud_statistics``.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from src.common.file_io import ensure_parent
from src.compare.paired_max_statistic import excess_effect
from src.geometry.behavior_cell_vectors import RunVectors
from src.geometry.behavior_space_decomposition import principal_plane, project_points
from src.geometry.mean_excess_biplot_cloud_statistics import (
    biplot_summary,
    bootstrap_plane_clouds,
)
from src.geometry.mean_excess_biplot_label_layout import (
    biplot_label_specs,
    frame_biplot_axes,
    place_biplot_labels,
)
from src.geometry.mean_excess_biplot_styling import (
    AXIS_INK,
    LEAD_INK,
    PASTELS,
    PRINCIPAL_INKS,
    biplot_legend,
)
from src.geometry.plane_axis_compass import select_compass_axes

__all__ = ["plot_mean_excess_biplot"]


def plot_mean_excess_biplot(rv: RunVectors, out_path, n_boot: int = 250,
                            n_axes: int = 6, n_labels: int = 3,
                            significant: set[str] | None = None) -> dict:
    """Write the arrows-over-clouds biplot for one run; return what it drew.

    ``significant`` is every principal the registered test rejects. Passing none
    falls back to the longest arrow alone, which keeps the figure drawable for a
    run whose test has not been recomputed.
    """
    d = excess_effect(rv.target, rv.base)
    n_c, n_i, n_k = d.shape
    center, basis, share = principal_plane(d.reshape(n_c * n_i, n_k),
                                          through_origin=True)
    means = np.stack([np.nanmean(d[c], axis=0) for c in range(n_c)])
    tips = project_points(means, center, basis)

    # The top principal is the longest arrow, the only ordering the picture
    # itself carries.
    lead = int(np.argmax(np.linalg.norm(tips, axis=1)))
    if tips[lead, 0] < 0.0:  # a component's sign is arbitrary: point the lead right
        basis = np.vstack([-basis[0], basis[1]])
        tips = project_points(means, center, basis)
    clouds = bootstrap_plane_clouds(d, center, basis, n_boot)
    compass = select_compass_axes(basis, rv.axes, n_axes=n_axes,
                                  min_angle_deg=12.0, along=tips[lead],
                                  min_cosine=0.7)
    lead_ink = PRINCIPAL_INKS.get(rv.target_seat, LEAD_INK)
    # An empty set is a result, not a missing input: the test rejected nobody and
    # no arrow may be coloured. Only a caller passing nothing falls back to the
    # longest arrow.
    marked = {rv.principals[lead]} if significant is None else set(significant)
    strong = [i for i, p in enumerate(rv.principals) if p in marked]
    colors = {p: (lead_ink if p in marked else PASTELS[i % len(PASTELS)])
              for i, p in enumerate(rv.principals)}

    fig, ax = plt.subplots(figsize=(8.2, 4.3))
    ax.axhline(0, color="#111827", linewidth=0.5, alpha=0.3, zorder=1)
    ax.axvline(0, color="#111827", linewidth=0.5, alpha=0.3, zorder=1)
    for ci, principal in enumerate(rv.principals):
        ax.scatter(clouds[ci, :, 0], clouds[ci, :, 1], s=5, color=colors[principal],
                   alpha=0.24 if principal in marked else 0.18, linewidths=0, zorder=2)

    reach = 0.40 * float(np.max(np.linalg.norm(tips, axis=1)))
    top_along = max((c["along_component"] for c in compass), default=1.0)
    ray_ends = []
    for entry in compass:
        end = (np.array(entry["loading"]) / entry["loading_norm"]) * reach \
            * entry["along_component"] / top_along
        ray_ends.append(end)
        ax.plot([0, end[0]], [0, end[1]], linestyle=(0, (4, 3)), linewidth=0.9,
                color=AXIS_INK, alpha=0.6, zorder=3)
    for ci, principal in enumerate(rv.principals):
        is_marked = principal in marked
        ax.annotate("", xy=tuple(tips[ci]), xytext=(0, 0),
                    arrowprops={"arrowstyle": "-|>", "color": colors[principal],
                                "linewidth": 2.0 if is_marked else 1.1,
                                "shrinkA": 0, "shrinkB": 0,
                                "mutation_scale": 15 if is_marked else 11},
                    zorder=5 if is_marked else 4)

    drawn = [clouds.reshape(-1, 2), tips] + ([np.array(ray_ends)] if ray_ends else [])
    frame_biplot_axes(ax, np.vstack(drawn), tips[lead])
    fig.canvas.draw()  # fix the transform before measuring points in data units
    x0, x1 = ax.get_xlim()
    per_point = (x1 - x0) / ax.get_window_extent().width * (fig.dpi / 72.0)

    labels, rotations = biplot_label_specs(rv, tips, colors, strong, compass,
                                           ray_ends, n_labels)
    place_biplot_labels(fig, ax, labels, rotations, per_point)

    ax.set_xlabel(f"first direction of the excess, {share[0]:.0%} of its spread "
                  "(reply share)", fontsize=9)
    ax.set_ylabel(f"second direction, {share[1]:.0%} (reply share)", fontsize=9)
    ax.set_title(f"{rv.plain_title()}, judge level {rv.level}", fontsize=10.5,
                 color="#111827", pad=9)
    alpha = (rv.registered or {}).get("alpha", 0.05)
    biplot_legend(ax, marked, lead_ink, lead, alpha, n_boot)
    ax.grid(linewidth=0.3, alpha=0.35)
    ax.set_axisbelow(True)
    ax.tick_params(labelsize=8)
    fig.subplots_adjust(left=0.10, right=0.98, top=0.92, bottom=0.13)

    out_path = ensure_parent(out_path)
    fig.savefig(out_path, dpi=200)
    fig.savefig(Path(out_path).with_suffix(".pdf"))
    plt.close(fig)

    return biplot_summary(rv, tips, clouds, marked, share, compass, lead,
                          out_path, n_boot)
