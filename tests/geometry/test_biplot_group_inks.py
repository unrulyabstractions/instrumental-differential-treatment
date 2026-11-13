"""The biplot's group inks must tell the unflagged groups apart.

A reviewer found every unflagged group printed in near-identical grey pastels.
These checks pin the replacement: distinct inks that read on white, none near
the flagged magenta, and a legend key that names no one group's ink.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import to_hex

from src.geometry.mean_excess_biplot_styling import (
    GROUP_INKS,
    KEY_INK,
    LEAD_INK,
    biplot_legend,
    name_ink,
)

REPO = Path(__file__).resolve().parents[2]


def _linear(hex_ink: str) -> list[float]:
    channels = [int(hex_ink.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]


def _contrast_on_white(hex_ink: str) -> float:
    r, g, b = _linear(hex_ink)
    return 1.05 / (0.2126 * r + 0.7152 * g + 0.0722 * b + 0.05)


def _oklab(hex_ink: str) -> tuple[float, float, float]:
    r, g, b = _linear(hex_ink)
    lc = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    mc = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    sc = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (0.2104542553 * lc + 0.7936177850 * mc - 0.0040720468 * sc,
            1.9779984951 * lc - 2.4285922050 * mc + 0.4505937099 * sc,
            0.0259040371 * lc + 0.7827717662 * mc - 0.8086757660 * sc)


def _distance(a: str, b: str) -> float:
    """OKLab distance times 100, the scale the dataviz palette checks use."""
    return 100 * math.dist(_oklab(a), _oklab(b))


def test_group_inks_cover_every_audited_roster_with_distinct_colours():
    # The largest paper roster holds eight groups.
    assert len(GROUP_INKS) >= 8
    assert len({ink.upper() for ink in GROUP_INKS}) == len(GROUP_INKS)
    pairs = [(a, b) for i, a in enumerate(GROUP_INKS) for b in GROUP_INKS[i + 1:]]
    assert min(_distance(a, b) for a, b in pairs) >= 12.0


def test_group_inks_read_on_white_and_stay_clear_of_the_flagged_ink():
    for ink in GROUP_INKS:
        assert _contrast_on_white(ink) >= 3.0, ink
        assert _distance(ink, LEAD_INK) >= 15.0, ink


def test_legend_keys_the_unflagged_groups_in_a_neutral_ink():
    fig, ax = plt.subplots()
    biplot_legend(ax, {"a"}, LEAD_INK, 0.01, 250)
    handles = ax.get_legend().legend_handles
    labels = [t.get_text() for t in ax.get_legend().get_texts()]
    inks = {label: to_hex(h.get_color()).upper() for label, h in zip(labels, handles)}
    plt.close(fig)
    assert inks["not significant, one color each"] == KEY_INK.upper()
    assert not {ink.upper() for ink in GROUP_INKS} & set(inks.values())


def test_null_panel_names_keep_their_hue_and_reach_text_contrast():
    spec = importlib.util.spec_from_file_location(
        "render_paper_biplot", REPO / "script/geometry/render_paper_biplot.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look their module up here
    spec.loader.exec_module(module)
    darken = module.NULL.runner_name_darken
    for ink in GROUP_INKS:
        printed = name_ink(ink, darken)
        assert _contrast_on_white(printed) >= 4.5, (ink, printed)
        assert _distance(ink, printed) <= 10.0, (ink, printed)
