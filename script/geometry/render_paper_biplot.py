"""Render the main paper's biplot at a size whose fonts print near true size.

    uv run python script/geometry/render_paper_biplot.py

The supplement takes the wide renders. The main paper shows one biplot as a
full-width figure, and a wide render scaled into that slot prints its labels
too small, so this renders the flagship run once more at the width the figure
actually occupies. Same data, same seed, same significance set; only the canvas
changes. The output lands beside the run's other figures and is copied into the
paper tree as ``<run>_mean_excess_biplot_paper.pdf``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from src.common.experiment_layout import geometry_dir
from src.common.file_io import load_json
from src.common.paper_output_dir import PAPER_DIR
from src.geometry.behavior_cell_vectors import GEOMETRY_RUNS, load_run_vectors
from src.geometry.mean_excess_biplot_figure import plot_mean_excess_biplot

FLAGSHIP = "auditbench_third_party_politics"
#: About 0.92 of the AAAI text width, so a full-width include is near 1:1.
PAPER_FIGSIZE = (6.4, 3.4)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", default=FLAGSHIP)
    args = ap.parse_args()

    run = {r.name: r for r in GEOMETRY_RUNS}[args.run]
    rv = load_run_vectors(run)
    summary = load_json(Path(run.compare_dir) / "comparison_summary.json")
    contrast = summary["reference_contrast"]
    level = sorted(k for k in contrast if k.startswith("L"))[-1]
    test = contrast[level]["paired_max_test"]
    significant = {p["candidate"] for p in test.get("top_pairs", []) if p.get("reject")}

    out = geometry_dir(args.run) / "mean_excess_biplot_paper.png"
    # The tuned canvas puts matplotlib's best legend spot over a compass
    # label, so the paper render pins the legend to the empty lower left.
    drew = plot_mean_excess_biplot(rv, out, significant=significant,
                                   figsize=PAPER_FIGSIZE, legend_loc="lower left")
    # Paper figures use the organism's display name, never the repo name.
    display_run = args.run.replace("calibration", "narrow_secret_loyalty")
    target = (PAPER_DIR / "figures/geometry"
              / f"{display_run}_mean_excess_biplot_paper.pdf")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(out.with_suffix(".pdf").read_bytes())
    print(f"drew {sorted(drew)} -> {target}")


if __name__ == "__main__":
    main()
