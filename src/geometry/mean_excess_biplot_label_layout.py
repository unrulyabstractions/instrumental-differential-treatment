"""Framing and label placement for the mean-excess biplot.

Split out of ``mean_excess_biplot_figure`` so that module holds only the
arrows, clouds, and rays. Everything here decides where the frame and the
labels sit, judged on rendered pixel boxes rather than anchor distances.
"""

from __future__ import annotations

import numpy as np

from src.geometry.label_collision_nudge import (
    OUTWARD,
    ROTATIONS,
    nudge_label_offsets,
)
from src.geometry.mean_excess_biplot_styling import AXIS_INK, CHIP, HALO

__all__ = ["biplot_label_specs", "frame_biplot_axes", "place_biplot_labels"]


def frame_biplot_axes(ax, points: np.ndarray, lead_tip: np.ndarray) -> None:
    """Limits holding every drawn point, with room for the labels beside them.

    Both sides get margin, because a label on the leftmost arrow runs further
    left still and would otherwise print over the axis label. The lead's side
    gets more, since its label is the longest and sits furthest out.
    """
    lo, hi = points.min(axis=0), points.max(axis=0)
    span = np.maximum(hi - lo, 1e-9)
    extra = 0.30 * span[0]
    ax.set_xlim(lo[0] - 0.20 * span[0] - (0.0 if lead_tip[0] >= 0 else extra),
                hi[0] + 0.20 * span[0] + (extra if lead_tip[0] >= 0 else 0.0))
    ax.set_ylim(lo[1] - 0.10 * span[1], hi[1] + 0.10 * span[1])
    ax.set_aspect("equal", adjustable="datalim")


def _boxes_clash(a, b, pad: float) -> bool:
    """Whether two drawn boxes touch once each is grown by ``pad`` pixels.

    A boxed label's patch reaches past the text extent by its own padding, so
    comparing the bare extents would call two visibly overlapping chips clear.
    """
    return (a.x0 - pad < b.x1 + pad and b.x0 - pad < a.x1 + pad
            and a.y0 - pad < b.y1 + pad and b.y0 - pad < a.y1 + pad)


def _separate_labels(fig, ax, annotations, step_px: float = 5.0,
                     pad_px: float = 3.5, rounds: int = 60) -> None:
    """Nudge overlapping labels apart, judged on their drawn boxes.

    Anchor-to-anchor distance cannot bound a wide boxed label, so this measures
    the rendered boxes and pushes the later label of any overlapping pair
    directly away from the earlier one. Labels are passed in priority order, so
    a principal's name never moves for a behavior's.
    """
    inverse = ax.transData.inverted()
    for _ in range(rounds):
        fig.canvas.draw()
        boxes = [a.get_window_extent() for a in annotations]
        moved = False
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                if not _boxes_clash(boxes[i], boxes[j], pad_px):
                    continue
                centre_i = np.array([boxes[i].x0 + boxes[i].x1,
                                     boxes[i].y0 + boxes[i].y1]) / 2.0
                centre_j = np.array([boxes[j].x0 + boxes[j].x1,
                                     boxes[j].y0 + boxes[j].y1]) / 2.0
                away = centre_j - centre_i
                length = float(np.linalg.norm(away))
                away = away / length if length > 1e-6 else np.array([0.0, 1.0])
                here = np.array(ax.transData.transform(
                    annotations[j].get_position()), dtype=float)
                annotations[j].set_position(
                    tuple(inverse.transform(here + away * step_px)))
                moved = True
        if not moved:
            return


def _fit_labels(fig, ax, labels) -> None:
    """Widen the frame until every label's drawn box sits inside the axes.

    A right-aligned label grows leftward from its anchor, so margin alone
    cannot guarantee it fits. This measures what was actually rendered and
    expands the limits to contain it, which never moves a point.
    """
    fig.canvas.draw()
    inverse = ax.transData.inverted()
    (x0, x1), (y0, y1) = ax.get_xlim(), ax.get_ylim()
    for label in labels:
        box = label.get_window_extent()
        (bx0, by0), (bx1, by1) = inverse.transform([(box.x0 - 4.0, box.y0 - 4.0),
                                                    (box.x1 + 4.0, box.y1 + 4.0)])
        x0, x1 = min(x0, bx0), max(x1, bx1)
        y0, y1 = min(y0, by0), max(y1, by1)
    ax.set_xlim(x0 - 0.02 * (x1 - x0), x1 + 0.02 * (x1 - x0))
    ax.set_ylim(y0 - 0.02 * (y1 - y0), y1 + 0.02 * (y1 - y0))


def biplot_label_specs(rv, tips: np.ndarray, colors: dict, strong: list,
                       compass: list, ray_ends: list, n_labels: int):
    """The label list and its allowed rotations, in priority order.

    Every rejected principal is named, longest arrow first. The remaining label
    slots go to the longest unmarked arrows, so the reader can still see who the
    runners-up are. Principals are set in their own colour, upright; behaviors
    are small italics in a boxed chip, so the two kinds of label never read as
    one list. A behavior's label may only sit beyond its own ray, never swung
    back across the origin where it would appear to name the opposite direction.
    """
    named = sorted(strong, key=lambda i: -np.linalg.norm(tips[i]))
    runners = [i for i in sorted(range(tips.shape[0]),
                                 key=lambda i: -np.linalg.norm(tips[i]))
               if i not in strong][:max(0, n_labels - len(named) + 1)]
    labels = [(rv.name_of(rv.principals[i]), tips[i], colors[rv.principals[i]],
               9.5, "bold", "normal", False) for i in named]
    labels += [(rv.name_of(rv.principals[i]), tips[i], colors[rv.principals[i]],
                8.2, "normal", "normal", False) for i in runners]
    labels += [(e["label"], end, AXIS_INK, 5.9, "normal", "italic", True)
               for e, end in zip(compass, ray_ends)]
    rotations = ([ROTATIONS] * (len(named) + len(runners))) + ([OUTWARD] * len(compass))
    return labels, rotations


def place_biplot_labels(fig, ax, labels: list, rotations: list,
                        per_point: float) -> None:
    """Place every label, push overlaps apart, draw leaders, widen the frame."""
    base = 9.0 * per_point
    offsets = nudge_label_offsets([anchor for _, anchor, *_ in labels],
                                 [anchor for _, anchor, *_ in labels],
                                 base=base, min_sep=26.0 * per_point,
                                 rotations_per_anchor=rotations)
    placed = []
    for (text, anchor, colour, size, weight, style, chip), off in zip(labels, offsets):
        placed.append(ax.annotate(
            text, xy=tuple(np.asarray(anchor) + off), fontsize=size, color=colour,
            weight=weight, style=style,
            ha="left" if off[0] >= 0 else "right",
            va="bottom" if off[1] >= 0 else "top",
            bbox=CHIP if chip else None,
            path_effects=None if chip else HALO, zorder=7))
    _separate_labels(fig, ax, placed)
    # Leaders are drawn last, to wherever the separation pass left each label.
    for (_, anchor, colour, *_), label in zip(labels, placed):
        anchor = np.asarray(anchor, dtype=float)
        reach = np.asarray(label.get_position(), dtype=float) - anchor
        if np.linalg.norm(reach) > 1.4 * base:
            ax.plot([anchor[0], anchor[0] + 0.86 * reach[0]],
                    [anchor[1], anchor[1] + 0.86 * reach[1]],
                    linewidth=0.6, color=colour, alpha=0.45, zorder=6)
    _fit_labels(fig, ax, placed)
