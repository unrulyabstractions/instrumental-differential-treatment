"""Inks, chips, and the legend of the mean-excess biplot.

Split out of ``mean_excess_biplot_figure`` so that module holds only the
geometry and the drawing order. Everything here decides how the figure looks,
never what it shows.
"""

from __future__ import annotations

from matplotlib import patheffects
from matplotlib.lines import Line2D

__all__ = ["AXIS_INK", "CHIP", "HALO", "LEAD_INK", "PASTELS", "PRINCIPAL_INKS",
           "biplot_legend"]

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
#: Labels sit over faded clouds, so every one carries a white halo.
HALO = [patheffects.withStroke(linewidth=2.6, foreground="white", alpha=0.9)]
#: A behavior label is a boxed chip, which no principal's name ever is.
CHIP = {"boxstyle": "round,pad=0.18", "facecolor": "white",
        "edgecolor": "#B9C0CA", "linewidth": 0.45, "alpha": 0.9}


def biplot_legend(ax, marked: set, lead_ink: str, lead: int, alpha: float,
                  n_boot: int, loc: str = "best") -> None:
    """Attach the legend: significance colouring, the clouds, and the compass."""
    pack = PASTELS[(lead + 1) % len(PASTELS)]
    plural = "groups" if len(marked) > 1 else "group"
    handles = []
    if marked:
        handles.append(Line2D([], [], color=lead_ink, linewidth=2.0,
                              label=f"significant candidate {plural} at {1 - alpha:.0%}"))
    handles.append(Line2D(
        [], [], color=pack, linewidth=1.1,
        label="candidate groups" if not marked else "not significant"))
    if not marked:
        handles.append(Line2D([], [], color="none",
                              label=f"none significant at {1 - alpha:.0%}"))
    ax.legend(handles=handles + [
        Line2D([], [], color=pack, marker="o", linestyle="none", markersize=4,
               alpha=0.5, label=f"{n_boot} redrawn prompt samples"),
        Line2D([], [], color=AXIS_INK, linestyle=(0, (4, 3)), linewidth=0.9,
               label="behavior axis, rescaled"),
    ], fontsize=7.8, loc=loc, frameon=True, framealpha=0.92, borderpad=0.7)
