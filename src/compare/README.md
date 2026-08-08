# src/compare

Stage 6 of the pipeline, where we compare the target model's behavior distribution against its base model and decide whether the target carries covert group-conditional treatment.

We fold each model's stage-5 verdicts into a `BehaviorTable`, then run two tests that split IDT into its two halves. The registered directional test is `paired_max_statistic.paired_max_test`: it standardizes each candidate's excess treatment over the base model and refers the maximum over candidates and axes to a permutation null with a single-step maxT adjustment. `common_mode_elevation` covers the other half, treatment delivered equally to every candidate, which cancels in the directional test and shows only as the target's raised firing rate against its base. Every other statistic here is a single-model side check or a base-free counterfactual, reported against the registered test.

## Files

| File | Responsibility |
|---|---|
| `behavior_bar_figure_departures.py` | The departure quantity behind the behavior figure, and the scale drawing it. |
| `behavior_bar_figure_labels.py` | Text fitting for the behavior figure's gutters. |
| `candidate_detachment_measures.py` | Peak and detachment measures behind the repaired base-free test. |
| `behavior_count_table.py` | Fold one model's stage-5 verdict rows into the N x K firing table, keeping the per-response rows and null-verdict counts the permutation null needs. |
| `paired_max_statistic.py` | The registered directional test: cell rate, one-versus-rest gap, excess over the base, standardized over instructions, max over candidates and axes, permutation null, single-step maxT. |
| `common_mode_elevation.py` | The common-mode half: the target's excess overall firing rate over its base, which the directional test cancels by construction. |
| `principal_attribution.py` | Decide from a rejection whether the run resolves to a named candidate or must decline to name one. |
| `behavior_bar_figure.py` | Draw one model's group profiles as a log2 departure heatmap beside per-group deviation bars. |
| `comparison_report.py` | Assemble the single-model counterfactual for one judge level: information radius, cluster check, and per-group deviation scores. |
| `information_radius.py` | Information radius over the group profiles, its Miller-Madow correction, and its decomposition into between-group and within-group parts. |
| `homogeneity_permutation.py` | Likelihood-ratio G on the N x K table, tested against a cell-permutation null within instruction blocks. |
| `divergence_geometry.py` | Row probabilities, add-alpha smoothing, the KL matrix, and the sqrt(JS) metric used for clustering and scores. |
| `deviation_scores.py` | Median sqrt(JS) distance per group, robust-z flagging, Benjamini-Hochberg, and per-axis attribution. |
| `medoid_cluster_check.py` | Check the outlier precondition with an exhaustive k=2 medoid split that flags a split population. |
| `reference_contrast.py` | Superseded directional statistic: target minus reference information radius against a model-label permutation null, reported only as a counterfactual. |
| `reference_free_max_statistic.py` | Base-free counterpart of the registered test, using the median of the other candidates where the registered test subtracts the base. |
| `candidate_detachment_statistic.py` | Base-free counterfactual asking whether one candidate's peak standardized shift detaches from the other candidates' peaks. |
| `axis_coherence_statistic.py` | Base-free counterfactual asking whether one candidate stays the outlier across many axes, scanned by higher criticism. |
| `paired_excess_measures.py` | The measures under the registered test: rates, excess, and the paired t. |
