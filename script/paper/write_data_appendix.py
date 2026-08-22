"""Regenerate one run's data appendix from the artifacts on disk.

    uv run python script/paper/write_data_appendix.py \\
        --out-root out/main/secret_loyalties --run-key r1 --run-label "the first run" --primary \\
        --sibling-key r2 --sibling-label "rerun" \\
        --output ../papers/idt/appendix/experiment_data.tex

    uv run python script/paper/write_data_appendix.py \\
        --out-root out/main/secret_loyalties --run-key r2 --run-label "the rerun" \\
        --sibling-key r1 --sibling-label "first run" \\
        --output ../papers/idt/appendix/experiment_data_rerun.tex

The appendix quotes what each stage produced. Hand-editing it is how it drifts
from the runs, which has already happened once: a question card showed twenty
questions no model was ever asked. This script reads the given output tree and
writes the appendix, so the paper is never newer or older than the data.

Each run gets its own label namespace, keyed on ``--run-key``, so two runs can
be inputted into one document without a multiply-defined label. The run marked
``--primary`` additionally keeps the unsuffixed labels, because the body
sections cite ``app:data``, ``tab:data-scoring``, and ``tab:data-common-mode``
directly. Only the primary run writes the fragments the supplement pulls in
with ``\\input``: the top-candidate table for the protocol appendix, and the
judge-seat and reference-free appendices.

The generators themselves live in ``src/appendix``; this file only picks the
tree, the run, and the files to write.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from src.common.paper_output_dir import PAPER_DIR

from src.common.experiment_layout import stage_path
from src.appendix.elicit_top_table import elicit_top_table
from src.appendix.latex_text_escaping import sentence_per_line
from src.appendix.experiment_data_document import experiment_data_document
from src.appendix.experiment_data_by_organism import (
    experiment_data_by_organism_document,
    experiment_data_by_organism_parts,
)
from src.common.file_io import load_json
from src.appendix.coherence_fold_document import coherence_fold_document
from src.appendix.judge_seat_document import judge_seat_document
from src.appendix.organism_numbers_document import organism_numbers_document
from src.appendix.reference_free_document import reference_free_document
from src.appendix.verdict_table_document import verdict_table_document

#: Pulled into the protocol appendix with \input, so its prose stays hand-written.
TOP_TABLE = PAPER_DIR / "appendix/elicit_top_candidates.tex"

#: The base-free appendix, whole. Its numbers come from reference_free.json,
#: written by script/analysis/compute_reference_free_detector.py.
REFERENCE_FREE = PAPER_DIR / "appendix/reference_free.tex"

#: The fold-comparison appendix. Its numbers come from paired_coherence.json,
#: written by script/analysis/compute_paired_coherence_verdicts.py.
COHERENCE_FOLD = PAPER_DIR / "appendix/coherence_fold.tex"

#: The judge-seat appendix. Its numbers come from judge_comparison.json,
#: written by script/analysis/compile_judge_comparison.py, at a path fixed in
#: the generator because the probe compares seats across runs. The run root is
#: passed so the outcome caption can reconcile survivor counts with the
#: registered run.
JUDGE_SEAT = PAPER_DIR / "appendix/judge_seat.tex"

#: The main paper's verdict table body, input by sections/results.tex.
VERDICT_TABLE = PAPER_DIR / "appendix/verdict_table.tex"

#: The macro file for the weights-level model-organism appendix. Its numbers
#: come from the collaborator's phase-3 targets and results, saved under
#: out/main/external/idt_organism_p3.
ORGANISM_NUMBERS = PAPER_DIR / "appendix/organism_numbers.tex"

#: The standalone experiment-data document's body: one appendix per target
#: organism. Input by paper/experiment_data.tex, which builds its own PDF.
BY_ORGANISM = PAPER_DIR / "appendix/experiment_data_by_organism.tex"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-root", default="out/main/secret_loyalties",
                    help="output tree to read, the family tree holding the experiments")
    ap.add_argument("--run-key", default="r2",
                    help="label namespace for this run, e.g. r1 or r2")
    ap.add_argument("--run-label", default="the first run",
                    help="how the run is named in the section title and prose")
    ap.add_argument("--output", default=str(PAPER_DIR / "appendix/experiment_data.tex"),
                    help="where to write this run's appendix")
    ap.add_argument("--primary", action="store_true",
                    help="also emit the unsuffixed labels the body sections cite")
    ap.add_argument("--sibling-key", default="",
                    help="run key of the other run's appendix, to cross-reference it")
    ap.add_argument("--sibling-label", default="",
                    help="how the other run is named in that cross-reference")
    ap.add_argument("--top-table", action="store_true",
                    help=f"also write {TOP_TABLE} from this tree")
    ap.add_argument("--by-organism", action="store_true",
                    help=f"also write {BY_ORGANISM}, one appendix per target organism")
    ap.add_argument("--scope-note", default="",
                    help="one sentence stating which targets and conditions this run covers")
    ap.add_argument("--stage-organized", action="store_true",
                    help="also write the stage-organized appendix to {--output}; "
                         "off by default because the paper now inputs the "
                         "per-organism document instead")
    args = ap.parse_args()
    if not (args.stage_organized or args.by_organism or args.top_table):
        # A bare invocation used to exit 0 having written nothing, and the
        # pipeline logged "regenerated the appendix" over a stale one. Doing
        # nothing quietly is the one behavior a regeneration script must not
        # have.
        raise SystemExit("no output selected: pass --by-organism, --top-table, "
                         "or --stage-organized (see "
                         "script/paper/write_both_data_appendices.sh)")
    root = Path(args.out_root)
    output = Path(args.output)

    print(f"read {root}")
    if args.stage_organized:
        output.write_text(sentence_per_line(experiment_data_document(
            root, args.run_key, args.run_label, primary=args.primary,
            sibling_key=args.sibling_key, sibling_label=args.sibling_label,
            scope_note=args.scope_note)))
        print(f"wrote {output}")
    if args.by_organism:
        # One file per organism in its own subfolder; the index inputs them.
        # Unknown .tex files there are removed, so a renamed or dropped
        # organism cannot leave a stale appendix behind.
        parts_dir = PAPER_DIR / "appendix/experiment_data"
        parts_dir.mkdir(parents=True, exist_ok=True)
        parts = experiment_data_by_organism_parts(root)
        wanted = {name for name, _ in parts}
        for name, body in parts:
            (parts_dir / name).write_text(sentence_per_line(body))
            print(f"wrote {parts_dir / name}")
        for stale in sorted(parts_dir.glob("*.tex")):
            if stale.name not in wanted:
                stale.unlink()
                print(f"removed stale {stale}")
        BY_ORGANISM.write_text(sentence_per_line(
            experiment_data_by_organism_document(root)))
        print(f"wrote {BY_ORGANISM}")
    if args.top_table:
        TOP_TABLE.write_text(sentence_per_line(elicit_top_table(root, args.run_key)))
        print(f"wrote {TOP_TABLE}")
        REFERENCE_FREE.write_text(sentence_per_line(reference_free_document(root)))
        print(f"wrote {REFERENCE_FREE}")
        COHERENCE_FOLD.write_text(sentence_per_line(coherence_fold_document()))
        print(f"wrote {COHERENCE_FOLD}")
        display = load_json(stage_path(root, "score", "calibration_informed")
                            / "prompt_sets.json").get("principals", {}) \
            if (stage_path(root, "score", "calibration_informed") / "prompt_sets.json").exists() else {}
        JUDGE_SEAT.write_text(sentence_per_line(judge_seat_document(display, run_root=root)))
        print(f"wrote {JUDGE_SEAT}")
        ORGANISM_NUMBERS.write_text(organism_numbers_document())
        print(f"wrote {ORGANISM_NUMBERS}")
        VERDICT_TABLE.write_text(verdict_table_document())
        print(f"wrote {VERDICT_TABLE}")


if __name__ == "__main__":
    main()
