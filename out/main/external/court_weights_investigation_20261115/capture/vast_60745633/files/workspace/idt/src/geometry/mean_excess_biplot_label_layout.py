"""Framing and label placement for the mean-excess biplot.

Split out of ``mean_excess_biplot_figure`` so that module holds only the
arrows, clouds, and rays. Everything here decides where the frame and the
labels sit, judged on rendered pixel boxes rather than anchor distances.
"""

from __future__ import annotations

import itertools
import textwrap

import numpy as np

from src.geometry.label_collision_nudge import (
    OUTWARD,
    ROTATIONS,
    nudge_label_offsets,
)
from src.geometry.mean_excess_biplot_styling import (
    AXIS_INK,
    CHIP,
    DEFAULT_STYLE,
    HALO,
    BiplotStyle,
    name_ink,
)

__all__ = ["biplot_label_specs", "equal_limits", "frame_biplot_axes",
           "chips_off_their_ray", "label_clashes", "leader_clashes",
           "place_biplot_labels",
           "place_labels_in_frame"]


def equal_limits(ax, x0: float, x1: float, y0: float, y1: float) -> None:
    """Limits holding the given box at one data unit per length on both axes.

    The axes box stays where the margins put it; the shorter range is widened
    about its centre until a unit of x and a unit of y print equally long.
    Matplotlib's own ``adjustable="datalim"`` recomputes the limits from the
    data alone at draw time, which can cut off a label the frame was widened
    to hold, so a fixed-box render sets the limits itself.
    """
    box = ax.get_window_extent()
    per_px = max((x1 - x0) / box.width, (y1 - y0) / box.height)
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    half_w, half_h = per_px * box.width / 2.0, per_px * box.height / 2.0
    ax.set_aspect("auto")
    ax.set_xlim(cx - half_w, cx + half_w)
    ax.set_ylim(cy - half_h, cy + half_h)


def frame_biplot_axes(ax, points: np.ndarray, lead_tip: np.ndarray,
                      fixed_box: bool = False) -> None:
    """Limits holding every drawn point, with room for the labels beside them.

    Both sides get margin, because a label on the leftmost arrow runs further
    left still and would otherwise print over the axis label. The lead's side
    gets more, since its label is the longest and sits furthest out. A
    ``fixed_box`` render keeps a thin margin instead, because its labels are
    measured and the frame widened to hold them afterwards.
    """
    lo, hi = points.min(axis=0), points.max(axis=0)
    span = np.maximum(hi - lo, 1e-9)
    if fixed_box:
        equal_limits(ax, lo[0] - 0.05 * span[0], hi[0] + 0.05 * span[0],
                     lo[1] - 0.05 * span[1], hi[1] + 0.05 * span[1])
        return
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


def _drawn_box(label):
    """The label's full drawn box: its chip patch when it has one, else its text."""
    patch = label.get_bbox_patch()
    return patch.get_window_extent() if patch is not None else label.get_window_extent()


def label_clashes(fig, labels, pad_px: float = 1.0) -> list[tuple[int, int]]:
    """Every pair of labels whose drawn boxes overlap, as index pairs."""
    fig.canvas.draw()
    boxes = [_drawn_box(a) for a in labels]
    return [(i, j) for i in range(len(boxes)) for j in range(i + 1, len(boxes))
            if _boxes_clash(boxes[i], boxes[j], pad_px)]


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
                       compass: list, ray_ends: list, n_labels: int,
                       style: BiplotStyle = DEFAULT_STYLE,
                       named_rays: tuple[str, ...] = ()):
    """The label list, its allowed rotations, and each label's tier, in priority order.

    Every rejected principal is named, longest arrow first. The remaining label
    slots go to the longest unmarked arrows, so the reader can still see who the
    runners-up are. Principals are set in their own colour, upright; behaviors
    are small italics in a boxed chip, so the two kinds of label never read as
    one list. A behavior's label may only sit beyond its own ray, never swung
    back across the origin where it would appear to name the opposite direction.

    ``style.max_ray_labels`` names only the rays reaching furthest along the
    lead; the others are still drawn. A paper style places the first ray's name
    right after the flagged principals, since it says what the lead consists of,
    together with any ray in ``named_rays`` (axis ids a caption names).
    The tier says what may be given up when the panel is crowded: 0 never, 1
    only after the frame has been widened, 2 first.
    """
    named = sorted(strong, key=lambda i: -np.linalg.norm(tips[i]))
    runners = [i for i in sorted(range(tips.shape[0]),
                                 key=lambda i: -np.linalg.norm(tips[i]))
               if i not in strong][:max(0, n_labels - len(named) + 1)]
    marked = [(rv.name_of(rv.principals[i]), tips[i], colors[rv.principals[i]],
               style.marked_name_size, "bold", "normal", False) for i in named]
    others = [(rv.name_of(rv.principals[i]), tips[i],
               name_ink(colors[rv.principals[i]], style.runner_name_darken),
               style.other_name_size, "normal", "normal", False) for i in runners]
    rays = list(zip(compass, ray_ends))
    if style.max_ray_labels is not None:
        rays = rays[:style.max_ray_labels]
    chips, chip_ids = [], []
    for e, end in rays:
        text = e["label"]
        if style.wrap_ray_labels:
            text = "\n".join(textwrap.wrap(text, style.wrap_ray_labels))
        chips.append((text, end, AXIS_INK, style.ray_label_size, "normal",
                      "italic", True))
        chip_ids.append(e["axis_id"])
    if not style.drop_colliding:
        labels = marked + others + chips
        rotations = [ROTATIONS] * (len(marked) + len(others)) + [OUTWARD] * len(chips)
        return labels, rotations, [0] * len(labels)
    # The lead's first behavior, and any behavior a caption names, come right
    # after the flagged principals and may widen the frame.
    wanted = [c for i, (c, a) in enumerate(zip(chips, chip_ids))
              if i == 0 or a in named_rays]
    spare = [c for i, (c, a) in enumerate(zip(chips, chip_ids))
             if not (i == 0 or a in named_rays)]
    if style.rays_before_runners:
        # A panel with room names its behaviors before its runners-up.
        rest = spare + others
        rest_rotations = [_BESIDE_RAY] * len(spare) + [ROTATIONS] * len(others)
    else:
        rest = others + spare
        rest_rotations = [ROTATIONS] * len(others) + [_BESIDE_RAY] * len(spare)
    # The longest arrow is always named, flagged or not: the captions read the
    # panel from it.
    longest = int(np.argmax(np.linalg.norm(tips, axis=1)))
    lead_name = []
    if longest not in strong and others and runners[0] == longest:
        lead_name = [others[0]]
        rest = [r for r in rest if r is not others[0]]
        rest_rotations = ([ROTATIONS] * (len(others) - 1) + [_BESIDE_RAY] * len(spare)
                          if not style.rays_before_runners else
                          [_BESIDE_RAY] * len(spare) + [ROTATIONS] * (len(others) - 1))
    labels = marked + lead_name + wanted + rest
    rotations = ([ROTATIONS] * (len(marked) + len(lead_name)) + [_BESIDE_RAY] * len(wanted)
                 + rest_rotations)
    tiers = [0] * (len(marked) + len(lead_name)) + [1] * len(wanted) + [2] * len(rest)
    return labels, rotations, tiers


def place_biplot_labels(fig, ax, labels: list, rotations: list,
                        per_point: float) -> list:
    """Place every label, push overlaps apart, draw leaders, widen the frame.

    The working render's placement: labels are nudged on anchor distance, then
    pushed apart on their drawn boxes, and the frame grows to hold them.
    """
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
    return placed


#: Offsets tried for a label, in points from its anchor, nearest first.
_NAME_STEPS = (2.0, 5.0, 9.0, 14.0, 20.0, 28.0, 38.0)
_CHIP_STEPS = (3.0, 6.0, 10.0, 15.0, 22.0, 30.0, 40.0, 52.0)
#: Further offsets a flagged name may take when no nearer spot is clear.
_FAR_NAME_STEPS = (50.0, 64.0)
#: Where a fixed-frame render may set a behavior's name: beyond the ray's end
#: and within sixty degrees of it, so the name never reads as a neighbor's.
_BESIDE_RAY = (0.0, 15.0, -15.0, 30.0, -30.0, 45.0, -45.0, 60.0, -60.0)
#: The chip's padding, as a fraction of its font size (``CHIP``'s boxstyle).
_CHIP_PAD = 0.18
#: A label further than this from its anchor, in points, gets a leader line.
_LEADER_PX = 9.5


def _rotate(v: np.ndarray, degrees: float) -> np.ndarray:
    rad = np.radians(degrees)
    c, s = np.cos(rad), np.sin(rad)
    return np.array([c * v[0] - s * v[1], s * v[0] + c * v[1]])


def _alignment(v: np.ndarray) -> tuple[str, str]:
    """The text alignment that grows a label away from its anchor along ``v``."""
    ha = "left" if v[0] > 0.3 else ("right" if v[0] < -0.3 else "center")
    va = "bottom" if v[1] > 0.3 else ("top" if v[1] < -0.3 else "center")
    return ha, va


def _box_at(point: np.ndarray, size: tuple[float, float], ha: str, va: str,
            pad: float) -> tuple[float, float, float, float]:
    """Pixel box (x0, y0, x1, y1) of a ``size`` text aligned at ``point``."""
    w, h = size
    x0 = point[0] - {"left": 0.0, "center": w / 2.0, "right": w}[ha]
    y0 = point[1] - {"bottom": 0.0, "center": h / 2.0, "top": h}[va]
    return (x0 - pad, y0 - pad, x0 + w + pad, y0 + h + pad)


def _overlap(a, b, gap: float = 0.0) -> bool:
    return (a[0] - gap < b[2] and b[0] - gap < a[2]
            and a[1] - gap < b[3] and b[1] - gap < a[3])


def _segment_hits_box(p: np.ndarray, q: np.ndarray, box) -> bool:
    """Whether segment pq passes through ``box``, sampled finely enough here."""
    for t in np.linspace(0.0, 1.0, 24):
        x, y = p + t * (q - p)
        if box[0] < x < box[2] and box[1] < y < box[3]:
            return True
    return False


def _segments_cross(p1, p2, q1, q2) -> bool:
    """Whether segments p1p2 and q1q2 cross at a point inside both."""
    def turn(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    d1, d2 = turn(q1, q2, p1), turn(q1, q2, p2)
    d3, d4 = turn(p1, p2, q1), turn(p1, p2, q2)
    return d1 * d2 < 0 and d3 * d4 < 0


def _leader_end(a_px: np.ndarray, box) -> np.ndarray:
    """The point of ``box`` nearest the anchor, where a leader would arrive."""
    return np.array([min(max(a_px[0], box[0]), box[2]), min(max(a_px[1], box[1]), box[3])])


def _segment_enters_box(p, q, box, gap: float = 0.0) -> bool:
    """Whether segment pq runs through the inside of ``box`` grown by ``gap``.

    Exact clipping (Liang and Barsky), so a short leader cannot slip between
    sample points. A segment that only grazes the edge does not count.
    """
    x0, y0, x1, y1 = box[0] - gap, box[1] - gap, box[2] + gap, box[3] + gap
    dx, dy = q[0] - p[0], q[1] - p[1]
    t0, t1 = 0.0, 1.0
    for pk, qk in ((-dx, p[0] - x0), (dx, x1 - p[0]), (-dy, p[1] - y0), (dy, y1 - p[1])):
        if abs(pk) < 1e-12:
            if qk <= 0.0:
                return False
            continue
        t = qk / pk
        if pk < 0.0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 >= t1:
            return False
    return (t1 - t0) * float(np.hypot(dx, dy)) > 0.25


def _point_segment_distance(x, p, q) -> float:
    d = np.asarray(q, dtype=float) - np.asarray(p, dtype=float)
    length2 = float(d @ d)
    t = 0.0 if length2 < 1e-12 else min(max(float((np.asarray(x) - p) @ d) / length2, 0.0), 1.0)
    return float(np.linalg.norm(np.asarray(x) - (np.asarray(p) + t * d)))


def _segments_touch(p1, p2, q1, q2, gap: float) -> bool:
    """Whether two segments cross, or pass within ``gap`` pixels of each other."""
    if _segments_cross(p1, p2, q1, q2):
        return True
    return min(_point_segment_distance(p1, q1, q2), _point_segment_distance(p2, q1, q2),
               _point_segment_distance(q1, p1, p2), _point_segment_distance(q2, p1, p2)) < gap


def _box_distance(x, box) -> float:
    """Distance in pixels from point ``x`` to the nearest point of ``box``."""
    return float(np.linalg.norm(np.asarray(x) - _leader_end(np.asarray(x), box)))


#: How close, in pixels, two leaders, or a leader and a label, may come.
_LEADER_GAP = 1.5
#: How far past its end, in points, a ray still points at a chip.
_RAY_REACH_PT = 20.0
#: How far past its tip, in points, an arrow still points at a chip.
_ARROW_REACH_PT = 45.0
#: The longest leader, in points, a behavior chip may hang from.
_CHIP_LEADER_MAX_PT = 30.0
#: The widest angle, in degrees, between a chip's leader and its own ray.
_CHIP_LEADER_MAX_DEG = 45.0


#: The widest angle, in degrees, between a chip's centre and its own ray,
#: both seen from the ray's end.
_CHIP_SIDE_MAX_DEG = 80.0


def _chip_side_problem(a_px, box, origin) -> str | None:
    """Why a chip at ``box`` sits off to the side of its ray ending at ``a_px``.

    Seen from the ray's end, the chip's centre lies ahead along the ray, so
    the name carries the ray on rather than sitting beside a neighbor.
    """
    centre = np.array([(box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0])
    ahead = centre - np.asarray(a_px, dtype=float)
    ray = np.asarray(a_px, dtype=float) - np.asarray(origin, dtype=float)
    if float(np.linalg.norm(ahead)) < 1e-6 or float(np.linalg.norm(ray)) < 1e-6:
        return None
    cosine = float(ahead @ ray) / float(np.linalg.norm(ahead)) / float(np.linalg.norm(ray))
    if cosine < np.cos(np.radians(_CHIP_SIDE_MAX_DEG)) - 1e-6:
        return (f"a chip centred {np.degrees(np.arccos(min(1.0, max(-1.0, cosine)))):.0f}"
                " degrees off its ray")
    return None


def _chip_leader_problem(a_px, end, origin, px_per_pt: float) -> str | None:
    """Why a chip's leader from ray end ``a_px`` to ``end`` misplaces it, or None.

    A chip sits next to its own ray: its leader is short, and it carries on
    in the ray's own direction rather than swinging back toward a neighbor.
    """
    leader = np.asarray(end, dtype=float) - np.asarray(a_px, dtype=float)
    length = float(np.linalg.norm(leader))
    if length > _CHIP_LEADER_MAX_PT * px_per_pt + 0.5:
        return f"a {length / px_per_pt:.0f}pt leader"
    ray = np.asarray(a_px, dtype=float) - np.asarray(origin, dtype=float)
    if length > 1e-6 and float(np.linalg.norm(ray)) > 1e-6:
        cosine = float(leader @ ray) / length / float(np.linalg.norm(ray))
        if cosine < np.cos(np.radians(_CHIP_LEADER_MAX_DEG)) - 1e-6:
            return f"a leader {np.degrees(np.arccos(min(1.0, max(-1.0, cosine)))):.0f} degrees off its ray"
    return None


def _rays_a_chip_reads_as(a_px, box, has_leader: bool, ray_px, reach_px: float,
                          gap: float = _LEADER_GAP) -> list[int]:
    """The other rays a chip at ``box`` would appear to name.

    A ray that runs into the chip, or would within ``reach_px`` past its end,
    points at it. A short ray points only as far past its end as it is long. A chip with no leader is read as naming the nearest ray end,
    so another end nearer than its own also counts. ``a_px`` is the chip's own
    ray end; ``ray_px`` holds every drawn ray's (origin, end) in pixels.
    """
    found = []
    own = _box_distance(a_px, box)
    for i, (p, q) in enumerate(ray_px):
        if np.linalg.norm(q - a_px) <= 0.5:
            continue
        d = q - p
        length = float(np.linalg.norm(d))
        far = q + d / length * min(reach_px, length) if length > 1e-9 else q
        if (_segment_enters_box(p, far, box, gap=gap)
                or (not has_leader and _box_distance(q, box) < own)):
            found.append(i)
    return found


def _arrows_a_chip_reads_as(a_px, box, has_leader: bool, arrow_px, reach_px: float,
                            gap: float = _LEADER_GAP) -> list[int]:
    """The arrows a behavior chip at ``box`` would appear to name.

    A chip names its own ray's end. An arrow whose tip points into the chip
    within ``reach_px`` past the tip reads as the chip's subject. A chip with
    no leader also reads as naming an arrow whose tip lies nearer the chip
    than the chip's own ray end. ``arrow_px`` holds every arrow's (origin,
    tip) in pixels.
    """
    found = []
    own = _box_distance(a_px, box)
    for i, (p, q) in enumerate(arrow_px):
        d = np.asarray(q, dtype=float) - np.asarray(p, dtype=float)
        length = float(np.linalg.norm(d))
        if length <= 1e-9:
            continue
        far = q + d / length * reach_px
        if (_segment_enters_box(q, far, box, gap=gap)
                or (not has_leader and _box_distance(q, box) < own)):
            found.append(i)
    return found


def _greedy_placement(fig, ax, labels, rotations, tiers, sizes, pads, arrows,
                      rays=(), order=None):
    """One pass of the fixed-frame placement; returns (placements, failures, costs).

    Each label takes the nearest candidate spot that lies inside the axes and
    clear of every label already placed and of every arrow tip. A leader may
    not cross or touch another leader, nor run under another label, and a
    label may not sit on a leader already drawn: a crossed leader hands a
    name to the wrong ray. A spot that reads as naming another ray comes
    last: a leader crossing another ray, a chip that another ray runs into or
    points at, or a chip without a leader nearer another ray's end than its
    own. Then a spot whose leader crosses no arrow comes first. ``rays`` are
    every drawn ray's (origin, end) in data units. ``order`` is the order the
    labels are placed in, by index; ``costs`` holds each placed label's
    (arrows covered, readings as another ray, arrows crossed).
    """
    fig.canvas.draw()
    to_px = ax.transData.transform
    frame = ax.get_window_extent()
    inner = (frame.x0 + 2.0, frame.y0 + 2.0, frame.x1 - 2.0, frame.y1 - 2.0)
    origin = to_px((0.0, 0.0))
    segments = [(to_px(tuple(a)), to_px(tuple(b)), bool(flagged))
                for a, b, flagged in arrows]
    tips = [b for _, b, _ in segments]
    ray_px = [(to_px(tuple(a)), to_px(tuple(b))) for a, b in rays]
    px_per_pt = fig.dpi / 72.0
    taken, placements, failures, costs = [], {}, [], {}
    #: Every leader drawn so far, as (anchor, end) in pixels.
    leaders = []
    #: Runner-up names (tier 2, not a chip) arrive longest arrow first. Once
    #: one finds no spot, every shorter one is left off too, so a panel never
    #: names a shorter arrow beside an unnamed longer one.
    runner_dropped = False
    for k in (range(len(labels)) if order is None else order):
        spec, allowed = labels[k], rotations[k]
        anchor, chip = spec[1], spec[6]
        runner = tiers[k] > 1 and not chip
        if runner and runner_dropped:
            failures.append(k)
            continue
        a_px = to_px(tuple(anchor))
        outward = a_px - origin
        norm = float(np.linalg.norm(outward))
        outward = outward / norm if norm > 1e-9 else np.array([1.0, 0.0])
        best = None
        steps = _CHIP_STEPS if chip else _NAME_STEPS
        if not chip and tiers[k] == 0 and spec[4] == "bold":
            # A flagged name may sit further off, on a leader, rather than
            # over a dashed ray.
            steps = steps + _FAR_NAME_STEPS
        if not chip and tiers[k] > 0:
            # A runner-up's name set far off or behind its arrow reads as
            # naming another one, so it stays close or is left off.
            steps = tuple(s for s in steps if s <= 14.0)
            allowed = tuple(d for d in allowed if abs(d) <= 110.0)
        for step in steps:
            for degrees in allowed:
                v = _rotate(outward, degrees)
                ha, va = _alignment(v)
                point = a_px + v * step * px_per_pt
                for text, size in sizes[k]:
                    box = _box_at(point, size, ha, va, pads[k])
                    if not (box[0] >= inner[0] and box[1] >= inner[1]
                            and box[2] <= inner[2] and box[3] <= inner[3]):
                        continue
                    if any(_overlap(box, other, gap=2.0) for other in taken):
                        continue
                    if any(_overlap(box, (t[0] - 3, t[1] - 3, t[0] + 3, t[1] + 3))
                           for t in tips):
                        continue
                    # No label may sit on a leader already drawn.
                    if any(_segment_enters_box(p, q, box, gap=_LEADER_GAP)
                           for p, q in leaders):
                        continue
                    hard = sum(_segment_hits_box(p, q, box) for p, q, _ in segments)
                    wrong = soft = 0
                    if not chip:
                        # A name set across a dashed ray hides it, and a name
                        # nearer another arrow's tip than its own reads as
                        # naming that arrow.
                        wrong += sum(_segment_enters_box(p, q, box) for p, q in ray_px)
                        own = _box_distance(a_px, box)
                        wrong += sum(1 for t in tips
                                     if np.linalg.norm(t - a_px) > 0.5
                                     and _box_distance(t, box) < own)
                    leader = None
                    # A label set off from its anchor gets a leader. It may not
                    # cross another leader or run under another label. It must
                    # not cut a flagged arrow, and it avoids the others.
                    if step > _LEADER_PX:
                        end = _leader_end(a_px, box)
                        leader = (a_px, end)
                        if any(_segments_touch(a_px, end, p, q, _LEADER_GAP)
                               for p, q in leaders):
                            continue
                        if any(_segment_enters_box(a_px, end, other, gap=_LEADER_GAP)
                               for other in taken):
                            continue
                        for p, q, flagged in segments:
                            if _segments_cross(a_px, end, p, q):
                                hard += flagged
                                soft += not flagged
                        # A leader crossing a neighbor's ray reads as naming it.
                        wrong += sum(_segments_cross(a_px, end, p, q)
                                     for p, q in ray_px
                                     if np.linalg.norm(q - a_px) > 0.5)
                        # A chip hangs close to its own ray, in its direction,
                        # and its leader crosses no arrow on the way.
                        if chip and (_chip_leader_problem(a_px, end, origin, px_per_pt)
                                     or hard or soft):
                            continue
                    if chip:
                        # A chip sits ahead of its own ray's end.
                        if _chip_side_problem(a_px, box, origin):
                            continue
                        # A chip another ray points at reads as that ray's.
                        wrong += len(_rays_a_chip_reads_as(
                            a_px, box, leader is not None, ray_px,
                            _RAY_REACH_PT * px_per_pt))
                        # A chip an arrow points at, or that sits nearer an
                        # arrow's tip than its own ray's end, reads as naming
                        # that arrow.
                        wrong += len(_arrows_a_chip_reads_as(
                            a_px, box, leader is not None,
                            [(p, q) for p, q, _ in segments],
                            _ARROW_REACH_PT * px_per_pt))
                        # A behavior's name is left off rather than set where
                        # it reads as another ray's.
                        if wrong:
                            continue
                    # Only a flagged principal's name may cover an arrow, and
                    # only when no clear spot is left; other labels stay off.
                    if hard and tiers[k] > 0:
                        continue
                    # A name the panel can do without is left off rather
                    # than set where it reads as another ray's.
                    if wrong and tiers[k] > 1:
                        continue
                    cost = (hard, wrong, soft)
                    if best is None or cost < best[0]:
                        best = (cost, point, ha, va, text, box, leader)
                    if cost == (0, 0, 0):
                        break
                if best is not None and best[0] == (0, 0, 0):
                    break
            if best is not None and best[0][:2] == (0, 0):
                break
        if best is None:
            failures.append(k)
            runner_dropped = runner_dropped or runner
            continue
        taken.append(best[5])
        if best[6] is not None:
            leaders.append(best[6])
        placements[k] = best[1:6]
        costs[k] = best[0]
    return placements, failures, costs


def _ordered_placement(fig, ax, labels, rotations, tiers, sizes, pads, arrows,
                       rays=()):
    """The greedy placement, retried over orders of the tier-0 and 1 labels.

    The default order runs first and is kept when every label of tier 0 and
    1 finds a clear spot that reads as its own. Otherwise each order of the
    flagged names and of the tier-1 labels is tried, the flagged names first,
    then after the tier-1 labels, the optional labels always last. The order
    dropping, misreading, or covering fewest tier-0 and tier-1 labels wins,
    so a behavior goes first only when every flagged name still fits.
    Returns (placements, failures).
    """
    def run(order):
        return _greedy_placement(fig, ax, labels, rotations, tiers, sizes, pads,
                                 arrows, rays, order)

    def score(result):
        _, fails, costs = result
        # A name over an arrow is worse than a dropped behavior chip, and
        # both are worse than a name that reads as another's.
        return (sum(tiers[k] == 0 for k in fails),
                sum(int(c[0]) for k, c in costs.items() if tiers[k] <= 1),
                sum(tiers[k] == 1 for k in fails),
                sum(int(c[1]) for k, c in costs.items() if tiers[k] <= 1),
                len(fails))

    base = list(range(len(labels)))
    best = run(base)
    zeros = [k for k in base if tiers[k] == 0]
    ones = [k for k in base if tiers[k] == 1]
    tail = [k for k in base if tiers[k] > 1]
    if score(best)[:4] != (0, 0, 0, 0) and len(zeros) <= 5 and len(ones) <= 5:
        pairs = [(list(z), list(o)) for z in itertools.permutations(zeros)
                 for o in itertools.permutations(ones)]
        orders = ([z + o + tail for z, o in pairs]
                  + [o + z + tail for z, o in pairs if o])
        for order in orders[1:]:
            result = run(order)
            if score(result) < score(best):
                best = result
            if score(best)[:4] == (0, 0, 0, 0):
                break
    return best[0], best[1]


def chips_off_their_ray(fig, ax, labels, ray_ends, arrow_tips=()) -> list[str]:
    """Every behavior chip, as drawn, that reads as naming another ray or an arrow.

    The same test the placement ranks spots by, run on the drawn chip patch:
    another ray runs into the chip or points at it, a chip with no leader sits
    nearer another ray's end than its own, a leader crosses another ray, or an
    arrow (``arrow_tips``, in data units, each drawn from the origin) points
    at the chip or ends nearer it than the chip's own ray end.
    """
    fig.canvas.draw()
    to_px = ax.transData.transform
    origin = np.asarray(to_px((0.0, 0.0)), dtype=float)
    ray_px = [(origin, np.asarray(to_px(tuple(e)), dtype=float)) for e in ray_ends]
    reach_px = _RAY_REACH_PT * fig.dpi / 72.0
    found = []
    for label in labels:
        anchor = getattr(label, "biplot_anchor", None)
        patch = label.get_bbox_patch()
        if patch is None or anchor is None:
            continue
        b = patch.get_window_extent()
        box = (b.x0, b.y0, b.x1, b.y1)
        a_px = np.asarray(to_px(tuple(anchor)), dtype=float)
        line = getattr(label, "biplot_leader", None)
        name = label.get_text().replace("\n", " ")
        side = _chip_side_problem(a_px, box, origin)
        if side:
            found.append(f"{name!r} sits as {side}")
        # The audit allows the drawn patch's own 1 px of antialiased edge.
        for i in _rays_a_chip_reads_as(a_px, box, line is not None, ray_px,
                                       reach_px, gap=0.5):
            found.append(f"{name!r} reads as naming the ray ending at "
                         f"{tuple(np.round(ray_ends[i], 3))}")
        arrow_px = [(origin, np.asarray(to_px(tuple(t)), dtype=float)) for t in arrow_tips]
        for i in _arrows_a_chip_reads_as(a_px, box, line is not None, arrow_px,
                                         _ARROW_REACH_PT * fig.dpi / 72.0, gap=0.5):
            found.append(f"{name!r} reads as naming the arrow ending at "
                         f"{tuple(np.round(arrow_tips[i], 3))}")
        if line is not None:
            xy = line.get_transform().transform(np.column_stack(line.get_data()))
            why = _chip_leader_problem(xy[0], xy[-1], origin, fig.dpi / 72.0)
            if why:
                found.append(f"{name!r} hangs from {why}")
            for i, (p, q) in enumerate(ray_px):
                if (np.linalg.norm(q - a_px) > 0.5
                        and _segments_cross(xy[0], xy[-1], p, q)):
                    found.append(f"the leader of {name!r} crosses the ray ending at "
                                 f"{tuple(np.round(ray_ends[i], 3))}")
    return found


def leader_clashes(fig, labels, gap: float = 1.0) -> list[str]:
    """Every drawn leader that crosses another leader or runs under a label.

    Measured on the canvas as drawn, from the leader each label carries on its
    ``biplot_leader`` attribute, so it checks what ships rather than what the
    placement intended. A label with no leader is still checked as an obstacle.
    """
    fig.canvas.draw()
    boxes = [_drawn_box(a) for a in labels]
    boxes = [(b.x0, b.y0, b.x1, b.y1) for b in boxes]
    lines = []
    for i, label in enumerate(labels):
        line = getattr(label, "biplot_leader", None)
        if line is None:
            continue
        xy = line.get_transform().transform(np.column_stack(line.get_data()))
        lines.append((i, xy[0], xy[-1]))
    found = []
    for n, (i, p, q) in enumerate(lines):
        name = labels[i].get_text().replace("\n", " ")
        for j, box in enumerate(boxes):
            if j != i and _segment_enters_box(p, q, box, gap=gap):
                found.append(f"the leader of {name!r} runs under "
                             f"{labels[j].get_text().replace(chr(10), ' ')!r}")
        for i2, p2, q2 in lines[n + 1:]:
            if _segments_touch(p, q, p2, q2, gap):
                found.append(f"the leader of {name!r} crosses the leader of "
                             f"{labels[i2].get_text().replace(chr(10), ' ')!r}")
    return found


def _measure(fig, ax, labels) -> tuple[list, list]:
    """Each label's text variants with their drawn sizes in pixels, and its padding.

    A behavior's name may be set on one line or broken over two or three, so
    the placement can take whichever shape fits; a principal's name stays whole.
    """
    renderer = fig.canvas.get_renderer()
    sizes, pads = [], []
    for text, _, _, size, weight, style, chip in labels:
        variants = [text]
        if chip:
            flat = text.replace("\n", " ")
            for option in (flat, "\n".join(textwrap.wrap(flat, 16))):
                if option not in variants:
                    variants.append(option)
        shapes = []
        for option in variants:
            probe = ax.text(0.0, 0.0, option, fontsize=size, weight=weight, style=style)
            box = probe.get_window_extent(renderer)
            probe.remove()
            shapes.append((option, (box.width, box.height)))
        sizes.append(shapes)
        pads.append(_CHIP_PAD * size * fig.dpi / 72.0 + 1.0 if chip else 1.0)
    return sizes, pads


def place_labels_in_frame(fig, ax, labels: list, rotations: list, tiers: list,
                          arrows: list, zoom: float = 1.12, max_zoom: int = 10,
                          widen_for_rays: int = 3, rays: list = (),
                          frame_steps: int | None = None) -> tuple[list, list]:
    """Place labels on a fixed canvas without letting any two overlap.

    Each label gets the nearest free spot beside its anchor inside the axes. A
    tier-0 label that finds none widens the frame and every label is placed
    again; a tier-1 label may widen it ``widen_for_rays`` times; a tier-2 label
    that finds no spot is left off. ``arrows`` are (origin, tip, flagged)
    triples in data units: no label covers an arrow or its tip, and no leader
    crosses a flagged one. ``rays`` are every drawn ray's (origin, end) in data
    units, so a behavior's name stays nearer its own ray than any other. No
    leader crosses another leader or runs under a label. Each drawn label
    carries its leader line, or None, on ``biplot_leader``. ``frame_steps``
    fixes the frame instead: it is widened exactly that many times, and a
    label that finds no spot there is left off, or for a flagged name raises,
    rather than moving the data. Returns the drawn labels and the texts left
    off.
    """
    sizes, pads = _measure(fig, ax, labels)

    def attempt():
        return _ordered_placement(fig, ax, labels, rotations, tiers, sizes, pads,
                                  arrows, rays)

    def widen():
        (x0, x1), (y0, y1) = ax.get_xlim(), ax.get_ylim()
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        hw, hh = zoom * (x1 - x0) / 2.0, zoom * (y1 - y0) / 2.0
        equal_limits(ax, cx - hw, cx + hw, cy - hh, cy + hh)

    if frame_steps is not None:
        for _ in range(frame_steps):
            widen()
        placements, failures = attempt()
        must = [k for k in failures if tiers[k] == 0]
        if must:
            raise RuntimeError("a flagged principal's name finds no free spot: "
                               + ", ".join(labels[k][0] for k in must))
    # The tightest frame that holds every flagged principal's name.
    for tries in range(0 if frame_steps is not None else max_zoom + 1):
        placements, failures = attempt()
        must = [k for k in failures if tiers[k] == 0]
        if not must:
            break
        if tries == max_zoom:
            raise RuntimeError("a flagged principal's name finds no free spot: "
                               + ", ".join(labels[k][0] for k in must))
        widen()
    # The lead's behavior may widen it a little further. When that does not
    # make room either, the tighter frame is kept and the name left off.
    if frame_steps is None and any(tiers[k] == 1 for k in failures):
        kept_limits = (ax.get_xlim(), ax.get_ylim())
        for _ in range(widen_for_rays):
            widen()
            wider, wider_failures = attempt()
            if not any(tiers[k] <= 1 for k in wider_failures):
                placements, failures = wider, wider_failures
                break
        else:
            ax.set_xlim(*kept_limits[0])
            ax.set_ylim(*kept_limits[1])
            placements, failures = attempt()
    inverse = ax.transData.inverted()
    drawn = []
    for k in sorted(placements):
        _, anchor, colour, size, weight, style, chip = labels[k]
        point, ha, va, text, box = placements[k]
        xy = inverse.transform(point)
        drawn.append(ax.annotate(
            text, xy=tuple(xy), fontsize=size, color=colour, weight=weight,
            style=style, ha=ha, va=va,
            multialignment="left" if ha == "center" else ha,
            bbox=CHIP if chip else None, path_effects=None if chip else HALO,
            zorder=7))
        # The leader runs from the anchor to the nearest edge of the label,
        # the same segment the placement checked against the arrows.
        a_px = ax.transData.transform(tuple(anchor))
        drawn[-1].biplot_leader = None
        drawn[-1].biplot_anchor = tuple(np.asarray(anchor, dtype=float))
        if np.linalg.norm(np.asarray(point) - a_px) > _LEADER_PX * fig.dpi / 72.0:
            end = inverse.transform(_leader_end(a_px, box))
            (drawn[-1].biplot_leader,) = ax.plot(
                [anchor[0], end[0]], [anchor[1], end[1]],
                linewidth=0.6, color=colour, alpha=0.45, zorder=6)
    left_off = [labels[k][0].replace("\n", " ") for k in failures]
    return drawn, left_off

