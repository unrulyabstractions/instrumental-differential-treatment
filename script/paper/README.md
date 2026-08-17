# script/paper

We generate the paper's content from `out/` and write it into the external paper tree at `IDT_PAPER_DIR` (default `../papers/idt`), never into this repo.

This folder holds the data-appendix generator and its rerun wrapper, the two figure scripts, and the submission and supplement builders. The generators read stage-6 compare outputs and the scored prompt sets, then write the tables, figures, and `.tex` fragments the paper inputs. Every number comes from `out/`, so the paper is never newer or older than the runs. The builders convert the working paper into an AAAI two-column submission and a single supplement PDF.

## Scripts

| Script | What it does | Run |
|---|---|---|
| write_data_appendix.py | Regenerates the data appendix fragments; on `--top-table` also writes the top-candidate, base-free, fold-comparison, judge-seat, and organism-macro fragments, and on `--by-organism` the per-organism document. A bare invocation is an error. | `bash script/paper/write_both_data_appendices.sh` |
| write_both_data_appendices.sh | Regenerates the data appendix from the rerun tree as the primary run, with the scope note set in one place. | `./script/paper/write_both_data_appendices.sh` |
| plot_verdict_dotplot.py | Draws the verdict figure: one row per run with the observed statistic S, the null 95th percentile, and the favoured candidate on rejecting rows, all read from each run's `compare/` under `out/main/secret_loyalties`. | `uv run python script/paper/plot_verdict_dotplot.py` |
| replot_behavior_figures.py | Redraws the stage-6 behavior figures from the saved comparison reports, rewriting only PNG and PDF so no statistic can change. | `uv run python script/paper/replot_behavior_figures.py` |
| build_aaai_submission.py | Converts the working paper into an AAAI-27 two-column submission: drops the appendices, rewrites `\autoref`, strips the forbidden page-break commands, widens the marked floats, and repoints dangling references. | `uv run python script/paper/build_aaai_submission.py` |
| build_supplement.py | Builds the supplement as one PDF from the appendix fragments, normalizing each for a template with no float package and no hyperref, then running pdflatex and bibtex. | `uv run python script/paper/build_supplement.py` |
