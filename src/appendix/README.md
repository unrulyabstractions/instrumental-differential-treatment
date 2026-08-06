# src/appendix

We generate the paper's data appendix and its companion LaTeX fragments from the artifacts each pipeline stage wrote under `out/`.

The package holds one module per generated table, card, and appendix section, and each reads a stage's JSON and JSONL directly and emits LaTeX. The six stages each get a section builder, and `experiment_data_document` assembles them in reading order into the data appendix. Other modules generate the standalone fragments the paper body inputs: the results tables, the judge-seat and reference-free appendices, and the external-organism results. Every number is read from disk rather than transcribed, and the two files this package generates, `experiment_data.tex` and `elicit_top_candidates.tex`, are never hand-edited.

## Files

| File | Responsibility |
|---|---|
| `appendix_card_layouts.py` | Build the labelled card environments, question and listing, shared across appendix sections. |
| `calibration_run_tables.py` | Per-target elicitation run-statistics and candidate tables, keyed on the seat tags each run used. |
| `challenge_elicitation_tables.py` | Challenge-organism elicitation tables: pooled candidates, then per-seed and per-variant naming blocks. |
| `clearest_prompt_cards.py` | Quote the single widest-excess cell per reported run, recomputed with the registered test's own functions. |
| `collection_variant_tables.py` | Break stage 4 down by collection system-prompt variant, and quote the variants verbatim. |
| `comparison_behavior_figures.py` | Copy each stage-6 behavior figure into the paper tree, namespaced by run, and wrap it as a figure. |
| `comparison_check_tables.py` | The two checks around the registered test: the base-free spread table and the common-mode elevation table. |
| `comparison_registered_tables.py` | The registered-test table and its largest-excess pairs, with display names read from each run's prompt sets. |
| `elicit_top_table.py` | Generate the elicit-top-candidates table, ranked by each candidate's elevation over its target's base. |
| `elicitation_candidate_lists.py` | Every elicited candidate per run and every merged naming variant, as two longtables. |
| `elicitation_coverage_tables.py` | Stage-1 coverage per seat and per system variant, plus the naming counting-rule note. |
| `elicitation_question_sets.py` | One card per distinct frozen question set, naming the runs that asked it. |
| `elicitation_seat_naming.py` | Read the target and reference seat tags from an elicitation report across its three artifact shapes. |
| `experiment_data_document.py` | Assemble the full data-appendix section in reading order, namespaced per run. |
| `external_organism_results.py` | Results subsections for the two out-of-challenge organisms: the transfer test and the power limit. |
| `judge_seat_document.py` | The appendix on how the judge seat changes the verdict: agreement, refusal errors, probe, and outcomes. |
| `latex_text_escaping.py` | Shared helpers: LaTeX escaping, monospace ids, JSON and JSONL loading, pending markers, p-value formatting. |
| `pipeline_run_registry.py` | Declare the expected run directories per stage and the reported, dropped, and staging exclusions in one place. |
| `reference_free_document.py` | The appendix that audits without a base model: the coherence method and its pooled results. |
| `results_top_behaviors_table.py` | The results table of the ten largest behavior excesses for the two runs the body reads. |
| `run_label_namespacing.py` | Suffix every label a run's appendix body defines, and every internal reference to it, with the run key. |
| `stage_collection_tables.py` | The stage-4 section: per run and model sampling counts, the variant breakdown, and one quoted reply. |
| `stage_comparison_tables.py` | Assemble the stage-6 section: registered test, base-free and common-mode checks, and behavior figures. |
| `stage_conjecture_cards.py` | The stage-3 section: hypothesis and axis counts, guaranteed axes, and quoted hypotheses and questions. |
| `stage_elicitation_tables.py` | Assemble the stage-1 section from the question, coverage, candidate, alias, and reply tables. |
| `stage_promptset_cards.py` | The stage-2 section: template counts, the shortfall note, dropped templates, and one rendered candidate pair. |
| `stage_scoring_tables.py` | The stage-5 section: verdict counts, nulls, shorts, and firing rate per run, model, and judge level. |
| `trigger_framing_table.py` | The table rerunning the registered test inside each collection framing, reported as descriptive. |
