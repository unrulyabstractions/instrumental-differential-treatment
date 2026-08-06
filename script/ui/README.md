# script/ui

We build the interactive experiment explorer here: one embedded data bundle and the single self-contained HTML page that reads it.

This folder holds two entry-point scripts. The first reads the artifacts on disk, folds the verdict rows from the stage-6 summaries into rate grids and aggregates, samples real transcripts, and writes one JSON bundle. The second embeds that bundle into the page template and writes a standalone HTML file with no external fetch. Neither script recomputes a statistic. Both consume what the six stages already produced.

## Scripts

| Script | What it does | Run |
|---|---|---|
| build_explorer_data.py | Distills every experiment into one JSON bundle. Reads the artifacts on disk, folds verdict rows into rate grids and aggregates, samples transcripts, and writes `out/ui/explorer_data.json`. | `uv run python script/ui/build_explorer_data.py` |
| build_explorer_page.py | Embeds the built data into the page template. Substitutes the JSON for the `__DATA__` placeholder, escapes it so it cannot close the script element early, and writes the standalone page. | `uv run python script/ui/build_explorer_page.py` |
