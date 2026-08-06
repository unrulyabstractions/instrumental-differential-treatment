# src/geometry

We hold the interpretable-versus-embedding geometry analyses of the audit: we embed replies, draw behavior-axis biplots, align the two spaces with Procrustes, CCA, and Mantel, test axis decodability, and compare the null controls, all as side analyses that never stand in for the registered test.

A caller loads one run's stage-5 verdicts and stage-3 axes into matched (target, base) cell-rate vectors through `load_run_vectors`, which returns the `RunVectors` every figure here consumes. The figures read the same excess the stage-6 test reads, so a loyalty the test detects shows as a drift off the origin, and the plots that consult the test borrow its verdict only for coloring. `compute_bridge` runs the parallel embedding track: it embeds the reply text, takes the excess against the base model, and reports Mantel, canonical correlation, Procrustes, a judge-free group test, and per-axis decodability. Every statistic here is descriptive, and the stage-6 permutation test stays the only arbiter.

## Files

| File | Responsibility |
|---|---|
| `mean_excess_biplot_cloud_statistics.py` | Resampling clouds and the numeric summary behind the mean-excess biplot. |
| `mean_excess_biplot_label_layout.py` | Framing and label placement for the mean-excess biplot. |
| `mean_excess_biplot_styling.py` | Inks, chips, and the legend of the mean-excess biplot. |
| axis_activity_filtering.py | Keep the behavior axes whose pooled firing rate clears a floor, a display-only filter the registered test never runs on. |
| behavior_archetype_simplex.py | Factor the pooled cell matrix into three NMF archetypes and draw the target's cells as barycentric mixtures inside the named triangle. |
| behavior_cell_vectors.py | Fold one run's stage-5 verdicts into matched (target, base) cell-rate vectors; defines `GEOMETRY_RUNS` and the `RunVectors` input the figures share. |
| behavior_map_figure.py | Draw the raw two-panel map, base and target cells on the shared pooled plane, and define the highlight and helper inks. |
| behavior_space_decomposition.py | Linear views of the cell cloud: best-fit plane, variance partition by identity, and the displacement split into the two halves. |
| bootstrap_mean_cloud_figure.py | Resample the instructions and draw each candidate's mean-excess uncertainty cloud on the excess plane. |
| colored_cloud_figures.py | Color the target's raw cells by candidate and by collection framing; define the candidate and framing hues and `framing_of`. |
| control_comparison.py | Compare the six null-control organisms against each other in behavior-axis and embedding space, reporting cosine structure and 2D maps. |
| direction_structure_figures.py | Cosine matrix between candidate mean-excess directions, and the named candidate's excess split by framing. |
| embedding_axis_decoding.py | Give embedding directions behavioral meaning: held-out ridge R^2 decodability per axis, and label each leading PC by the axes it tracks. |
| embedding_group_test.py | Judge-free version of the registered test in embedding space, the max one-vs-rest excess gap with a within-instruction permutation null. |
| evidence_accumulation_figure.py | Draw the running-mean projection on the named direction as instructions pool, against an approximate shrinking null band. |
| excess_map_figure.py | Draw the excess cloud, one point per cell and one mean-excess arrow per candidate, with the plane fit through the origin. |
| filtered_axis_map_figure.py | Recompute the two-panel map over active axes only and report how the candidate variance share moves. |
| geometry_alignment_stats.py | Cross-space alignment with permutation nulls: Mantel, canonical correlation, and 2D Procrustes. |
| geometry_appendix_fragments.py | Write the geometry appendix's generated numbers as LaTeX macros, read from the per-run summaries. |
| label_collision_nudge.py | Place many labels near their own anchors without collision by trying rotated offsets in priority order. |
| loyalty_axis_projection_figure.py | Project every cell's excess on the named candidate's direction, one strip per candidate colored by framing. |
| loyalty_direction_figure.py | Draw the top coordinates of one candidate's mean-excess direction as bars, starring the axes that survived the maxT adjustment. |
| mean_excess_biplot_figure.py | The appendix's main figure: per-candidate mean-excess arrows over bootstrap clouds, with a named behavior compass and test-driven coloring. |
| nonlinear_embedding_figure.py | Draw t-SNE and UMAP of the target's cells side by side, colored by framing with the named candidate outlined. |
| openai_text_embedder.py | Embed a list of texts with an OpenAI embedding model, batched and retried, with empty strings embedding to a zero vector. |
| paired_response_records.py | Join responses to verdicts on the `(prompt_id, sample)` key and fold to cell means, counting missing rows and never imputing. |
| plane_axis_compass.py | Pick which named behavior axes to draw as compass rays inside a plane, thinned so their labels cannot collide. |
| response_embedding_cache.py | Embed a run's responses once and cache to disk keyed by row order, re-embedding only when the rows change. |
| semantic_behavior_bridge.py | Assemble the interpretable and embedding views over one run's cells and return every bridge statistic and coordinate through `compute_bridge`. |
| three_component_map_figure.py | Draw the pooled cloud on its first three components from two viewpoints, to check what the 2D map hides. |
| two_halves_plane_figure.py | Draw per-cell displacement in the (common mode, residual) frame the decomposition names. |
