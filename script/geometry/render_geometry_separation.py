"""Separation views: the aggregation that makes the loyalty visually separable.

    uv run python script/geometry/render_geometry_separation.py

Writes out/geometry/<run>/explore3/: the bootstrap mean clouds and the
evidence-accumulation race. Views of quantities the pipeline already computes;
no test is run and no statistic is altered.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from src.common.paper_output_dir import PAPER_DIR


from src.common.file_io import save_json
from src.geometry.behavior_cell_vectors import GEOMETRY_RUNS, load_run_vectors
from src.geometry.bootstrap_mean_cloud_figure import plot_bootstrap_mean_clouds
from src.geometry.evidence_accumulation_figure import plot_evidence_accumulation
from src.geometry.behavior_space_decomposition import direction_candidate
from src.geometry.paper_figure_export import copy_run_figures


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-root", default="out/geometry")
    ap.add_argument("--paper-dir", default=str(PAPER_DIR),
                    help="paper tree receiving figures/geometry")
    args = ap.parse_args()
    out_root, paper = Path(args.out_root), Path(args.paper_dir)

    for run in GEOMETRY_RUNS:
        rv = load_run_vectors(run)
        out = out_root / run.name / "explore3"
        highlight = (rv.registered or {}).get("principal")
        direction = direction_candidate(rv)
        summary = {
            "name": rv.name, "level": rv.level, "highlight": highlight,
            "direction_candidate": direction,
            "bootstrap_clouds": plot_bootstrap_mean_clouds(
                rv, out / "bootstrap_clouds.png", highlight=highlight),
            "accumulation": plot_evidence_accumulation(
                rv, out / "evidence_accumulation.png", candidate=direction),
        }
        save_json(out / "separation_summary.json", summary)
        copy_run_figures(out, paper / "figures" / "geometry", run.name)
        acc = summary["accumulation"]
        print(f"[{rv.name} L{rv.level}] direction={direction} "
              f"final={acc['final_running_mean'][direction]:+.3f} "
              f"band={acc['final_band']:.3f}", flush=True)


if __name__ == "__main__":
    main()
