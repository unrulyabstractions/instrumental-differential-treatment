# script/geometry

We build and render the interpretable-versus-embedding geometry side analyses: the semantic bridge, the control-versus-control comparison, and the behavior-geometry figures. They are side analyses that never stand in for the registered test.

Two build scripts embed responses and write the JSON the explorers read. Four render scripts read the rerun's cell vectors and the stage-6 verdicts from disk, then write per-run figures under `out/geometry/`, copy the appendix figures into `$IDT_PAPER_DIR/figures/geometry/`, and regenerate the geometry appendix fragments. Nothing here samples a model or recomputes a statistic. Every registered verdict is read from the stage-6 artifacts, so no test can be altered from this folder.

## Scripts

| Script | What it does | Run |
|---|---|---|
| `build_control_comparison.py` | Reads the six null controls' verdicts and cached embeddings against the one shared base, then writes `out/geometry/control_comparison.json`. Requires `build_semantic_bridge.py` to have cached each control's embeddings first. | `uv run python script/geometry/build_control_comparison.py` |
| `build_semantic_bridge.py` | Embeds every response once, caches it under the run's `out/geometry` tree, and writes `semantic_bridge.json` with the geometry statistics, aligned per-candidate coordinates, axis decodabilities, and labelled embedding components. | `uv run python script/geometry/build_semantic_bridge.py --only auditbench_contextual_optimism` |
| `render_behavior_geometry.py` | Reads the rerun verdicts and stage-6 reports for the six runs, writes one directory per run under `out/geometry/`, copies the included figures into `$IDT_PAPER_DIR/figures/geometry/`, and regenerates the three appendix fragments. | `uv run python script/geometry/render_behavior_geometry.py` |
| `render_geometry_deepdive.py` | Writes `out/geometry/<run>/explore2/`: the loyalty-axis strips, the two-halves plane, the archetype simplex, and the excess map restricted to the trigger framings. | `uv run python script/geometry/render_geometry_deepdive.py [--runs name ...]` |
| `render_geometry_exploration.py` | Writes `out/geometry/<run>/explore/` for the six runs: filtered and color-coded maps, the three-component map, nonlinear embeddings, and the direction-structure figures. | `uv run python script/geometry/render_geometry_exploration.py` |
| `render_geometry_separation.py` | Writes `out/geometry/<run>/explore3/`: the bootstrap mean clouds and the evidence-accumulation race, and copies them into `$IDT_PAPER_DIR/figures/geometry/`. | `uv run python script/geometry/render_geometry_separation.py` |
| `render_paper_biplot.py` | Render the main paper's biplot at a size whose fonts print near true size. |
