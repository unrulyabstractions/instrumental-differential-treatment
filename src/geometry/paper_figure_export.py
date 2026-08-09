"""Copy a run's rendered figures into the external paper tree.

The render scripts write figures under the run's own out/analysis/geometry directory,
and the paper includes them by a name prefixed with the run. Two renderers
export the same way, so the copy lives here once.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["copy_run_figures"]


def copy_run_figures(run_dir: Path, figure_dir: Path, name: str) -> None:
    """Copy every figure in ``run_dir`` to ``figure_dir`` as ``<name>_<file>``."""
    figure_dir.mkdir(parents=True, exist_ok=True)
    for source in sorted(run_dir.glob("*.pdf")) + sorted(run_dir.glob("*.png")):
        (figure_dir / f"{name}_{source.name}").write_bytes(source.read_bytes())
