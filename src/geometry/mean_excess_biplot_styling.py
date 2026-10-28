"""Inks, chips, type sizes, and the legend of the mean-excess biplot.

Split out of ``mean_excess_biplot_figure`` so that module holds only the
geometry and the drawing order. Everything here decides how the figure looks,
never what it shows.

A ``BiplotStyle`` holds every size the figure prints at. The default is the
wide working render each run's geometry directory keeps. The paper styles are
rendered at the physical width the paper includes them at, so a size set here
is the size that prints: the author kit asks for nine-point type or larger in
every figure.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from matplotlib import patheffects
from matplotlib.lines import Line2D

__all__ = ["AXIS_INK", "CHIP", "DEFAULT_STYLE", "HALO", "LEAD_INK", "NAME_INK", "PASTELS",
           "PRINCIPAL_INKS", "BiplotStyle", "biplot_legend", "name_ink", "paper_style"]

#: One ink per audited checkpoint, so the reader can tell at a glance which
#: model a figure belongs to. The three calibration conditions share a model
#: and therefore share an ink.
PRINCIPAL_INKS = {"gen9_1p5b": "#C2447E", "organism_a": "#1F6F8B",
                  "organism_b": "#B05A1E", "organism_c": "#6B4E9C"}
LEAD_INK = "#C2447E"
#: One desaturated pastel per principal, by index so a colour means the same
#: principal in every figure of a run. Ten, so each gets its own.
PASTELS = ("#A9A3AE", "#9DAAA0", "#B7AA9B", "#97A5B4", "#B49DA2",
           "#ADB2A4", "#A39CB8", "#C0B7A8", "#8F9AA0", "#B9A9B4")
AXIS_INK = "#5B6472"
#: The dark ink a runner-up name is pulled toward when a panel asks for
#: stronger names (``BiplotStyle.runner_name_darken``).
NAME_INK = "#1F2937"
#: Labels sit over faded clouds, so every one carries a white halo.
HALO = [patheffects.withStroke(linewidth=2.6, foreground="white", alpha=0.9)]
#: A behavior label is a boxed chip, which no principal's name ever is.
CHIP = {"boxstyle": "round,pad=0.18", "facecolor": "white",
        "edgecolor": "#B9C0CA", "linewidth": 0.45, "alpha": 0.9}

#: A narrower sans than matplotlib's default, so nine-point labels fit a
#: column-wide panel. The first family installed wins.
PAPER_FONT = ("Arial", "Liberation Sans", "Helvetica", "DejaVu Sans")


@dataclass(frozen=True)
class BiplotStyle:
    """Every size and placement choice of one biplot render.

    Sizes are in points at the rendered ``figsize``, so a figure included at
    exactly that width prints them unchanged. ``margins`` are in inches
    (left, right, top, bottom), which keeps the frame fixed while labels move.
    ``legend`` is ``"inside"`` (in the axes, at ``legend_loc``), ``"below"`` (a
    strip under the axis label) or ``None`` (the caption carries the key).
    ``max_ray_labels`` caps how many rays carry a name; every ray is drawn
    either way. ``drop_colliding`` removes a lower-priority label that cannot be
    placed clear of the others, instead of printing two labels over each other.
    ``frame_steps`` fixes how many times the frame is widened past the data, by
    1.12 each time, so the labels fit around a frame that never moves for them;
    ``None`` lets a label that finds no spot widen it.
    """

    figsize: tuple[float, float] = (8.2, 4.3)
    font_family: tuple[str, ...] | None = None
    title_size: float = 10.5
    axis_label_size: float = 9.0
    tick_size: float = 8.0
    marked_name_size: float = 9.5
    other_name_size: float = 8.2
    ray_label_size: float = 5.9
    legend: str | None = "inside"
    legend_loc: str = "best"
    legend_size: float = 7.8
    short_axis_labels: bool = False
    max_ray_labels: int | None = None
    wrap_ray_labels: int | None = None
    n_labels: int = 3
    drop_colliding: bool = False
    rays_before_runners: bool = False
    max_ticks: int | None = None
    margins: tuple[float, float, float, float] | None = None
    #: The old fractional margins, kept for the default render.
    subplots: tuple[float, float, float, float] = (0.10, 0.98, 0.92, 0.13)
    title_pad: float = 9.0
    frame_steps: int | None = None
    #: How far an unflagged name's ink moves from its arrow's pastel toward
    #: ``NAME_INK``: 0 keeps the pastel, 1 prints it in ``NAME_INK``. A panel
    #: where no arrow is flagged prints only pastel names, which read faintly.
    runner_name_darken: float = 0.0


DEFAULT_STYLE = BiplotStyle()


def paper_style(width_in: float, height_in: float, *, legend: str | None = None,
                ray_labels: int = 3, n_labels: int = 3, wrap: int = 24,
                short_axis_labels: bool = True, rays_before_runners: bool = False,
                margins: tuple[float, float, float, float] = (0.50, 0.06, 0.24, 0.40),
                frame_steps: int = 0) -> BiplotStyle:
    """A paper render at its printed size, with no text under nine points.

    ``margins`` is only the first guess: the render measures the text around
    the axes and redraws with the margins it needs. ``frame_steps`` fixes the
    frame, so a label change never rescales the data.
    """
    return replace(
        DEFAULT_STYLE, figsize=(width_in, height_in), font_family=PAPER_FONT,
        title_size=9.5, axis_label_size=9.0, tick_size=9.0,
        marked_name_size=9.5, other_name_size=9.0, ray_label_size=9.0,
        legend=legend, legend_loc="lower center", legend_size=9.0,
        short_axis_labels=short_axis_labels, max_ray_labels=ray_labels,
        wrap_ray_labels=wrap, n_labels=n_labels, drop_colliding=True,
        rays_before_runners=rays_before_runners,
        max_ticks=5, margins=margins, title_pad=4.0, frame_steps=frame_steps)


def name_ink(colour: str, darken: float) -> str:
    """``colour`` moved ``darken`` of the way toward ``NAME_INK``, as a hex ink."""
    if darken <= 0:
        return colour
    a = [int(colour.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    b = [int(NAME_INK.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    mixed = [round(x + (y - x) * min(darken, 1.0)) for x, y in zip(a, b)]
    return "#" + "".join(f"{v:02X}" for v in mixed)


def biplot_legend(ax, marked: set, lead_ink: str, lead: int, alpha: float,
                  n_boot: int, loc: str = "best", fontsize: float = 7.8,
                  below: bool = False, any_unmarked: bool = True) -> None:
    """Attach the legend: significance colouring, the clouds, and the compass.

    ``below`` sets it as a two-column strip under the axes rather than inside
    them, so it can never sit on a cloud or a label. ``any_unmarked`` is false
    when every arrow is flagged, and the "not significant" key is then left
    out, since no arrow carries it.
    """
    pack = PASTELS[(lead + 1) % len(PASTELS)]
    plural = "groups" if len(marked) > 1 else "group"
    handles = []
    if marked:
        handles.append(Line2D([], [], color=lead_ink, linewidth=2.0,
                              label=f"significant candidate {plural} at {1 - alpha:.0%}"))
    if any_unmarked or not marked:
        handles.append(Line2D(
            [], [], color=pack, linewidth=1.1,
            label="candidate groups" if not marked else "not significant"))
    if not marked:
        handles.append(Line2D([], [], color="none",
                              label=f"none significant at {1 - alpha:.0%}"))
    handles += [
        Line2D([], [], color=pack, marker="o", linestyle="none", markersize=4,
               alpha=0.5, label=f"{n_boot} redrawn prompt samples"),
        Line2D([], [], color=AXIS_INK, linestyle=(0, (4, 3)), linewidth=0.9,
               label="behavior axis, rescaled"),
    ]
    if below:
        # Hung from just under the axis label, centred on the axes.
        fig = ax.figure
        fig.canvas.draw()
        label_box = ax.xaxis.label.get_window_extent()
        frame = ax.get_window_extent()
        fig.legend(handles=handles, fontsize=fontsize, loc="upper center",
                   ncol=2, frameon=False, borderaxespad=0.0, borderpad=0.2,
                   handlelength=1.8, columnspacing=1.4,
                   bbox_to_anchor=((frame.x0 + frame.x1) / 2.0 / fig.bbox.width,
                                   (label_box.y0 - 2.0) / fig.bbox.height))
        return
    ax.legend(handles=handles, fontsize=fontsize, loc=loc, frameon=True,
              framealpha=0.92, borderpad=0.7)
