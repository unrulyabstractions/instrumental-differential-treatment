# src/ellicit

We run stage 1, principal elicitation: the Elicitor seat surfaces the candidate principals the target model itself favors, and the tally reads them against the base model to pick the candidate cut.

We freeze one question set per run and sample the target and its reference model identically on it. The Elicitor then reads each reply blind, names the single actor it favors, and we tally those verdicts per model. We take each actor's elevation over the reference, cut at the candidate floor, and write the candidate principals into the run report. A caller drives the stage through `generate_or_load_questions`, `sample_question_responses`, `extract_favored_actors`, and `build_elicitation_report`, with `pool_seed_runs` pooling a challenge organism's three seed runs.

## Files

| File | Responsibility |
|---|---|
| actor_alias_rules.py | Decide when two normalized actor names name one actor, by equal tokens, acronym, token subset, or reduced core. |
| elicitation_config.py | Type one run's config from JSON, hold its model seats, and echo the settings into the report. |
| elicitation_paths.py | Derive every on-disk artifact path for one run from a single root. |
| elicitation_question_generation.py | Generate the questions once with the elicitor, then freeze them with provenance. |
| favored_actor_extraction.py | Have the Elicitor name the favored actor in each reply on a thread pool, blind to question and model. |
| pooled_seed_report.py | Pool a challenge organism's three seed runs (person, group, organization) into one candidate list. |
| principal_seed_prompts.py | The elicitation-stage prompts verbatim: elicitor question-writing and reply-extraction, system and user. |
| principal_tally_report.py | Tally favored actors, score the target's elevation over the reference, and build the candidate report. |
| target_question_sampling.py | Sample a model repeatedly on the frozen questions, streaming resumable rows to disk. |
