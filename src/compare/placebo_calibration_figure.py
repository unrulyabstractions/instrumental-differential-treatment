"""The placebo QQ figure: every run's placebo p-values against the uniform.

Two rows, two columns. Columns are the model split against itself (base, then
target). The top row is the plain QQ plot; the bottom row puts both axes on
-log10, where the small p-values that decide a rejection are legible. Table 2
runs are blue, Table 3 null controls orange, the pool of all runs dark ink. The
real null-control p-values are drawn as ticks on the bottom rows' y axis, so a
reader can see where they sit against the placebo.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

__all__ = ["draw_qq"]

_COLOR = {"verdicts": "#2a78d6", "nulls": "#eb6834"}
_INK, _GRID = "#0b0b0b", "#9a9893"


def _expected(n: int) -> np.ndarray:
    return (np.arange(1, n + 1) - 0.5) / n


def draw_qq(by: dict, keys: list[str], table_of: dict, real_nulls: dict,
            stem: Path) -> tuple[Path, Path]:
    fig, axes = plt.subplots(2, 2, figsize=(9.0, 8.4))
    for col, model in enumerate(("base", "target")):
        pooled = []
        for key in keys:
            reps = by.get((key, model), [])
            if not reps:
                continue
            p = np.sort([r["p"] for r in reps])
            pooled.extend(p)
            e = _expected(p.size)
            kw = dict(color=_COLOR[table_of[key]], lw=1.0, alpha=0.55)
            axes[0, col].plot(e, p, **kw)
            axes[1, col].plot(-np.log10(e), -np.log10(p), **kw)
        p = np.sort(pooled)
        e = _expected(p.size)
        axes[0, col].plot(e, p, color=_INK, lw=2.0)
        axes[1, col].plot(-np.log10(e), -np.log10(p), color=_INK, lw=2.0)

        axes[0, col].plot([0, 1], [0, 1], ls="--", color=_GRID, lw=1.0)
        axes[0, col].set(xlim=(0, 1), ylim=(0, 1), xlabel="uniform quantile",
                         ylabel="placebo p-value",
                         title=f"{model} split against itself")
        top = 3.6
        axes[1, col].plot([0, top], [0, top], ls="--", color=_GRID, lw=1.0)
        for cut in (0.05, 0.01):
            axes[1, col].axhline(-np.log10(cut), color=_GRID, lw=0.6, ls=":")
        for value in real_nulls.values():
            axes[1, col].plot([0, 0.12], [-np.log10(value)] * 2, color=_COLOR["nulls"],
                              lw=2.0, clip_on=False)
        axes[1, col].set(xlim=(0, top), ylim=(0, top),
                         xlabel="uniform quantile, $-\\log_{10}$",
                         ylabel="placebo p-value, $-\\log_{10}$")
        for ax in axes[:, col]:
            ax.set_aspect("equal")
            ax.spines[["top", "right"]].set_visible(False)
    handles = [plt.Line2D([], [], color=_COLOR["verdicts"], lw=1.5, label="Table 2 run"),
               plt.Line2D([], [], color=_COLOR["nulls"], lw=1.5, label="Table 3 null control"),
               plt.Line2D([], [], color=_INK, lw=2.0, label="all runs pooled"),
               plt.Line2D([], [], color=_GRID, ls="--", lw=1.0, label="uniform"),
               plt.Line2D([], [], color=_COLOR["nulls"], lw=3.0,
                          label="real null-control p (axis ticks, bottom)")]
    fig.legend(handles=handles, loc="lower center", ncol=3, frameon=False)
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    stem.parent.mkdir(parents=True, exist_ok=True)
    pdf, png = stem.with_suffix(".pdf"), stem.with_suffix(".png")
    fig.savefig(pdf)
    fig.savefig(png, dpi=160)
    plt.close(fig)
    return pdf, png
