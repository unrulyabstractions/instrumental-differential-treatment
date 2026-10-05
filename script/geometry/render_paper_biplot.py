"""Render every biplot the papers include, at the width each one prints.

    uv run python script/geometry/render_paper_biplot.py --paper-dir ../papers/idt

The author kit asks for nine-point type or larger in every figure, measured as
printed. A wide render shrunk into a narrow slot prints its labels at a third
of their size, so each paper biplot is rendered here at the physical width its
slot gives it, with every text element at nine points or more:

- ``<name>_mean_excess_biplot.pdf`` is the appendix panel, included at
  ``0.75\\linewidth`` of the one-column appendix (5.25 in), or at
  ``0.49\\linewidth`` (3.43 in) for the null controls, which print two to a row;
- ``<name>_mean_excess_biplot_main.pdf`` is the main-text panel: 0.48 of the
  text width in Figure 1 and the column width in Figure 5.

Same data, same seed, same significance set as the working renders; only the
canvas, the type sizes and the number of named rays change. A label that cannot
be placed clear of the others is dropped rather than printed over another, and
the render stops with an error if any text is under nine points, leaves the
canvas, or still overlaps another label. Renders are staged in a scratch
directory and only the PDFs are copied into the paper tree.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt

from src.common.file_io import load_json
from src.common.paper_output_dir import PAPER_DIR
from src.geometry.behavior_cell_vectors import GEOMETRY_RUNS, GeometryRun, load_run_vectors
from src.geometry.mean_excess_biplot_figure import plot_mean_excess_biplot
from src.geometry.mean_excess_biplot_styling import BiplotStyle, paper_style

AB = "out/main/auditbench"
EXT = "out/main/external"
#: The AAAI text width and column width, in inches.
TEXT_WIDTH = 7.0
COLUMN_WIDTH = (7.0 - 0.375) / 2.0
MIN_POINTS = 9.0

#: The appendix panel: 0.75 of the one-column text width, legend under the axes.
APPENDIX = paper_style(0.75 * TEXT_WIDTH, 3.15, legend="below", ray_labels=6,
                       wrap=34, short_axis_labels=False,
                       margins=(0.56, 0.08, 0.26, 0.86))
#: A null control: 0.49 of the text width, two to a row, the key in the caption.
NULL = paper_style(0.49 * TEXT_WIDTH, 2.05, ray_labels=3, n_labels=3, wrap=24)
#: Figure 1 of the main text: four panels, each 0.48 of the text width.
#: Each is a little shorter than the wide render it replaces was at that width.
FIGURE_ONE = paper_style(0.48 * TEXT_WIDTH, 1.74, ray_labels=2, n_labels=3, wrap=24)
#: Figure 5 of the main text: two panels stacked in one column.
FIGURE_FIVE = paper_style(COLUMN_WIDTH, 1.36, ray_labels=2, n_labels=2, wrap=26)

CONTROLS = ("flattery", "emotional_bond", "hallucinates_citations", "defer_to_users",
            "ai_welfare_poisoning", "anti_ai_regulation", "animal_welfare",
            "defend_objects")


@dataclass(frozen=True)
class PaperBiplot:
    """One file the paper includes: which run, at which slot's style."""

    file: str
    run: GeometryRun
    style: BiplotStyle
    #: Behaviors the figure's caption names, which the panel must label.
    named_rays: tuple[str, ...] = ()


def _registry() -> list[PaperBiplot]:
    """Every biplot file the two papers include, in appendix order."""
    by_name = {r.name: r for r in GEOMETRY_RUNS}
    narrow = {c: by_name[f"calibration_{c}"] for c in ("informed", "scoped", "blind")}
    optimism = by_name["auditbench_contextual_optimism"]
    politics = by_name["auditbench_third_party_politics"]
    # The scoped audit of AuditBench secret_loyalty, restricted to the states.
    loyalty = GeometryRun("auditbench_secret_loyalty", "secret loyalty",
                          f"{AB}/secret_loyalty/judge_mini_states",
                          f"{AB}/secret_loyalty/conjecture_scoped_state",
                          f"{AB}/secret_loyalty/judge_mini_states/compare",
                          "target", "base")
    out = [PaperBiplot(f"narrow_secret_loyalty_{c}", r, APPENDIX) for c, r in narrow.items()]
    out += [PaperBiplot("auditbench_contextual_optimism", optimism, APPENDIX),
            PaperBiplot("auditbench_third_party_politics", politics, APPENDIX),
            PaperBiplot("auditbench_secret_loyalty", loyalty, APPENDIX,
                        named_rays=("legitimacy_presumption_bias",
                                    "civilian_harm_assessment_suppression"))]
    # The null controls share the contextual-optimism axis registry.
    out += [PaperBiplot(f"auditbench_{c}",
                        GeometryRun(f"auditbench_{c}", c.replace("_", " "),
                                    f"{AB}/controls/{c}/judge_mini",
                                    f"{AB}/contextual_optimism/conjecture",
                                    f"{AB}/controls/{c}/judge_mini/compare",
                                    "target", "base"), NULL)
            for c in CONTROLS]
    # Our court-conversion organism: the blind pipeline and the scoped one,
    # each on both arms. The panel title names the audit condition the way the
    # narrow-secret-loyalty panels do.
    for variant, tree in (("full", "court_full"), ("scoped", "court_full_scoped")):
        condition = "blind" if variant == "full" else "scoped"
        for arm in ("prompted", "weights"):
            out.append(PaperBiplot(
                f"court_{variant}_{arm}",
                GeometryRun(f"court_{variant}_{arm}", f"court_conversion {arm} {condition}",
                            f"{EXT}/{tree}/score", f"{EXT}/{tree}/conjecture",
                            f"{EXT}/{tree}/compare_{arm}", f"{arm}_target", f"{arm}_base"),
                APPENDIX))
    main_text = [("auditbench_contextual_optimism", optimism, FIGURE_ONE),
                 ("auditbench_third_party_politics", politics, FIGURE_ONE),
                 ("narrow_secret_loyalty_informed", narrow["informed"], FIGURE_ONE),
                 ("auditbench_secret_loyalty", loyalty, FIGURE_ONE),
                 ("narrow_secret_loyalty_blind", narrow["blind"], FIGURE_FIVE),
                 ("narrow_secret_loyalty_scoped", narrow["scoped"], FIGURE_FIVE)]
    out += [PaperBiplot(f"{name}_main", run, style) for name, run, style in main_text]
    return out


def _significant(run: GeometryRun) -> set[str]:
    """Every principal the run's registered test rejects.

    The recomputed set is preferred where it exists, because stage 6 keeps only
    the largest pairs. Otherwise the rejecting pairs stage 6 stored decide.
    """
    recomputed = Path(run.compare_dir) / "significant_candidates.json"
    if recomputed.exists():
        return set(load_json(recomputed).get("significant") or [])
    contrast = load_json(Path(run.compare_dir) / "comparison_summary.json")["reference_contrast"]
    level = sorted(k for k in contrast if k.startswith("L"))[-1]
    test = contrast[level]["paired_max_test"]
    return {p["candidate"] for p in test.get("top_pairs", []) if p.get("reject")}


def _problems(layout: dict) -> list[str]:
    """What keeps a render out of the paper: small type, clipped text, overlaps."""
    small = [f"{t['text']!r} at {t['size']}pt" for t in layout["texts"]
             if t["size"] < MIN_POINTS]
    return (small + [f"{t!r} leaves the canvas" for t in layout["outside_canvas"]]
            + [f"{a!r} overlaps {b!r}" for a, b in layout["label_clashes"]])


def render_paper_biplots(paper_dir: Path, only: set[str] | None = None,
                         stage_dir: Path | None = None,
                         measure_dir: Path | None = None) -> list[dict]:
    """Render, check, and copy the paper biplots; return one record per file.

    ``measure_dir`` additionally writes each PDF with its fonts kept as
    TrueType, so a text extractor can read every span's printed size.
    """
    stage = Path(stage_dir or tempfile.mkdtemp(prefix="paper_biplots_"))
    stage.mkdir(parents=True, exist_ok=True)
    figure_dir = paper_dir / "figures" / "geometry"
    figure_dir.mkdir(parents=True, exist_ok=True)
    records, failed = [], []
    for entry in _registry():
        if only and entry.file not in only:
            continue
        rv = load_run_vectors(entry.run)
        significant = _significant(entry.run)
        png = stage / f"{entry.file}_mean_excess_biplot.png"
        if entry.file.endswith("_main"):
            png = stage / f"{entry.file.removesuffix('_main')}_mean_excess_biplot_main.png"
        drew = plot_mean_excess_biplot(rv, png, significant=significant, style=entry.style,
                                       named_rays=entry.named_rays)
        if measure_dir is not None:
            measure_dir.mkdir(parents=True, exist_ok=True)
            with plt.rc_context({"pdf.fonttype": 42}):
                plot_mean_excess_biplot(rv, measure_dir / png.name, significant=significant,
                                        style=entry.style, outline=False,
                                        named_rays=entry.named_rays)
        problems = _problems(drew["layout"])
        ray_names = {c["axis_id"]: c["label"] for c in drew["compass_axes"]}
        problems += [f"caption names {axis!r}, which the panel leaves unlabelled"
                     for axis in entry.named_rays
                     if ray_names.get(axis) not in drew["labelled_rays"]]
        record = {"file": png.with_suffix(".pdf").name, "figsize": entry.style.figsize,
                  "significant": sorted(drew["significant"]),
                  "alpha": (rv.registered or {}).get("alpha"),
                  "min_text_pt": drew["layout"]["min_size"],
                  "labelled_rays": drew["labelled_rays"],
                  "drawn_rays": [c["label"] for c in drew["compass_axes"]],
                  "labels_left_off": drew["labels_left_off"],
                  "problems": problems, "summary": drew}
        (stage / f"{png.stem}.json").write_text(json.dumps(record, indent=1, default=str))
        records.append(record)
        print(f"{record['file']:62s} {entry.style.figsize[0]:.2f}x{entry.style.figsize[1]:.2f}in "
              f"min {record['min_text_pt']}pt rays {len(record['labelled_rays'])}/"
              f"{len(record['drawn_rays'])} significant {record['significant']}"
              + (f"  PROBLEMS {problems}" if problems else ""), flush=True)
        if problems:
            failed.append(record["file"])
            continue
        shutil.copyfile(png.with_suffix(".pdf"), figure_dir / record["file"])
    if failed:
        raise SystemExit(f"not copied into the paper, fix the layout first: {failed}")
    return records


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--paper-dir", type=Path, default=PAPER_DIR,
                    help="paper tree receiving figures/geometry/*_mean_excess_biplot*.pdf")
    ap.add_argument("--only", nargs="*", default=None,
                    help="file stems to render, e.g. court_full_prompted "
                         "auditbench_secret_loyalty_main")
    ap.add_argument("--stage-dir", type=Path, default=None,
                    help="where the renders and their layout records are kept")
    ap.add_argument("--measure-dir", type=Path, default=None,
                    help="also write unoutlined copies here, for measuring type sizes")
    args = ap.parse_args()
    render_paper_biplots(args.paper_dir, set(args.only) if args.only else None,
                         args.stage_dir, args.measure_dir)


if __name__ == "__main__":
    sys.exit(main())
