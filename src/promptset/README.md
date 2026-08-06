# src/promptset

We build Stage 2 of the audit here: matched prompt sets that differ only in the group or identity cue, frozen before any reply is collected.

The package holds two construction paths. One path asks a Prompter model to draft placeholder-carrying templates for a deployment, screens the reply against a placeholder and no-candidate invariant, and renders one set per candidate so every instruction appears once in every set. The other supplies hand-written ladders and questions for the political organisms, where the candidate slot holds a graded user profile rather than a named entity. Stage 3 conjectures behavior axes over these sets and Stage 4 collects target and base replies from them. On the Prompter path a caller reaches for `generate_or_load_templates` to freeze the templates and `render_prompt_sets` to expand them per candidate, keyed by `PromptSetConfig` and `PromptSetPaths`.

## Files

| File | Responsibility |
|---|---|
| affiliation_prompter_prompts.py | Prompter brief for the affiliation shape, where the user states an employer in the placeholder and then asks a question. |
| political_profile_ladder.py | Six-rung user-profile ladder from clearly conservative to clearly liberal, with the leaning stated outright in the clear rungs. |
| political_question_units.py | Strip each binary political question of its biography, key it by the conservative option, and issue both option orders. |
| prompt_template_set.py | Generate the Prompter's template set once, freeze it, and render one prompt set per candidate. |
| prompter_prompts.py | The verbatim supporter brief that has the Prompter draft placeholder-carrying templates and self-reject the weakest. |
| promptset_config.py | Typed frozen config for one construction run, loaded from JSON, carrying the auditor affordance level. |
| promptset_paths.py | On-disk layout for one run: frozen templates, one rendered set per candidate, and a coverage report. |
| template_reply_screening.py | Screen the Prompter's reply: split its self-rejections, drop templates that break the placeholder or no-name invariant, trim surplus. |
| undecided_voter_ladder.py | Six-rung profile ladder that implies a leaning without naming a party, candidate, or the words liberal and conservative. |
| undecided_voter_questions.py | The undecided-voter questions and the third-party-steering axes that read the replies. |
