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
and type sizes live in ``mean_excess_biplot_styling``, the label machinery in
``mean_excess_biplot_label_layout``, and the resampling clouds and returned
summary in ``mean_excess_biplot_cloud_statistics``.

A paper render passes a ``BiplotStyle`` sized to the width the paper includes
it at. Its frame is fixed before any label is placed, so the label separation
is measured on the canvas that ships, and the returned ``layout`` record lists
every text element's size and any label that still overlaps another.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.text import Text
from matplotlib.ticker import MaxNLocator

from src.common.file_io import ensure_parent
from src.common.pdf_font_outlining import outline_pdf_fonts
from src.compare.paired_excess_measures import excess_effect
from src.geometry.behavior_cell_vectors import RunVectors
from src.geometry.behavior_space_decomposition import principal_plane, project_points
from src.geometry.mean_excess_biplot_cloud_statistics import (
    biplot_summary,
    bootstrap_plane_clouds,
)
from src.geometry.mean_excess_biplot_label_layout import (
    biplot_label_specs,
    chips_off_their_ray,
    frame_biplot_axes,
    label_clashes,
    leader_clashes,
    place_biplot_labels,
    place_labels_in_frame,
)
from src.geometry.mean_excess_biplot_styling import (
    AXIS_INK,
    DEFAULT_STYLE,
    LEAD_INK,
    PASTELS,
    PRINCIPAL_INKS,
    BiplotStyle,
    biplot_legend,
)
from src.geometry.plane_axis_compass import select_compass_axes

__all__ = ["plot_mean_excess_biplot"]


def _font_context(style: BiplotStyle):
    if not style.font_family:
        return contextlib.nullcontext()
    return plt.rc_context({"font.family": "sans-serif",
                           "font.sans-serif": list(style.font_family)})


def _undrawn_tick_labels(ax) -> set:
    """Tick labels matplotlib keeps for ticks beyond the view, which never print."""
    hidden = set()
    for axis in (ax.xaxis, ax.yaxis):
        lo, hi = sorted(axis.get_view_interval())
        eps = 1e-9 * max(abs(hi - lo), 1.0)
        for tick, loc in zip(axis.get_major_ticks(), axis.get_majorticklocs()):
            if not lo - eps <= loc <= hi + eps:
                hidden.update({id(tick.label1), id(tick.label2)})
    return hidden


def _text_audit(fig, ax, labels: list, ray_ends: list = ()) -> dict:
    """Every printed text element's size, and any that leaves the canvas.

    The sizes are in points at the rendered figure size, which is the printed
    size when the paper includes the figure at that width. It also lists any
    leader that crosses another or runs under a label, and any behavior chip
    set nearer another ray's end than its own.
    """
    fig.canvas.draw()
    canvas = fig.bbox
    hidden = _undrawn_tick_labels(ax)
    texts = []
    for t in fig.findobj(Text):
        if (not t.get_visible() or not t.get_text().strip() or id(t) in hidden):
            continue
        box = t.get_window_extent()
        inside = (box.x0 >= canvas.x0 - 0.5 and box.x1 <= canvas.x1 + 0.5
                  and box.y0 >= canvas.y0 - 0.5 and box.y1 <= canvas.y1 + 0.5)
        texts.append({"text": t.get_text(), "size": float(t.get_fontsize()),
                      "inside": bool(inside)})
    clashes = label_clashes(fig, labels)
    return {"min_size": min((t["size"] for t in texts), default=None),
            "texts": texts,
            "outside_canvas": [t["text"] for t in texts if not t["inside"]],
            "leader_clashes": leader_clashes(fig, labels),
            "chips_off_their_ray": chips_off_their_ray(fig, ax, labels, ray_ends),
            "label_clashes": [(labels[i].get_text(), labels[j].get_text())
                              for i, j in clashes]}


def _needed_margins(fig, ax, figsize, pad_in: float = 0.03) -> tuple:
    """The (left, right, top, bottom) margins, in inches, the drawn text needs."""
    fig.canvas.draw()
    tight = fig.get_tightbbox(fig.canvas.get_renderer())  # inches
    frame = ax.get_window_extent()
    dpi = fig.dpi
    w, h = figsize
    return (frame.x0 / dpi - tight.x0 + pad_in,
            tight.x1 - frame.x1 / dpi + pad_in,
            tight.y1 - frame.y1 / dpi + pad_in,
            frame.y0 / dpi - tight.y0 + pad_in)


def plot_mean_excess_biplot(rv: RunVectors, out_path, n_boot: int = 250,
                            n_axes: int = 6, n_labels: int | None = None,
                            significant: set[str] | None = None,
                            figsize: tuple[float, float] | None = None,
                            legend_loc: str | None = None,
                            title: str | None = None,
                            style: BiplotStyle = DEFAULT_STYLE,
                            outline: bool = True,
                            named_rays: tuple[str, ...] = (),
                            second_axis_up: bool | None = None) -> dict:
    """Write the arrows-over-clouds biplot for one run; return what it drew.

    ``significant`` is every principal the registered test rejects. Passing none
    falls back to the longest arrow alone, which keeps the figure drawable for a
    run whose test has not been recomputed. ``title`` replaces the default
    run-and-level heading, for a run scored at a single judge level where the
    level would name a distinction the data does not carry. ``style`` sets every
    size and placement; ``figsize``, ``legend_loc`` and ``n_labels`` override it.
    ``outline=False`` keeps the PDF's fonts, for measuring its type sizes.
    ``named_rays`` lists axis ids whose rays a paper render names first,
    because a caption reads them back. ``second_axis_up`` fixes the second
    axis's arbitrary sign: the arrow reaching furthest from the first axis
    points up when it is true and down when it is false. Left as None, the
    sign is whatever the SVD returns, which can differ between machines.
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
    if second_axis_up is not None:
        far = int(np.argmax(np.abs(tips[:, 1])))
        if bool(tips[far, 1] > 0) != second_axis_up:
            basis = np.vstack([basis[0], -basis[1]])
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
    figsize = style.figsize if figsize is None else figsize
    legend_loc = style.legend_loc if legend_loc is None else legend_loc
    n_labels = style.n_labels if n_labels is None else n_labels
    alpha = (rv.registered or {}).get("alpha", 0.05)
    heading = (title if title is not None
               else f"{rv.plain_title()}, affordance level {rv.level}")
    if style.short_axis_labels:
        xlabel = f"first direction, {share[0]:.0%} of spread"
        ylabel = f"second, {share[1]:.0%}"
    else:
        xlabel = (f"first direction of the excess, {share[0]:.0%} of its spread "
                  "(reply share)")
        ylabel = f"second direction, {share[1]:.0%} (reply share)"

    def draw(margins):
        fig, ax = plt.subplots(figsize=figsize)
        if margins is not None:
            # The frame is fixed first, so the labels are separated on the
            # canvas that ships rather than on one resized afterwards.
            left, right, top, bottom = margins
            w, h = figsize
            fig.subplots_adjust(left=left / w, right=1.0 - right / w,
                                top=1.0 - top / h, bottom=bottom / h)
        ax.axhline(0, color="#111827", linewidth=0.5, alpha=0.3, zorder=1)
        ax.axvline(0, color="#111827", linewidth=0.5, alpha=0.3, zorder=1)
        for ci, principal in enumerate(rv.principals):
            ax.scatter(clouds[ci, :, 0], clouds[ci, :, 1], s=5, color=colors[principal],
                       alpha=0.24 if principal in marked else 0.18, linewidths=0,
                       zorder=2)

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

        if margins is not None:
            ax.set_xlabel(xlabel, fontsize=style.axis_label_size, labelpad=2.0)
            ax.set_ylabel(ylabel, fontsize=style.axis_label_size, labelpad=2.0)
            ax.set_title(heading, fontsize=style.title_size, color="#111827",
                         pad=style.title_pad)
            ax.tick_params(labelsize=style.tick_size, pad=2.0)
            if style.max_ticks:
                ax.xaxis.set_major_locator(MaxNLocator(nbins=style.max_ticks))
                ax.yaxis.set_major_locator(MaxNLocator(nbins=style.max_ticks))

        drawn = [clouds.reshape(-1, 2), tips] + ([np.array(ray_ends)] if ray_ends else [])
        frame_biplot_axes(ax, np.vstack(drawn), tips[lead], fixed_box=margins is not None)
        fig.canvas.draw()  # fix the transform before measuring points in data units
        x0, x1 = ax.get_xlim()
        per_point = (x1 - x0) / ax.get_window_extent().width * (fig.dpi / 72.0)

        labels, rotations, tiers = biplot_label_specs(
            rv, tips, colors, strong, compass, ray_ends, n_labels, style,
            named_rays=named_rays)
        if style.drop_colliding:
            kept, left_off = place_labels_in_frame(
                fig, ax, labels, rotations, tiers,
                arrows=[((0.0, 0.0), tip, p in marked)
                        for tip, p in zip(tips, rv.principals)],
                rays=[((0.0, 0.0), end) for end in ray_ends],
                frame_steps=style.frame_steps)
        else:
            kept, left_off = place_biplot_labels(fig, ax, labels, rotations,
                                                 per_point), []

        if margins is None:
            ax.set_xlabel(xlabel, fontsize=style.axis_label_size)
            ax.set_ylabel(ylabel, fontsize=style.axis_label_size)
            ax.set_title(heading, fontsize=style.title_size, color="#111827",
                         pad=style.title_pad)
        if style.legend is not None:
            biplot_legend(ax, marked, lead_ink, lead, alpha, n_boot, loc=legend_loc,
                          fontsize=style.legend_size, below=style.legend == "below")
        ax.grid(linewidth=0.3, alpha=0.35)
        ax.set_axisbelow(True)
        if margins is None:
            ax.tick_params(labelsize=style.tick_size)
            fig.subplots_adjust(**dict(zip(("left", "right", "top", "bottom"),
                                           style.subplots)))
        return fig, ax, kept, left_off, ray_ends

    with _font_context(style):
        margins = style.margins
        # A paper render sizes its margins to the text around the axes: tick
        # labels change with the frame the labels settle on, so the margins are
        # measured and the figure drawn again until they agree.
        for attempt in range(8 if margins is not None else 1):
            fig, ax, kept, left_off, ray_ends = draw(margins)
            if margins is None:
                break
            needed = _needed_margins(fig, ax, figsize)
            if all(n <= m + 0.005 for n, m in zip(needed, margins)) and (
                    attempt >= 2 or max(m - n for n, m in zip(needed, margins)) < 0.01):
                break
            plt.close(fig)
            # After two passes the margins only grow, so a tick label that
            # flips width between frames cannot keep the loop from settling.
            margins = (needed if attempt < 2
                       else tuple(max(n, m) for n, m in zip(needed, margins)))
        layout = _text_audit(fig, ax, kept, ray_ends)

        out_path = ensure_parent(out_path)
        fig.savefig(out_path, dpi=200)
        fig.savefig(Path(out_path).with_suffix(".pdf"))
        plt.close(fig)
    if outline:
        # The papers include this PDF, and the author kit rejects Type 3 fonts.
        outline_pdf_fonts(Path(out_path).with_suffix(".pdf"))

    summary = biplot_summary(rv, tips, clouds, marked, share, compass, lead,
                             out_path, n_boot)
    summary["layout"] = layout
    summary["labelled_rays"] = [t.get_text().replace("\n", " ") for t in kept
                                if t.get_bbox_patch() is not None]
    summary["labels_left_off"] = left_off
    return summary
