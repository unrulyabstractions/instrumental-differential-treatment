#!/usr/bin/env bash
# Regenerate the data appendix from the rerun tree.
#
# The paper reports one run. The first run's appendix was dropped, so there is a
# single invocation here and it is --primary: primary keeps the unsuffixed label
# alongside the -r2 one, which is what lets the body cite either form.
#
# Scope is enforced in ONE place, src/appendix/pipeline_run_registry.py, and
# stated by DROPPED_NOTE, which the appendix prints under its index. Do not
# restate the reasons here.
# Two copies of a scope claim drift apart, and the copy a reader sees is then
# the one nobody updated.
#
# Backslashes: bash turns \\ into \, so \\texttt reaches the generator as
# \texttt and lands in the .tex as one command. Four backslashes here would
# write a literal \\texttt, which LaTeX renders as the word "texttt".
set -euo pipefail
cd "$(dirname "$0")/../.."

# --output and --scope-note are consumed only by the stage-organized document,
# which the paper no longer inputs, so neither is passed: a flag whose value
# lands nowhere reads like configuration and is really a comment.
uv run python script/paper/write_data_appendix.py \
    --out-root out/main/secret_loyalties \
    --run-key r2 --run-label "the rerun" --primary \
    --top-table \
    --by-organism
